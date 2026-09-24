"""FILE: vidbyte/providers/tool_catalogs/base.py

PURPOSE: Defines ToolCatalogProvider, the contract every public tool-catalog adapter implements, plus the shared HTTP, parsing, and local-index helpers the adapters reuse.
ROLE IN CODEBASE: Each adapter in this package subclasses ToolCatalogProvider; ToolCatalogs builds them from settings and JevAgentAlignment searches, describes, connects, and executes through this interface only.
ARCHITECTURE NOTE: Adapters speak each catalog's HTTP API through vidbyte.lib.http.HttpTransport with a timeout and a byte ceiling on every call, and return only vidbyte.lib.dataclasses.tool_catalogs records; payload dictionaries stay inside this package.
COMMON MODIFICATION PATTERNS: A new catalog subclasses ToolCatalogProvider (or IndexedToolCatalogProvider for whole-file indexes), sets `name`, implements search(), and overrides describe()/connect()/execute() only when the catalog supports them.
KNOWN EDGE CASES: Non-2xx responses and undecodable bodies raise ProviderRequestError or ProviderResponseError with the catalog name; callers treat one catalog's failure as that catalog's error, never the whole search's. Index caches live on the adapter instance, so one agent reuses a downloaded catalog across runs until the TTL passes.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from typing import ClassVar
from urllib.parse import urlencode

import yaml

from vidbyte.lib.constants.tool_catalogs import (
    TOOL_CATALOG_DESCRIPTION_CHARS,
    TOOL_CATALOG_HTTP_MULTIPLE_CHOICES,
    TOOL_CATALOG_HTTP_OK,
    TOOL_CATALOG_INDEX_MAX_RESPONSE_BYTES,
    TOOL_CATALOG_INDEX_TIMEOUT_SECONDS,
    TOOL_CATALOG_INDEX_TTL_SECONDS,
    TOOL_CATALOG_MAX_RESPONSE_BYTES,
    TOOL_CATALOG_RETRY_COUNT,
    TOOL_CATALOG_TIMEOUT_SECONDS,
    TOOL_CATALOG_TOOL_DESCRIPTION_CHARS,
)
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogCredentials,
    ToolCatalogEntry,
    ToolConnection,
    ToolInstall,
)
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName
from vidbyte.lib.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

_WORD = re.compile(r"[a-z0-9]+")
_MIN_TERM_CHARS = 2
_NAME_WEIGHT = 3
_TEXT_WEIGHT = 1


class ToolCatalogProvider(ABC):
    """One public tool catalog, normalized into ToolCatalogEntry records."""

    name: ClassVar[ToolCatalogName]
    # True when the platform runs a tool through its own execute endpoint instead of an MCP connection.
    executes_directly: ClassVar[bool] = False

    def __init__(self, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> None:
        # Retains the owner's credentials for this catalog and the shared HTTP transport.
        self.credentials = credentials or ToolCatalogCredentials()
        self.transport = transport or HttpTransport()

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Return up to `limit` entries matching `query`, best first."""

    async def describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        """Return the entry with its tool list and installs filled in; the default returns it unchanged."""
        return entry

    async def connect(self, entry: ToolCatalogEntry, install: ToolInstall, *, tool_names: Sequence[str], user_id: str | None) -> ToolConnection:
        """Resolve a MANAGED install to an MCP endpoint; catalogs without managed installs refuse."""
        del entry, install, tool_names, user_id
        raise ProviderConfigurationError(f"The {self.name.value} catalog has no managed installs to connect.", provider=self.name.value)

    async def execute(self, entry: ToolCatalogEntry, tool: CatalogTool, arguments: Mapping[str, object], *, user_id: str | None) -> tuple[str, bool]:
        """Run one tool through the platform's execute endpoint and return (output text, is_error)."""
        del entry, tool, arguments, user_id
        raise ProviderConfigurationError(f"The {self.name.value} catalog does not execute tools directly.", provider=self.name.value)

    def require_credentials(self, *fields: str) -> ToolCatalogCredentials:
        """Return the credentials, raising when any named field is missing."""
        missing = [field_name for field_name in fields if not getattr(self.credentials, field_name)]
        if missing:
            raise ProviderConfigurationError(f"The {self.name.value} catalog needs credentials: {', '.join(missing)}.", provider=self.name.value)
        return self.credentials

    async def get_json(self, url: str, *, params: Mapping[str, object] | None = None, headers: Mapping[str, str] | None = None, index: bool = False) -> object:
        """GET one catalog URL and decode its JSON body; `index` selects the whole-file size ceiling and timeout."""
        response = await self._request("GET", _with_query(url, params), headers=headers, body=None, index=index)
        return self._decode_json(response)

    async def send_json(self, method: str, url: str, body: Mapping[str, object], *, headers: Mapping[str, str] | None = None) -> object:
        """Send one JSON body to a catalog endpoint and decode the JSON reply."""
        response = await self._request(method, url, headers=headers, body=body, index=False)
        return self._decode_json(response)

    async def get_text(self, url: str, *, index: bool = False) -> str:
        """GET one catalog URL and return its body as text."""
        response = await self._request("GET", url, headers=None, body=None, index=index)
        return response.body

    async def _request(self, method: str, url: str, *, headers: Mapping[str, str] | None, body: Mapping[str, object] | None, index: bool) -> HttpResponse:
        # Sends one bounded catalog request and turns every non-2xx status into a typed provider error.
        # @intent catalog-bodies-are-untrusted-and-bounded
        # Catalog bodies come from third parties, so every read has a byte ceiling before decoding, and only GETs
        # are retried because retrying a POST (Composio session, Arcade execute) could repeat its side effect.
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        response = await self.transport.request(
            method=method,
            url=url,
            headers=request_headers,
            json_body=body,
            timeout_seconds=TOOL_CATALOG_INDEX_TIMEOUT_SECONDS if index else TOOL_CATALOG_TIMEOUT_SECONDS,
            retry_count=TOOL_CATALOG_RETRY_COUNT if method.upper() == "GET" else 0,
            max_response_bytes=TOOL_CATALOG_INDEX_MAX_RESPONSE_BYTES if index else TOOL_CATALOG_MAX_RESPONSE_BYTES,
            follow_redirects=True,
        )
        if not TOOL_CATALOG_HTTP_OK <= response.status_code < TOOL_CATALOG_HTTP_MULTIPLE_CHOICES:
            raise ProviderRequestError(f"The {self.name.value} catalog returned HTTP {response.status_code}.", provider=self.name.value, status_code=response.status_code)
        return response

    def _decode_json(self, response: HttpResponse) -> object:
        # Decodes a JSON body, naming the catalog when it is not JSON.
        try:
            return json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"The {self.name.value} catalog returned a body that is not JSON.", provider=self.name.value, status_code=response.status_code) from exc


class IndexedToolCatalogProvider(ToolCatalogProvider):
    """A catalog published as one downloadable index file, searched locally and cached on the adapter."""

    index_url: ClassVar[str]

    def __init__(self, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> None:
        # Starts with an empty cache; the first search downloads the index.
        super().__init__(credentials=credentials, transport=transport)
        self._entries: tuple[ToolCatalogEntry, ...] = ()
        self._loaded_at: float | None = None

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Rank the cached index against the query's words and return the best `limit` entries."""
        entries = await self.entries()
        return rank_entries(entries, query, limit=limit)

    async def entries(self) -> tuple[ToolCatalogEntry, ...]:
        """Return the parsed index, downloading it again once the cache is older than the TTL."""
        now = time.monotonic()
        if self._loaded_at is None or now - self._loaded_at > TOOL_CATALOG_INDEX_TTL_SECONDS:
            self._entries = tuple(self.parse_index(await self.get_text(self.index_url, index=True)))
            self._loaded_at = now
        return self._entries

    @abstractmethod
    def parse_index(self, body: str) -> Iterable[ToolCatalogEntry]:
        """Turn the downloaded index file into entries, skipping malformed items."""

    def load_yaml(self, body: str) -> object:
        """Parse a YAML index with the safe loader, naming the catalog when it does not parse."""
        try:
            return yaml.safe_load(body)
        except yaml.YAMLError as exc:
            raise ProviderResponseError(f"The {self.name.value} catalog index is not valid YAML.", provider=self.name.value) from exc

    def load_json(self, body: str) -> object:
        """Parse a JSON index, naming the catalog when it does not parse."""
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"The {self.name.value} catalog index is not valid JSON.", provider=self.name.value) from exc


def rank_entries(entries: Iterable[ToolCatalogEntry], query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
    """Score entries by how many query words appear in their name, description, and tools; drop entries with no hit."""
    terms = query_terms(query)
    if not terms:
        return ()
    scored: list[tuple[int, int, ToolCatalogEntry]] = []
    for position, entry in enumerate(entries):
        score = _entry_score(entry, terms)
        if score:
            scored.append((score, -position, entry))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return tuple(entry for _, _, entry in scored[: max(0, limit)])


def query_terms(query: str) -> frozenset[str]:
    """Return the lowercase words of a query that are long enough to match on."""
    return frozenset(word for word in _WORD.findall(query.lower()) if len(word) >= _MIN_TERM_CHARS)


def _entry_score(entry: ToolCatalogEntry, terms: frozenset[str]) -> int:
    # Weights name hits above description and tool hits so "github" ranks the GitHub server above servers that mention it.
    name_words = set(_WORD.findall(f"{entry.name} {entry.entry_id}".lower()))
    text_words = set(_WORD.findall(" ".join((entry.description, *(f"{tool.name} {tool.description}" for tool in entry.tools))).lower()))
    return sum(_NAME_WEIGHT for term in terms if term in name_words) + sum(_TEXT_WEIGHT for term in terms if term in text_words)


def text(value: object, *, limit: int = TOOL_CATALOG_DESCRIPTION_CHARS) -> str:
    """Return a stripped, length-capped string for any catalog field, or empty text for missing values."""
    if value is None:
        return ""
    return str(value).strip()[:limit]


def tool_text(value: object) -> str:
    """Return a tool description capped at the tool-description ceiling."""
    return text(value, limit=TOOL_CATALOG_TOOL_DESCRIPTION_CHARS)


def mapping(value: object) -> Mapping[str, object]:
    """Return `value` when it is a JSON object, or an empty mapping for anything else."""
    return value if isinstance(value, Mapping) else {}


def items(value: object) -> tuple[object, ...]:
    """Return `value` as a tuple when it is a JSON array, or an empty tuple for anything else."""
    return tuple(value) if isinstance(value, list) else ()


def optional_bool(value: object) -> bool | None:
    """Return a declared boolean hint, or None when the catalog did not declare one."""
    return value if isinstance(value, bool) else None


def schema_from_parameters(parameters: Iterable[object]) -> Mapping[str, object]:
    """Build a JSON Schema object from a flat parameter list shaped like {name, type, description, required}."""
    properties: dict[str, object] = {}
    required: list[str] = []
    for raw in parameters:
        parameter = mapping(raw)
        name = text(parameter.get("name"))
        if not name:
            continue
        properties[name] = {"type": text(parameter.get("type")) or "string", "description": text(parameter.get("desc") or parameter.get("description"))}
        if parameter.get("required") is True:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _with_query(url: str, params: Mapping[str, object] | None) -> str:
    # Appends encoded query parameters, dropping None values so optional filters stay off the wire.
    present = {key: value for key, value in (params or {}).items() if value is not None}
    if not present:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(present)}"


__all__ = [
    "IndexedToolCatalogProvider",
    "ToolCatalogProvider",
    "items",
    "mapping",
    "optional_bool",
    "query_terms",
    "rank_entries",
    "schema_from_parameters",
    "text",
    "tool_text",
]
