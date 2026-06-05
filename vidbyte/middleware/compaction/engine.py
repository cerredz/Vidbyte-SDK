from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, CompactionStats, Summarizer
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
        before = tuple(self._provider_to_context_message(m) for m in messages)
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

    def _provider_to_context_message(self, message: Mapping[str, Any]) -> ContextMessage:
        # Converts a provider message dictionary into a generic ContextMessage.
        raw = dict(message)
        role = str(raw.get("role", "assistant"))
        kind = self._provider_message_kind(raw)
        content = self._provider_message_content(raw)
        return ContextMessage(role=role, content=content, kind=kind, metadata={"provider_message": raw})

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

    def _coerce_mode(self, mode: CompactionMode | str) -> CompactionMode:
        # Normalizes enum objects and raw strings into a CompactionMode.
        if isinstance(mode, CompactionMode):
            return mode
        return CompactionMode(str(mode))


__all__ = [
    "ContextCompactionEngine",
]
