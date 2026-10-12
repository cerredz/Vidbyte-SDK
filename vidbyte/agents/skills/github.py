"""FILE: vidbyte/agents/skills/github.py

PURPOSE: Defines GitHubSkillResolver, which loads SKILL.md files from GitHub repositories through the REST API: one commit lookup per repository, ref, and token (skipped for a full SHA), one tree listing only when some entry must be searched for by name, and one raw file request per skill, all pinned to the same commit and labelled `github:<owner>/<repo>@<sha12>/<folder>/SKILL.md`. It also defines _GitHubAnswer, the private map from a GitHub HTTP status to an explained resolution.
ROLE IN CODEBASE: Registered for SkillSourceType.GITHUB in SkillLoader (loader.py), which groups entries by group_key = (repo, ref, token) so entries that share lookups resolve in one call. Requests go through SkillFetch (fetch.py); files are parsed by SkillMarkdown (markdown.py).
ARCHITECTURE NOTE: resolve is the one narrated main; its step leaves (_commit_sha, _tree_paths, _raw_document) each call SkillFetch.get and then _GitHubAnswer.failure, so the three steps share one status map without calls going two levels deep (spec D-31). Raw files are fetched concurrently and every gather result is classified against BaseException.
FUNCTION INVENTORY: _GitHubAnswer.failure(response, *, step, target) -> SkillResolution | None; GitHubSkillResolver.group_key(entry) -> Hashable; GitHubSkillResolver.resolve(entries) -> tuple[SkillResolution, ...]; GitHubSkillResolver._token(entry) -> str | None; GitHubSkillResolver._commit_sha(entry, auth) -> str | SkillResolution; GitHubSkillResolver._tree_paths(repo, sha, auth) -> tuple[str, ...] | SkillResolution; GitHubSkillResolver._search(paths, entry, sha) -> str | SkillResolution; GitHubSkillResolver._raw_document(entry, folder, sha, auth) -> SkillResolution.
COMMON MODIFICATION PATTERNS: A status GitHub starts using for a known condition joins the dict in _GitHubAnswer.failure. A change to how a folder is found by name changes _search only.
WHAT NOT TO DO IN THIS FILE: 1. Do not follow redirects or read a Location header. 2. Do not send a token that starts with the Vidbyte key prefix or holds a character outside printable ASCII (a header cannot carry it, and httpx would raise outside every catch), and never put any token in a URL, label, or detail. 3. Do not call HTTPStatus(status): 529 is not a member. 4. Do not echo a response body. 5. Do not mix entries with different tokens in one group.
KNOWN EDGE CASES: A 403 with x-ratelimit-remaining "0" or a retry-after header is GitHub's rate limit (RATE_LIMITED, transient); any other 403 is AUTH_FAILED. A 3xx means the repository moved (NOT_FOUND, remembered). A commit answer that is not a 40-character SHA, a tree that is not usable JSON, and a tree whose items are not all objects with a text path (what a 2,000-level nested body parses to on Python 3.12+) are network faults (FETCH_FAILED, transient). A truncated tree, or two folders of the same name at the shallowest depth, is INVALID_SKILL for the searched entries only. A SKILL.md at the repository root is not supported (spec Q-6).
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-10, D-11, D-18, D-21, D-30, D-31, section 9.2)
TESTS: tests/features/jev_skills_preload/test_skill_sources_github.py; tests/features/jev_skills_preload/test_skill_sources_security.py
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Hashable
from http import HTTPStatus
from urllib.parse import quote

from vidbyte.agents.skills.fetch import SkillFetch
from vidbyte.agents.skills.markdown import SkillMarkdown
from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.lib.constants.jev import VIDBYTE_API_KEY_PREFIX
from vidbyte.lib.constants.skills import (
    GITHUB_ACCEPT_JSON,
    GITHUB_ACCEPT_RAW,
    GITHUB_ACCEPT_SHA,
    GITHUB_API_BASE_URL,
    GITHUB_COMMIT_SHA_PATTERN,
    GITHUB_CREDENTIAL_ENV_VAR,
    GITHUB_DEFAULT_REF,
    GITHUB_RATE_LIMIT_EXHAUSTED,
    GITHUB_RATE_LIMIT_REMAINING_HEADER,
    HTTP_RETRY_AFTER_HEADER,
    SKILL_DOWNLOAD_MAX_BYTES,
    SKILL_LABEL_HASH_CHARS,
    SKILL_MARKDOWN_FILE_NAME,
    SKILL_MARKDOWN_MAX_BYTES,
)
from vidbyte.lib.dataclasses.skills import GitHubSkill, SkillResolution
from vidbyte.lib.enums.skills import (
    SkillFetchStep,
    SkillSourceType,
    SkillUnavailableReason,
)
from vidbyte.lib.http.parser import HttpResponseParser
from vidbyte.lib.http.transport import HttpResponse


class _GitHubAnswer:
    """Maps one GitHub HTTP status to an explained resolution; None for a 2xx answer."""

    @staticmethod
    def failure(response: HttpResponse, *, step: SkillFetchStep, target: str) -> SkillResolution | None:
        # @intent github-status-map
        # Each status names its fix and never echoes the body. Lookups
        # use the integer status, because HTTPStatus(529) raises. A 403
        # is the rate limit only when GitHub's limit headers say so.
        status = response.status_code
        if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            return None
        headers = response.headers
        if status == HTTPStatus.FORBIDDEN and (headers.get(GITHUB_RATE_LIMIT_REMAINING_HEADER) == GITHUB_RATE_LIMIT_EXHAUSTED or HTTP_RETRY_AFTER_HEADER in headers):
            return SkillResolution(reason=SkillUnavailableReason.RATE_LIMITED, detail=f"GitHub's rate limit stopped {step.value} for {target} (HTTP 403); set GITHUB_TOKEN for a higher limit. Retried on the next run.")
        moved = (SkillUnavailableReason.NOT_FOUND, f"GitHub answered {step.value} for {target} with HTTP {status}: the repository may have moved; use the current owner/repo.")
        reasons: dict[int, tuple[SkillUnavailableReason, str]] = {
            HTTPStatus.MOVED_PERMANENTLY: moved,
            HTTPStatus.FOUND: moved,
            HTTPStatus.TEMPORARY_REDIRECT: moved,
            HTTPStatus.PERMANENT_REDIRECT: moved,
            HTTPStatus.UNAUTHORIZED: (SkillUnavailableReason.AUTH_FAILED, f"GitHub refused the token for {target} (HTTP 401); fix GITHUB_TOKEN or the entry's token=."),
            HTTPStatus.FORBIDDEN: (SkillUnavailableReason.AUTH_FAILED, f"GitHub refused access to {target} (HTTP 403); check that GITHUB_TOKEN or the entry's token= may read it."),
            HTTPStatus.NOT_FOUND: (SkillUnavailableReason.NOT_FOUND, f"{target} was not found on GitHub (HTTP 404), or it is private: set GITHUB_TOKEN or pass token=."),
            HTTPStatus.UNPROCESSABLE_ENTITY: (SkillUnavailableReason.NOT_FOUND, f"GitHub does not know the ref in {target} (HTTP 422); check ref=."),
            HTTPStatus.TOO_MANY_REQUESTS: (SkillUnavailableReason.RATE_LIMITED, f"GitHub's rate limit stopped {step.value} for {target} (HTTP 429); retried on the next run."),
        }
        reason, detail = reasons.get(status, (SkillUnavailableReason.FETCH_FAILED, f"GitHub answered {step.value} for {target} with HTTP {status}; retried on the next run."))
        return SkillResolution(reason=reason, detail=detail)


class GitHubSkillResolver(SkillResolver[GitHubSkill]):
    """Loads a group of SKILL.md files from one repository, ref, and token with shared lookups."""

    def __init__(self) -> None:
        self.fetch = SkillFetch()

    def group_key(self, entry: GitHubSkill) -> Hashable:
        # Entries share the commit lookup and tree listing only when the
        # same token would read them, so one token's view never decides
        # another entry's result.
        return (entry.repo, entry.ref, entry.token)

    async def resolve(self, entries: tuple[GitHubSkill, ...]) -> tuple[SkillResolution, ...]:
        # @intent github-shared-lookups
        # One commit lookup and at most one tree listing serve the
        # whole group, so five skills from one repository cost seven
        # requests. The token is checked before any request: a Vidbyte
        # key is never sent to GitHub, and a token a header cannot
        # carry is refused instead of crashing the run. A shared step's
        # failure applies to exactly the entries that needed it.
        first = entries[0]
        # Pick the token: the entry's own, else GITHUB_TOKEN, stripped.
        token = self._token(first)
        if token is not None and token.startswith(VIDBYTE_API_KEY_PREFIX):
            refused = SkillResolution(reason=SkillUnavailableReason.AUTH_FAILED, detail="The GitHub token is a Vidbyte API key, and a Vidbyte key is never sent to GitHub; set GITHUB_TOKEN or token= to a GitHub token, or leave both unset for public repositories.")
            return (refused,) * len(entries)
        # An HTTP header carries only printable ASCII, so a token with
        # any other character is refused before a request is built.
        if token is not None and not (token.isascii() and token.isprintable()):
            refused = SkillResolution(reason=SkillUnavailableReason.AUTH_FAILED, detail="The GitHub token holds a character an HTTP header cannot carry (only printable ASCII is allowed); fix the entry's token= or GITHUB_TOKEN.")
            return (refused,) * len(entries)
        auth = HttpResponseParser().bearer_headers(token) if token else {}
        # Pin the ref to one commit so every file comes from the same
        # snapshot; a full SHA needs no lookup.
        sha = await self._commit_sha(first, auth)
        if isinstance(sha, SkillResolution):
            return (sha,) * len(entries)
        # List the repository tree once, only if an entry has no path.
        paths = await self._tree_paths(first.repo, sha, auth) if any(entry.path is None for entry in entries) else ()
        # Find each folder: the entry's own path, else the shallowest
        # folder named after the skill.
        folders = [entry.path if entry.path is not None else self._search(paths, entry, sha) for entry in entries]
        # Fetch every SKILL.md at the same time; each failure stays with
        # its own entry, and a crash is re-raised, never hidden.
        answers = await asyncio.gather(*(self._raw_document(entry, folder, sha, auth) for entry, folder in zip(entries, folders, strict=True)), return_exceptions=True)
        resolutions: list[SkillResolution] = []
        for answer in answers:
            if isinstance(answer, BaseException):
                raise answer
            resolutions.append(answer)
        return tuple(resolutions)

    @staticmethod
    def _token(entry: GitHubSkill) -> str | None:
        # The entry's token wins; GITHUB_TOKEN is
        # read only at load time. Both are stripped,
        # and the stripped value is the one sent.
        raw = entry.token if entry.token is not None else os.environ.get(GITHUB_CREDENTIAL_ENV_VAR)
        stripped = (raw or "").strip()
        return stripped or None

    async def _commit_sha(self, entry: GitHubSkill, auth: dict[str, str]) -> str | SkillResolution:
        # @intent github-commit-lookup
        # A non-SHA answer (a proxy page, a short SHA) is the network's
        # fault, so it is FETCH_FAILED and the next run asks again.
        if entry.ref is not None and GITHUB_COMMIT_SHA_PATTERN.fullmatch(entry.ref):
            return entry.ref
        ref = entry.ref or GITHUB_DEFAULT_REF
        target = f"{entry.repo}@{ref}"
        answer = await self.fetch.get(url=f"{GITHUB_API_BASE_URL}/repos/{entry.repo}/commits/{quote(ref, safe='')}", headers={"accept": GITHUB_ACCEPT_SHA, **auth}, max_bytes=SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.GITHUB_COMMIT)
        if isinstance(answer, SkillResolution):
            return answer
        failure = _GitHubAnswer.failure(answer, step=SkillFetchStep.GITHUB_COMMIT, target=target)
        if failure is not None:
            return failure
        sha = answer.body.strip()
        if GITHUB_COMMIT_SHA_PATTERN.fullmatch(sha) is None:
            return SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"GitHub gave an unexpected answer to {SkillFetchStep.GITHUB_COMMIT.value} for {target} (not a commit SHA); retried on the next run.")
        return sha

    async def _tree_paths(self, repo: str, sha: str, auth: dict[str, str]) -> tuple[str, ...] | SkillResolution:
        # @intent github-tree-listing
        # A listing that is not usable JSON, or whose items are not all
        # objects with a text path, is a network fault (transient): its
        # items cannot be searched, so a miss there proves nothing. A
        # truncated one cannot prove a folder is the only match, so the
        # searched entries are told to pass path= (permanent).
        target = f"{repo}@{sha[:SKILL_LABEL_HASH_CHARS]}"
        answer = await self.fetch.get(url=f"{GITHUB_API_BASE_URL}/repos/{repo}/git/trees/{sha}?recursive=1", headers={"accept": GITHUB_ACCEPT_JSON, **auth}, max_bytes=SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.GITHUB_TREE)
        if isinstance(answer, SkillResolution):
            return answer
        failure = _GitHubAnswer.failure(answer, step=SkillFetchStep.GITHUB_TREE, target=target)
        if failure is not None:
            return failure
        try:
            listing = json.loads(answer.raw_bytes or b"")
        except (ValueError, RecursionError):
            listing = None
        tree = listing.get("tree") if isinstance(listing, dict) else None
        if not isinstance(listing, dict) or not isinstance(tree, list) or not all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in tree):
            return SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"GitHub gave an unexpected answer to {SkillFetchStep.GITHUB_TREE.value} for {target}; retried on the next run. Set path= on the entry to skip the tree listing.")
        if listing.get("truncated") is True:
            return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"GitHub truncated the tree listing of {target}, so the skill folder cannot be found by name; pass path= with the skill's folder.")
        return tuple(item["path"] for item in tree if item.get("type") == "blob")

    @staticmethod
    def _search(paths: tuple[str, ...] | SkillResolution, entry: GitHubSkill, sha: str) -> str | SkillResolution:
        # The shallowest folder named exactly after
        # the skill wins, as npx skills does; a tie
        # cannot be decided, so it asks for path=.
        if isinstance(paths, SkillResolution):
            return paths
        suffix = f"/{entry.name}/{SKILL_MARKDOWN_FILE_NAME}"
        folders = [path.removesuffix(f"/{SKILL_MARKDOWN_FILE_NAME}") for path in paths if f"/{path}".endswith(suffix)]
        target = f"{entry.repo}@{sha[:SKILL_LABEL_HASH_CHARS]}"
        if not folders:
            return SkillResolution(reason=SkillUnavailableReason.NOT_FOUND, detail=f"No {entry.name}/{SKILL_MARKDOWN_FILE_NAME} folder in {target}; pass path= with the skill's folder.")
        depth = min(folder.count("/") for folder in folders)
        shallowest = sorted(folder for folder in folders if folder.count("/") == depth)
        if len(shallowest) > 1:
            return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"{target} has {len(shallowest)} {entry.name} folders at the same depth ({', '.join(shallowest)}); pass path= to choose one.")
        return shallowest[0]

    async def _raw_document(self, entry: GitHubSkill, folder: str | SkillResolution, sha: str, auth: dict[str, str]) -> SkillResolution:
        # @intent github-raw-file
        # The file is read at the pinned commit with the SKILL.md
        # cap, and a failure here belongs to this entry alone.
        if isinstance(folder, SkillResolution):
            return folder
        file_path = f"{folder}/{SKILL_MARKDOWN_FILE_NAME}"
        answer = await self.fetch.get(url=f"{GITHUB_API_BASE_URL}/repos/{entry.repo}/contents/{quote(file_path, safe='/')}?ref={sha}", headers={"accept": GITHUB_ACCEPT_RAW, **auth}, max_bytes=SKILL_MARKDOWN_MAX_BYTES, step=SkillFetchStep.GITHUB_FILE)
        if isinstance(answer, SkillResolution):
            return answer
        failure = _GitHubAnswer.failure(answer, step=SkillFetchStep.GITHUB_FILE, target=f"{entry.repo}/{file_path}@{sha[:SKILL_LABEL_HASH_CHARS]}")
        if failure is not None:
            return failure
        return SkillMarkdown.parse(answer.raw_bytes or b"", name=entry.name, source=f"{SkillSourceType.GITHUB.value}:{entry.repo}@{sha[:SKILL_LABEL_HASH_CHARS]}/{file_path}")


__all__ = ["GitHubSkillResolver"]
