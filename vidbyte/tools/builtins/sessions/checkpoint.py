"""Context Protocol Header

Description:
    Prebuilt tool that writes a checkpoint of an agent's session.
Purpose:
    Lets an agent snapshot its own current thread or, when scope permits, mark a
    labeled checkpoint on another agent's session by copying that session's head
    state. The agent-supplied label is persisted on the new checkpoint so later
    fork/resume calls can name it.
Architecture:
    - CheckpointTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.checkpoint() for the bound thread and a direct store put for an
    in-scope other thread. Sibling tools: ForkTool, RewindTool, Resume*Tool.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from vidbyte.sessions.contracts import Checkpoint, SessionStatus
from vidbyte.tools.builtins.sessions.descriptions import CHECKPOINT_TOOL_DESCRIPTION, LABEL_DESCRIPTION, SESSION_ID_DESCRIPTION
from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "checkpoint"


class CheckpointTool(_SessionBuiltinTool):
    """Builtin tool that writes a labeled checkpoint of a session."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing checkpoint operation and its arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=CHECKPOINT_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
                    "label": {"type": "string", "description": LABEL_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route the call to the bound or cross-thread checkpoint path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Resolve the target session and write a labeled checkpoint on it.
        label = str(arguments.get("label", ""))
        session_id = str(arguments.get("session_id", "")).strip()
        if not session_id:
            return self._checkpoint_bound(label)
        if not self._scope.permits(session_id):
            return self._denied(_TOOL_NAME, session_id)
        return self._checkpoint_other(session_id, label)

    def _checkpoint_bound(self, label: str) -> ToolResult:
        # Snapshot the bound session via Session.checkpoint().
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        return ToolResult.success(_TOOL_NAME, session.checkpoint(label=label))

    def _checkpoint_other(self, session_id: str, label: str) -> ToolResult:
        # Copy the target session's head state into a new labeled checkpoint on that session.
        head = self._store.head(session_id)
        if head is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        marker = Checkpoint(
            id=f"ck_{uuid4().hex}",
            session_id=session_id,
            parent_id=head.id,
            seq=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            run_state=head.run_state,
            label=label,
            status=SessionStatus.ACTIVE,
        )
        stored = self._store.put(marker)
        return ToolResult.success(_TOOL_NAME, stored.id)


__all__ = ["CheckpointTool"]
