"""Context Protocol Header

Description:
    Prebuilt tool that resumes a thread by APPENDING its context window into the current one.
Purpose:
    Lets an agent incorporate another agent's full thread into its own context
    window without losing its own history. The other thread's history is rendered
    as a single framed <resumed_thread> block and appended to the bound agent's
    history, then persisted as a new checkpoint on the bound session.
Architecture:
    - ResumeAppendTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.append_context(). Differs from ResumeReplaceTool (which overrides
    the current context entirely) and ResumeOutputTool (which appends only the
    other thread's final output, and errors if that thread is not completed).
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.descriptions import (
    CHECKPOINT_ID_DESCRIPTION,
    RESUME_APPEND_TOOL_DESCRIPTION,
    SESSION_ID_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "resume_append"


class ResumeAppendTool(_SessionBuiltinTool):
    """Builtin tool that appends another thread's context window into the current one."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing resume-append operation and its arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=RESUME_APPEND_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["session_id"],
                "properties": {
                    "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
                    "checkpoint_id": {"type": "string", "description": CHECKPOINT_ID_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route the call to the append path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Validate scope, resolve the target checkpoint, and append its context to the bound session.
        session_id = str(arguments.get("session_id", "")).strip()
        checkpoint_id = str(arguments.get("checkpoint_id", "")).strip() or None
        if not session_id:
            return ToolResult.error(_TOOL_NAME, "resume_append requires a session_id.")
        resolved_session_id = self._resolve_session_id(session_id)
        if not self._scope.permits(resolved_session_id):
            return self._denied(_TOOL_NAME, session_id)
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        target = checkpoint_id or self._target_head_id(resolved_session_id)
        if target is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        new_head = session.append_context(target)
        return ToolResult.success(_TOOL_NAME, new_head)

    def _target_head_id(self, session_id: str) -> str | None:
        # Return the target session's head checkpoint id, or None when empty.
        head = self._store.head(session_id)
        return head.id if head is not None else None


__all__ = ["ResumeAppendTool"]
