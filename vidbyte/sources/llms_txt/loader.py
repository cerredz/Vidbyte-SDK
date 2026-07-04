"""Context Protocol Header

Description:
    Compatibility exports for the llms.txt source loader.
Purpose:
    Preserves the draft vidbyte.sources.llms_txt.loader import path while the authoritative
    loader lives under vidbyte.sources.loaders.llms_txt.
Architecture:
    - Re-exports LlmsTxtSource.
Relations:
    New code may import from vidbyte.sources.loaders.llms_txt or vidbyte.sources.llms_txt.
"""

from __future__ import annotations

from vidbyte.sources.loaders.llms_txt import LlmsTxtSource

__all__ = [
    "LlmsTxtSource",
]
