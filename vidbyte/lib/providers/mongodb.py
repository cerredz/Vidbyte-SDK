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

    def create_collection(self, name: str, *, validator: dict[str, Any] | None = None) -> str:
        """Create a MongoDB collection and return its name."""
        options = {"validator": validator} if validator is not None else {}
        try:
            self._sessions.database.create_collection(name, **options)
        except Exception as exc:
            raise SessionStoreError("Failed to create MongoDB collection.", details={"provider": "mongodb", "collection": name}) from exc
        return name

    def create_index(self, collection: str, keys: list[tuple[str, int]], *, unique: bool = False) -> str:
        """Create an index on a MongoDB collection and return the index name."""
        try:
            return str(self._sessions.database[collection].create_index(keys, unique=unique))
        except Exception as exc:
            raise SessionStoreError("Failed to create MongoDB index.", details={"provider": "mongodb", "collection": collection}) from exc

    def insert_document(self, collection: str, document: dict[str, Any]) -> str:
        """Insert one document into a MongoDB collection and return the inserted id."""
        try:
            result = self._sessions.database[collection].insert_one(dict(document))
        except Exception as exc:
            raise SessionStoreError("Failed to insert MongoDB document.", details={"provider": "mongodb", "collection": collection}) from exc
        return str(result.inserted_id)

    def find_documents(self, collection: str, query: dict[str, Any] | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """Find documents in a MongoDB collection and return JSON-friendly dictionaries."""
        try:
            cursor = self._sessions.database[collection].find(dict(query or {})).limit(limit)
            return [self._json_document(document) for document in cursor]
        except Exception as exc:
            raise SessionStoreError("Failed to find MongoDB documents.", details={"provider": "mongodb", "collection": collection}) from exc

    def update_documents(self, collection: str, query: dict[str, Any], update: dict[str, Any], *, many: bool = True) -> int:
        """Update matching MongoDB documents and return the modified count."""
        try:
            operation = self._sessions.database[collection].update_many if many else self._sessions.database[collection].update_one
            result = operation(dict(query), {"$set": dict(update)})
        except Exception as exc:
            raise SessionStoreError("Failed to update MongoDB documents.", details={"provider": "mongodb", "collection": collection}) from exc
        return int(result.modified_count)

    def delete_documents(self, collection: str, query: dict[str, Any], *, many: bool = True) -> int:
        """Delete matching MongoDB documents and return the deleted count."""
        try:
            operation = self._sessions.database[collection].delete_many if many else self._sessions.database[collection].delete_one
            result = operation(dict(query))
        except Exception as exc:
            raise SessionStoreError("Failed to delete MongoDB documents.", details={"provider": "mongodb", "collection": collection}) from exc
        return int(result.deleted_count)

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

    @staticmethod
    def _json_document(document: dict[str, Any]) -> dict[str, Any]:
        # Convert common BSON values to strings so tool outputs stay JSON serializable.
        return {str(key): str(value) if key == "_id" else value for key, value in document.items()}


__all__ = ["MongoDbSessionStore"]
