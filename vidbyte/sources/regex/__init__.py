"""Context Protocol Header

Description:
    Public regex helper package for artifact sources.
Purpose:
    Exposes central source regex helpers without scattering patterns through loaders and
    parsers.
Architecture:
    - SourcesRegex, DocumentRegex, and LlmsTxtRegex helper classes.
Relations:
    Consumed by vidbyte.sources loaders and parser modules.
"""

from __future__ import annotations

from vidbyte.sources.regex.regex import DocumentRegex, LlmsTxtRegex, SourcesRegex

__all__ = [
    "DocumentRegex",
    "LlmsTxtRegex",
    "SourcesRegex",
]
