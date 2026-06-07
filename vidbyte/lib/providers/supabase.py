"""Context Protocol Header

Description:
    Supabase-backed session store.
Purpose:
    Persists session checkpoints and metadata through the Supabase client into two
    provisioned tables. The supabase package is imported lazily.
Architecture:
    - SupabaseSessionStore: ProviderSessionStore over a supabase client.
Relations:
    Implements vidbyte.lib.providers.base.ProviderSessionStore.
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.errors import ConfigurationError, SessionStoreError
from vidbyte.lib.providers.base import ProviderSessionStore


class SupabaseSessionStore(ProviderSessionStore):
    """Durable session store backed by Supabase tables."""

    def __init__(self, *, url: str, key: str, table_prefix: str = "vidbyte_") -> None:
        # Build a Supabase client (lazy import); tables are assumed provisioned.
        super().__init__()
        create_client = self._import_driver()
        try:
            self._client = create_client(url, key)
        except Exception as exc:
            raise SessionStoreError("Failed to create the Supabase client.", details={"provider": "supabase"}) from exc
        self._sessions_table = f"{table_prefix}sessions"
        self._checkpoints_table = f"{table_prefix}checkpoints"

    @staticmethod
    def _import_driver() -> Any:
        # Import the supabase factory lazily, raising a helpful error when absent.
        try:
            from supabase import create_client
        except ImportError as exc:
            raise ConfigurationError("SupabaseSessionStore requires the 'supabase' package. Install it with `pip install supabase`.") from exc
        return create_client

    def _upsert_checkpoint_row(self, checkpoint_id: str, session_id: str, parent_id: str | None, seq: int, created_at: str, payload: dict[str, Any]) -> None:
        # Upsert a checkpoint row keyed by id.
        record = {"id": checkpoint_id, "session_id": session_id, "parent_id": parent_id, "seq": seq, "created_at": created_at, "payload": payload}
        self._client.table(self._checkpoints_table).upsert(record).execute()

    def _get_checkpoint_row(self, checkpoint_id: str) -> dict[str, Any] | None:
        # Fetch a checkpoint payload by id.
        response = self._client.table(self._checkpoints_table).select("payload").eq("id", checkpoint_id).execute()
        return self._first_payload(response)

    def _get_session_checkpoint_rows(self, session_id: str) -> list[dict[str, Any]]:
        # Fetch all checkpoint payloads for a session ordered by seq.
        response = self._client.table(self._checkpoints_table).select("payload").eq("session_id", session_id).order("seq").execute()
        return [row["payload"] for row in (response.data or [])]

    def _delete_checkpoint_row(self, checkpoint_id: str) -> None:
        # Delete a checkpoint row by id.
        self._client.table(self._checkpoints_table).delete().eq("id", checkpoint_id).execute()

    def _upsert_meta_row(self, session_id: str, payload: dict[str, Any]) -> None:
        # Upsert a session meta row keyed by session id.
        self._client.table(self._sessions_table).upsert({"session_id": session_id, "payload": payload}).execute()

    def _get_meta_row(self, session_id: str) -> dict[str, Any] | None:
        # Fetch a session meta payload by id.
        response = self._client.table(self._sessions_table).select("payload").eq("session_id", session_id).execute()
        return self._first_payload(response)

    def _get_all_meta_rows(self) -> list[dict[str, Any]]:
        # Fetch all session meta payloads.
        response = self._client.table(self._sessions_table).select("payload").execute()
        return [row["payload"] for row in (response.data or [])]

    @staticmethod
    def _first_payload(response: Any) -> dict[str, Any] | None:
        # Return the first row's payload from a Supabase response, or None.
        data = getattr(response, "data", None) or []
        return data[0]["payload"] if data else None


__all__ = ["SupabaseSessionStore"]
