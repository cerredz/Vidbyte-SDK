"""Context Protocol Header

Description:
    Public surface for the llms.txt artifact source.
Purpose:
    Exports the loader, its parser, and its typed IR so callers can import from
    vidbyte.sources.llms_txt directly.
Architecture:
    - Re-exports LlmsTxtSource, parse_llms_txt, and the LlmsTxt* IR types.
Relations:
    Aggregated into vidbyte.sources.__init__.
"""

from __future__ import annotations

from vidbyte.sources.llms_txt.loader import LlmsTxtSource
from vidbyte.sources.llms_txt.parser import parse_llms_txt
from vidbyte.sources.llms_txt.types import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection

__all__ = [
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtSection",
    "LlmsTxtSource",
    "parse_llms_txt",
]
