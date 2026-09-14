"""FILE: vidbyte/integrations/github.py

PURPOSE: Implements the GitHub REST provider behind the SourceProviderClient protocol.
ROLE IN CODEBASE: First concrete provider proving both SourceContext loads and SourceTool calls end to end.
ARCHITECTURE NOTE: Every URL derives from the bound config scope; model input only supplies repo-relative paths or queries.
COMMON MODIFICATION PATTERNS: Add an endpoint as one private fetch method plus error mapping through _raise_for_status.
KNOWN EDGE CASES: Empty sections are kept explicit, pagination is bounded, and auth failures never surface the token.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote

from vidbyte.lib.constants.integrations import (
    SOURCES_CONTENTS_OVERHEAD_BYTES,
    SOURCES_CONTENTS_SLACK_DENOMINATOR,
    SOURCES_CONTENTS_SLACK_NUMERATOR,
    SOURCES_DIFF_MAX_BYTES,
    SOURCES_HTTP_FORBIDDEN,
    SOURCES_HTTP_NOT_FOUND,
    SOURCES_HTTP_OK_MAX,
    SOURCES_HTTP_OK_MIN,
    SOURCES_HTTP_RATE_LIMITED,
    SOURCES_HTTP_TIMEOUT_SECONDS,
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
from vidbyte.lib.dataclasses.integrations import LoadedSection, SourceConfig
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SourceFetchError,
)
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

_API_ROOT = "https://api.github.com"


class GitHubClient:
    """Reads GitHub pull requests and repositories through the REST API."""

    def __init__(self, api_key: str, *, transport: HttpTransport | None = None, timeout_seconds: float = SOURCES_HTTP_TIMEOUT_SECONDS) -> None:
        """Hold the provider key in memory beside an injectable HTTP transport."""
        # @intent external boundaries
        # The key lives only on this client for header use; no persistence or logging path may read it.
        self._api_key = api_key
        self._transport = transport if transport is not None else HttpTransport()
        self._timeout_seconds = timeout_seconds

    async def load_context(self, config: SourceConfig) -> tuple[LoadedSection, ...]:
        """Fetch a pull request's description, diff, reviews, and discussion as sections."""
        # @intent external boundaries
        # Sections stay explicit even when empty so a missing part reads as empty, never as skipped.
        self._require_pull_request(config)
        pull = await self._fetch_pull(config)
        diff = await self._fetch_diff(config)
        reviews = await self._fetch_paged(config, f"/repos/{config.owner}/{config.repo}/pulls/{config.number}/reviews")
        comments = await self._fetch_paged(config, f"/repos/{config.owner}/{config.repo}/issues/{config.number}/comments")
        return self._assemble_sections(config, pull, diff, reviews, comments)

    async def read_repo_file(self, config: SourceConfig, path: str, ref: str | None, *, max_bytes: int) -> str:
        """Fetch and base64-decode one repo-relative file bounded by max_bytes."""
        self._require_repository(config)
        payload = await self._get_json(config, self._contents_url(config, path, ref), max_bytes=max_bytes * SOURCES_CONTENTS_SLACK_NUMERATOR // SOURCES_CONTENTS_SLACK_DENOMINATOR + SOURCES_CONTENTS_OVERHEAD_BYTES)
        return self._decode_contents(payload, max_bytes)

    async def list_repo_files(self, config: SourceConfig, path: str, ref: str | None, *, max_entries: int) -> str:
        """List one repo-relative directory's entry names bounded by max_entries."""
        self._require_repository(config)
        payload = await self._get_json(config, self._contents_url(config, path, ref), max_bytes=max_entries * SOURCES_LISTING_BYTES_PER_ENTRY + SOURCES_LISTING_OVERHEAD_BYTES)
        return self._render_listing(payload, max_entries)

    async def search_repo_code(self, config: SourceConfig, query: str, ref: str | None, *, max_items: int) -> str:
        """Search code confined to the bound repository with bounded items."""
        self._require_repository(config)
        scoped = f"{query} repo:{config.owner}/{config.repo}"
        payload = await self._get_json(config, f"{_API_ROOT}/search/code?q={quote(scoped)}&per_page={min(max_items, SOURCES_PER_PAGE)}", max_bytes=max_items * SOURCES_SEARCH_BYTES_PER_ITEM + SOURCES_SEARCH_OVERHEAD_BYTES)
        return self._render_search(payload, config, max_items)

    def _headers(self, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
        """Build request headers carrying the in-memory provider key."""
        return {"authorization": f"Bearer {self._api_key}", "accept": accept, "user-agent": "vidbyte-sdk"}

    async def _get_json(self, config: SourceConfig, url: str, *, max_bytes: int | None = None) -> Any:
        """GET one URL and return its decoded JSON body or raise a typed access error."""
        # @intent external boundaries
        # Malformed bodies become typed access errors so untrusted bytes never flow downstream as data.
        response = await self._send(config, url, accept="application/vnd.github+json", max_bytes=max_bytes)
        try:
            return json.loads(response.body)
        except ValueError as exc:
            raise SourceFetchError(f"Cannot access github resource '{config.resource}': invalid response.", details={"provider": "github", "resource": config.resource, "state": "TRANSPORT_FAILED"}) from exc

    async def _send(self, config: SourceConfig, url: str, *, accept: str, max_bytes: int | None) -> HttpResponse:
        """Send one bounded GET and map HTTP failures to typed access states."""
        # @intent external boundaries
        # Transport failures map to TRANSPORT_FAILED here so no raw HTTP error escapes the provider seam.
        try:
            response = await self._transport.request(method="GET", url=url, headers=self._headers(accept=accept), timeout_seconds=self._timeout_seconds, max_response_bytes=max_bytes)
        except ProviderRequestError as exc:
            raise SourceFetchError(f"Cannot access github resource '{config.resource}': transport failed.", details={"provider": "github", "resource": config.resource, "state": "TRANSPORT_FAILED"}) from exc
        self._raise_for_status(config, response)
        return response

    def _raise_for_status(self, config: SourceConfig, response: HttpResponse) -> None:
        """Translate non-2xx GitHub statuses into named access states without key material."""
        # @intent external boundaries
        # Non-2xx responses become named states so callers branch on meaning, never on raw codes.
        if SOURCES_HTTP_OK_MIN <= response.status_code < SOURCES_HTTP_OK_MAX:
            return
        state = self._classify_status(response)
        raise SourceFetchError(f"Cannot access github resource '{config.resource}': {state}.", details={"provider": "github", "resource": config.resource, "state": state})

    @staticmethod
    def _classify_status(response: HttpResponse) -> str:
        """Name the access state one HTTP status and body imply."""
        # @intent external boundaries
        # Status codes map to retry-or-escalate states here so transport noise never leaks as raw numbers.
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

    async def _fetch_pull(self, config: SourceConfig) -> dict[str, Any]:
        """Fetch one pull request's metadata record as decoded JSON."""
        # @intent external boundaries
        # A non-object payload is a transport failure, not an empty pull, so shape drift cannot read as content.
        payload = await self._get_json(config, f"{_API_ROOT}/repos/{config.owner}/{config.repo}/pulls/{config.number}", max_bytes=SOURCES_PULL_MAX_BYTES)
        if not isinstance(payload, dict):
            raise SourceFetchError(f"Cannot access github resource '{config.resource}': invalid response.", details={"provider": "github", "resource": config.resource, "state": "TRANSPORT_FAILED"})
        return payload

    async def _fetch_diff(self, config: SourceConfig) -> str:
        """Fetch one pull request's unified diff text within a byte ceiling."""
        # @intent external boundaries
        # Diffs stream under a hard byte ceiling so one huge pull cannot exhaust memory before clipping.
        response = await self._send(config, f"{_API_ROOT}/repos/{config.owner}/{config.repo}/pulls/{config.number}", accept="application/vnd.github.diff", max_bytes=SOURCES_DIFF_MAX_BYTES)
        return response.body

    async def _fetch_paged(self, config: SourceConfig, path: str) -> list[dict[str, Any]]:
        """Collect bounded pages of a list endpoint into one flat record list."""
        # @intent external boundaries
        # Pagination stops at a fixed page cap so a hostile list endpoint cannot page forever.
        records: list[dict[str, Any]] = []
        for page in range(1, SOURCES_MAX_PAGES + 1):
            payload = await self._get_json(config, f"{_API_ROOT}{path}?per_page={SOURCES_PER_PAGE}&page={page}", max_bytes=SOURCES_PAGE_MAX_BYTES)
            items = payload if isinstance(payload, list) else payload.get("items", [])
            records.extend(item for item in items if isinstance(item, dict))
            if len(items) < SOURCES_PER_PAGE:
                break
        return records

    def _assemble_sections(self, config: SourceConfig, pull: dict[str, Any], diff: str, reviews: list[dict[str, Any]], comments: list[dict[str, Any]]) -> tuple[LoadedSection, ...]:
        """Convert raw pull records into the four explicit context sections."""
        revision = self._revision_of(pull)
        base_url = f"https://github.com/{config.owner}/{config.repo}/pull/{config.number}"
        description = str(pull.get("body") or "")
        title = str(pull.get("title") or f"Pull #{config.number}")
        return (LoadedSection(title=f"PR description: {title}", source_url=base_url, body=description, revision=revision), LoadedSection(title=f"PR diff: {title}", source_url=f"{base_url}.diff", body=diff, revision=revision), LoadedSection(title=f"PR reviews: {title}", source_url=f"{base_url}#reviews", body=self._render_reviews(reviews), revision=revision), LoadedSection(title=f"PR discussion: {title}", source_url=f"{base_url}#discussion", body=self._render_comments(comments), revision=revision))

    @staticmethod
    def _revision_of(pull: dict[str, Any]) -> str | None:
        """Extract the head SHA identifying the fetched pull snapshot."""
        head = pull.get("head")
        sha = head.get("sha") if isinstance(head, dict) else None
        return str(sha) if sha else None

    @staticmethod
    def _render_reviews(reviews: list[dict[str, Any]]) -> str:
        """Render review records as attributable body lines, possibly empty."""
        return "\n\n".join(f"@{review.get('user', {}).get('login', 'unknown')} [{review.get('state', '')}]: {review.get('body') or ''}".strip() for review in reviews)

    @staticmethod
    def _render_comments(comments: list[dict[str, Any]]) -> str:
        """Render discussion records as attributable body lines, possibly empty."""
        return "\n\n".join(f"@{comment.get('user', {}).get('login', 'unknown')}: {comment.get('body') or ''}".strip() for comment in comments)

    def _contents_url(self, config: SourceConfig, path: str, ref: str | None) -> str:
        """Build the contents URL for a repo-relative path from the bound scope only."""
        encoded = quote(path, safe="/")
        url = f"{_API_ROOT}/repos/{config.owner}/{config.repo}/contents/{encoded}"
        return f"{url}?ref={quote(ref)}" if ref else url

    @staticmethod
    def _decode_contents(payload: Any, max_bytes: int) -> str:
        """Base64-decode a file payload and clip it to max_bytes on a UTF-8 boundary."""
        if not isinstance(payload, dict) or payload.get("type") != "file" or not isinstance(payload.get("content"), str):
            raise SourceFetchError("Cannot decode github file: expected a file payload.", details={"provider": "github", "resource": "repository", "state": "RESOURCE_UNAVAILABLE"})
        raw = base64.b64decode(payload["content"])
        text = raw.decode("utf-8", errors="replace")
        return clip_text(text, max_bytes)

    @staticmethod
    def _render_listing(payload: Any, max_entries: int) -> str:
        """Render a directory payload as newline names bounded by max_entries."""
        if isinstance(payload, dict):
            raise SourceFetchError("Cannot list github path: expected a directory.", details={"provider": "github", "resource": "repository", "state": "RESOURCE_UNAVAILABLE"})
        names = [str(entry.get("path", "")) for entry in payload if isinstance(entry, dict)]
        return "\n".join(names[:max(0, max_entries)])

    @staticmethod
    def _render_search(payload: Any, config: SourceConfig, max_items: int) -> str:
        """Render search matches as path lines already confined to the bound repo."""
        items = payload.get("items", []) if isinstance(payload, dict) else []
        lines = [str(item.get("path", "")) for item in items if isinstance(item, dict)]
        return "\n".join(f"{config.owner}/{config.repo}/{path}" for path in lines[:max(0, max_items)])

    @staticmethod
    def _require_pull_request(config: SourceConfig) -> None:
        """Reject non-pull-request configs before any network use."""
        # @intent external boundaries
        # Kind is checked before the first request so a wrong-kind config never touches the network.
        if config.kind != SourceKind.PULL_REQUEST:
            raise ConfigurationError("Loading pull context requires a pull-request resource.")

    @staticmethod
    def _require_repository(config: SourceConfig) -> None:
        """Reject non-repository configs before any network use."""
        if config.kind != SourceKind.REPOSITORY:
            raise ConfigurationError("Repository operations require a repository resource.")


def clip_text(text: str, max_bytes: int) -> str:
    """Clip text to max_bytes of UTF-8 without splitting a code point."""
    from vidbyte.lib.constants.integrations import SOURCES_TRUNCATION_MARKER

    encoded = text.encode("utf-8")
    ceiling = max(0, max_bytes)
    if len(encoded) <= ceiling:
        return text
    marker = SOURCES_TRUNCATION_MARKER.encode("utf-8")
    if ceiling <= len(marker):
        return marker[:ceiling].decode("utf-8", errors="ignore")
    room = ceiling - len(marker)
    clipped = encoded[:room].decode("utf-8", errors="ignore")
    return f"{clipped}{SOURCES_TRUNCATION_MARKER}"


__all__ = [
    "GitHubClient",
    "clip_text",
]
