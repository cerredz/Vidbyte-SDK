"""FILE: vidbyte/agents/jev/alignment/tool.py

PURPOSE: Implements edit_system_prompt_section, the single tool the alignment editor uses to add text to the main agent's system prompt; the four tool-scout tools that forward to the active tool-alignment pass; and CatalogExecuteTool for catalog tools run through a platform's execute endpoint.
ROLE IN CODEBASE: JevAgentAlignment registers one instance and binds it to the current pass's JevPromptDraft through a context variable before running its loop.
ARCHITECTURE NOTE: The tool writes only to the run-local draft, never to an agent, a settings object, or the editor's own prompt. JevPromptDraft owns every validation rule.
COMMON MODIFICATION PATTERNS: Keep the input schema in step with JevPromptDraft.add and EDITABLE_SECTIONS.
KNOWN EDGE CASES: Called outside an alignment pass, the tool returns an error instead of editing anything. Refused edits return the repair hint so the model can retry. The scout tools hold no rules of their own: JevAgentAlignment's bound handler validates every argument, so the rules cannot drift between tools.
RELATED DOCS: docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import Any, Protocol

from vidbyte.agents.jev.alignment.draft import MAX_EDIT_CHARS, JevPromptDraft
from vidbyte.agents.jev.alignment.questions import EDITABLE_SECTIONS
from vidbyte.lib.dataclasses.tool_catalogs import CatalogTool, ToolCatalogEntry
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.providers.tool_catalogs import ToolCatalogProvider
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

EDIT_TOOL_NAME = "edit_system_prompt_section"

_ACTIVE_DRAFT: ContextVar[JevPromptDraft | None] = ContextVar("jev_alignment_active_draft", default=None)

_DESCRIPTION = (
    "Add text to one section of the main agent's system prompt so that it closes one or more listed gaps. "
    "The text is added under the section's heading, and the heading is created at the end of the prompt when it does not exist yet. "
    "Existing prompt text is never replaced or removed, and calling the tool again for the same section replaces only your earlier addition. "
    "Only the sections named in the section enum can be edited; role, scope, boundaries, audience, knowledge, and permissions belong to the developer. "
    "Each call must name the gap questions it closes, and the result tells you whether the edit was accepted or why it was refused."
)


@contextmanager
def bind_prompt_draft(draft: JevPromptDraft) -> Iterator[None]:
    """Bind the draft the edit tool writes to for the duration of one editor run."""
    token = _ACTIVE_DRAFT.set(draft)
    try:
        yield
    finally:
        _ACTIVE_DRAFT.reset(token)


class EditSystemPromptSectionTool(BaseTool):
    """Adds validated text to one editable section of the active alignment draft."""

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration with a closed section enum."""
        return ToolSpec(
            name=EDIT_TOOL_NAME,
            description=_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Record one edit on the active draft, or return the reason it was refused."""
        draft = _ACTIVE_DRAFT.get()
        if draft is None:
            return ToolResult.error(EDIT_TOOL_NAME, "No alignment pass is active, so there is no system prompt to edit.")
        arguments = call.arguments
        fixes = arguments.get("fixes") or ()
        if isinstance(fixes, str):
            fixes = (fixes,)
        try:
            edit = draft.add(str(arguments.get("section", "")), str(arguments.get("content", "")), tuple(fixes))
        except ValueError as exc:
            return ToolResult.error(EDIT_TOOL_NAME, f"Edit refused: {exc}")
        return ToolResult.success(
            EDIT_TOOL_NAME,
            f"Added {len(edit.content)} characters to the {edit.section.heading} section, closing {', '.join(edit.fixes)}.",
            metadata={"section": edit.section.value, "fixes": edit.fixes},
        )

    def _input_schema(self) -> dict[str, Any]:
        # Declares the closed section enum so the model cannot name an owner-only section by accident.
        return {
            "type": "object",
            "required": ["section", "content", "fixes"],
            "additionalProperties": False,
            "properties": {
                "section": {
                    "type": "string",
                    "enum": sorted(section.value for section in EDITABLE_SECTIONS),
                    "description": "The prompt section to add to. Pick the section named on the gap you are closing.",
                },
                "content": {
                    "type": "string",
                    "description": f"The text to add under the section heading, without the heading itself, at most {MAX_EDIT_CHARS} characters. Write general rules for this kind of request, not rules about this one message.",
                },
                "fixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "The gap question names this edit closes, copied exactly from the gap list, such as alignment.section.output.",
                },
            },
        }


class JevToolScoutAction(StrEnum):
    """The four actions the tool scout can take; JevAgentAlignment implements each one."""

    WRITE_NEEDS = "write_tool_needs"
    SEARCH = "search_tool_catalogs"
    DESCRIBE = "describe_catalog_entry"
    PROPOSE = "propose_tool_candidates"


class JevToolScoutHandler(Protocol):
    """The callable a tool-alignment pass binds for the scout's tools: one scout action in, one tool result out."""

    async def __call__(self, action: JevToolScoutAction, arguments: Mapping[str, Any]) -> ToolResult:
        """Run one scout action against the active pass."""


_ACTIVE_SCOUT: ContextVar[JevToolScoutHandler | None] = ContextVar("jev_tool_alignment_active_scout", default=None)

_SCOUT_DESCRIPTIONS: Mapping[JevToolScoutAction, str] = {
    JevToolScoutAction.WRITE_NEEDS: (
        "Write down the outside actions the user's request requires, as one to three needs. "
        "An outside action is work that reaches a system beyond the conversation, such as reading or changing data in another product, fetching live data, sending a message, or running code. "
        "Each need is an action verb, the object it acts on, and the named product or service only when the user named one. "
        "Call this once; a second call replaces the first."
    ),
    JevToolScoutAction.SEARCH: (
        "Search every configured public tool catalog for servers or toolkits that could perform one uncovered need. "
        "Use a short query of one to three words, product name first when the user named a product, such as 'linear' or 'pdf text'. "
        "The result lists matching entries by key with their install kinds and any tool names the catalog already knows. "
        "Each pass allows only a few searches, so search for the need, not for synonyms of it."
    ),
    JevToolScoutAction.DESCRIBE: (
        "Read one catalog entry in full: its description, how it can be installed, the secrets it needs, and each tool's name and description. "
        "Pass an entry key exactly as search_tool_catalogs returned it. "
        "You must describe an entry before you propose any of its tools. "
        "Entries with a remote or managed install may be connected briefly to read their live tool list; no tool is called."
    ),
    JevToolScoutAction.PROPOSE: (
        "Propose tools from one described entry for one uncovered need. "
        "Name the need id, the entry key, and one to five tool names copied exactly from describe_catalog_entry. "
        "Propose only tools that perform the need itself; a separate check reads each tool's description against the user's request and may reject it. "
        "You may propose up to three entries per need, best first."
    ),
}

_SCOUT_SCHEMAS: Mapping[JevToolScoutAction, Mapping[str, Any]] = {
    JevToolScoutAction.WRITE_NEEDS: {
        "type": "object",
        "required": ["needs"],
        "additionalProperties": False,
        "properties": {
            "needs": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["action", "object"],
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "description": "One verb for the outside action, such as create, read, search, send, convert."},
                        "object": {"type": "string", "description": "What the action is done to, such as issue, calendar event, web page, PDF file."},
                        "system": {"type": "string", "description": "The product or service, only when the user named one, such as Linear or Gmail; otherwise leave it out."},
                    },
                },
            }
        },
    },
    JevToolScoutAction.SEARCH: {
        "type": "object",
        "required": ["need_id", "query"],
        "additionalProperties": False,
        "properties": {
            "need_id": {"type": "string", "description": "The id of the uncovered need this search is for, such as need_1."},
            "query": {"type": "string", "description": "One to three words, product name first when the user named a product."},
        },
    },
    JevToolScoutAction.DESCRIBE: {
        "type": "object",
        "required": ["entry_key"],
        "additionalProperties": False,
        "properties": {"entry_key": {"type": "string", "description": "An entry key exactly as search_tool_catalogs returned it, such as mcp_registry:app.linear/linear."}},
    },
    JevToolScoutAction.PROPOSE: {
        "type": "object",
        "required": ["need_id", "entry_key", "tool_names"],
        "additionalProperties": False,
        "properties": {
            "need_id": {"type": "string", "description": "The id of the uncovered need these tools perform."},
            "entry_key": {"type": "string", "description": "The key of an entry you described with describe_catalog_entry."},
            "tool_names": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {"type": "string"},
                "description": "Tool names copied exactly from describe_catalog_entry.",
            },
        },
    },
}


@contextmanager
def bind_tool_scout(handler: JevToolScoutHandler) -> Iterator[None]:
    """Bind the handler the scout's tools call for the duration of one tool-alignment pass."""
    token = _ACTIVE_SCOUT.set(handler)
    try:
        yield
    finally:
        _ACTIVE_SCOUT.reset(token)


class JevToolScoutTool(BaseTool):
    """One scout tool; it validates nothing itself and forwards to the active pass's handler, where every rule lives."""

    def __init__(self, action: JevToolScoutAction) -> None:
        # Fixes which scout action this tool performs.
        self.action = action

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this scout action."""
        return ToolSpec(
            name=self.action.value,
            description=_SCOUT_DESCRIPTIONS[self.action],
            permission=ToolPermission.SAFE,
            input_schema=_SCOUT_SCHEMAS[self.action],
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Forward the call to the active tool-alignment pass, or refuse outside one."""
        handler = _ACTIVE_SCOUT.get()
        if handler is None:
            return ToolResult.error(self.action.value, "No tool-alignment pass is active, so there is nothing to search or propose.")
        return await handler(self.action, call.arguments)


class CatalogExecuteTool(BaseTool):
    """A catalog tool run through its platform's execute endpoint (Arcade) instead of an MCP session."""

    def __init__(self, provider: ToolCatalogProvider, entry: ToolCatalogEntry, tool: CatalogTool, *, exposed_name: str, permission: ToolPermission, user_id: str | None) -> None:
        # Keeps the exact tool Jev judged, the name the model calls it by, and the end user it runs for.
        # @intent execute-tool-keeps-judged-identity
        # The provider, entry, and tool are fixed at construction, so the tool that runs is the one Jev approved,
        # under the permission its judged effect earned.
        self.provider = provider
        self.entry = entry
        self.tool = tool
        self.exposed_name = exposed_name
        self.permission = permission
        self.user_id = user_id

    def spec(self) -> ToolSpec:
        """Return the catalog tool's own description and input schema under its exposed name."""
        return ToolSpec(
            name=self.exposed_name,
            description=self.tool.description,
            permission=self.permission,
            input_schema=dict(self.tool.input_schema),
            metadata={"source": self.provider.name.value, "catalog_tool": self.tool.name},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the tool on the platform and return its output, or the platform's safe error message."""
        # @intent catalog-tool-runs-on-its-platform
        # The platform runs the tool for the configured end user; its failure is returned as a tool error, never raised.
        try:
            output, is_error = await self.provider.execute(self.entry, self.tool, call.arguments, user_id=self.user_id)
        except VidbyteSdkError as exc:
            return ToolResult.error(self.exposed_name, f"The {self.provider.name.value} tool failed: {exc.message}")
        if is_error:
            return ToolResult.error(self.exposed_name, output)
        return ToolResult.success(self.exposed_name, output)


__all__ = [
    "EDIT_TOOL_NAME",
    "CatalogExecuteTool",
    "EditSystemPromptSectionTool",
    "JevToolScoutAction",
    "JevToolScoutHandler",
    "JevToolScoutTool",
    "bind_prompt_draft",
    "bind_tool_scout",
]
