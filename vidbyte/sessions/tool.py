"""Context Protocol Header

Description:
    Agent-facing tool for operating on durable sessions.
Purpose:
    Lets an agent checkpoint, fork, list, and read its own runs through a
    permission-gated tool — the foundation for subagent checkpoint/return flows.
Architecture:
    - SessionScope: allowlist deciding which sessions the tool may read.
    - SessionTool: BaseTool routing model-issued session operations.
Relations:
    Uses vidbyte.sessions.store.SessionStore and binds to a Session at runtime.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec
from vidbyte.sessions.store import SessionStore

if TYPE_CHECKING:
    from vidbyte.sessions.session import Session

_TOOL_NAME = "session"


class SessionScope:
    """Decides which session ids a SessionTool is permitted to read."""

    def __init__(self, *, allow_ids: Sequence[str] = (), all_runs: bool = False) -> None:
        # Hold an allowlist (which can grow) and an all-runs override.
        self._allow_ids: set[str] = set(allow_ids)
        self._all_runs = all_runs

    @staticmethod
    def own_runs() -> "SessionScope":
        # Scope limited to sessions this tool creates or is bound to.
        return SessionScope()

    @staticmethod
    def sessions(ids: Sequence[str]) -> "SessionScope":
        # Scope limited to a fixed set of session ids.
        return SessionScope(allow_ids=ids)

    @staticmethod
    def all_runs() -> "SessionScope":
        # Unrestricted scope (use with caution; bypasses isolation).
        return SessionScope(all_runs=True)

    def allow(self, session_id: str) -> None:
        # Add a session id to the allowlist.
        self._allow_ids.add(session_id)

    def permits(self, session_id: str) -> bool:
        # Report whether reads of a session id are allowed.
        return self._all_runs or session_id in self._allow_ids

    def allowed_ids(self) -> set[str]:
        # Return the current allowlist snapshot.
        return set(self._allow_ids)


class SessionTool(BaseTool):
    """Permission-gated tool exposing session operations to an agent."""

    def __init__(self, store: SessionStore, *, scope: SessionScope | None = None) -> None:
        # Bind the store, scope, and an optional active session.
        self._store = store
        self._scope = scope or SessionScope.own_runs()
        self._session: "Session | None" = None

    def bind_session(self, session: "Session") -> None:
        # Attach the active session and grant it scope access.
        self._session = session
        self._scope.allow(session.id)

    def spec(self) -> ToolSpec:
        # Declare the model-facing session operations and arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description="Operate on durable agent sessions: create_checkpoint, fork_current, list_my_runs, read_run.",
            parameters=(
                ToolParameter(name="operation", type="string", description="One of create_checkpoint, fork_current, list_my_runs, read_run."),
                ToolParameter(name="session_id", type="string", description="Target session id for read_run.", required=False),
                ToolParameter(name="label", type="string", description="Optional checkpoint label.", required=False),
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
        if self._session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        checkpoint_id = self._session.checkpoint(label=str(arguments.get("label", "")))
        return ToolResult.success(_TOOL_NAME, checkpoint_id)

    def _fork_current(self, arguments: dict[str, Any]) -> ToolResult:
        # Fork the bound session and grant the new session scope access.
        if self._session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        branch = self._session.fork()
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
        if not self._scope.permits(session_id):
            return ToolResult.error(_TOOL_NAME, f"Access denied for session: {session_id}.")
        head = self._store.head(session_id)
        if head is None:
            return ToolResult.error(_TOOL_NAME, f"Unknown or empty session: {session_id}.")
        return ToolResult.success(_TOOL_NAME, json.dumps(dict(head.trace_artifact or {})))


__all__ = ["SessionScope", "SessionTool"]
