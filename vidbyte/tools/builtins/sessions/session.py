"""Context Protocol Header

Description:
    Central combined agent-facing tool for operating on durable sessions.
Purpose:
    Lets an agent checkpoint, fork, list, and read its own (or in-scope) runs
    through one permission-gated tool. This is the relocated form of the original
    vidbyte/sessions/tool.py SessionTool, now living with the other session
    builtins so every agent-facing session tool shares one home.
Architecture:
    - SessionTool: _SessionBuiltinTool routing model-issued session operations.
Relations:
    Reuses vidbyte.sessions.scope.SessionScope and vidbyte.sessions.store.SessionStore
    via _SessionBuiltinTool. Sits alongside the granular Checkpoint/Fork/Rewind/Resume* tools.
"""

from __future__ import annotations

import json
from typing import Any

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.descriptions import (
    LABEL_DESCRIPTION,
    OPERATION_DESCRIPTION,
    SESSION_ID_DESCRIPTION,
    SESSION_TOOL_DESCRIPTION,
)
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

_TOOL_NAME = "session"


class SessionTool(_SessionBuiltinTool):
    """Permission-gated tool exposing the combined session operations to an agent."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing session operations and arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=SESSION_TOOL_DESCRIPTION,
            parameters=(
                ToolParameter(name="operation", type="string", description=OPERATION_DESCRIPTION),
                ToolParameter(name="session_id", type="string", description=SESSION_ID_DESCRIPTION, required=False),
                ToolParameter(name="label", type="string", description=LABEL_DESCRIPTION, required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route a validated session operation to its handler.
        operation = str(call.arguments.get("operation", "")).strip()
        handlers = {
            "create_checkpoint": self._create_checkpoint,
            "fork_current": self._fork_current,
            "list_my_runs": self._list_my_runs,
            "read_run": self._read_run,
        }
        handler = handlers.get(operation)
        if handler is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown session operation: {operation or '(none)'}.")
        return handler(call.arguments)

    def _create_checkpoint(self, arguments: dict[str, Any]) -> ToolResult:
        # Write a checkpoint of the bound session and return its id.
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        checkpoint_id = session.checkpoint(label=str(arguments.get("label", "")))
        return ToolResult.success(_TOOL_NAME, checkpoint_id)

    def _fork_current(self, arguments: dict[str, Any]) -> ToolResult:
        # Fork the bound session and grant the new session scope access.
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        branch = session.fork()
        self._scope.allow(branch.id)
        return ToolResult.success(_TOOL_NAME, branch.id)

    def _list_my_runs(self, arguments: dict[str, Any]) -> ToolResult:
        # List session ids visible within the current scope.
        ids = [meta.session_id for meta in self._store.list_sessions() if self._scope.permits(meta.session_id)]
        return ToolResult.success(_TOOL_NAME, json.dumps(ids))

    def _read_run(self, arguments: dict[str, Any]) -> ToolResult:
        # Return a session's trace artifact, gated by scope and existence.
        session_id = str(arguments.get("session_id", "")).strip()
        if not session_id:
            return ToolResult.error(_TOOL_NAME, "read_run requires a session_id.")
        resolved_session_id = self._resolve_session_id(session_id)
        if not self._scope.permits(resolved_session_id):
            return self._denied(_TOOL_NAME, session_id)
        head = self._store.head(resolved_session_id)
        if head is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        return ToolResult.success(_TOOL_NAME, json.dumps(dict(head.trace_artifact or {})))


__all__ = ["SessionTool"]
