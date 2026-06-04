from __future__ import annotations

from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, CompactionStats, Summarizer
from vidbyte.middleware.compaction.context_compaction import MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
from vidbyte.middleware.compaction.strategies import (
    ClearExceptSystemAndLogCompaction,
    DeduplicateToolCallsCompaction,
    KeepLastNMessagesCompaction,
    NoOpCompaction,
    RemoveAllToolCallsCompaction,
    RemoveLastNCompaction,
    RemoveToolCallPercentageCompaction,
    StripToolResultBodiesCompaction,
    SummarizeByTopicBlocksCompaction,
    SummarizeOldestNCompaction,
    SummarizeRangeCompaction,
    TruncateToolResultMessagesCompaction,
)

__all__ = [
    "BaseCompaction",
    "ClearExceptSystemAndLogCompaction",
    "CompactionMode",
    "CompactionStats",
    "ContextCompactionEngine",
    "DeduplicateToolCallsCompaction",
    "KeepLastNMessagesCompaction",
    "MessageHistoryCompactionMiddleware",
    "NoOpCompaction",
    "RemoveAllToolCallsCompaction",
    "RemoveLastNCompaction",
    "RemoveToolCallPercentageCompaction",
    "StripToolResultBodiesCompaction",
    "Summarizer",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "SummaryCompactionMiddleware",
    "ToolResultCompactionMiddleware",
    "TruncateToolResultMessagesCompaction",
]
