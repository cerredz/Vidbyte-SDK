"""Context Protocol Header

Description:
    Prebuilt tool that resumes a thread by REPLACING the current context window.
Purpose:
    Lets an agent continue another agent's thread by completely overriding its
    own context window with that thread's checkpointed history, then persisting
    the result as a new checkpoint on the bound session. For the agent's own
    thread, this is equivalent to rewind (time-travel to an earlier checkpoint).
Architecture:
    - ResumeReplaceTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.rewind() for own-thread and Session.adopt() for cross-thread.
    Differs from ResumeAppendTool (which keeps the current context and appends the
    other thread) and ResumeOutputTool (which appends only the other thread's final
    output, and errors if that thread is not completed).
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.sessions.descriptions import CHECKPOINT_ID_DESCRIPTION, RESUME_REPLACE_TOOL_DESCRIPTION, SESSION_ID_DESCRIPTION
from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "resume_replace"


class ResumeReplaceTool(_SessionBuiltinTool):
    """Builtin tool that overrides the current context with a resumed thread's state."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing resume-replace operation and its arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=RESUME_REPLACE_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
                    "checkpoint_id": {"type": "string", "description": CHECKPOINT_ID_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route the call to the own-thread or cross-thread replace path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Decide own-thread rewind vs cross-thread adopt and dispatch.
        session_id = str(arguments.get("session_id", "")).strip()
        checkpoint_id = str(arguments.get("checkpoint_id", "")).strip() or None
        if not session_id or (self._session is not None and session_id == self._session.id):
            return self._replace_own(checkpoint_id)
        resolved_session_id = self._resolve_session_id(session_id)
        if self._session is not None and resolved_session_id == self._session.id:
            return self._replace_own(checkpoint_id)
        if not self._scope.permits(resolved_session_id):
            return self._denied(_TOOL_NAME, session_id)
        return self._replace_other(resolved_session_id, checkpoint_id)

    def _replace_own(self, checkpoint_id: str | None) -> ToolResult:
        # Rewind the bound session to the named checkpoint (own-thread time-travel).
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        if checkpoint_id is None:
            return ToolResult.error(_TOOL_NAME, "resume_replace on the current thread requires a checkpoint_id.")
        session.rewind(to=checkpoint_id)
        return ToolResult.success(_TOOL_NAME, session.head or checkpoint_id)

    def _replace_other(self, session_id: str, checkpoint_id: str | None) -> ToolResult:
        # Adopt the target session's checkpoint (or its head) into the bound session, replacing history.
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        target = checkpoint_id or self._target_head_id(session_id)
        if target is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        new_head = session.adopt(target)
        return ToolResult.success(_TOOL_NAME, new_head)

    def _target_head_id(self, session_id: str) -> str | None:
        # Return the target session's head checkpoint id, or None when empty.
        head = self._store.head(session_id)
        return head.id if head is not None else None


__all__ = ["ResumeReplaceTool"]
