"""Context Protocol Header

Description:
    Public loader package for artifact sources.
Purpose:
    Groups concrete source-to-context-item loaders under a semantic package separate from
    source contracts, fetchers, caches, regex helpers, and parsers.
Architecture:
    - DocumentSource: Single-document loader.
    - LlmsTxtSource: llms.txt index and expansion loader.
Relations:
    Re-exported by vidbyte.sources.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import MarkdownDocument
from vidbyte.sources.loaders.document import DocumentSource
from vidbyte.sources.loaders.llms_txt import LlmsTxtSource

__all__ = [
    "DocumentSource",
    "LlmsTxtSource",
    "MarkdownDocument",
]
