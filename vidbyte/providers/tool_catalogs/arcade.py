"""FILE: vidbyte/providers/tool_catalogs/arcade.py

PURPOSE: Adapts Arcade's tool API: search returns toolkits with their matching tools and declared behavior, and execute() runs one tool for one end user through `POST /v1/tools/execute`.
ROLE IN CODEBASE: ToolCatalogs builds ArcadeCatalog for ToolCatalogName.ARCADE when the owner supplies an API key; JevAgentAlignment judges the tools from search and bridges approved ones as tools that call execute().
ARCHITECTURE NOTE: Arcade exposes MCP only through owner-created gateways, so this adapter uses the direct execute endpoint instead (executes_directly=True); the tool that runs is the fully qualified name that was judged.
COMMON MODIFICATION PATTERNS: Map a new `val_type` in _JSON_TYPES; extend execute() only with fields the Arcade API reference documents.
KNOWN EDGE CASES: `search` is a literal substring match where every word must appear, so the adapter also searches word by word and merges the results. A tool that needs authorization the end user has not granted returns Arcade's authorization URL as an error, and the main model relays it. Execute POSTs are never retried.
RELATED DOCS: https://docs.arcade.dev/en/references/api (OpenAPI at https://api.arcade.dev/v1/swagger) and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import ClassVar

from vidbyte.lib.constants.tool_catalogs import ARCADE_API_BASE_URL
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogEntry,
    ToolInstall,
)
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ProviderConfigurationError
from vidbyte.providers.tool_catalogs.base import (
    ToolCatalogProvider,
    items,
    mapping,
    optional_bool,
    query_terms,
    text,
    tool_text,
)

ARCADE_MAX_TERM_SEARCHES = 3
ARCADE_OUTPUT_CHARS = 8_000
_JSON_TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean", "array": "array", "json": "object"}


class ArcadeCatalog(ToolCatalogProvider):
    """Arcade's managed toolkits, run for one end user through the execute endpoint."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.ARCADE
    executes_directly: ClassVar[bool] = True
    base_url: ClassVar[str] = ARCADE_API_BASE_URL

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Search tools by the whole query and by its words, grouped into one entry per toolkit."""
        found: dict[str, Mapping[str, object]] = {}
        for term in (query, *sorted(query_terms(query), key=len, reverse=True)[:ARCADE_MAX_TERM_SEARCHES]):
            payload = await self.get_json(f"{self.base_url}/v1/tools", params={"search": term, "limit": limit}, headers=self._headers())
            for raw in items(mapping(payload).get("items")):
                tool = mapping(raw)
                qualified = text(tool.get("fully_qualified_name") or tool.get("qualified_name"))
                if qualified:
                    found.setdefault(qualified, tool)
        grouped: dict[str, list[CatalogTool]] = {}
        toolkits: dict[str, Mapping[str, object]] = {}
        for qualified, tool in found.items():
            toolkit = mapping(tool.get("toolkit"))
            toolkit_name = text(toolkit.get("name"))
            if not toolkit_name:
                continue
            toolkits.setdefault(toolkit_name, toolkit)
            grouped.setdefault(toolkit_name, []).append(_catalog_tool(qualified, tool))
        return tuple(_entry(self.name, name, toolkits[name], tuple(tools)) for name, tools in list(grouped.items())[:limit])

    async def execute(self, entry: ToolCatalogEntry, tool: CatalogTool, arguments: Mapping[str, object], *, user_id: str | None) -> tuple[str, bool]:
        """Run one tool for `user_id` and return its output as text, flagging Arcade-reported failures."""
        # @intent arcade-executes-the-judged-tool-for-one-user
        # The fully qualified name that Jev judged is the one executed, always on behalf of the configured end user.
        del entry
        if not user_id:
            raise ProviderConfigurationError("Arcade runs tools for an end user; set JevToolAlignmentSettings.user_id.", provider=self.name.value)
        body = {"tool_name": tool.name, "input": dict(arguments), "user_id": user_id}
        payload = mapping(await self.send_json("POST", f"{self.base_url}/v1/tools/execute", body, headers=self._headers()))
        output = mapping(payload.get("output"))
        error = mapping(output.get("error"))
        authorization = mapping(output.get("authorization"))
        if error:
            return text(error.get("message"), limit=ARCADE_OUTPUT_CHARS) or "The Arcade tool failed.", True
        if authorization and text(authorization.get("url")):
            return f"The user must authorize this tool first: {text(authorization.get('url'), limit=ARCADE_OUTPUT_CHARS)}", True
        value = output.get("value")
        rendered = value if isinstance(value, str) else json.dumps(value, default=str)
        return rendered[:ARCADE_OUTPUT_CHARS], payload.get("success") is False

    def _headers(self) -> Mapping[str, str]:
        # Arcade authenticates with a bearer API key on every call.
        return {"Authorization": f"Bearer {self.require_credentials('api_key').api_key}"}


def _entry(catalog: ToolCatalogName, toolkit_name: str, toolkit: Mapping[str, object], tools: tuple[CatalogTool, ...]) -> ToolCatalogEntry:
    # Builds one toolkit entry whose install is the Arcade execute endpoint.
    return ToolCatalogEntry(
        catalog=catalog,
        entry_id=toolkit_name,
        name=toolkit_name,
        description=text(toolkit.get("description")) or f"Arcade {toolkit_name} toolkit, run with the end user's authorization.",
        installs=(ToolInstall(kind=ToolInstallKind.MANAGED, reference=toolkit_name),),
        tools=tools,
        version=text(toolkit.get("version")) or None,
        publisher="arcade",
        verified=True,
    )


def _catalog_tool(qualified_name: str, tool: Mapping[str, object]) -> CatalogTool:
    # Converts one Arcade tool, building a JSON Schema from its parameter list and reading its declared behavior.
    behavior = mapping(mapping(tool.get("metadata")).get("behavior"))
    return CatalogTool(
        name=qualified_name,
        description=tool_text(tool.get("description")),
        input_schema=_input_schema(items(mapping(tool.get("input")).get("parameters"))),
        read_only=optional_bool(behavior.get("read_only")),
        destructive=optional_bool(behavior.get("destructive")),
    )


def _input_schema(parameters: tuple[object, ...]) -> Mapping[str, object]:
    # Translates Arcade parameters ({name, required, description, value_schema.val_type}) into a JSON Schema object.
    properties: dict[str, object] = {}
    required: list[str] = []
    for raw in parameters:
        parameter = mapping(raw)
        name = text(parameter.get("name"))
        if not name:
            continue
        value_schema = mapping(parameter.get("value_schema"))
        prop: dict[str, object] = {"type": _JSON_TYPES.get(text(value_schema.get("val_type")), "string"), "description": text(parameter.get("description") or value_schema.get("description"))}
        enum = [text(value) for value in items(value_schema.get("enum"))]
        if enum:
            prop["enum"] = enum
        properties[name] = prop
        if parameter.get("required") is True:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


__all__ = ["ArcadeCatalog"]
