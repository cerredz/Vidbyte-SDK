"""FILE: vidbyte/tools/edit_system_prompt_section.py

PURPOSE: Implements edit_system_prompt_section, the single tool the alignment editor uses to add text to the main agent's system prompt.
ROLE IN CODEBASE: JevAgentAlignment registers one instance and binds it to the current pass's JevPromptDraft through a context variable before running its loop.
ARCHITECTURE NOTE: The tool writes only to the run-local draft, never to an agent, a settings object, or the editor's own prompt. JevPromptDraft owns every validation rule.
COMMON MODIFICATION PATTERNS: Keep the input schema in step with JevPromptDraft.add and EDITABLE_SECTIONS.
KNOWN EDGE CASES: Called outside an alignment pass, the tool returns an error instead of editing anything. Refused edits return the repair hint so the model can retry.
RELATED DOCS: docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from vidbyte.lib.dataclasses.jev_alignment import (
    JEV_ALIGNMENT_EDITABLE_SECTIONS,
    JEV_ALIGNMENT_MAX_EDIT_CHARS,
    JevPromptEdit,
)
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

EDIT_TOOL_NAME = "edit_system_prompt_section"


class _PromptDraft(Protocol):
    """Edit surface required by the alignment tool, independent of the agent implementation."""

    def add(self, section: str, content: str, fixes: Collection[str]) -> JevPromptEdit:
        """Validate and record a section edit in the active draft."""

_ACTIVE_DRAFT: ContextVar[_PromptDraft | None] = ContextVar("jev_alignment_active_draft", default=None)

_DESCRIPTION = (
    "Add text to one section of the main agent's system prompt so that it closes one or more listed gaps. "
    "The text is added under the section's heading, and the heading is created at the end of the prompt when it does not exist yet. "
    "Existing prompt text is never replaced or removed, and calling the tool again for the same section replaces only your earlier addition. "
    "Only the sections named in the section enum can be edited; role, scope, boundaries, audience, knowledge, and permissions belong to the developer. "
    "Each call must name the gap questions it closes, and the result tells you whether the edit was accepted or why it was refused."
)


@contextmanager
def bind_prompt_draft(draft: _PromptDraft) -> Iterator[None]:
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
                    "enum": sorted(section.value for section in JEV_ALIGNMENT_EDITABLE_SECTIONS),
                    "description": "The prompt section to add to. Pick the section named on the gap you are closing.",
                },
                "content": {
                    "type": "string",
                    "description": f"The text to add under the section heading, without the heading itself, at most {JEV_ALIGNMENT_MAX_EDIT_CHARS} characters. Write general rules for this kind of request, not rules about this one message.",
                },
                "fixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "The gap question names this edit closes, copied exactly from the gap list, such as alignment.section.output.",
                },
            },
        }


__all__ = ["EDIT_TOOL_NAME", "EditSystemPromptSectionTool", "bind_prompt_draft"]
