"""Context Protocol Header

Description:
    Exports built-in code search tools.
Purpose:
    Provides a stable import surface for root-scoped glob, grep, and
    semantic-style search.
Architecture:
    - GlobTool: Finds files by path pattern.
    - GrepTool: Finds line matches in text files.
    - SemanticSearchTool: Ranks code chunks for natural-language queries.
Relations:
    Related to vidbyte.tools.builtins and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.code_search.glob import GlobTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.code_search.semantic import EmbeddingProvider, SemanticSearchTool

__all__ = [
    "EmbeddingProvider",
    "GlobTool",
    "GrepTool",
    "SemanticSearchTool",
]
