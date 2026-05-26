"""Context Protocol Header

Description:
    Implements BasePdfBackend using the PyMuPDF (fitz) library.
Purpose:
    Provides high-performance PDF text extraction, table detection, and metadata
    retrieval via pymupdf. All I/O operations run in a thread pool via asyncio.
Architecture:
    - PyMuPDFBackend: Wraps fitz.open() in asyncio.to_thread for non-blocking use.
    - Supports page range filtering ("1-5", "1,3,5", or None for all).
    - Table extraction via fitz.Page.find_tables().
Relations:
    Related to vidbyte.lib.providers.pdf.base and vidbyte.tools.builtins.pdf.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from vidbyte.lib.providers.pdf.base import BasePdfBackend, PDFTableResult, PDFTextResult


class PyMuPDFBackend(BasePdfBackend):
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
    def _import_fitz():
        try:
            import fitz
            return fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Install with: pip install pymupdf"
            ) from None

    @classmethod
    def _read_text_blocking(cls, file_path: str, page_range: str | None) -> PDFTextResult:
        fitz = cls._import_fitz()
        doc = fitz.open(file_path)
        try:
            pages = cls._resolve_pages(doc, page_range)
            parts: list[str] = []
            for page_num in pages:
                page = doc[page_num]
                parts.append(page.get_text())
            return PDFTextResult(
                text="\n".join(parts),
                page_count=doc.page_count,
            )
        finally:
            doc.close()

    @classmethod
    def _read_tables_blocking(cls, file_path: str, page_range: str | None) -> PDFTableResult:
        fitz = cls._import_fitz()
        doc = fitz.open(file_path)
        try:
            pages = cls._resolve_pages(doc, page_range)
            all_tables: list[list[list[str]]] = []
            for page_num in pages:
                page = doc[page_num]
                tables_on_page = page.find_tables()
                if tables_on_page:
                    for table in tables_on_page:
                        rows = table.extract()
                        all_tables.append(
                            [[str(cell) if cell is not None else "" for cell in row] for row in rows]
                        )
            return PDFTableResult(tables=all_tables)
        finally:
            doc.close()

    @classmethod
    def _get_metadata_blocking(cls, file_path: str) -> dict:
        fitz = cls._import_fitz()
        doc = fitz.open(file_path)
        try:
            return {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "producer": doc.metadata.get("producer", ""),
                "format": doc.metadata.get("format", ""),
                "page_count": doc.page_count,
            }
        finally:
            doc.close()

    @staticmethod
    def _resolve_pages(doc, page_range: str | None) -> list[int]:
        total = max(0, doc.page_count)
        if page_range is None:
            return list(range(total))

        pages: set[int] = set()
        for part in page_range.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str.strip()) - 1
                    end = int(end_str.strip()) - 1
                    start = max(0, start)
                    end = min(total - 1, end)
                    pages.update(range(start, end + 1))
                except (ValueError, TypeError):
                    continue
            else:
                try:
                    page_num = int(part.strip()) - 1
                    if 0 <= page_num < total:
                        pages.add(page_num)
                except (ValueError, TypeError):
                    continue

        return sorted(pages)


__all__ = [
    "PyMuPDFBackend",
]
