"""Context Protocol Header

Description:
    Compatibility exports for the generic document source loader.
Purpose:
    Preserves the draft vidbyte.sources.document import path while the authoritative loader
    lives under vidbyte.sources.loaders.document.
Architecture:
    - Re-exports DocumentSource and MarkdownDocument.
Relations:
    New code may import from vidbyte.sources.loaders.document or vidbyte.sources.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import MarkdownDocument
from vidbyte.sources.loaders.document import DocumentSource

__all__ = [
    "DocumentSource",
    "MarkdownDocument",
]
