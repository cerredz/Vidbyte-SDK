"""Context Protocol Header

Description:
    Exports built-in code search tools.
Purpose:
    Provides a stable import surface for root-scoped glob, grep,
    semantic-style search, and InfiniteMemory's ranked memory search.
Architecture:
    - GlobTool: Finds files by path pattern.
    - GrepTool: Finds line matches in text files.
    - SemanticSearchTool: Ranks code chunks for natural-language queries.
    - InfiniteSearchMemoryTool: Ranks a memory workspace's live entries and
      note lines with a shared full-text index (search_memory).
Relations:
    Related to vidbyte.tools.builtins and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.code_search.glob import GlobTool
from vidbyte.tools.builtins.code_search.grep import GrepTool
from vidbyte.tools.builtins.code_search.search_memory import InfiniteSearchMemoryTool
from vidbyte.tools.builtins.code_search.semantic import EmbeddingProvider, SemanticSearchTool

__all__ = [
    "EmbeddingProvider",
    "GlobTool",
    "GrepTool",
    "InfiniteSearchMemoryTool",
    "SemanticSearchTool",
]
