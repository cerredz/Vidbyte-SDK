"""Context Protocol Header

Description:
    Shared base for the agent-facing session builtin tools.
Purpose:
    Holds the store, scope, and bound-session wiring that every session builtin
    needs, so each granular tool only declares its spec and operation behavior.
Architecture:
    - _SessionBuiltinTool: BaseTool with store + SessionScope + optional bound Session.
Relations:
    Subclassed by CheckpointTool, ForkTool, RewindTool, ResumeReplaceTool,
    ResumeAppendTool, ResumeOutputTool, and the relocated SessionTool.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.sessions.errors import SessionError
from vidbyte.sessions.scope import SessionScope
from vidbyte.sessions.store import SessionStore
from vidbyte.tools.types import ToolResult

if TYPE_CHECKING:
    from vidbyte.sessions.session import Session


class _SessionBuiltinTool(BaseTool):
    """Common store/scope/binding state for session builtin tools."""

    def __init__(self, store: SessionStore, *, scope: SessionScope | None = None) -> None:
        # Bind the store, scope (default own runs), and an unset active session.
        self._store = store
        self._scope = scope or SessionScope.own_runs()
        self._session: "Session | None" = None

    def bind_session(self, session: "Session") -> None:
        # Attach the active session and grant it scope access.
        self._session = session
        self._scope.allow(session.id)

    def _denied(self, name: str, session_id: str) -> ToolResult:
        # Return a denied result for an out-of-scope session id.
        return ToolResult.error(name, f"Access denied for session: {session_id}.")

    def _require_bound(self, name: str) -> "Session | None":
        # Return the bound session, or None when no session is attached (caller returns an error result).
        if self._session is None:
            return None
        return self._session

    def _caught(self, name: str, operation: "Callable[[], ToolResult]") -> ToolResult:
        # Run an operation, converting session errors into error results so the tool never raises.
        try:
            return operation()
        except SessionError as exc:
            return ToolResult.error(name, f"{type(exc).__name__}: {exc}")


__all__ = ["_SessionBuiltinTool"]
