"""Context Protocol Header

Description:
    Shared base for database-backed session stores.
Purpose:
    Converts session contracts to/from the same JSON payload shape used by the
    filesystem store, leaving only row-level persistence to each DB provider.
Architecture:
    - ProviderSessionStore: BaseSessionStore serializing through SessionSerializer
      and delegating to abstract row operations.
Relations:
    Subclassed by vidbyte.lib.providers.{postgres,mongodb,supabase}.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from vidbyte.lib.dataclasses.sessions import Checkpoint, SessionMeta
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.store import BaseSessionStore


class ProviderSessionStore(BaseSessionStore):
    """Database-backed session store sharing the JSON payload shape across providers."""

    def __init__(self, *, serializer: SessionSerializer | None = None) -> None:
        # Bind the serializer used to render and parse stored payloads.
        self._serializer = serializer or SessionSerializer()

    def _write_checkpoint(self, checkpoint: Checkpoint) -> None:
        # Serialize and upsert a checkpoint row.
        payload = self._serializer.checkpoint_to_dict(checkpoint)
        self._upsert_checkpoint_row(checkpoint.id, checkpoint.session_id, checkpoint.parent_id, checkpoint.seq, checkpoint.created_at, payload)

    def _read_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        # Fetch and parse a checkpoint row by id.
        row = self._get_checkpoint_row(checkpoint_id)
        return self._serializer.checkpoint_from_dict(row) if row is not None else None

    def _read_session_checkpoints(self, session_id: str) -> list[Checkpoint]:
        # Fetch and parse all checkpoint rows for a session.
        return [self._serializer.checkpoint_from_dict(row) for row in self._get_session_checkpoint_rows(session_id)]

    def _delete_checkpoint(self, checkpoint_id: str) -> None:
        # Delete a checkpoint row by id.
        self._delete_checkpoint_row(checkpoint_id)

    def _write_meta(self, meta: SessionMeta) -> None:
        # Serialize and upsert a session meta row.
        self._upsert_meta_row(meta.session_id, self._serializer.meta_to_dict(meta))

    def _read_meta(self, session_id: str) -> SessionMeta | None:
        # Fetch and parse a session meta row.
        row = self._get_meta_row(session_id)
        return self._serializer.meta_from_dict(row) if row is not None else None

    def _read_all_meta(self) -> list[SessionMeta]:
        # Fetch and parse all session meta rows.
        return [self._serializer.meta_from_dict(row) for row in self._get_all_meta_rows()]

    @abstractmethod
    def _upsert_checkpoint_row(self, checkpoint_id: str, session_id: str, parent_id: str | None, seq: int, created_at: str, payload: dict[str, Any]) -> None: ...
    @abstractmethod
    def _get_checkpoint_row(self, checkpoint_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    def _get_session_checkpoint_rows(self, session_id: str) -> list[dict[str, Any]]: ...
    @abstractmethod
    def _delete_checkpoint_row(self, checkpoint_id: str) -> None: ...
    @abstractmethod
    def _upsert_meta_row(self, session_id: str, payload: dict[str, Any]) -> None: ...
    @abstractmethod
    def _get_meta_row(self, session_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    def _get_all_meta_rows(self) -> list[dict[str, Any]]: ...


__all__ = ["ProviderSessionStore"]
