"""Context Protocol Header

Description:
    Prebuilt tool that resumes a thread by APPENDING only its final output.
Purpose:
    Lets an agent pull just the final assistant output of another agent's thread
    into its own context window, framed as a <resumed_output> block. The target
    session MUST be completed; an unfinished thread raises an error so the agent
    does not silently incorporate partial work.
Architecture:
    - ResumeOutputTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.append_output(), which checks SessionStatus.COMPLETED. Differs
    from ResumeReplaceTool (overrides the whole context) and ResumeAppendTool
    (appends the whole other thread's history, not just its final output).
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.sessions.descriptions import RESUME_OUTPUT_TOOL_DESCRIPTION, SESSION_ID_DESCRIPTION
from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "resume_output"


class ResumeOutputTool(_SessionBuiltinTool):
    """Builtin tool that appends another thread's final output to the current context."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing resume-output operation and its required argument.
        return ToolSpec(
            name=_TOOL_NAME,
            description=RESUME_OUTPUT_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["session_id"],
                "properties": {
                    "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route the call to the append-output path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Validate scope and append the target session's final output to the bound session.
        session_id = str(arguments.get("session_id", "")).strip()
        if not session_id:
            return ToolResult.error(_TOOL_NAME, "resume_output requires a session_id.")
        if not self._scope.permits(session_id):
            return self._denied(_TOOL_NAME, session_id)
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        new_head = session.append_output(session_id)
        return ToolResult.success(_TOOL_NAME, new_head)


__all__ = ["ResumeOutputTool"]
