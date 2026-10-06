"""Context Protocol Header

Description:
    PostgreSQL-backed session store.
Purpose:
    Persists session checkpoints and metadata in two JSONB tables, created on
    first use. The psycopg driver is imported lazily so the SDK core stays clean.
Architecture:
    - PostgresSessionStore: ProviderSessionStore over a psycopg connection.
Relations:
    Implements vidbyte.lib.providers.base.ProviderSessionStore.
"""

from __future__ import annotations

import json
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.sessions.errors import SessionStoreError
from vidbyte.lib.providers.base import ProviderSessionStore


class PostgresSessionStore(ProviderSessionStore):
    """Durable session store backed by PostgreSQL JSONB tables."""

    def __init__(self, *, dsn: str, table_prefix: str = "vidbyte_") -> None:
        # Connect to Postgres (lazy driver import) and ensure the schema exists.
        super().__init__()
        self._psycopg = self._import_driver()
        self._sessions_table = f"{table_prefix}sessions"
        self._checkpoints_table = f"{table_prefix}checkpoints"
        try:
            self._conn = self._psycopg.connect(dsn)
        except Exception as exc:
            raise SessionStoreError("Failed to connect to PostgreSQL.", details={"provider": "postgres"}) from exc
        self._ensure_schema()

    @staticmethod
    def _import_driver() -> Any:
        # Import psycopg lazily, raising a helpful error when it is absent.
        try:
            import psycopg
        except ImportError as exc:
            raise ConfigurationError("PostgresSessionStore requires the 'psycopg' package. Install it with `pip install psycopg`.") from exc
        return psycopg

    def _ensure_schema(self) -> None:
        # Create the sessions/checkpoints tables and indexes idempotently.
        with self._conn.cursor() as cur:
            cur.execute(f"CREATE TABLE IF NOT EXISTS {self._sessions_table} (session_id TEXT PRIMARY KEY, payload JSONB)")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {self._checkpoints_table} (id TEXT PRIMARY KEY, session_id TEXT, parent_id TEXT, seq INTEGER, created_at TEXT, payload JSONB)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{self._checkpoints_table}_session_seq ON {self._checkpoints_table} (session_id, seq)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{self._checkpoints_table}_parent ON {self._checkpoints_table} (parent_id)")
        self._conn.commit()

    def create_schema(self, name: str) -> str:
        """Create a PostgreSQL schema if it does not exist and return its name."""
        with self._conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(name)}")
        self._conn.commit()
        return name

    def create_table(self, table: str, columns: dict[str, str], *, schema: str | None = None) -> str:
        """Create a PostgreSQL table from a column-name to SQL-type mapping."""
        column_sql = ", ".join(f"{self._quote_identifier(name)} {definition}" for name, definition in columns.items())
        qualified = self._qualified_table(table, schema=schema)
        with self._conn.cursor() as cur:
            cur.execute(f"CREATE TABLE IF NOT EXISTS {qualified} ({column_sql})")
        self._conn.commit()
        return qualified

    def insert_row(self, table: str, row: dict[str, Any], *, schema: str | None = None) -> int:
        """Insert one PostgreSQL row and return the affected row count."""
        columns = list(row)
        placeholders = ", ".join(["%s"] * len(columns))
        quoted_columns = ", ".join(self._quote_identifier(column) for column in columns)
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._qualified_table(table, schema=schema)} ({quoted_columns}) VALUES ({placeholders})",
                tuple(row[column] for column in columns),
            )
            count = cur.rowcount
        self._conn.commit()
        return int(count)

    def select_rows(self, table: str, where: dict[str, Any] | None = None, *, schema: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Select PostgreSQL rows using optional equality filters."""
        where_sql, values = self._where_clause(where or {})
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {self._qualified_table(table, schema=schema)}{where_sql} LIMIT %s", (*values, limit))
            names = [column.name for column in cur.description]
            rows = cur.fetchall()
        return [dict(zip(names, row)) for row in rows]

    def update_rows(self, table: str, values: dict[str, Any], where: dict[str, Any], *, schema: str | None = None) -> int:
        """Update PostgreSQL rows using equality filters and return the affected row count."""
        assignments = ", ".join(f"{self._quote_identifier(column)}=%s" for column in values)
        where_sql, where_values = self._where_clause(where)
        with self._conn.cursor() as cur:
            cur.execute(
                f"UPDATE {self._qualified_table(table, schema=schema)} SET {assignments}{where_sql}",
                (*tuple(values.values()), *where_values),
            )
            count = cur.rowcount
        self._conn.commit()
        return int(count)

    def delete_rows(self, table: str, where: dict[str, Any], *, schema: str | None = None) -> int:
        """Delete PostgreSQL rows using equality filters and return the affected row count."""
        where_sql, values = self._where_clause(where)
        with self._conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self._qualified_table(table, schema=schema)}{where_sql}", values)
            count = cur.rowcount
        self._conn.commit()
        return int(count)

    def _upsert_checkpoint_row(self, checkpoint_id: str, session_id: str, parent_id: str | None, seq: int, created_at: str, payload: dict[str, Any]) -> None:
        # Insert or replace a checkpoint row.
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._checkpoints_table} (id, session_id, parent_id, seq, created_at, payload) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET session_id=EXCLUDED.session_id, parent_id=EXCLUDED.parent_id, seq=EXCLUDED.seq, created_at=EXCLUDED.created_at, payload=EXCLUDED.payload",
                (checkpoint_id, session_id, parent_id, seq, created_at, json.dumps(payload)),
            )
        self._conn.commit()

    def _get_checkpoint_row(self, checkpoint_id: str) -> dict[str, Any] | None:
        # Fetch a single checkpoint payload by id.
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT payload FROM {self._checkpoints_table} WHERE id=%s", (checkpoint_id,))
            row = cur.fetchone()
        return self._payload(row)

    def _get_session_checkpoint_rows(self, session_id: str) -> list[dict[str, Any]]:
        # Fetch all checkpoint payloads for a session ordered by seq.
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT payload FROM {self._checkpoints_table} WHERE session_id=%s ORDER BY seq", (session_id,))
            rows = cur.fetchall()
        return [self._payload(row) for row in rows if row is not None]

    def _delete_checkpoint_row(self, checkpoint_id: str) -> None:
        # Delete a checkpoint row by id.
        with self._conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self._checkpoints_table} WHERE id=%s", (checkpoint_id,))
        self._conn.commit()

    def _upsert_meta_row(self, session_id: str, payload: dict[str, Any]) -> None:
        # Insert or replace a session meta row.
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._sessions_table} (session_id, payload) VALUES (%s, %s) ON CONFLICT (session_id) DO UPDATE SET payload=EXCLUDED.payload",
                (session_id, json.dumps(payload)),
            )
        self._conn.commit()

    def _get_meta_row(self, session_id: str) -> dict[str, Any] | None:
        # Fetch a single session meta payload.
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT payload FROM {self._sessions_table} WHERE session_id=%s", (session_id,))
            row = cur.fetchone()
        return self._payload(row)

    def _get_all_meta_rows(self) -> list[dict[str, Any]]:
        # Fetch all session meta payloads.
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT payload FROM {self._sessions_table}")
            rows = cur.fetchall()
        return [self._payload(row) for row in rows if row is not None]

    @staticmethod
    def _payload(row: Any) -> dict[str, Any] | None:
        # Normalize a fetched row into a payload dict, or None.
        if row is None:
            return None
        value = row[0]
        return json.loads(value) if isinstance(value, (str, bytes)) else value

    @classmethod
    def _qualified_table(cls, table: str, *, schema: str | None = None) -> str:
        if schema:
            return f"{cls._quote_identifier(schema)}.{cls._quote_identifier(table)}"
        return cls._quote_identifier(table)

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @classmethod
    def _where_clause(cls, where: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        if not where:
            return "", ()
        clauses = [f"{cls._quote_identifier(column)}=%s" for column in where]
        return " WHERE " + " AND ".join(clauses), tuple(where.values())


__all__ = ["PostgresSessionStore"]
