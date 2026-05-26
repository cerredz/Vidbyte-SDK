"""Context Protocol Header

Description:
    Implements BaseSqlBackend using Python's built-in sqlite3 module.
Purpose:
    Provides read-only SQL querying, table listing, and schema description
    for SQLite databases with safety checks against write operations.
Architecture:
    - SqliteBackend: Wraps sqlite3 in asyncio.to_thread for non-blocking execution.
    - Enforces read-only mode with DANGEROUS_PATTERNS regex validation.
    - Limits query results to 1000 rows with truncation flag.
    - Sanitizes table names to prevent SQL injection in describe_table().
Relations:
    Related to vidbyte.lib.providers.sql.base and vidbyte.tools.builtins.sql.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path

from vidbyte.lib.providers.sql.base import BaseSqlBackend, QueryResult

MAX_ROWS = 1000
DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)\b",
    re.IGNORECASE,
)
VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SqliteBackend(BaseSqlBackend):
    async def query(self, connection_string: str, sql: str) -> QueryResult:
        self._check_read_only(sql)

        db_path = self._resolve_path(connection_string)
        return await asyncio.to_thread(self._run_query, db_path, sql)

    async def list_tables(self, connection_string: str) -> list[str]:
        db_path = self._resolve_path(connection_string)
        return await asyncio.to_thread(self._run_list_tables, db_path)

    async def describe_table(self, connection_string: str, table: str) -> list[dict]:
        db_path = self._resolve_path(connection_string)
        return await asyncio.to_thread(self._run_describe_table, db_path, table)

    @staticmethod
    def _check_read_only(sql: str) -> None:
        if DANGEROUS_PATTERNS.search(sql):
            raise ValueError(
                "Write operations are not allowed in read-only SQL mode. "
                "Set sql_read_only=False to enable writes."
            )

    @staticmethod
    def _resolve_path(connection_string: str) -> str:
        path = Path(connection_string)
        if not path.exists():
            raise FileNotFoundError(f"Database file not found: {connection_string}")
        return str(path.resolve())

    @staticmethod
    def _run_query(db_path: str, sql: str) -> QueryResult:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            all_rows = cursor.fetchall()
            truncated = len(all_rows) > MAX_ROWS
            rows = [list(row) for row in (all_rows[:MAX_ROWS])]
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(all_rows),
                truncated=truncated,
            )
        finally:
            conn.close()

    @staticmethod
    def _run_list_tables(db_path: str) -> list[str]:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _run_describe_table(db_path: str, table: str) -> list[dict]:
        if not VALID_TABLE_NAME.match(table):
            raise ValueError(
                f"Invalid table name: {table}. "
                "Table names must contain only alphanumeric characters and underscores."
            )

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            rows = cursor.fetchall()
            col_names = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            return [dict(zip(col_names, row)) for row in rows]
        finally:
            conn.close()


__all__ = [
    "SqliteBackend",
]
