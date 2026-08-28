"""Context Protocol Header

Description:
    Public surface for the llms.txt artifact source.
Purpose:
    Exports the llms.txt parser, typed IR, and loader while keeping the concrete loader under
    vidbyte.sources.loaders.
Architecture:
    - Re-exports LlmsTxtParser, parse_llms_txt, LlmsTxtSource, and the LlmsTxt* IR types.
Relations:
    Aggregated into vidbyte.sources.__init__.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sources import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection
from vidbyte.sources.llms_txt.parser import LlmsTxtParser, parse_llms_txt

__all__ = [
    "LlmsTxtDocument",
    "LlmsTxtLink",
    "LlmsTxtParser",
    "LlmsTxtSection",
    "LlmsTxtSource",
    "parse_llms_txt",
]


def __getattr__(name: str) -> object:
    # Lazily resolves the loader to avoid parser/loader import cycles.
    if name == "LlmsTxtSource":
        from vidbyte.sources.loaders.llms_txt import LlmsTxtSource

        return LlmsTxtSource
    raise AttributeError(name)
