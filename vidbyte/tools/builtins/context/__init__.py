"""Context Protocol Header

Description:
    Exports context compaction tools and types.
Purpose:
    Provides a stable import surface for agent context memory reduction.
Architecture:
    - ContextCompactionTool and CompactionMode from compaction.
    - ContextMessage, ContextState, and ProgressLog from types.
Relations:
    Related to vidbyte.tools.builtins and future agent loop state modules.
"""

from __future__ import annotations

from vidbyte.tools.builtins.context.compaction import CompactionMode, ContextCompactionTool
from vidbyte.tools.builtins.context.types import ContextMessage, ContextState, ProgressLog

__all__ = [
    "CompactionMode",
    "ContextCompactionTool",
    "ContextMessage",
    "ContextState",
    "ProgressLog",
]
