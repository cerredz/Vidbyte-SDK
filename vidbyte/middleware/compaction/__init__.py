"""
FILE: vidbyte/middleware/compaction/__init__.py

PURPOSE:
    Defines package re-exports and the public import surface for this folder.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/compaction/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.middleware.compaction.base: imported by this file.
    - vidbyte.middleware.compaction.context_compaction: imported by this file.
    - vidbyte.middleware.compaction.engine: imported by this file.
    - vidbyte.middleware.compaction.strategies: imported by this file.
    - vidbyte.middleware.compaction.trace_render: imported by this file.

FUNCTION INVENTORY:
    - BaseCompaction (export): public or navigational symbol owned here.
    - ClearExceptSystemAndLogCompaction (export): public or navigational symbol owned here.
    - CompactionMode (export): public or navigational symbol owned here.
    - CompactionStats (export): public or navigational symbol owned here.
    - ContextSnapshotBranchTrimCompaction (export): public or navigational symbol owned here.
    - ContextCompactionEngine (export): public or navigational symbol owned here.
    - DeduplicateToolCallsCompaction (export): public or navigational symbol owned here.
    - DeleteMessagesByIdOrRangeCompaction (export): public or navigational symbol owned here.
    - HeadTailToolPreviewCompaction (export): public or navigational symbol owned here.
    - KeepLastNMessagesCompaction (export): public or navigational symbol owned here.
    - MechanicalBloatScrubberCompaction (export): public or navigational symbol owned here.
    - MessageHistoryCompactionMiddleware (export): public or navigational symbol owned here.
    - NoOpCompaction (export): public or navigational symbol owned here.
    - QueryRelevanceFilterCompaction (export): public or navigational symbol owned here.
    - RemoveAllToolCallsCompaction (export): public or navigational symbol owned here.
    - RemoveLastNCompaction (export): public or navigational symbol owned here.
    - RemoveToolCallPercentageCompaction (export): public or navigational symbol owned here.
    - ReplaceWithTraceCompaction (export): public or navigational symbol owned here.
    - SalienceScoreEvictionCompaction (export): public or navigational symbol owned here.
    - SelectiveContextPruningCompaction (export): public or navigational symbol owned here.
    - StripToolResultBodiesCompaction (export): public or navigational symbol owned here.
    - Summarizer (export): public or navigational symbol owned here.
    - SummaryWithBackrefsCompaction (export): public or navigational symbol owned here.
    - SummarizeByTopicBlocksCompaction (export): public or navigational symbol owned here.
    - SummarizeOldestNCompaction (export): public or navigational symbol owned here.
    - SummarizeRangeCompaction (export): public or navigational symbol owned here.
    - SummaryCompactionMiddleware (export): public or navigational symbol owned here.
    - TokenCounter (export): public or navigational symbol owned here.
    - ToolResultCompactionMiddleware (export): public or navigational symbol owned here.
    - ToolOutputSlidingWindowCompaction (export): public or navigational symbol owned here.
    - ToolResultClearingWithExclusionsCompaction (export): public or navigational symbol owned here.
    - TraceArtifactRenderer (export): public or navigational symbol owned here.
    - TraceReplacementCompactionMiddleware (export): public or navigational symbol owned here.
    - TraceSummaryTailCompactionMiddleware (export): public or navigational symbol owned here.
    - TrimToTokenBudgetCompaction (export): public or navigational symbol owned here.
    - TrimWithProviderBoundariesCompaction (export): public or navigational symbol owned here.
    - TruncateToolResultMessagesCompaction (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - No explicit concurrency primitive; keep future mutable state local to calls unless documented here.
"""

from __future__ import annotations

from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, CompactionStats, Summarizer, TokenCounter
from vidbyte.middleware.compaction.context_compaction import MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware, TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
from vidbyte.middleware.compaction.strategies import (
    ClearExceptSystemAndLogCompaction,
    ContextSnapshotBranchTrimCompaction,
    DeduplicateToolCallsCompaction,
    DeleteMessagesByIdOrRangeCompaction,
    HeadTailToolPreviewCompaction,
    KeepLastNMessagesCompaction,
    MechanicalBloatScrubberCompaction,
    NoOpCompaction,
    QueryRelevanceFilterCompaction,
    RemoveAllToolCallsCompaction,
    RemoveLastNCompaction,
    RemoveToolCallPercentageCompaction,
    ReplaceWithTraceCompaction,
    SalienceScoreEvictionCompaction,
    SelectiveContextPruningCompaction,
    StripToolResultBodiesCompaction,
    SummaryWithBackrefsCompaction,
    SummarizeByTopicBlocksCompaction,
    SummarizeOldestNCompaction,
    SummarizeRangeCompaction,
    ToolOutputSlidingWindowCompaction,
    ToolResultClearingWithExclusionsCompaction,
    TrimToTokenBudgetCompaction,
    TrimWithProviderBoundariesCompaction,
    TruncateToolResultMessagesCompaction,
)
from vidbyte.middleware.compaction.trace_render import TraceArtifactRenderer

__all__ = [
    "BaseCompaction",
    "ClearExceptSystemAndLogCompaction",
    "CompactionMode",
    "CompactionStats",
    "ContextSnapshotBranchTrimCompaction",
    "ContextCompactionEngine",
    "DeduplicateToolCallsCompaction",
    "DeleteMessagesByIdOrRangeCompaction",
    "HeadTailToolPreviewCompaction",
    "KeepLastNMessagesCompaction",
    "MechanicalBloatScrubberCompaction",
    "MessageHistoryCompactionMiddleware",
    "NoOpCompaction",
    "QueryRelevanceFilterCompaction",
    "RemoveAllToolCallsCompaction",
    "RemoveLastNCompaction",
    "RemoveToolCallPercentageCompaction",
    "ReplaceWithTraceCompaction",
    "SalienceScoreEvictionCompaction",
    "SelectiveContextPruningCompaction",
    "StripToolResultBodiesCompaction",
    "Summarizer",
    "SummaryWithBackrefsCompaction",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "SummaryCompactionMiddleware",
    "TokenCounter",
    "ToolResultCompactionMiddleware",
    "ToolOutputSlidingWindowCompaction",
    "ToolResultClearingWithExclusionsCompaction",
    "TraceArtifactRenderer",
    "TraceReplacementCompactionMiddleware",
    "TraceSummaryTailCompactionMiddleware",
    "TrimToTokenBudgetCompaction",
    "TrimWithProviderBoundariesCompaction",
    "TruncateToolResultMessagesCompaction",
]
