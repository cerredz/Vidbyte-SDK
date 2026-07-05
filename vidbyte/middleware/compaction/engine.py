from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, CompactionStats, Summarizer
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
    _head_tail_text,
    _scrub_bloat_text,
)


class ContextCompactionEngine:
    """Apply context compaction strategies to SDK context shapes."""

    def __init__(self, *, summarizer: Summarizer | None = None) -> None:
        # Stores the optional summarizer used by summary-producing modes.
        self.summarizer = summarizer

    async def compact_messages(self, messages: Sequence[ContextMessage], *, mode: CompactionMode | str, options: Mapping[str, Any] | None = None) -> tuple[tuple[ContextMessage, ...], CompactionStats]:
        # Applies a named compaction strategy to generic ContextMessage records.
        selected = self._coerce_mode(mode)
        before = tuple(messages)
        opts = dict(options or {})
        strategy = self._build_strategy(selected, opts)
        after = await strategy.compact(before)
        return after, self._stats(before, after, selected)

    async def compact_provider_messages(self, messages: Sequence[Mapping[str, Any]], *, mode: CompactionMode | str, options: Mapping[str, Any] | None = None) -> tuple[tuple[dict[str, Any], ...], CompactionStats]:
        # Converts provider messages to ContextMessage records, compacts them, and restores dictionaries.
        selected = self._coerce_mode(mode)
        before = tuple(self._provider_to_context_message(m, index) for index, m in enumerate(messages))
        opts = dict(options or {})
        strategy = self._build_strategy(selected, opts)
        compacted = await strategy.compact(before)
        restored = tuple(self._context_message_to_provider(m) for m in compacted)
        return restored, self._stats(before, compacted, selected)

    def compact_tool_result(self, call: ToolCall, result: ToolResult, *, mode: CompactionMode | str, options: Mapping[str, Any] | None = None) -> tuple[ToolResult, CompactionStats]:
        # Applies a tool-result compaction strategy to one model-visible tool result.
        selected = self._coerce_mode(mode)
        opts = dict(options or {})
        if selected is CompactionMode.TRUNCATE_TOOL_RESULTS:
            visible = self._truncate_tool_result(result, int(opts.get("max_chars", 1000)), str(opts.get("truncation_indicator", " [... truncated {count} characters ...]")))
        elif selected is CompactionMode.STRIP_TOOL_RESULT_BODIES:
            visible = self._replace_tool_result(result, str(opts.get("placeholder", "[tool result stripped by compaction]")), {"compaction": selected.value, "original_chars": len(result.output)})
        elif selected is CompactionMode.HIDE_TOOL_RESULTS:
            output = f"Tool '{call.tool_name}' completed with status '{result.status.value}'. Raw tool output was withheld from the model context window."
            visible = self._replace_tool_result(result, output, {"context_window_algorithm": "hide_tool_outputs", "raw_output_hidden": True, "raw_output_chars": len(result.output)})
        elif selected is CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS:
            visible = self._clear_tool_result_with_exclusions(call, result, opts)
        elif selected is CompactionMode.HEAD_TAIL_TOOL_PREVIEW:
            visible = self._head_tail_tool_result(result, opts)
        elif selected is CompactionMode.MECHANICAL_BLOAT_SCRUBBER:
            visible = self._scrub_tool_result(result, opts)
        else:
            visible = result
        stats = CompactionStats(mode=selected.value, before_count=1, after_count=1, metadata=dict(visible.metadata))
        return visible, stats

    def to_context_messages(self, messages: Sequence[Mapping[str, Any]]) -> tuple[ContextMessage, ...]:
        # Converts provider message dictionaries into generic ContextMessage records.
        return tuple(self._provider_to_context_message(m) for m in messages)

    def from_context_messages(self, messages: Sequence[ContextMessage]) -> tuple[dict[str, Any], ...]:
        # Converts ContextMessage records back into provider message dictionaries.
        return tuple(self._context_message_to_provider(m) for m in messages)

    def _build_strategy(self, mode: CompactionMode, options: Mapping[str, Any]) -> BaseCompaction:
        # Creates the appropriate compaction strategy instance for the given mode and options.
        if mode is CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG:
            return ClearExceptSystemAndLogCompaction(progress_log=options.get("progress_log"))
        if mode is CompactionMode.REMOVE_ALL_TOOL_CALLS:
            return RemoveAllToolCallsCompaction()
        if mode is CompactionMode.REMOVE_LAST_N_TOOL_CALLS:
            return RemoveLastNCompaction(int(options.get("n", 0)))
        if mode is CompactionMode.REMOVE_TOOL_CALL_PERCENTAGE:
            return RemoveToolCallPercentageCompaction(float(options.get("percentage", 0)), str(options.get("order", "oldest")))
        if mode is CompactionMode.KEEP_LAST_N_MESSAGES:
            return KeepLastNMessagesCompaction(int(options.get("n", 10)))
        if mode is CompactionMode.STRIP_TOOL_RESULT_BODIES:
            return StripToolResultBodiesCompaction(str(options.get("placeholder", "[tool result stripped by compaction]")))
        if mode is CompactionMode.DEDUPLICATE_TOOL_CALLS:
            return DeduplicateToolCallsCompaction()
        if mode is CompactionMode.REPLACE_WITH_TRACE:
            return ReplaceWithTraceCompaction(
                str(options.get("trace_text", "")),
                scope=str(options.get("scope", "all_non_system")),
                n=int(options.get("n", 0)),
                percentage=float(options.get("percentage", 0.0)),
                keep_last_groups=int(options.get("keep_last_groups", 0)),
                keep_last_user=bool(options.get("keep_last_user", False)),
                keep_pinned=bool(options.get("keep_pinned", False)),
                keep_errors=bool(options.get("keep_errors", False)),
                keep_active_branch=options.get("keep_active_branch"),
                placement=str(options.get("placement", "summary")),
                trace_marker=str(options.get("trace_marker", "continual_trace")),
            )
        if mode is CompactionMode.TRUNCATE_TOOL_RESULTS:
            return TruncateToolResultMessagesCompaction(int(options.get("max_chars", 1000)), str(options.get("truncation_indicator", " [... truncated {count} characters ...]")))
        if mode is CompactionMode.TRIM_TO_TOKEN_BUDGET:
            return TrimToTokenBudgetCompaction(int(options.get("max_tokens", 0)), options.get("token_counter"), bool(options.get("preserve_system", True)))
        if mode is CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES:
            max_messages = options.get("max_messages")
            max_tokens = options.get("max_tokens")
            return TrimWithProviderBoundariesCompaction(None if max_messages is None else int(max_messages), None if max_tokens is None else int(max_tokens), options.get("token_counter"))
        if mode is CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE:
            start = options.get("start")
            end = options.get("end")
            return DeleteMessagesByIdOrRangeCompaction(self._string_tuple(options.get("message_ids", ())), None if start is None else int(start), None if end is None else int(end))
        if mode is CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW:
            raw_mode = options.get("window_mode", CompactionMode.TRUNCATE_TOOL_RESULTS)
            window_mode = raw_mode if isinstance(raw_mode, CompactionMode) else CompactionMode(str(raw_mode))
            return ToolOutputSlidingWindowCompaction(int(options.get("keep_recent", 2)), window_mode, int(options.get("max_chars", 600)), str(options.get("placeholder", "[older tool result cleared by compaction]")), int(options.get("head_chars", 400)), int(options.get("tail_chars", 200)))
        if mode is CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS:
            return ToolResultClearingWithExclusionsCompaction(self._string_tuple(options.get("exclude_tools", ())), str(options.get("placeholder", "[tool result cleared by compaction]")))
        if mode is CompactionMode.HEAD_TAIL_TOOL_PREVIEW:
            return HeadTailToolPreviewCompaction(int(options.get("head_chars", 400)), int(options.get("tail_chars", 200)), str(options.get("indicator", "\n...[omitted {count} characters]...\n")))
        if mode is CompactionMode.MECHANICAL_BLOAT_SCRUBBER:
            return MechanicalBloatScrubberCompaction(int(options.get("base64_min_chars", 80)), int(options.get("max_repeated_lines", 3)), str(options.get("placeholder", "[scrubbed {kind}: {count} chars]")))
        if mode is CompactionMode.SUMMARY_WITH_BACKREFS:
            start = options.get("start")
            end = options.get("end")
            return SummaryWithBackrefsCompaction(None if start is None else int(start), None if end is None else int(end), int(options.get("excerpt_chars", 120)))
        if mode is CompactionMode.SELECTIVE_CONTEXT_PRUNING:
            return SelectiveContextPruningCompaction(bool(options.get("remove_empty", True)), bool(options.get("remove_duplicates", True)), self._string_tuple(options.get("boilerplate_patterns", ())), int(options.get("min_unique_terms", 0)))
        if mode is CompactionMode.SALIENCE_SCORE_EVICTION:
            max_tokens = options.get("max_tokens")
            return SalienceScoreEvictionCompaction(int(options.get("max_messages", 10)), None if max_tokens is None else int(max_tokens), options.get("token_counter"))
        if mode is CompactionMode.QUERY_RELEVANCE_FILTER:
            max_messages = options.get("max_messages")
            return QueryRelevanceFilterCompaction(str(options.get("query", "")), None if max_messages is None else int(max_messages), int(options.get("min_score", 1)), int(options.get("keep_recent", 0)))
        if mode is CompactionMode.CONTEXT_SNAPSHOT_BRANCH_TRIM:
            return ContextSnapshotBranchTrimCompaction(str(options.get("active_branch", "")), bool(options.get("include_ancestors", True)))
        if mode is CompactionMode.SUMMARIZE_OLDEST_N:
            self._require_summarizer("summarize_oldest_n")
            return SummarizeOldestNCompaction(self.summarizer, int(options.get("n", 5)))  # type: ignore[arg-type]
        if mode is CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS:
            self._require_summarizer("summarize_by_topic_blocks")
            return SummarizeByTopicBlocksCompaction(self.summarizer, int(options.get("block_size", 10)))  # type: ignore[arg-type]
        if mode is CompactionMode.SUMMARIZE_RANGE:
            self._require_summarizer("summarize_range")
            return SummarizeRangeCompaction(self.summarizer, int(options.get("keep_last", 3)))  # type: ignore[arg-type]
        return NoOpCompaction()

    def _truncate_tool_result(self, result: ToolResult, max_chars: int, truncation_indicator: str) -> ToolResult:
        # Truncates one ToolResult output while preserving status and base metadata.
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        if len(result.output) <= max_chars:
            return result
        count = len(result.output) - max_chars
        formatted = truncation_indicator.replace("{count}", str(count))
        output = result.output[:max_chars].rstrip() + formatted
        return self._replace_tool_result(result, output, {"context_window_algorithm": "compact_tool_outputs", "raw_output_compacted": True, "raw_output_chars": len(result.output), "compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value, "original_chars": len(result.output), "truncated_chars": count})

    def _clear_tool_result_with_exclusions(self, call: ToolCall, result: ToolResult, options: Mapping[str, Any]) -> ToolResult:
        # Clears one model-visible tool result unless its tool name is excluded.
        excluded = set(self._string_tuple(options.get("exclude_tools", ())))
        if call.tool_name in excluded:
            return result
        placeholder = str(options.get("placeholder", "[tool result cleared by compaction]"))
        return self._replace_tool_result(result, placeholder, {"compaction": CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS.value, "original_chars": len(result.output), "raw_output_cleared": True})

    def _head_tail_tool_result(self, result: ToolResult, options: Mapping[str, Any]) -> ToolResult:
        # Replaces one long model-visible tool result with a head/tail preview.
        preview, omitted = _head_tail_text(result.output, int(options.get("head_chars", 400)), int(options.get("tail_chars", 200)), str(options.get("indicator", "\n...[omitted {count} characters]...\n")))
        if not omitted:
            return result
        return self._replace_tool_result(result, preview, {"compaction": CompactionMode.HEAD_TAIL_TOOL_PREVIEW.value, "original_chars": len(result.output), "omitted_chars": omitted})

    def _scrub_tool_result(self, result: ToolResult, options: Mapping[str, Any]) -> ToolResult:
        # Scrubs mechanical bloat from one model-visible tool result.
        scrubbed, stats = _scrub_bloat_text(result.output, base64_min_chars=int(options.get("base64_min_chars", 80)), max_repeated_lines=int(options.get("max_repeated_lines", 3)), placeholder=str(options.get("placeholder", "[scrubbed {kind}: {count} chars]")))
        if scrubbed == result.output:
            return result
        return self._replace_tool_result(result, scrubbed, {"compaction": CompactionMode.MECHANICAL_BLOAT_SCRUBBER.value, **stats})

    def _provider_to_context_message(self, message: Mapping[str, Any], index: int = 0) -> ContextMessage:
        # Converts a provider message dictionary into a generic ContextMessage.
        raw = dict(message)
        role = str(raw.get("role", "assistant"))
        kind = self._provider_message_kind(raw)
        content = self._provider_message_content(raw)
        return ContextMessage(role=role, content=content, kind=kind, metadata={"provider_message": raw, "provider_index": index, "provider_id": self._provider_message_id(raw, index), "tool_name": self._provider_tool_name(raw)})

    def _context_message_to_provider(self, message: ContextMessage) -> dict[str, Any]:
        # Converts a compacted ContextMessage back to a provider message dictionary.
        original = message.metadata.get("provider_message") if isinstance(message.metadata, Mapping) else None
        if isinstance(original, Mapping):
            return self._replace_provider_content(dict(original), message.content)
        return {"role": "assistant" if message.role != "system" else "system", "content": message.content}

    def _provider_message_kind(self, message: Mapping[str, Any]) -> str:
        # Classifies provider message dictionaries for compaction decisions.
        if message.get("role") == "tool" or "tool_call_id" in message:
            return "tool_result"
        if "tool_calls" in message:
            return "tool_call"
        content = message.get("content")
        if isinstance(content, list) and any(isinstance(item, Mapping) and item.get("type") == "tool_result" for item in content):
            return "tool_result"
        parts = message.get("parts")
        if isinstance(parts, list) and any(isinstance(item, Mapping) and "functionResponse" in item for item in parts):
            return "tool_result"
        return "message"

    def _provider_message_content(self, message: Mapping[str, Any]) -> str:
        # Extracts comparable text content from known provider message shapes.
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            values = []
            for item in content:
                if isinstance(item, Mapping):
                    values.append(str(item.get("content") or item.get("text") or item))
                else:
                    values.append(str(item))
            return "\n".join(values)
        parts = message.get("parts")
        if isinstance(parts, list):
            return "\n".join(str(part) for part in parts)
        return str(content or message)

    def _provider_message_id(self, message: Mapping[str, Any], index: int) -> str:
        # Extracts stable provider IDs when available, otherwise uses the original index.
        for key in ("id", "message_id", "call_id", "tool_call_id"):
            value = message.get(key)
            if value is not None:
                return str(value)
        return str(index)

    def _provider_tool_name(self, message: Mapping[str, Any]) -> str | None:
        # Extracts tool names from common provider tool call/result message shapes.
        for key in ("name", "tool_name"):
            value = message.get(key)
            if value is not None:
                return str(value)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
            for call in tool_calls:
                if isinstance(call, Mapping):
                    function = call.get("function")
                    if isinstance(function, Mapping) and function.get("name") is not None:
                        return str(function["name"])
                    if call.get("name") is not None:
                        return str(call["name"])
        return None

    def _replace_provider_content(self, message: dict[str, Any], content: str) -> dict[str, Any]:
        # Replaces content in known provider message shapes without changing other fields.
        if isinstance(message.get("content"), str):
            message["content"] = content
            return message
        raw_content = message.get("content")
        if isinstance(raw_content, list):
            items = [dict(item) if isinstance(item, Mapping) else item for item in raw_content]
            for item in items:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    item["content"] = content
                    message["content"] = items
                    return message
            message["content"] = content
            return message
        parts = message.get("parts")
        if isinstance(parts, list):
            replaced = []
            for part in parts:
                if isinstance(part, Mapping) and isinstance(part.get("functionResponse"), Mapping):
                    raw_response = dict(part["functionResponse"])
                    response = dict(raw_response.get("response", {}))
                    response["output"] = content
                    raw_response["response"] = response
                    replaced.append({"functionResponse": raw_response})
                else:
                    replaced.append(part)
            message["parts"] = replaced
            return message
        message["content"] = content
        return message

    def _stats(self, before: Sequence[ContextMessage], after: Sequence[ContextMessage], mode: CompactionMode) -> CompactionStats:
        # Builds bounded compaction statistics for metadata and legacy tool results.
        tool_before = sum(1 for m in before if m.kind in {"tool_call", "tool_result"})
        tool_after = sum(1 for m in after if m.kind in {"tool_call", "tool_result"})
        return CompactionStats(mode=mode.value, before_count=len(before), after_count=len(after), removed_count=len(before) - len(after), removed_tool_messages=tool_before - tool_after)

    def _require_summarizer(self, mode: str) -> None:
        # Raises when a summary mode is requested without an injected summarizer.
        if self.summarizer is None:
            raise ValueError(f"{mode} requires an injected summarizer.")

    def _replace_tool_result(self, result: ToolResult, output: str, metadata: Mapping[str, Any]) -> ToolResult:
        # Returns a ToolResult with replaced output and merged metadata.
        return ToolResult(tool_name=result.tool_name, status=result.status, output=output, metadata={**dict(result.metadata), **dict(metadata)})

    def _string_tuple(self, value: object) -> tuple[str, ...]:
        # Converts scalar or sequence option values into a tuple of strings.
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return tuple(str(item) for item in value)
        return (str(value),)

    def _coerce_mode(self, mode: CompactionMode | str) -> CompactionMode:
        # Normalizes enum objects and raw strings into a CompactionMode.
        if isinstance(mode, CompactionMode):
            return mode
        return CompactionMode(str(mode))


__all__ = [
    "ContextCompactionEngine",
]
