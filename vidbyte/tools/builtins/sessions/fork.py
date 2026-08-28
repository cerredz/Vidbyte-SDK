"""Context Protocol Header

Description:
    Prebuilt tool that branches a new session from a checkpoint.
Purpose:
    Lets an agent fork its own current thread (from head) or, when scope permits,
    fork another agent's thread from any checkpoint. The fork records parent
    lineage and never mutates the source session's stored state.
Architecture:
    - ForkTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.fork() for the bound thread and Session.fork_from() for a
    cross-thread fork. Sibling tools: CheckpointTool, RewindTool, Resume*Tool.
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.descriptions import (
    CHECKPOINT_ID_DESCRIPTION,
    FORK_TOOL_DESCRIPTION,
    SESSION_ID_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "fork"


class ForkTool(_SessionBuiltinTool):
    """Builtin tool that forks a new session from a checkpoint."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing fork operation and its arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=FORK_TOOL_DESCRIPTION,
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
        # Route the call to the bound or cross-thread fork path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Resolve the source checkpoint and branch a new session from it.
        checkpoint_id = str(arguments.get("checkpoint_id", "")).strip() or None
        session_id = str(arguments.get("session_id", "")).strip()
        if not session_id:
            return self._fork_bound(checkpoint_id)
        resolved_session_id = self._resolve_session_id(session_id)
        if not self._scope.permits(resolved_session_id):
            return self._denied(_TOOL_NAME, session_id)
        return self._fork_other(resolved_session_id, checkpoint_id)

    def _fork_bound(self, checkpoint_id: str | None) -> ToolResult:
        # Fork the bound session from its head (or a named in-session checkpoint).
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        branch = session.fork(at=checkpoint_id)
        self._scope.allow(branch.id)
        return ToolResult.success(_TOOL_NAME, branch.id)

    def _fork_other(self, session_id: str, checkpoint_id: str | None) -> ToolResult:
        # Fork another session's checkpoint (or its head) into a new session via Session.fork_from.
        source_id = checkpoint_id or self._target_head_id(session_id)
        if source_id is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        from vidbyte.sessions.session import Session
        branch = Session.fork_from(self._store, source_id)
        self._scope.allow(branch.id)
        return ToolResult.success(_TOOL_NAME, branch.id)

    def _target_head_id(self, session_id: str) -> str | None:
        # Return the target session's head checkpoint id, or None when empty.
        head = self._store.head(session_id)
        return head.id if head is not None else None


__all__ = ["ForkTool"]
