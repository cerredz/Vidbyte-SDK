"""Context Protocol Header

Description:
    MongoDB-backed session store.
Purpose:
    Persists session checkpoints and metadata in two collections with indexes
    ensured on first use. The pymongo driver is imported lazily.
Architecture:
    - MongoDbSessionStore: ProviderSessionStore over a pymongo database.
Relations:
    Implements vidbyte.lib.providers.base.ProviderSessionStore.
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.sessions.errors import SessionStoreError
from vidbyte.lib.providers.base import ProviderSessionStore


class MongoDbSessionStore(ProviderSessionStore):
    """Durable session store backed by MongoDB collections."""

    def __init__(self, *, uri: str, database: str = "vidbyte", collection_prefix: str = "vidbyte_") -> None:
        # Connect to MongoDB (lazy driver import) and ensure indexes exist.
        super().__init__()
        client_cls = self._import_driver()
        try:
            self._client = client_cls(uri)
            db = self._client[database]
        except Exception as exc:
            raise SessionStoreError("Failed to connect to MongoDB.", details={"provider": "mongodb"}) from exc
        self._sessions = db[f"{collection_prefix}sessions"]
        self._checkpoints = db[f"{collection_prefix}checkpoints"]
        self._ensure_indexes()

    @staticmethod
    def _import_driver() -> Any:
        # Import pymongo lazily, raising a helpful error when it is absent.
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise ConfigurationError("MongoDbSessionStore requires the 'pymongo' package. Install it with `pip install pymongo`.") from exc
        return MongoClient

    def _ensure_indexes(self) -> None:
        # Create the lookup indexes used by reads.
        self._checkpoints.create_index([("id", 1)], unique=True)
        self._checkpoints.create_index([("session_id", 1), ("seq", 1)])
        self._checkpoints.create_index([("parent_id", 1)])
        self._sessions.create_index([("session_id", 1)], unique=True)

    def _upsert_checkpoint_row(self, checkpoint_id: str, session_id: str, parent_id: str | None, seq: int, created_at: str, payload: dict[str, Any]) -> None:
        # Insert or replace a checkpoint document.
        document = {"id": checkpoint_id, "session_id": session_id, "parent_id": parent_id, "seq": seq, "created_at": created_at, "payload": payload}
        self._checkpoints.replace_one({"id": checkpoint_id}, document, upsert=True)

    def _get_checkpoint_row(self, checkpoint_id: str) -> dict[str, Any] | None:
        # Fetch a checkpoint payload by id.
        document = self._checkpoints.find_one({"id": checkpoint_id})
        return document["payload"] if document else None

    def _get_session_checkpoint_rows(self, session_id: str) -> list[dict[str, Any]]:
        # Fetch all checkpoint payloads for a session ordered by seq.
        cursor = self._checkpoints.find({"session_id": session_id}).sort("seq", 1)
        return [document["payload"] for document in cursor]

    def _delete_checkpoint_row(self, checkpoint_id: str) -> None:
        # Delete a checkpoint document by id.
        self._checkpoints.delete_one({"id": checkpoint_id})

    def _upsert_meta_row(self, session_id: str, payload: dict[str, Any]) -> None:
        # Insert or replace a session meta document.
        self._sessions.replace_one({"session_id": session_id}, {"session_id": session_id, "payload": payload}, upsert=True)

    def _get_meta_row(self, session_id: str) -> dict[str, Any] | None:
        # Fetch a session meta payload by id.
        document = self._sessions.find_one({"session_id": session_id})
        return document["payload"] if document else None

    def _get_all_meta_rows(self) -> list[dict[str, Any]]:
        # Fetch all session meta payloads.
        return [document["payload"] for document in self._sessions.find({})]


__all__ = ["MongoDbSessionStore"]
