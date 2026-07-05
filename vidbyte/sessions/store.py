"""Context Protocol Header

Description:
    Defines the SessionStore storage port and the shared BaseSessionStore.
Purpose:
    Lets the Session facade persist checkpoints through interchangeable backends
    (memory, filesystem, database providers) behind one contract.
Architecture:
    - SessionStore: structural Protocol every backend implements.
    - BaseSessionStore: ABC providing seq assignment, head advance, and pruning
      on top of backend-specific raw read/write primitives.
Relations:
    Implemented by vidbyte.sessions.stores.* and vidbyte.lib.providers.*; consumed
    by vidbyte.sessions.session.Session.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from vidbyte.sessions.contracts import Checkpoint, SessionMeta, SessionStatus
from vidbyte.sessions.errors import CheckpointNotFoundError, SessionNotFoundError


@runtime_checkable
class SessionStore(Protocol):
    """Structural contract for a durable checkpoint backend."""

    def put(self, checkpoint: Checkpoint) -> Checkpoint: ...
    def get(self, checkpoint_id: str) -> Checkpoint: ...
    def head(self, session_id: str) -> Checkpoint | None: ...
    def history(self, session_id: str) -> list[Checkpoint]: ...
    def put_meta(self, meta: SessionMeta) -> None: ...
    def get_meta(self, session_id: str) -> SessionMeta: ...
    def resolve(self, identifier: str) -> str: ...
    def list_sessions(self, *, agent_name: str | None = None, tag: str | None = None, status: SessionStatus | None = None) -> list[SessionMeta]: ...
    def prune(self, session_id: str, *, keep: int | None = None) -> None: ...


class BaseSessionStore(ABC):
    """Shared store behavior built on backend-specific raw primitives."""

    def put(self, checkpoint: Checkpoint) -> Checkpoint:
        # Assign a monotonic seq, persist the checkpoint, and advance the session head.
        stored = replace(checkpoint, seq=self._next_seq(checkpoint.session_id))
        self._write_checkpoint(stored)
        self._advance_head(stored)
        return stored

    def get(self, checkpoint_id: str) -> Checkpoint:
        # Return a checkpoint or raise CheckpointNotFoundError.
        found = self._read_checkpoint(checkpoint_id)
        if found is None:
            raise CheckpointNotFoundError(f"Unknown checkpoint id: {checkpoint_id}.", details={"checkpoint_id": checkpoint_id})
        return found

    def head(self, session_id: str) -> Checkpoint | None:
        # Return the current head checkpoint for a session, or None when empty.
        meta = self._read_meta(session_id)
        if meta is None or meta.head_id is None:
            return None
        return self._read_checkpoint(meta.head_id)

    def history(self, session_id: str) -> list[Checkpoint]:
        # Return all checkpoints for a session ordered by seq.
        return sorted(self._read_session_checkpoints(session_id), key=lambda item: item.seq)

    def put_meta(self, meta: SessionMeta) -> None:
        # Persist session metadata as supplied by the caller.
        self._write_meta(meta)

    def get_meta(self, session_id: str) -> SessionMeta:
        # Return session metadata or raise SessionNotFoundError.
        meta = self._read_meta(session_id)
        if meta is None:
            raise SessionNotFoundError(f"Unknown session id: {session_id}.", details={"session_id": session_id})
        return meta

    def resolve(self, identifier: str) -> str:
        # Resolve a concrete session id or tag/name to a concrete session id.
        if self._read_meta(identifier) is not None:
            return identifier
        matches = [meta for meta in self._read_all_meta() if identifier in meta.tags]
        if not matches:
            raise SessionNotFoundError(f"No session id or tag: {identifier}.", details={"identifier": identifier})
        return max(matches, key=lambda meta: (meta.updated_at, meta.session_id)).session_id

    def list_sessions(self, *, agent_name: str | None = None, tag: str | None = None, status: SessionStatus | None = None) -> list[SessionMeta]:
        # Return all session metadata records matching the optional filters.
        results = []
        for meta in self._read_all_meta():
            if agent_name is not None and meta.agent_name != agent_name:
                continue
            if tag is not None and tag not in meta.tags:
                continue
            if status is not None and meta.status != status:
                continue
            results.append(meta)
        return sorted(results, key=lambda item: item.updated_at)

    def prune(self, session_id: str, *, keep: int | None = None) -> None:
        # Delete oldest checkpoints beyond `keep`, never removing the current head.
        if keep is None:
            return
        meta = self._read_meta(session_id)
        head_id = meta.head_id if meta is not None else None
        checkpoints = self.history(session_id)
        removable = [c for c in checkpoints if c.id != head_id]
        excess = len(removable) - max(keep - (1 if head_id else 0), 0)
        for checkpoint in removable[: max(excess, 0)]:
            self._delete_checkpoint(checkpoint.id)

    def _next_seq(self, session_id: str) -> int:
        # Compute the next monotonic sequence number for a session.
        existing = self._read_session_checkpoints(session_id)
        return (max((item.seq for item in existing), default=-1)) + 1

    def _advance_head(self, checkpoint: Checkpoint) -> None:
        # Point the session head at the just-written checkpoint, creating meta if absent.
        now = self._now()
        meta = self._read_meta(checkpoint.session_id)
        if meta is None:
            meta = SessionMeta(
                session_id=checkpoint.session_id,
                head_id=checkpoint.id,
                parent_session_id=None,
                agent_name=checkpoint.run_state.agent_name,
                status=checkpoint.status,
                created_at=now,
                updated_at=now,
                tags=(),
            )
        else:
            meta = replace(meta, head_id=checkpoint.id, status=checkpoint.status, updated_at=now)
        self._write_meta(meta)

    @staticmethod
    def _now() -> str:
        # Return the current UTC timestamp as an ISO-8601 string.
        return datetime.now(timezone.utc).isoformat()

    @abstractmethod
    def _write_checkpoint(self, checkpoint: Checkpoint) -> None: ...
    @abstractmethod
    def _read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None: ...
    @abstractmethod
    def _read_session_checkpoints(self, session_id: str) -> list[Checkpoint]: ...
    @abstractmethod
    def _delete_checkpoint(self, checkpoint_id: str) -> None: ...
    @abstractmethod
    def _write_meta(self, meta: SessionMeta) -> None: ...
    @abstractmethod
    def _read_meta(self, session_id: str) -> SessionMeta | None: ...
    @abstractmethod
    def _read_all_meta(self) -> list[SessionMeta]: ...


__all__ = ["SessionStore", "BaseSessionStore"]
