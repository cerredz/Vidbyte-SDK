from __future__ import annotations

from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, CompactionStats, Summarizer, TokenCounter
from vidbyte.middleware.compaction.context_compaction import MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware, TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
from vidbyte.middleware.compaction.strategies import (
    ClearExceptSystemAndLogCompaction,
    DeduplicateToolCallsCompaction,
    KeepLastNMessagesCompaction,
    NoOpCompaction,
    RemoveAllToolCallsCompaction,
    RemoveLastNCompaction,
    RemoveToolCallPercentageCompaction,
    ReplaceWithTraceCompaction,
    StripToolResultBodiesCompaction,
    SummarizeByTopicBlocksCompaction,
    SummarizeOldestNCompaction,
    SummarizeRangeCompaction,
    TruncateToolResultMessagesCompaction,
)
from vidbyte.middleware.compaction.trace_render import TraceArtifactRenderer

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
    "ReplaceWithTraceCompaction",
    "StripToolResultBodiesCompaction",
    "Summarizer",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "SummaryCompactionMiddleware",
    "TokenCounter",
    "ToolResultCompactionMiddleware",
    "TraceArtifactRenderer",
    "TraceReplacementCompactionMiddleware",
    "TraceSummaryTailCompactionMiddleware",
    "TruncateToolResultMessagesCompaction",
]
