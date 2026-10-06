"""Context Protocol Header

Description:
    Compatibility exports for llms.txt IR dataclasses.
Purpose:
    Preserves the draft vidbyte.sources.llms_txt.types import path while dataclass
    definitions live in vidbyte.lib.dataclasses.sources.
Architecture:
    - Re-exports LlmsTxtDocument, LlmsTxtLink, and LlmsTxtSection.
Relations:
    Used by parser, loaders, and callers that prefer the llms_txt package path.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection

__all__ = [
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtSection",
]
