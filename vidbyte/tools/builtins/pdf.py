"""Context Protocol Header

Description:
    Defines built-in PDF tools using the @tool decorator for extracting text,
    tables, and metadata from PDF files.
Purpose:
    Provides PDF file inspection capabilities for agentic workflows.
Architecture:
    - pdf_read: Extracts text from PDF, preferring PyMuPDF, falling back to pdfplumber.
    - pdf_read_tables: Extracts tables as markdown pipe tables, with page annotations.
    - pdf_metadata: Returns structured metadata (author, title, page count, etc.).
    - All tools are decorated with @tool(permission=ToolPermission.READ).
Relations:
    Related to vidbyte.lib.providers.pdf and vidbyte.lib.providers.pdf.base.
"""

from __future__ import annotations

import logging

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

logger = logging.getLogger(__name__)
MAX_OUTPUT_CHARS = 50000


def _format_markdown_table(table: list[list[str]]) -> str:
    if not table:
        return ""
    lines: list[str] = []
    header = table[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in table[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[:len(header)]) + " |")
    return "\n".join(lines)


def _truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[Output truncated at {max_chars} characters]"


@tool(permission=ToolPermission.READ)
async def pdf_read(file_path: str, page_range: str | None = None) -> str:
    """Extract text from a PDF file.

    Args:
        file_path: Path to the PDF file
        page_range: Optional page range like '1-5' or '1,3,5'. If None, extracts all pages.
    """
    backend = _get_backend()
    try:
        result = await backend.read_text(file_path, page_range)
        output = result.text if result.text else "(No text extracted)"
        return _truncate(output)
    except FileNotFoundError as exc:
        return str(exc)
    except Exception as exc:
        logger.exception("pdf_read failed")
        return f"Failed to read PDF: {exc}"


@tool(permission=ToolPermission.READ)
async def pdf_read_tables(file_path: str, page_range: str | None = None) -> str:
    """Extract tables from a PDF file as markdown tables."""
    backend = _get_backend()
    try:
        result = await backend.read_tables(file_path, page_range)
        if not result.tables:
            return "(No tables found)"

        parts: list[str] = []
        for idx, table in enumerate(result.tables, start=1):
            page_info = f"Table {idx} (page ...):"
            parts.append(page_info)
            parts.append(_format_markdown_table(table))
            parts.append("")

        return _truncate("\n".join(parts))
    except FileNotFoundError as exc:
        return str(exc)
    except Exception as exc:
        logger.exception("pdf_read_tables failed")
        return f"Failed to extract tables: {exc}"


@tool(permission=ToolPermission.READ)
async def pdf_metadata(file_path: str) -> str:
    """Get metadata from a PDF file (author, title, pages, etc.)."""
    backend = _get_backend()
    try:
        meta = await backend.get_metadata(file_path)
        lines = [
            f"Title:       {meta.get('title', '')}",
            f"Author:      {meta.get('author', '')}",
            f"Subject:     {meta.get('subject', '')}",
            f"Creator:     {meta.get('creator', '')}",
            f"Producer:    {meta.get('producer', '')}",
            f"Format:      {meta.get('format', '')}",
            f"Page Count:  {meta.get('page_count', '')}",
        ]
        return "\n".join(lines)
    except FileNotFoundError as exc:
        return str(exc)
    except Exception as exc:
        logger.exception("pdf_metadata failed")
        return f"Failed to get metadata: {exc}"


def _get_backend():
    try:
        from vidbyte.lib.providers.pdf.pymupdf_backend import PyMuPDFBackend
        backend = PyMuPDFBackend()
        backend._import_fitz()
        return backend
    except ImportError:
        pass
    try:
        from vidbyte.lib.providers.pdf.pdfplumber_backend import PDFPlumberBackend
        return PDFPlumberBackend()
    except ImportError:
        raise ImportError(
            "No PDF backend available. Install one of: pip install pymupdf  or  pip install pdfplumber"
        )
