"""FILE: vidbyte/skills/sources/github.py

PURPOSE: Resolves explicit GitHub skill repository, tree, blob, and raw sources.
ROLE IN CODEBASE: Supplies bounded GitHub catalog lookup for Jev's GITHUB and SKILLS_SH source adapters.
ARCHITECTURE NOTE: GitHub API credentials are sent only to api.github.com; raw downloads are always anonymous.
COMMON MODIFICATION PATTERNS: Keep URL normalization, bounded ref probes, catalog selection, and GitHub response validation together.
KNOWN EDGE CASES: Ambiguous slash-containing refs require explicit revisions; only genuine 404 probe results are ignored.
RELATED DOCS: docs/design/jev-skill-providers.md and docs/jev-skill-providers.md.
TESTS: tests/test_jev_skill_remote_sources.py and scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import replace
from urllib.parse import SplitResult, parse_qsl, quote, unquote, urlencode, urlsplit

import yaml

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SkillSourceError,
)
from vidbyte.lib.errors.skills import provider_failure_reason
from vidbyte.lib.http.parser import HttpResponseParser
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.skills.sources.base import SkillDocumentParser, SkillSourceAdapter

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_HOST = "api.github.com"
_GITHUB_WEB_HOST = "github.com"
_GITHUB_RAW_HOST = "raw.githubusercontent.com"
_GITHUB_API_VERSION = "2026-03-10"
_GITHUB_TIMEOUT_SECONDS = 20.0
_GITHUB_BLOB_MAX_RESPONSE_BYTES = 512_000
_GITHUB_DOCUMENT_MAX_BYTES = 256_000
_GITHUB_TREE_MAX_BYTES = 8_000_000
_MAX_GITHUB_REF_PATH_SPLITS = 8
_GITHUB_HTTP_OK = 200
_GITHUB_HTTP_MULTIPLE_CHOICES = 300
_GITHUB_HTTP_NOT_FOUND = 404
_GITHUB_RETRY_COUNT = 0
_MULTIPLE_REF_CANDIDATE_BOUNDARY = 1
_PATH_COMPONENT_SEPARATOR_COUNT = 1
_CREDENTIAL_QUERY_PARTS = ("token", "auth", "key", "secret", "credential", "password")
_OWNER_OR_REPO = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubSkillSourceAdapter(SkillSourceAdapter):
    """Reads one validated SKILL.md from an explicit public or authenticated GitHub source."""

    def __init__(self, *, transport: HttpTransport | None = None, response_parser: HttpResponseParser | None = None, document_parser: SkillDocumentParser | None = None) -> None:
        # @intent keep-github-transport-and-parsing-injectable
        # Requests share one bounded approved-host transport while parser injection keeps interpretation deterministic in tests.
        self.transport = transport or HttpTransport()
        self.response_parser = response_parser or HttpResponseParser()
        self.document_parser = document_parser or SkillDocumentParser()

    async def resolve(self, source: SkillSource) -> SkillDocument:
        try:
            return await self._resolve_source(source)
        except SkillSourceError as exc:
            raise SkillSourceError(exc.reason, source_kind="github", status_code=exc.status_code) from exc
        except ProviderRequestError as exc:
            raise SkillSourceError(provider_failure_reason(exc.status_code, message=exc.message), source_kind="github", status_code=exc.status_code) from exc
        except TimeoutError as exc:
            raise SkillSourceError("the GitHub request timed out", source_kind="github") from exc
        except OSError as exc:
            raise SkillSourceError("the GitHub service could not be reached", source_kind="github") from exc
        except UnicodeError as exc:
            raise SkillSourceError("the returned skill document contains invalid UTF-8", source_kind="github") from exc
        except yaml.YAMLError as exc:
            raise SkillSourceError("the returned skill frontmatter is not valid YAML", source_kind="github") from exc
        except (ConfigurationError, ValueError, TypeError, binascii.Error) as exc:
            raise SkillSourceError("the source descriptor or returned skill did not satisfy the SDK contract", source_kind="github") from exc

    async def _resolve_source(self, source: SkillSource) -> SkillDocument:
        # Routes one validated descriptor through raw, blob, or repository catalog resolution.
        if not isinstance(source, SkillSource) or source.kind is not SkillSourceKind.GITHUB:
            raise SkillSourceError("GitHub adapter requires a GITHUB SkillSource.")
        mode, owner, repo, revision, path = self._parse_location(source)
        ref_candidates = self._revision_candidates(source)
        if mode == "raw":
            if path is None:
                raise SkillSourceError("GitHub raw URL must identify a SKILL.md file.")
            if len(ref_candidates) > _MULTIPLE_REF_CANDIDATE_BOUNDARY:
                return await self._resolve_url_candidates(source, owner, repo, mode, ref_candidates)
            return await self._resolve_raw(source, owner, repo, revision, path)
        repository = await self._get_repository(source, owner, repo)
        default_branch = repository.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch.strip():
            raise SkillSourceError("GitHub repository metadata did not include a default branch.")
        selected_revision = revision or source.revision or default_branch
        if len(ref_candidates) > _MULTIPLE_REF_CANDIDATE_BOUNDARY:
            return await self._resolve_url_candidates(source, owner, repo, mode, ref_candidates)
        if mode == "blob":
            if not path or path.rsplit("/", _PATH_COMPONENT_SEPARATOR_COUNT)[-1] != "SKILL.md":
                raise SkillSourceError("GitHub blob sources must identify a SKILL.md file.")
            return await self._resolve_contents(source, owner, repo, selected_revision, path)
        return await self._resolve_tree(source, owner, repo, selected_revision, path)

    async def _resolve_repository_path(self, source: SkillSource, path: str) -> SkillDocument:
        # Resolves a single skills.sh-selected directory through the same repository catalog path.
        if source.kind is not SkillSourceKind.GITHUB:
            raise SkillSourceError("GitHub adapter requires a GITHUB SkillSource.")
        location = self._parse_location(source)
        mode, owner, repo, revision, url_path = location
        if mode != "repo" or url_path or not path:
            raise SkillSourceError("skills.sh source did not identify a GitHub repository and skill slug.")
        repository = await self._get_repository(source, owner, repo)
        default_branch = repository.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch.strip():
            raise SkillSourceError("GitHub repository metadata did not include a default branch.")
        return await self._resolve_tree(source, owner, repo, revision or source.revision or default_branch, selected_slug=path)

    async def _resolve_raw(self, source: SkillSource, owner: str, repo: str, revision: str, path: str) -> SkillDocument:
        # @intent never-forward-github-credentials-to-raw-host
        # Raw content is fetched anonymously because only api.github.com is approved to receive a caller-supplied GitHub key.
        if not path or path.rsplit("/", 1)[-1] != "SKILL.md":
            raise SkillSourceError("GitHub raw sources must identify a SKILL.md file.")
        url = self._raw_url(owner, repo, revision, path)
        response = await self._request(url, source, raw=True, maximum_bytes=_GITHUB_DOCUMENT_MAX_BYTES + 1)
        if not _GITHUB_HTTP_OK <= response.status_code < _GITHUB_HTTP_MULTIPLE_CHOICES:
            raise ProviderRequestError("GitHub raw content endpoint returned a non-success status.", provider="github", status_code=response.status_code)
        content = response.raw_bytes if response.raw_bytes is not None else response.body.encode("utf-8")
        if len(content) > _GITHUB_DOCUMENT_MAX_BYTES:
            raise SkillSourceError("GitHub skill document exceeds the SDK size limit.")
        provenance = self._provenance(owner, repo, revision, path)
        return self.document_parser.parse(content, source=source, provenance=provenance)

    async def _resolve_contents(self, source: SkillSource, owner: str, repo: str, revision: str, path: str) -> SkillDocument:
        # Reads one selected file from the authenticated API without exposing its key to the raw host.
        url = self._contents_url(owner, repo, revision, path)
        payload = await self._get_json(url, source, maximum_bytes=_GITHUB_BLOB_MAX_RESPONSE_BYTES)
        content, returned_path = self._decode_api_file(payload)
        if returned_path != path:
            raise SkillSourceError("GitHub API returned a different skill file than requested.")
        provenance = self._provenance(owner, repo, revision, path)
        return self.document_parser.parse(content, source=source, provenance=provenance)

    async def _resolve_tree(self, source: SkillSource, owner: str, repo: str, revision: str, selected_path: str | None = None, *, selected_slug: str | None = None) -> SkillDocument:
        # Parses every matching catalog candidate so malformed entries cannot hide a valid requested name.
        url = self._tree_url(owner, repo, revision)
        payload = await self._get_json(url, source, maximum_bytes=_GITHUB_TREE_MAX_BYTES)
        documents = await self._tree_documents(source, owner, repo, revision, payload, selected_path)
        if selected_slug is not None:
            documents = [(document, path) for document, path in documents if self._matches_slug(document, path, selected_slug)]
            if not documents:
                raise SkillSourceError("GitHub repository did not contain the requested skills.sh skill.")
        return self._select_document(source, documents)

    async def _tree_documents(self, source: SkillSource, owner: str, repo: str, revision: str, payload: dict[str, object], selected_path: str | None) -> list[tuple[SkillDocument, str]]:
        # Resolves every selected SKILL.md candidate, preserving failures that could hide a requested name.
        candidates = self._tree_candidates(payload, selected_path)
        if not candidates:
            return []
        parser_source = replace(source, skill_name=None)
        documents: list[tuple[SkillDocument, str]] = []
        for candidate_path, sha, size in candidates:
            if size is not None and size > _GITHUB_DOCUMENT_MAX_BYTES:
                raise SkillSourceError("GitHub skill document exceeds the SDK size limit.")
            content = await self._get_blob(source, owner, repo, sha)
            provenance = self._provenance(owner, repo, revision, candidate_path)
            documents.append((self.document_parser.parse(content, source=parser_source, provenance=provenance), candidate_path))
        return documents

    async def _resolve_url_candidates(self, source: SkillSource, owner: str, repo: str, mode: str, candidates: list[tuple[str, str]]) -> SkillDocument:
        # Dispatches bounded slash-ref probes to a focused file or tree resolver.
        if mode in ("blob", "raw"):
            return await self._resolve_file_url_candidates(source, owner, repo, candidates)
        return await self._resolve_tree_url_candidates(source, owner, repo, candidates)

    async def _resolve_file_url_candidates(self, source: SkillSource, owner: str, repo: str, candidates: list[tuple[str, str]]) -> SkillDocument:
        # Resolves file interpretations while preserving exact 404-only probe semantics.
        file_candidates: list[tuple[dict[str, object], str, str]] = []
        for revision, path in candidates:
            payload = await self._try_get_json(
                self._contents_url(owner, repo, revision, path),
                source,
                maximum_bytes=_GITHUB_BLOB_MAX_RESPONSE_BYTES,
            )
            if payload is not None:
                file_candidates.append((payload, revision, path))
        if len(file_candidates) > 1:
            raise SkillSourceError("GitHub URL has an ambiguous revision and path; set SkillSource.revision explicitly.")
        if not file_candidates:
            raise SkillSourceError("GitHub URL did not identify a matching SKILL.md.")
        payload, revision, path = file_candidates[0]
        content, returned_path = self._decode_api_file(payload)
        if returned_path != path:
            raise SkillSourceError("GitHub API returned a different skill file than requested.")
        document = self.document_parser.parse(content, source=replace(source, skill_name=None), provenance=self._provenance(owner, repo, revision, path))
        if source.skill_name is not None and document.name != source.skill_name:
            raise SkillSourceError("SKILL.md name does not match the requested skill name.")
        return document

    async def _resolve_tree_url_candidates(self, source: SkillSource, owner: str, repo: str, candidates: list[tuple[str, str]]) -> SkillDocument:
        # Resolves tree interpretations and refuses multiple matching revision boundaries.
        tree_matches: list[SkillDocument] = []
        tree_interpretations = 0
        for revision, path in candidates:
            payload = await self._try_get_json(
                self._tree_url(owner, repo, revision),
                source,
                maximum_bytes=_GITHUB_TREE_MAX_BYTES,
            )
            if payload is None:
                continue
            documents = await self._tree_documents(source, owner, repo, revision, payload, path or None)
            if documents:
                tree_interpretations += 1
            document = self._matching_document(source, documents)
            if document is not None:
                tree_matches.append(document)
        if tree_interpretations > 1:
            raise SkillSourceError("GitHub URL has an ambiguous revision and path; set SkillSource.revision explicitly.")
        if not tree_matches:
            raise SkillSourceError("GitHub URL did not identify a matching SKILL.md.")
        if len(tree_matches) != 1:
            raise SkillSourceError("GitHub URL has an ambiguous revision and path; set SkillSource.revision explicitly.")
        return tree_matches[0]

    async def _get_repository(self, source: SkillSource, owner: str, repo: str) -> dict[str, object]:
        # Uses repository metadata rather than assuming a branch named main.
        url = f"{_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        return await self._get_json(url, source, maximum_bytes=_GITHUB_BLOB_MAX_RESPONSE_BYTES)

    async def _get_blob(self, source: SkillSource, owner: str, repo: str, sha: str) -> bytes:
        # Reads blob bytes through the authenticated API endpoint and enforces the decoded file cap.
        if not isinstance(sha, str) or not sha:
            raise SkillSourceError("GitHub repository tree contained an invalid skill blob.")
        url = f"{_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/git/blobs/{quote(sha, safe='')}"
        payload = await self._get_json(url, source, maximum_bytes=_GITHUB_BLOB_MAX_RESPONSE_BYTES)
        content, _ = self._decode_api_file(payload, require_path=False, expected_type=None, expected_sha=sha)
        return content

    async def _get_json(self, url: str, source: SkillSource, *, maximum_bytes: int) -> dict[str, object]:
        # Enforces the fixed GitHub API host and response cap; resolve() translates transport failures once.
        if urlsplit(url).hostname != _GITHUB_API_HOST:
            raise SkillSourceError("GitHub API request did not use the approved host.")
        response = await self._request(url, source, raw=False, maximum_bytes=maximum_bytes)
        return self.response_parser.parse_json_response(response, provider="github")

    async def _try_get_json(self, url: str, source: SkillSource, *, maximum_bytes: int) -> dict[str, object] | None:
        # @intent ignore-only-definite-github-404
        # Only an actual 404 means a probe did not match; auth, parse, size, and transport failures invalidate the source.
        if urlsplit(url).hostname != _GITHUB_API_HOST:
            raise SkillSourceError("GitHub API request did not use the approved host.")
        response = await self._request(url, source, raw=False, maximum_bytes=maximum_bytes)
        if response.status_code == _GITHUB_HTTP_NOT_FOUND:
            return None
        return self.response_parser.parse_json_response(response, provider="github")

    async def _request(self, url: str, source: SkillSource, *, raw: bool, maximum_bytes: int) -> HttpResponse:
        # @intent scope-github-credentials-to-api-host
        # Only the fixed API host receives explicit keys, and redirects are disabled so the transport cannot forward them elsewhere.
        host = urlsplit(url).hostname
        allowed_host = _GITHUB_RAW_HOST if raw else _GITHUB_API_HOST
        if host != allowed_host:
            raise SkillSourceError("GitHub request did not use the approved host.")
        headers = {"Accept": "text/plain" if raw else "application/vnd.github+json"}
        if not raw:
            headers["X-GitHub-Api-Version"] = _GITHUB_API_VERSION
            if source.api_key is not None:
                headers["Authorization"] = f"Bearer {source.api_key}"
        return await self.transport.request(
            method="GET",
            url=url,
            headers=headers,
            timeout_seconds=_GITHUB_TIMEOUT_SECONDS,
            retry_count=_GITHUB_RETRY_COUNT,
            max_response_bytes=maximum_bytes,
            follow_redirects=False,
        )

    def _parse_location(self, source: SkillSource) -> tuple[str, str, str, str, str | None]:
        # Keeps shorthand parsing separate from URL parsing and host validation.
        """Normalizes a GitHub source into mode, owner, repository, revision, and path."""
        if "://" not in source.location:
            return self._parse_shorthand_location(source)
        return self._parse_url_location(source)

    def _parse_shorthand_location(self, source: SkillSource) -> tuple[str, str, str, str, str | None]:
        # Parses only the explicit owner/repository shorthand form.
        owner, separator, repo = source.location.partition("/")
        if not separator or "/" in repo:
            raise SkillSourceError("GitHub source must identify an owner and repository.")
        self._validate_repo_parts(owner, repo)
        return "repo", owner, repo.removesuffix(".git"), source.revision or "", None

    def _parse_url_location(self, source: SkillSource) -> tuple[str, str, str, str, str | None]:
        # Validates URL credentials, query data, protocol, port, and approved hosts before routing.
        parsed = urlsplit(source.location)
        hostname = parsed.hostname
        port = parsed.port
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or port not in (None, 443):
            raise SkillSourceError("GitHub skill sources must use an approved HTTPS URL without user information.")
        if parsed.fragment:
            raise SkillSourceError("GitHub skill source URL fragments are not supported.")
        self._validate_query(parsed.query)
        if hostname == _GITHUB_RAW_HOST:
            return self._parse_raw_url_location(source, parsed)
        if hostname == _GITHUB_WEB_HOST:
            return self._parse_web_url_location(source, parsed)
        raise SkillSourceError("GitHub skill sources must use an approved HTTPS host.")

    def _parse_raw_url_location(self, source: SkillSource, parsed: SplitResult) -> tuple[str, str, str, str, str | None]:
        # Routes raw.githubusercontent.com URLs after shared HTTPS and credential validation.
        raw_parts = [segment for segment in parsed.path.split("/") if segment]
        parts = [unquote(segment) for segment in raw_parts]
        if len(parts) < 4:
            raise SkillSourceError("GitHub raw URL must include owner, repository, revision, and file path.")
        owner, repo = parts[:2]
        self._validate_repo_parts(owner, repo)
        revision, path = self._split_revision(raw_parts[2:], source.revision)
        self._validate_skill_path(path)
        return "raw", owner, repo.removesuffix(".git"), revision, path

    def _parse_web_url_location(self, source: SkillSource, parsed: SplitResult) -> tuple[str, str, str, str, str | None]:
        # Parses GitHub web repository, tree, blob, and raw URL routes after shared validation.
        raw_parts = [segment for segment in parsed.path.split("/") if segment]
        parts = [unquote(segment) for segment in raw_parts]
        if len(parts) < 2:
            raise SkillSourceError("GitHub source must identify an owner and repository.")
        owner, repo = parts[:2]
        self._validate_repo_parts(owner, repo)
        repo = repo.removesuffix(".git")
        if len(parts) == 2:
            return "repo", owner, repo, source.revision or "", None
        mode = parts[2]
        if mode not in ("tree", "blob", "raw"):
            raise SkillSourceError("GitHub URL must identify a repository, tree, blob, or raw file.")
        revision, path = self._split_revision(raw_parts[3:], source.revision)
        self._validate_skill_path(path)
        if mode == "raw":
            return "raw", owner, repo, revision, path
        return mode, owner, repo, revision, path

    def _split_revision(self, raw_parts: list[str], explicit_revision: str | None) -> tuple[str, str | None]:
        # Requires an explicit revision when a URL encodes a slash-containing ref in one segment.
        if not raw_parts:
            raise SkillSourceError("GitHub tree or file URL must identify a revision.")
        parts = [unquote(part) for part in raw_parts]
        if explicit_revision is None:
            if any("%2f" in part.lower() for part in raw_parts):
                raise SkillSourceError("GitHub URL has an ambiguous slash revision; set SkillSource.revision explicitly.")
            return parts[0], "/".join(parts[1:]) or None
        revision_parts = explicit_revision.split("/")
        if len(parts) == 1 and parts[0] == explicit_revision:
            return explicit_revision, None
        if parts[0] == explicit_revision and "%2f" in raw_parts[0].lower():
            return explicit_revision, "/".join(parts[1:]) or None
        if parts[: len(revision_parts)] == revision_parts:
            return explicit_revision, "/".join(parts[len(revision_parts) :]) or None
        raise SkillSourceError("GitHub URL revision does not match the explicit SkillSource.revision.")

    def _revision_candidates(self, source: SkillSource) -> list[tuple[str, str]]:
        # Enumerates ref/path splits only when the caller has not explicitly pinned a revision.
        if source.revision is not None:
            return []
        parsed = urlsplit(source.location)
        raw_parts = [segment for segment in parsed.path.split("/") if segment]
        if parsed.hostname == _GITHUB_RAW_HOST:
            selected_parts = raw_parts[2:]
        elif parsed.hostname == _GITHUB_WEB_HOST and len(raw_parts) >= 4 and unquote(raw_parts[2]) in {"blob", "raw", "tree"}:
            selected_parts = raw_parts[3:]
        else:
            return []
        if any("%2f" in part.lower() for part in selected_parts):
            raise SkillSourceError("GitHub URL has an ambiguous slash revision; set SkillSource.revision explicitly.")
        decoded = [unquote(part) for part in selected_parts]
        tree_url = parsed.hostname == _GITHUB_WEB_HOST and len(raw_parts) >= 3 and unquote(raw_parts[2]) == "tree"
        split_count = len(decoded) if tree_url else max(0, len(decoded) - 1)
        if split_count > _MAX_GITHUB_REF_PATH_SPLITS:
            raise SkillSourceError("GitHub URL has too many possible ref/path splits; set SkillSource.revision explicitly.")
        candidates = [("/".join(decoded[:index]), "/".join(decoded[index:])) for index in range(1, split_count + 1)]
        for _, path in candidates:
            self._validate_skill_path(path)
        return candidates

    def _contents_url(self, owner: str, repo: str, revision: str, path: str) -> str:
        # Encodes a single contents lookup with the selected ref kept in its query field.
        encoded_path = quote(path, safe="/")
        query = urlencode({"ref": revision})
        return f"{_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/{encoded_path}?{query}"

    def _tree_url(self, owner: str, repo: str, revision: str) -> str:
        # Encodes the documented recursive tree lookup for one exact ref.
        encoded_revision = quote(revision, safe="")
        return f"{_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/git/trees/{encoded_revision}?recursive=1"

    def _validate_repo_parts(self, owner: str, repo: str) -> None:
        # Rejects path tricks before constructing fixed GitHub API URLs.
        normalized_repo = repo.removesuffix(".git")
        if not _OWNER_OR_REPO.fullmatch(owner) or not _OWNER_OR_REPO.fullmatch(normalized_repo):
            raise SkillSourceError("GitHub owner or repository name is invalid.")

    def _validate_skill_path(self, path: str | None) -> None:
        # Rejects path traversal before any user-controlled path is placed into an API URL.
        if path is None:
            return
        if any(part in {".", ".."} for part in path.split("/")) or "\\" in path:
            raise SkillSourceError("GitHub skill path is invalid.")

    def _validate_query(self, query: str) -> None:
        # Refuses credentials and unsupported query data instead of forwarding caller parameters.
        for key, value in parse_qsl(query, keep_blank_values=True):
            normalized = key.lower().replace("-", "").replace("_", "")
            if any(part in normalized for part in _CREDENTIAL_QUERY_PARTS):
                raise SkillSourceError("GitHub skill URLs must not include credential query parameters.")
            if normalized not in {"raw", "plain"} or value not in {"", "1"}:
                raise SkillSourceError("GitHub skill URL query parameters are not supported.")

    def _tree_candidates(self, payload: dict[str, object], selected_path: str | None) -> list[tuple[str, str, int | None]]:
        # Rejects incomplete trees and selects only SKILL.md blobs in the requested catalog scope.
        tree = payload.get("tree")
        truncated = payload.get("truncated")
        if not isinstance(tree, list) or not isinstance(truncated, bool):
            raise SkillSourceError("GitHub repository tree response is malformed.")
        if truncated:
            raise SkillSourceError("GitHub repository tree was truncated; skill selection cannot be verified.")
        candidates: list[tuple[str, str, int | None]] = []
        for item in tree:
            if not isinstance(item, dict):
                raise SkillSourceError("GitHub repository tree response is malformed.")
            path = item.get("path")
            sha = item.get("sha")
            if item.get("type") != "blob" or not isinstance(path, str) or path.rsplit("/", 1)[-1] != "SKILL.md":
                continue
            if not self._path_is_selected(path, selected_path):
                continue
            if not isinstance(sha, str) or not sha:
                raise SkillSourceError("GitHub repository tree contained an invalid skill blob.")
            size = item.get("size")
            size = self._validate_optional_size(size, "GitHub repository tree contained an invalid skill size.")
            candidates.append((path, sha, size))
        return candidates

    def _validate_optional_size(self, size: object, error_detail: str) -> int | None:
        # Owns the bool-safe nonnegative integer contract shared by GitHub size fields.
        if size is None:
            return None
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SkillSourceError(error_detail)
        return size

    def _path_is_selected(self, path: str, selected_path: str | None) -> bool:
        # Matches a direct SKILL.md path or a directory subtree without using ambiguous basename matches.
        if selected_path is None:
            return True
        if path == selected_path:
            return True
        if selected_path.endswith("/SKILL.md"):
            return False
        return path.startswith(f"{selected_path.rstrip('/')}/")

    def _decode_api_file(self, payload: dict[str, object], *, require_path: bool = True, expected_type: str | None = "file", expected_sha: str | None = None) -> tuple[bytes, str]:
        # Validates API content envelopes and decodes only bounded base64 skill bytes.
        if (expected_type is not None and payload.get("type") != expected_type) or payload.get("encoding") != "base64":
            raise SkillSourceError("GitHub API did not return a base64 skill file.")
        encoded = payload.get("content")
        path = payload.get("path")
        size = self._validate_optional_size(payload.get("size"), "GitHub API returned an invalid skill file size.")
        if not isinstance(encoded, str) or (require_path and not isinstance(path, str)):
            raise SkillSourceError("GitHub API returned a malformed skill file.")
        if expected_sha is not None and payload.get("sha") != expected_sha:
            raise SkillSourceError("GitHub API returned a different skill blob than requested.")
        if size is not None and size > _GITHUB_DOCUMENT_MAX_BYTES:
            raise SkillSourceError("GitHub skill document exceeds the SDK size limit.")
        content = base64.b64decode("".join(encoded.split()), validate=True)
        if len(content) > _GITHUB_DOCUMENT_MAX_BYTES:
            raise SkillSourceError("GitHub skill document exceeds the SDK size limit.")
        if size is not None and len(content) != size:
            raise SkillSourceError("GitHub API returned an incomplete skill file.")
        return content, path if isinstance(path, str) else ""

    def _matches_slug(self, document: SkillDocument, path: str, slug: str) -> bool:
        # Matches a skills.sh slug against either the skill directory or its validated frontmatter name.
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        directory_name = directory.rsplit("/", 1)[-1]
        return directory_name == slug or self._slugify(document.name) == slug

    def _slugify(self, value: str) -> str:
        # Uses a stable lowercase hyphen form only for skills.sh catalog matching.
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _select_document(self, source: SkillSource, documents: list[tuple[SkillDocument, str]]) -> SkillDocument:
        # Selects exactly one frontmatter name match and never returns the first duplicate candidate.
        document = self._matching_document(source, documents)
        if document is None:
            if source.skill_name is not None:
                raise SkillSourceError("GitHub repository did not contain the requested skill name.")
            raise SkillSourceError("GitHub repository did not contain a matching SKILL.md.")
        return document

    def _matching_document(self, source: SkillSource, documents: list[tuple[SkillDocument, str]]) -> SkillDocument | None:
        # Returns one metadata match or None while keeping duplicate names explicitly ambiguous.
        if source.skill_name is not None:
            matches = [document for document, _ in documents if document.name == source.skill_name]
            if not matches:
                return None
            if len(matches) != 1:
                raise SkillSourceError("GitHub skill selection is ambiguous.")
            return matches[0]
        if len(documents) > 1:
            raise SkillSourceError("GitHub skill selection is ambiguous.")
        return documents[0][0] if documents else None

    def _provenance(self, owner: str, repo: str, revision: str, path: str) -> str:
        # Produces a stable credential-free repository/ref/path URL for source reporting.
        return f"https://github.com/{quote(owner, safe='')}/{quote(repo, safe='')}/blob/{quote(revision, safe='')}/{quote(path, safe='/')}"

    def _raw_url(self, owner: str, repo: str, revision: str, path: str) -> str:
        # Creates an anonymous raw-file URL from already validated repository components.
        return f"https://{_GITHUB_RAW_HOST}/{quote(owner, safe='')}/{quote(repo, safe='')}/{quote(revision, safe='')}/{quote(path, safe='/')}"


__all__ = ["GitHubSkillSourceAdapter"]
