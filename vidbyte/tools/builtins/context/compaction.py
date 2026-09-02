"""Context Protocol Header

Description:
    Provides the legacy model-visible context compaction tool wrapper.
Purpose:
    Preserves the existing `compact_context` tool API while delegating actual
    compaction behavior to vidbyte.context.compaction.
Architecture:
    - ContextCompactionTool: Compatibility tool that mutates an injected ContextState.
Relations:
    Uses shared compaction contracts from vidbyte.context.compaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine, Summarizer
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.context.types import ContextState
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ContextCompactionTool(BaseTool):
    """Apply named compaction strategies to an injected context state."""

    def __init__(self, state: ContextState, *, summarizer: Summarizer | None = None) -> None:
        # Stores the mutable state and shared compaction engine for compatibility use.
        self.state = state
        self.engine = ContextCompactionEngine(summarizer=summarizer)

    def spec(self) -> ToolSpec:
        # Returns the existing model-facing declaration for the legacy compaction tool.
        return ToolSpec(
            name="compact_context",
            description=(
                "Compact agent context by clearing, summarizing, or removing tool traces. "
                "Modes: clear_except_system_and_log, remove_all_tool_calls, "
                "remove_last_n_tool_calls, remove_tool_call_percentage, summarize_range, "
                "keep_last_n_messages, summarize_oldest_n, strip_tool_result_bodies, "
                "deduplicate_tool_calls, summarize_by_topic_blocks, truncate_tool_results, "
                "trim_to_token_budget, trim_with_provider_boundaries, delete_messages_by_id_or_range, "
                "tool_output_sliding_window, tool_result_clearing_with_exclusions, "
                "head_tail_tool_preview, mechanical_bloat_scrubber, summary_with_backrefs, "
                "selective_context_pruning, salience_score_eviction, query_relevance_filter, "
                "context_snapshot_branch_trim."
            ),
            permission=ToolPermission.SAFE,
            parameters=(
                ToolParameter("mode", "string", "Compaction strategy name."),
                ToolParameter("n", "integer", "Number of messages or tool pairs to act on.", required=False),
                ToolParameter("percentage", "number", "Fraction of tool messages to remove.", required=False),
                ToolParameter("order", "string", "'oldest' or 'newest' for percentage removal.", required=False),
                ToolParameter("keep_last", "integer", "Recent messages to preserve for summarization.", required=False),
                ToolParameter("block_size", "integer", "Messages per block for block summarization.", required=False),
                ToolParameter("progress_log", "object", "Structured progress log fields.", required=False),
                ToolParameter("max_chars", "integer", "Maximum characters to keep for tool results when truncating.", required=False),
                ToolParameter("max_tokens", "integer", "Maximum deterministic token budget for token trimming modes.", required=False),
                ToolParameter("max_messages", "integer", "Maximum messages to keep for bounded trim, relevance, or salience modes.", required=False),
                ToolParameter("message_ids", "array", "Provider or context message IDs to delete.", required=False),
                ToolParameter("start", "integer", "Zero-based inclusive start index for range modes.", required=False),
                ToolParameter("end", "integer", "Zero-based inclusive end index for range modes.", required=False),
                ToolParameter("keep_recent", "integer", "Recent tool outputs or messages to preserve.", required=False),
                ToolParameter("head_chars", "integer", "Characters to keep from the head of long tool outputs.", required=False),
                ToolParameter("tail_chars", "integer", "Characters to keep from the tail of long tool outputs.", required=False),
                ToolParameter("exclude_tools", "array", "Tool names whose outputs should not be cleared.", required=False),
                ToolParameter("query", "string", "Lexical query used by query_relevance_filter.", required=False),
                ToolParameter("min_score", "integer", "Minimum lexical overlap required by relevance filtering.", required=False),
                ToolParameter("active_branch", "string", "Active branch ID for context snapshot branch trimming.", required=False),
                ToolParameter("truncation_indicator", "string", "Custom indicator suffix or replacement text.", required=False),
                ToolParameter("placeholder", "string", "Custom replacement placeholder for clearing and scrubbing modes.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Dispatches the requested compaction mode and replaces state only after success.
        try:
            mode = CompactionMode(str(call.arguments["mode"]))
            options = self._options(call.arguments)
            before = tuple(self.state.messages())
            after, stats = await self.engine.compact_messages(before, mode=mode, options=options)
        except KeyError:
            return ToolResult.error(self.name, "Missing compaction mode.", metadata={"error": "missing_mode"})
        except ValueError as exc:
            return self._mode_error(str(exc))

        self.state.replace_messages(after)
        return ToolResult.success(
            self.name,
            f"Context compacted. Messages: {stats.before_count} -> {stats.after_count}.",
            metadata={
                "before_count": stats.before_count,
                "after_count": stats.after_count,
                "removed_count": stats.removed_count,
                "removed_tool_messages": stats.removed_tool_messages,
            },
        )

    def _options(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        # Copies call arguments into engine options without exposing the mapping for mutation.
        return dict(arguments)

    def _mode_error(self, message: str) -> ToolResult:
        # Converts shared-engine validation failures into legacy ToolResult errors.
        if "is not a valid CompactionMode" in message:
            return ToolResult.error(self.name, "Unknown compaction mode.", metadata={"error": "bad_mode"})
        if "requires an injected summarizer" in message:
            return ToolResult.error(self.name, message, metadata={"error": "missing_summarizer"})
        return ToolResult.error(self.name, message)


__all__ = [
    "CompactionMode",
    "ContextCompactionTool",
    "Summarizer",
]
