"""FILE: vidbyte/integrations/github.py

PURPOSE: Reads GitHub pull requests and repositories through gh with typed REST fallback.
ROLE IN CODEBASE: Concrete provider used by SourceContext and the repository-scoped GitHub tools.
ARCHITECTURE NOTE: Provider-owned command plans preserve scope; CliRunner owns process safety and HttpTransport owns REST I/O.
COMMON MODIFICATION PATTERNS: Add an operation to both the native plan and the REST fallback, then normalize their responses together.
KNOWN EDGE CASES: Missing gh falls back, attempted CLI failures do not; empty sections remain explicit and pagination is bounded.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from vidbyte.lib.cli import (
    CliCommandError,
    CliError,
    CliRequest,
    CliResult,
    CliUnavailableError,
)
from vidbyte.lib.constants.integrations import (
    SOURCES_CLI_MAX_OUTPUT_BYTES,
    SOURCES_CONTENTS_OVERHEAD_BYTES,
    SOURCES_CONTENTS_SLACK_DENOMINATOR,
    SOURCES_CONTENTS_SLACK_NUMERATOR,
    SOURCES_DIFF_MAX_BYTES,
    SOURCES_GITHUB_API_ROOT,
    SOURCES_GITHUB_PR_JSON_FIELDS,
    SOURCES_HTTP_FORBIDDEN,
    SOURCES_HTTP_NOT_FOUND,
    SOURCES_HTTP_OK_MAX,
    SOURCES_HTTP_OK_MIN,
    SOURCES_HTTP_RATE_LIMITED,
    SOURCES_HTTP_UNAUTHORIZED,
    SOURCES_LISTING_BYTES_PER_ENTRY,
    SOURCES_LISTING_OVERHEAD_BYTES,
    SOURCES_MAX_PAGES,
    SOURCES_PAGE_MAX_BYTES,
    SOURCES_PER_PAGE,
    SOURCES_PULL_MAX_BYTES,
    SOURCES_SEARCH_BYTES_PER_ITEM,
    SOURCES_SEARCH_OVERHEAD_BYTES,
)
from vidbyte.lib.dataclasses.integrations import (
    GitHubClientConfig,
    LoadedSection,
    SourceConfig,
)
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SourceFetchError,
)
from vidbyte.lib.http.transport import HttpResponse


@dataclass(frozen=True, slots=True)
class _ProviderPayload:
    """Decoded provider text plus the transport that produced it."""

    body: str
    transport: str


class GitHubClient:
    """Reads GitHub resources through the native CLI and a safe REST fallback."""

    def __init__(self, config: GitHubClientConfig) -> None:
        """Hold validated transports and the credential-bearing client configuration."""
        self._config = config

    # @intent provider-boundary
    async def load_context(self, source: SourceConfig) -> tuple[LoadedSection, ...]:
        """Fetch pull-request description, diff, reviews, and discussion."""
        self._require_pull_request(source)
        try:
            pull = await self._cli_json(source, self._pull_command(source), SOURCES_PULL_MAX_BYTES)
            diff = await self._cli_text(source, self._diff_command(source), SOURCES_DIFF_MAX_BYTES)
            return self._assemble_sections(source, pull, diff, "cli")
        except CliUnavailableError:
            pull = await self._fetch_pull(source)
            diff = await self._fetch_diff(source)
            reviews = await self._fetch_paged(source, f"/repos/{source.owner}/{source.repo}/pulls/{source.number}/reviews")
            comments = await self._fetch_paged(source, f"/repos/{source.owner}/{source.repo}/issues/{source.number}/comments")
            return self._assemble_sections(source, pull, diff, "rest", reviews=reviews, comments=comments)

    # @intent provider-boundary
    async def read_repo_file(self, source: SourceConfig, path: str, ref: str | None, *, max_bytes: int) -> _ProviderPayload:
        """Read and decode one repository file using the bound repository scope."""
        self._require_repository(source)
        cli_args = self._contents_command(source, path, ref)
        try:
            payload = await self._cli_json(source, cli_args, self._contents_limit(max_bytes))
            transport = "cli"
        except CliUnavailableError:
            payload = await self._get_json(source, self._contents_url(source, path, ref), max_bytes=self._contents_limit(max_bytes))
            transport = "rest"
        return _ProviderPayload(self._decode_contents(payload, max_bytes, source), transport)

    # @intent provider-boundary
    async def list_repo_files(self, source: SourceConfig, path: str, ref: str | None, *, max_entries: int) -> _ProviderPayload:
        """List one repository directory with a bounded number of names."""
        self._require_repository(source)
        cli_args = self._contents_command(source, path, ref)
        max_bytes = max_entries * SOURCES_LISTING_BYTES_PER_ENTRY + SOURCES_LISTING_OVERHEAD_BYTES
        try:
            payload = await self._cli_json(source, cli_args, max_bytes)
            transport = "cli"
        except CliUnavailableError:
            payload = await self._get_json(source, self._contents_url(source, path, ref), max_bytes=max_bytes)
            transport = "rest"
        return _ProviderPayload(self._render_listing(payload, max_entries, source), transport)

    # @intent provider-boundary
    async def search_repo_code(self, source: SourceConfig, query: str, ref: str | None, *, max_items: int) -> _ProviderPayload:
        """Search code with the repository scope fixed by the validated source."""
        self._require_repository(source)
        scoped = f"{query} repo:{source.owner}/{source.repo}"
        max_bytes = max_items * SOURCES_SEARCH_BYTES_PER_ITEM + SOURCES_SEARCH_OVERHEAD_BYTES
        try:
            payload = await self._cli_json(source, self._search_command(scoped, ref, max_items), max_bytes)
            transport = "cli"
        except CliUnavailableError:
            url = f"{SOURCES_GITHUB_API_ROOT}/search/code?q={quote(scoped)}&per_page={min(max_items, SOURCES_PER_PAGE)}"
            if ref:
                url += f"&ref={quote(ref)}"
            payload = await self._get_json(source, url, max_bytes=max_bytes)
            transport = "rest"
        return _ProviderPayload(self._render_search(payload, source, max_items), transport)

    # @intent provider-boundary
    async def _cli_json(self, source: SourceConfig, args: tuple[str, ...], max_bytes: int) -> Any:
        """Run one provider-authored JSON command and normalize safe failures."""
        result = await self._run_cli(source, args, max_bytes)
        try:
            return json.loads(result.stdout)
        except (TypeError, ValueError) as exc:
            raise self._fetch_error(source, "TRANSPORT_FAILED") from exc

    async def _cli_text(self, source: SourceConfig, args: tuple[str, ...], max_bytes: int) -> str:
        """Run one provider-authored text command and return bounded stdout."""
        return (await self._run_cli(source, args, max_bytes)).stdout

    # @intent provider-boundary
    async def _run_cli(self, source: SourceConfig, args: tuple[str, ...], max_bytes: int) -> CliResult:
        """Send one fixed command through the central secret-safe CLI runner."""
        try:
            return await self._config.runner.run(
                CliRequest(
                    executable="gh",
                    args=args,
                    api_key=self._config.api_key,
                    timeout_seconds=self._config.timeout_seconds,
                    max_output_bytes=min(max(SOURCES_CLI_MAX_OUTPUT_BYTES, max_bytes), SOURCES_CLI_MAX_OUTPUT_BYTES),
                )
            )
        except CliUnavailableError:
            raise
        except CliCommandError as exc:
            raise self._fetch_error(source, exc.category) from exc
        except CliError as exc:
            raise self._fetch_error(source, "TRANSPORT_FAILED") from exc

    # @intent provider-boundary
    async def _get_json(self, source: SourceConfig, url: str, *, max_bytes: int | None = None) -> Any:
        """GET one REST route and decode its JSON body without exposing raw payloads."""
        response = await self._send_rest(source, url, accept="application/vnd.github+json", max_bytes=max_bytes)
        try:
            return json.loads(response.body)
        except (TypeError, ValueError) as exc:
            raise self._fetch_error(source, "TRANSPORT_FAILED") from exc

    # @intent provider-boundary
    async def _send_rest(self, source: SourceConfig, url: str, *, accept: str, max_bytes: int | None) -> HttpResponse:
        """Send one bounded REST request and translate transport failures safely."""
        try:
            response = await self._config.transport.request(
                method="GET",
                url=url,
                headers={"authorization": f"Bearer {self._config.api_key}", "accept": accept, "user-agent": "vidbyte-sdk"},
                timeout_seconds=self._config.timeout_seconds,
                max_response_bytes=max_bytes,
            )
        except ProviderRequestError as exc:
            raise self._fetch_error(source, "TRANSPORT_FAILED") from exc
        self._raise_for_status(source, response)
        return response

    # @intent provider-boundary
    def _raise_for_status(self, source: SourceConfig, response: HttpResponse) -> None:
        """Translate REST status codes into stable source access categories."""
        if SOURCES_HTTP_OK_MIN <= response.status_code < SOURCES_HTTP_OK_MAX:
            return
        raise self._fetch_error(source, self._classify_status(response))

    @staticmethod
    def _classify_status(response: HttpResponse) -> str:
        """Classify one status and safe body signal without returning body text."""
        if response.status_code == SOURCES_HTTP_UNAUTHORIZED:
            return "AUTH_REQUIRED"
        if response.status_code == SOURCES_HTTP_RATE_LIMITED:
            return "RATE_LIMITED"
        if response.status_code == SOURCES_HTTP_NOT_FOUND:
            return "RESOURCE_UNAVAILABLE"
        if response.status_code == SOURCES_HTTP_FORBIDDEN and "rate limit" in response.body.lower():
            return "RATE_LIMITED"
        if response.status_code == SOURCES_HTTP_FORBIDDEN:
            return "INSUFFICIENT_SCOPE"
        return "TRANSPORT_FAILED"

    # @intent provider-boundary
    async def _fetch_pull(self, source: SourceConfig) -> dict[str, Any]:
        """Fetch REST pull-request metadata and require an object payload."""
        payload = await self._get_json(source, f"{SOURCES_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}/pulls/{source.number}", max_bytes=SOURCES_PULL_MAX_BYTES)
        if not isinstance(payload, dict):
            raise self._fetch_error(source, "TRANSPORT_FAILED")
        return payload

    # @intent provider-boundary
    async def _fetch_diff(self, source: SourceConfig) -> str:
        """Fetch the pull-request unified diff with a hard byte ceiling."""
        response = await self._send_rest(source, f"{SOURCES_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}/pulls/{source.number}", accept="application/vnd.github.diff", max_bytes=SOURCES_DIFF_MAX_BYTES)
        return response.body

    # @intent provider-boundary
    async def _fetch_paged(self, source: SourceConfig, path: str) -> list[dict[str, Any]]:
        """Collect bounded REST pages into one list, failing on page errors."""
        records: list[dict[str, Any]] = []
        for page in range(1, SOURCES_MAX_PAGES + 1):
            payload = await self._get_json(source, f"{SOURCES_GITHUB_API_ROOT}{path}?per_page={SOURCES_PER_PAGE}&page={page}", max_bytes=SOURCES_PAGE_MAX_BYTES)
            items = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise self._fetch_error(source, "TRANSPORT_FAILED")
            records.extend(item for item in items if isinstance(item, dict))
            if len(items) < SOURCES_PER_PAGE:
                break
        return records

    # @intent provider-boundary
    def _assemble_sections(self, source: SourceConfig, pull: dict[str, Any], diff: str, transport: str, *, reviews: list[dict[str, Any]] | None = None, comments: list[dict[str, Any]] | None = None) -> tuple[LoadedSection, ...]:
        """Normalize native or REST pull data into four explicit sections."""
        title = str(pull.get("title") or f"Pull #{source.number}")
        base_url = f"https://github.com/{source.owner}/{source.repo}/pull/{source.number}"
        native_reviews = self._records(pull, "reviews")
        native_comments = self._records(pull, "comments")
        revision = self._revision_of(pull)
        return (
            LoadedSection(f"PR description: {title}", base_url, str(pull.get("body") or ""), revision, transport),
            LoadedSection(f"PR diff: {title}", f"{base_url}.diff", diff, revision, transport),
            LoadedSection(f"PR reviews: {title}", f"{base_url}#reviews", self._render_reviews(reviews if reviews is not None else native_reviews), revision, transport),
            LoadedSection(f"PR discussion: {title}", f"{base_url}#discussion", self._render_comments(comments if comments is not None else native_comments), revision, transport),
        )

    @staticmethod
    def _revision_of(pull: dict[str, Any]) -> str | None:
        """Extract a pull head SHA from either REST or gh JSON shape."""
        head = pull.get("head")
        sha = head.get("sha") if isinstance(head, dict) else pull.get("headRefOid")
        return str(sha) if sha else None

    @staticmethod
    def _records(payload: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
        """Keep only object records from an optional native JSON collection."""
        raw = payload.get(field_name)
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    @staticmethod
    def _render_reviews(reviews: list[dict[str, Any]]) -> str:
        """Render review bodies and states while tolerating REST and gh authors."""
        lines: list[str] = []
        for review in reviews:
            author = review.get("user") or review.get("author") or {}
            login = author.get("login") or author.get("name") or "unknown" if isinstance(author, dict) else "unknown"
            state = review.get("state") or ""
            body = review.get("body") or ""
            lines.append(f"@{login} [{state}]: {body}".strip())
        return "\n\n".join(lines)

    @staticmethod
    def _render_comments(comments: list[dict[str, Any]]) -> str:
        """Render discussion bodies while tolerating REST and gh authors."""
        lines: list[str] = []
        for comment in comments:
            author = comment.get("user") or comment.get("author") or {}
            login = author.get("login") or author.get("name") or "unknown" if isinstance(author, dict) else "unknown"
            lines.append(f"@{login}: {comment.get('body') or ''}".strip())
        return "\n\n".join(lines)

    @staticmethod
    def _pull_command(source: SourceConfig) -> tuple[str, ...]:
        """Build the fixed gh pull-view command from validated scope."""
        return ("pr", "view", str(source.number), "--repo", f"{source.owner}/{source.repo}", "--json", SOURCES_GITHUB_PR_JSON_FIELDS)

    @staticmethod
    def _diff_command(source: SourceConfig) -> tuple[str, ...]:
        """Build the fixed gh pull-diff command from validated scope."""
        return ("pr", "diff", str(source.number), "--repo", f"{source.owner}/{source.repo}")

    @staticmethod
    def _contents_command(source: SourceConfig, path: str, ref: str | None) -> tuple[str, ...]:
        """Build a fixed gh API contents command with path and ref as values."""
        endpoint = f"repos/{source.owner}/{source.repo}/contents"
        if path:
            endpoint += f"/{quote(path, safe='/')}"
        args = ["api", endpoint, "--method", "GET"]
        if ref:
            args.extend(("--field", f"ref={ref}"))
        return tuple(args)

    @staticmethod
    def _search_command(scoped_query: str, ref: str | None, max_items: int) -> tuple[str, ...]:
        """Build a fixed gh API search command with the repository scope in its query."""
        args = ["api", "search/code", "--method", "GET", "--field", f"q={scoped_query}", "--field", f"per_page={min(max_items, SOURCES_PER_PAGE)}"]
        if ref:
            args.extend(("--field", f"ref={ref}"))
        return tuple(args)

    @staticmethod
    def _contents_url(source: SourceConfig, path: str, ref: str | None) -> str:
        """Build the REST contents route from provider-owned scope and path."""
        endpoint = f"{SOURCES_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}/contents"
        if path:
            endpoint += f"/{quote(path, safe='/')}"
        return f"{endpoint}?ref={quote(ref)}" if ref else endpoint

    @staticmethod
    def _contents_limit(max_bytes: int) -> int:
        """Reserve enough bounded response space for base64 JSON overhead."""
        return max(SOURCES_CLI_MAX_OUTPUT_BYTES, max_bytes * SOURCES_CONTENTS_SLACK_NUMERATOR // SOURCES_CONTENTS_SLACK_DENOMINATOR + SOURCES_CONTENTS_OVERHEAD_BYTES)

    @staticmethod
    # @intent provider-boundary
    def _decode_contents(payload: Any, max_bytes: int, source: SourceConfig) -> str:
        """Decode a GitHub file payload and clip it without leaking malformed content."""
        if not isinstance(payload, dict) or payload.get("type") != "file" or not isinstance(payload.get("content"), str):
            raise GitHubClient._fetch_error(source, "RESOURCE_UNAVAILABLE")
        try:
            raw = base64.b64decode(payload["content"])
        except (ValueError, binascii.Error) as exc:
            raise GitHubClient._fetch_error(source, "TRANSPORT_FAILED") from exc
        from vidbyte.lib.text import TextClipper

        return TextClipper.clip(raw.decode("utf-8", errors="replace"), max_bytes)

    @staticmethod
    # @intent provider-boundary
    def _render_listing(payload: Any, max_entries: int, source: SourceConfig) -> str:
        """Render directory entry paths and reject a file payload."""
        if not isinstance(payload, list):
            raise GitHubClient._fetch_error(source, "RESOURCE_UNAVAILABLE")
        return "\n".join(str(entry.get("path", "")) for entry in payload[:max(0, max_entries)] if isinstance(entry, dict))

    @staticmethod
    # @intent provider-boundary
    def _render_search(payload: Any, source: SourceConfig, max_items: int) -> str:
        """Render search paths from REST or gh's list-shaped response."""
        items = payload.get("items", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        if not isinstance(items, list):
            raise GitHubClient._fetch_error(source, "TRANSPORT_FAILED")
        lines = [str(item.get("path", "")) for item in items if isinstance(item, dict)]
        return "\n".join(f"{source.owner}/{source.repo}/{path}" for path in lines[:max(0, max_items)])

    @staticmethod
    # @intent provider-boundary
    def _require_pull_request(source: SourceConfig) -> None:
        """Reject repository resources before any native or network request."""
        if source.kind != SourceKind.PULL_REQUEST:
            raise ConfigurationError("Loading pull context requires a pull-request resource.")

    @staticmethod
    # @intent provider-boundary
    def _require_repository(source: SourceConfig) -> None:
        """Reject pull-request resources before any native or network request."""
        if source.kind != SourceKind.REPOSITORY:
            raise ConfigurationError("Repository operations require a repository resource.")

    @staticmethod
    # @intent provider-boundary
    def _fetch_error(source: SourceConfig, state: str) -> SourceFetchError:
        """Construct a safe source error containing only provider-authored identity."""
        return SourceFetchError(
            f"Cannot access github resource '{source.resource}': {state}.",
            details={"provider": "github", "resource": source.resource, "state": state},
        )


__all__ = ["GitHubClient"]
