"""Context Protocol Header

Description:
    SQLite-backed session store.
Purpose:
    Persists session checkpoints and metadata in two tables created on first
    use. Uses the stdlib sqlite3 module, so unlike the Mongo/Supabase/Postgres
    stores it has no optional driver dependency and never raises
    ConfigurationError — it is safe to import and construct anywhere.
Architecture:
    - SqliteSessionStore: ProviderSessionStore over a sqlite3 connection.
Relations:
    Implements vidbyte.lib.providers.base.ProviderSessionStore. Re-exported
    from vidbyte.lib.providers alongside the other database-backed stores.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from vidbyte.sessions.errors import SessionStoreError
from vidbyte.lib.providers.base import ProviderSessionStore


class SqliteSessionStore(ProviderSessionStore):
    """Durable session store backed by a local SQLite database file."""

    def __init__(self, *, path: str, table_prefix: str = "vidbyte_") -> None:
        # Open the sqlite3 connection (stdlib; no lazy driver) and ensure the schema exists.
        super().__init__()
        self._sessions_table = f"{table_prefix}sessions"
        self._checkpoints_table = f"{table_prefix}checkpoints"
        try:
            self._conn = sqlite3.connect(path)
        except sqlite3.Error as exc:
            raise SessionStoreError("Failed to open SQLite database.", details={"provider": "sqlite", "path": path}) from exc
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Create the sessions/checkpoints tables and indexes idempotently.
        cursor = self._conn.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {self._sessions_table} (session_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {self._checkpoints_table} (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, parent_id TEXT, seq INTEGER NOT NULL, created_at TEXT, payload TEXT NOT NULL)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS ix_{self._checkpoints_table}_session_seq ON {self._checkpoints_table} (session_id, seq)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS ix_{self._checkpoints_table}_parent ON {self._checkpoints_table} (parent_id)")
        self._conn.commit()

    def create_table(self, table: str, columns: dict[str, str]) -> str:
        """Create a SQLite table from a column-name to SQL-type mapping."""
        column_sql = ", ".join(f"{self._quote_identifier(name)} {definition}" for name, definition in columns.items())
        qualified = self._quote_identifier(table)
        cursor = self._conn.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {qualified} ({column_sql})")
        self._conn.commit()
        return qualified

    def insert_row(self, table: str, row: dict[str, Any]) -> int:
        """Insert one SQLite row and return the affected row count."""
        columns = list(row)
        quoted_columns = ", ".join(self._quote_identifier(column) for column in columns)
        placeholders = ", ".join(["?"] * len(columns))
        cursor = self._conn.cursor()
        cursor.execute(
            f"INSERT INTO {self._quote_identifier(table)} ({quoted_columns}) VALUES ({placeholders})",
            tuple(row[column] for column in columns),
        )
        self._conn.commit()
        return int(cursor.rowcount)

    def select_rows(self, table: str, where: dict[str, Any] | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """Select SQLite rows using optional equality filters."""
        where_sql, values = self._where_clause(where or {})
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT * FROM {self._quote_identifier(table)}{where_sql} LIMIT ?", (*values, limit))
        return [dict(row) for row in cursor.fetchall()]

    def update_rows(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> int:
        """Update SQLite rows using equality filters and return the affected row count."""
        assignments = ", ".join(f"{self._quote_identifier(column)}=?" for column in values)
        where_sql, where_values = self._where_clause(where)
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE {self._quote_identifier(table)} SET {assignments}{where_sql}",
            (*tuple(values.values()), *where_values),
        )
        self._conn.commit()
        return int(cursor.rowcount)

    def delete_rows(self, table: str, where: dict[str, Any]) -> int:
        """Delete SQLite rows using equality filters and return the affected row count."""
        where_sql, values = self._where_clause(where)
        cursor = self._conn.cursor()
        cursor.execute(f"DELETE FROM {self._quote_identifier(table)}{where_sql}", values)
        self._conn.commit()
        return int(cursor.rowcount)

    def _upsert_checkpoint_row(self, checkpoint_id: str, session_id: str, parent_id: str | None, seq: int, created_at: str, payload: dict[str, Any]) -> None:
        # Insert or replace a checkpoint row.
        cursor = self._conn.cursor()
        cursor.execute(
            f"INSERT OR REPLACE INTO {self._checkpoints_table} (id, session_id, parent_id, seq, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (checkpoint_id, session_id, parent_id, seq, created_at, json.dumps(payload)),
        )
        self._conn.commit()

    def _get_checkpoint_row(self, checkpoint_id: str) -> dict[str, Any] | None:
        # Fetch a single checkpoint payload by id.
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT payload FROM {self._checkpoints_table} WHERE id=?", (checkpoint_id,))
        row = cursor.fetchone()
        return self._payload(row)

    def _get_session_checkpoint_rows(self, session_id: str) -> list[dict[str, Any]]:
        # Fetch all checkpoint payloads for a session ordered by seq.
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT payload FROM {self._checkpoints_table} WHERE session_id=? ORDER BY seq", (session_id,))
        return [self._payload(row) for row in cursor.fetchall() if row is not None]

    def _delete_checkpoint_row(self, checkpoint_id: str) -> None:
        # Delete a checkpoint row by id.
        cursor = self._conn.cursor()
        cursor.execute(f"DELETE FROM {self._checkpoints_table} WHERE id=?", (checkpoint_id,))
        self._conn.commit()

    def _upsert_meta_row(self, session_id: str, payload: dict[str, Any]) -> None:
        # Insert or replace a session meta row.
        cursor = self._conn.cursor()
        cursor.execute(
            f"INSERT OR REPLACE INTO {self._sessions_table} (session_id, payload) VALUES (?, ?)",
            (session_id, json.dumps(payload)),
        )
        self._conn.commit()

    def _get_meta_row(self, session_id: str) -> dict[str, Any] | None:
        # Fetch a single session meta payload.
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT payload FROM {self._sessions_table} WHERE session_id=?", (session_id,))
        row = cursor.fetchone()
        return self._payload(row)

    def _get_all_meta_rows(self) -> list[dict[str, Any]]:
        # Fetch all session meta payloads.
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT payload FROM {self._sessions_table}")
        return [self._payload(row) for row in cursor.fetchall() if row is not None]

    @staticmethod
    def _payload(row: Any) -> dict[str, Any] | None:
        # Normalize a fetched row into a payload dict, or None.
        if row is None:
            return None
        value = row[0]
        return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @classmethod
    def _where_clause(cls, where: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        if not where:
            return "", ()
        clauses = [f"{cls._quote_identifier(column)}=?" for column in where]
        return " WHERE " + " AND ".join(clauses), tuple(where.values())


__all__ = ["SqliteSessionStore"]
