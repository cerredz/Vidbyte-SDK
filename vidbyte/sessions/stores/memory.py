"""Context Protocol Header

Description:
    In-memory implementation of the session store.
Purpose:
    Provides the default zero-config backend for tests and ephemeral sessions.
Architecture:
    - InMemorySessionStore: dict-backed BaseSessionStore.
Relations:
    Implements vidbyte.sessions.store.BaseSessionStore.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sessions import Checkpoint, SessionMeta
from vidbyte.sessions.store import BaseSessionStore


class InMemorySessionStore(BaseSessionStore):
    """Process-local session store backed by plain dictionaries."""

    def __init__(self) -> None:
        # Initialize empty checkpoint and metadata maps.
        self._checkpoints: dict[str, Checkpoint] = {}
        self._meta: dict[str, SessionMeta] = {}

    def _write_checkpoint(self, checkpoint: Checkpoint) -> None:
        # Store a checkpoint by id.
        self._checkpoints[checkpoint.id] = checkpoint

    def _read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        # Return a checkpoint by id, or None.
        return self._checkpoints.get(checkpoint_id)

    def _read_session_checkpoints(self, session_id: str) -> list[Checkpoint]:
        # Return all checkpoints belonging to a session.
        return [c for c in self._checkpoints.values() if c.session_id == session_id]

    def _delete_checkpoint(self, checkpoint_id: str) -> None:
        # Remove a checkpoint by id if present.
        self._checkpoints.pop(checkpoint_id, None)

    def _write_meta(self, meta: SessionMeta) -> None:
        # Store session metadata by session id.
        self._meta[meta.session_id] = meta

    def _read_meta(self, session_id: str) -> SessionMeta | None:
        # Return session metadata by id, or None.
        return self._meta.get(session_id)

    def _read_all_meta(self) -> list[SessionMeta]:
        # Return all session metadata records.
        return list(self._meta.values())


__all__ = ["InMemorySessionStore"]
