"""Context Protocol Header

Description:
    Access-control scope for cross-session reads and operations.
Purpose:
    Decides which session ids a session tool (or any scope-gated caller) is
    permitted to read, fork, or resume. Defaults to the caller's own runs so an
    agent cannot silently read another agent's session without explicit consent.
Architecture:
    - SessionScope: allowlist with an all-runs override; grows via allow().
Relations:
    Used by the builtin session tools in vidbyte.tools.builtins.sessions and by
    the relocated SessionTool. Re-exported from vidbyte.sessions.
"""

from __future__ import annotations

from collections.abc import Sequence


class SessionScope:
    """Decides which session ids a caller is permitted to read or operate on."""

    def __init__(self, *, allow_ids: Sequence[str] = (), all_runs: bool = False) -> None:
        # Hold an allowlist (which can grow) and an all-runs override.
        self._allow_ids: set[str] = set(allow_ids)
        self._all_runs = all_runs

    @staticmethod
    def own_runs() -> "SessionScope":
        # Scope limited to sessions this caller creates or is bound to.
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
        # Report whether operations on a session id are allowed.
        return self._all_runs or session_id in self._allow_ids

    def allowed_ids(self) -> set[str]:
        # Return the current allowlist snapshot.
        return set(self._allow_ids)


__all__ = ["SessionScope"]
