"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for SQL backends.
Purpose:
    Provides a typed contract that all SQL provider backends must implement,
    along with the shared QueryResult dataclass.
Architecture:
    - QueryResult: Lightweight frozen dataclass for query results.
    - BaseSqlBackend: ABC requiring query(), list_tables(), and describe_table().
Relations:
    Related to vidbyte.lib.providers.sql and vidbyte.tools.builtins.sql.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class QueryResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool = False


class BaseSqlBackend(ABC):
    @abstractmethod
    async def query(self, connection_string: str, sql: str) -> QueryResult:
        ...

    @abstractmethod
    async def list_tables(self, connection_string: str) -> list[str]:
        ...

    @abstractmethod
    async def describe_table(self, connection_string: str, table: str) -> list[dict]:
        ...


__all__ = [
    "BaseSqlBackend",
    "QueryResult",
]
