"""Context Protocol Header

Description:
    Re-exports SQL backend implementations for built-in SQL tools.
Purpose:
    Provides a single import surface for all SQL provider backends.
Architecture:
    - BaseSqlBackend: Abstract contract for SQL operations.
    - SqliteBackend: SQLite implementation using the stdlib sqlite3 module.
Relations:
    Related to vidbyte.tools.builtins.sql.
"""

from __future__ import annotations

from vidbyte.lib.providers.sql.base import BaseSqlBackend
from vidbyte.lib.providers.sql.sqlite_backend import SqliteBackend

__all__ = [
    "BaseSqlBackend",
    "SqliteBackend",
]
