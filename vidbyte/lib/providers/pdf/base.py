"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer objects for PDF backends.
Purpose:
    Provides a typed contract that all PDF provider backends must implement,
    along with the shared PDFTextResult and PDFTableResult dataclasses.
Architecture:
    - PDFTextResult: Dataclass holding extracted text and page count.
    - PDFTableResult: Dataclass holding tables as nested lists of strings.
    - BasePdfBackend: ABC requiring read_text(), read_tables(), and get_metadata().
Relations:
    Related to vidbyte.lib.providers.pdf and vidbyte.tools.builtins.pdf.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class PDFTextResult:
    text: str
    page_count: int


@dataclass(slots=True)
class PDFTableResult:
    tables: list[list[list[str]]]


class BasePdfBackend(ABC):
    @abstractmethod
    async def read_text(self, file_path: str, page_range: str | None) -> PDFTextResult:
        ...

    @abstractmethod
    async def read_tables(self, file_path: str, page_range: str | None) -> PDFTableResult:
        ...

    @abstractmethod
    async def get_metadata(self, file_path: str) -> dict:
        ...


__all__ = [
    "BasePdfBackend",
    "PDFTableResult",
    "PDFTextResult",
]
