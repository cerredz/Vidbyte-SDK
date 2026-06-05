from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from vidbyte.lib.dataclasses.context import ContextMessage


class CompactionMode(str, Enum):
    """Supported context compaction strategies."""

    CLEAR_EXCEPT_SYSTEM_AND_LOG = "clear_except_system_and_log"
    REMOVE_ALL_TOOL_CALLS = "remove_all_tool_calls"
    REMOVE_LAST_N_TOOL_CALLS = "remove_last_n_tool_calls"
    REMOVE_TOOL_CALL_PERCENTAGE = "remove_tool_call_percentage"
    SUMMARIZE_RANGE = "summarize_range"
    KEEP_LAST_N_MESSAGES = "keep_last_n_messages"
    SUMMARIZE_OLDEST_N = "summarize_oldest_n"
    STRIP_TOOL_RESULT_BODIES = "strip_tool_result_bodies"
    DEDUPLICATE_TOOL_CALLS = "deduplicate_tool_calls"
    SUMMARIZE_BY_TOPIC_BLOCKS = "summarize_by_topic_blocks"
    TRUNCATE_TOOL_RESULTS = "truncate_tool_results"
    HIDE_TOOL_RESULTS = "hide_tool_results"
    REPLACE_WITH_TRACE = "replace_with_trace"
    TRIM_TO_TOKEN_BUDGET = "trim_to_token_budget"
    TRIM_WITH_PROVIDER_BOUNDARIES = "trim_with_provider_boundaries"
    DELETE_MESSAGES_BY_ID_OR_RANGE = "delete_messages_by_id_or_range"
    TOOL_OUTPUT_SLIDING_WINDOW = "tool_output_sliding_window"
    TOOL_RESULT_CLEARING_WITH_EXCLUSIONS = "tool_result_clearing_with_exclusions"
    HEAD_TAIL_TOOL_PREVIEW = "head_tail_tool_preview"
    MECHANICAL_BLOAT_SCRUBBER = "mechanical_bloat_scrubber"
    SUMMARY_WITH_BACKREFS = "summary_with_backrefs"
    SELECTIVE_CONTEXT_PRUNING = "selective_context_pruning"
    SALIENCE_SCORE_EVICTION = "salience_score_eviction"
    QUERY_RELEVANCE_FILTER = "query_relevance_filter"
    CONTEXT_SNAPSHOT_BRANCH_TRIM = "context_snapshot_branch_trim"


class Summarizer(Protocol):
    """Protocol for optional async model-backed summarizers."""

    async def summarize(self, messages: Sequence[ContextMessage]) -> str:
        # Returns a compact summary of the supplied messages.
        ...


TokenCounter = Callable[[str], int]


@dataclass(frozen=True, slots=True)
class CompactionStats:
    """Summary statistics for one compaction operation."""

    mode: str
    before_count: int = 0
    after_count: int = 0
    removed_count: int = 0
    removed_tool_messages: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


class BaseCompaction(ABC):
    """Abstract base class for all message-level compaction strategies."""

    @abstractmethod
    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        """Apply this compaction strategy to the given messages."""
        ...


__all__ = [
    "BaseCompaction",
    "CompactionMode",
    "CompactionStats",
    "Summarizer",
    "TokenCounter",
]
