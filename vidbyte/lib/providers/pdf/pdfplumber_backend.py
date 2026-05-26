"""Context Protocol Header

Description:
    Implements BasePdfBackend using the pdfplumber library.
Purpose:
    Provides robust PDF text and table extraction via pdfplumber, with superior
    table detection compared to PyMuPDF. All I/O runs in a thread pool via asyncio.
Architecture:
    - PDFPlumberBackend: Wraps pdfplumber.open() in asyncio.to_thread.
    - Supports page range filtering ("1-5", "1,3,5", or None for all).
    - Table extraction via page.extract_tables().
Relations:
    Related to vidbyte.lib.providers.pdf.base and vidbyte.tools.builtins.pdf.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from vidbyte.lib.providers.pdf.base import BasePdfBackend, PDFTableResult, PDFTextResult


class PDFPlumberBackend(BasePdfBackend):
    async def read_text(self, file_path: str, page_range: str | None) -> PDFTextResult:
        self._check_path(file_path)
        return await asyncio.to_thread(self._read_text_blocking, file_path, page_range)

    async def read_tables(self, file_path: str, page_range: str | None) -> PDFTableResult:
        self._check_path(file_path)
        return await asyncio.to_thread(self._read_tables_blocking, file_path, page_range)

    async def get_metadata(self, file_path: str) -> dict:
        self._check_path(file_path)
        return await asyncio.to_thread(self._get_metadata_blocking, file_path)

    @staticmethod
    def _check_path(file_path: str) -> None:
        if not Path(file_path).is_file():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

    @staticmethod
    def _import_pdfplumber():
        try:
            import pdfplumber
            return pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber is not installed. Install with: pip install pdfplumber"
            ) from None

    @classmethod
    def _read_text_blocking(cls, file_path: str, page_range: str | None) -> PDFTextResult:
        pdfplumber = cls._import_pdfplumber()
        with pdfplumber.open(file_path) as pdf:
            pages = cls._resolve_page_numbers(pdf.pages, page_range)
            parts: list[str] = []
            for idx in pages:
                page = pdf.pages[idx]
                text = page.extract_text()
                if text:
                    parts.append(text)
            return PDFTextResult(
                text="\n".join(parts),
                page_count=len(pdf.pages),
            )

    @classmethod
    def _read_tables_blocking(cls, file_path: str, page_range: str | None) -> PDFTableResult:
        pdfplumber = cls._import_pdfplumber()
        with pdfplumber.open(file_path) as pdf:
            pages = cls._resolve_page_numbers(pdf.pages, page_range)
            all_tables: list[list[list[str]]] = []
            for idx in pages:
                page = pdf.pages[idx]
                tables_on_page = page.extract_tables()
                if tables_on_page:
                    for table in tables_on_page:
                        all_tables.append(
                            [[str(cell) if cell is not None else "" for cell in row] for row in table]
                        )
            return PDFTableResult(tables=all_tables)

    @classmethod
    def _get_metadata_blocking(cls, file_path: str) -> dict:
        pdfplumber = cls._import_pdfplumber()
        with pdfplumber.open(file_path) as pdf:
            meta = pdf.metadata or {}
            return {
                "title": meta.get("Title", ""),
                "author": meta.get("Author", ""),
                "subject": meta.get("Subject", ""),
                "creator": meta.get("Creator", ""),
                "producer": meta.get("Producer", ""),
                "format": "PDF",
                "page_count": len(pdf.pages),
            }

    @staticmethod
    def _resolve_page_numbers(pages_list, page_range: str | None) -> list[int]:
        total = len(pages_list)
        if page_range is None:
            return list(range(total))

        result: set[int] = set()
        for part in page_range.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str.strip()) - 1
                    end = int(end_str.strip()) - 1
                    start = max(0, start)
                    end = min(total - 1, end)
                    result.update(range(start, end + 1))
                except (ValueError, TypeError):
                    continue
            else:
                try:
                    page_num = int(part.strip()) - 1
                    if 0 <= page_num < total:
                        result.add(page_num)
                except (ValueError, TypeError):
                    continue

        return sorted(result)


__all__ = [
    "PDFPlumberBackend",
]
