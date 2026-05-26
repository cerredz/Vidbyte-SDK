"""Context Protocol Header

Description:
    Re-exports PDF backend implementations for built-in PDF tools.
Purpose:
    Provides a single import surface for all PDF provider backends.
Architecture:
    - BasePdfBackend: Abstract contract for PDF operations.
    - PyMuPDFBackend: High-performance text extraction via pymupdf (fitz).
    - PDFPlumberBackend: Robust table extraction via pdfplumber.
Relations:
    Related to vidbyte.tools.builtins.pdf.
"""

from __future__ import annotations

from vidbyte.lib.providers.pdf.base import BasePdfBackend
from vidbyte.lib.providers.pdf.pdfplumber_backend import PDFPlumberBackend
from vidbyte.lib.providers.pdf.pymupdf_backend import PyMuPDFBackend

__all__ = [
    "BasePdfBackend",
    "PDFPlumberBackend",
    "PyMuPDFBackend",
]
