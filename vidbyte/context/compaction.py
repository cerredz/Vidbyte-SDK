"""Context Protocol Header

Description:
    Provides shared context compaction algorithms for tools and middleware.
Purpose:
    Keeps compaction behavior in one implementation so model-visible tools,
    middleware, and context-window compatibility presets cannot drift apart.
Architecture:
    - CompactionMode: Stable names for all supported compaction strategies.
    - ContextCompactionEngine: Applies compaction to ContextMessage sequences,
      ToolResult payloads, and provider message dictionaries.
Relations:
    Used by vidbyte.tools.builtins.context.compaction, middleware built-ins, and
    context-window compatibility helpers.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from vidbyte.lib.dataclasses.context import ContextMessage, ProgressLog
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult


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


class Summarizer(Protocol):
    """Protocol for optional async model-backed summarizers."""

    async def summarize(self, messages: Sequence[ContextMessage]) -> str:
        # Returns a compact summary of the supplied messages.
        ...


@dataclass(frozen=True, slots=True)
class CompactionStats:
    """Summary statistics for one compaction operation."""

    mode: str
    before_count: int = 0
    after_count: int = 0
    removed_count: int = 0
    removed_tool_messages: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


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
        after = await self._apply_message_mode(before, selected, opts)
        return after, self._stats(before, after, selected)

    async def compact_provider_messages(self, messages: Sequence[Mapping[str, Any]], *, mode: CompactionMode | str, options: Mapping[str, Any] | None = None) -> tuple[tuple[dict[str, Any], ...], CompactionStats]:
        # Converts provider messages to ContextMessage records, compacts them, and restores dictionaries.
        selected = self._coerce_mode(mode)
        before = tuple(self._provider_to_context_message(message) for message in messages)
        compacted = await self._apply_message_mode(before, selected, dict(options or {}))
        restored = tuple(self._context_message_to_provider(message) for message in compacted)
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

    async def _apply_message_mode(self, messages: Sequence[ContextMessage], mode: CompactionMode, options: Mapping[str, Any]) -> tuple[ContextMessage, ...]:
        # Dispatches message compaction modes to their concrete implementation.
        if mode is CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG:
            return self._clear_except_system_and_log(messages, options.get("progress_log"))
        if mode is CompactionMode.REMOVE_ALL_TOOL_CALLS:
            return tuple(message for message in messages if not self._is_tool_message(message))
        if mode is CompactionMode.REMOVE_LAST_N_TOOL_CALLS:
            return self._remove_last_n(messages, int(options.get("n", 0)))
        if mode is CompactionMode.REMOVE_TOOL_CALL_PERCENTAGE:
            return self._remove_percentage(messages, float(options.get("percentage", 0)), str(options.get("order", "oldest")))
        if mode is CompactionMode.KEEP_LAST_N_MESSAGES:
            return self._keep_last_n_messages(messages, int(options.get("n", 10)))
        if mode is CompactionMode.STRIP_TOOL_RESULT_BODIES:
            return self._strip_tool_result_bodies(messages, str(options.get("placeholder", "[tool result stripped by compaction]")))
        if mode is CompactionMode.DEDUPLICATE_TOOL_CALLS:
            return self._deduplicate_tool_calls(messages)
        if mode is CompactionMode.TRUNCATE_TOOL_RESULTS:
            return self._truncate_tool_result_messages(messages, int(options.get("max_chars", 1000)), str(options.get("truncation_indicator", " [... truncated {count} characters ...]")))
        if mode is CompactionMode.SUMMARIZE_OLDEST_N:
            return await self._summarize_oldest_n(messages, int(options.get("n", 5)))
        if mode is CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS:
            return await self._summarize_by_topic_blocks(messages, int(options.get("block_size", 10)))
        if mode is CompactionMode.SUMMARIZE_RANGE:
            return await self._summarize_range(messages, int(options.get("keep_last", 3)))
        return tuple(messages)

    def _clear_except_system_and_log(self, messages: Sequence[ContextMessage], raw_log: object) -> tuple[ContextMessage, ...]:
        # Keeps system messages and appends one compact progress summary.
        system_messages = tuple(message for message in messages if message.role == "system")
        progress_log = self._progress_log(raw_log)
        summary = ContextMessage(role="assistant", content=progress_log.to_markdown(), kind="summary", metadata={"compaction": CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG.value})
        return system_messages + (summary,)

    def _remove_last_n(self, messages: Sequence[ContextMessage], n: int) -> tuple[ContextMessage, ...]:
        # Removes the newest n tool-call or tool-result messages.
        if n <= 0:
            return tuple(messages)
        remove_indexes: set[int] = set()
        for index in range(len(messages) - 1, -1, -1):
            if self._is_tool_message(messages[index]):
                remove_indexes.add(index)
                if len(remove_indexes) >= n:
                    break
        return tuple(message for index, message in enumerate(messages) if index not in remove_indexes)

    def _remove_percentage(self, messages: Sequence[ContextMessage], percentage: float, order: str) -> tuple[ContextMessage, ...]:
        # Removes a percentage of tool messages from the oldest or newest side.
        if not 0 <= percentage <= 1:
            raise ValueError("percentage must be between 0 and 1.")
        if order not in {"oldest", "newest"}:
            raise ValueError("order must be 'oldest' or 'newest'.")
        tool_indexes = [index for index, message in enumerate(messages) if self._is_tool_message(message)]
        count = math.ceil(len(tool_indexes) * percentage)
        if order == "newest":
            selected = set(tool_indexes[-count:] if count else ())
        else:
            selected = set(tool_indexes[:count])
        return tuple(message for index, message in enumerate(messages) if index not in selected)

    def _keep_last_n_messages(self, messages: Sequence[ContextMessage], n: int) -> tuple[ContextMessage, ...]:
        # Keeps system messages and the last n non-system messages.
        n = max(0, n)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        return system + non_system[-n:] if n else system

    def _strip_tool_result_bodies(self, messages: Sequence[ContextMessage], placeholder: str) -> tuple[ContextMessage, ...]:
        # Replaces tool-result message bodies with a compact placeholder.
        result = []
        for message in messages:
            if message.kind == "tool_result":
                result.append(dataclasses.replace(message, content=placeholder, metadata={**dict(message.metadata), "compaction": CompactionMode.STRIP_TOOL_RESULT_BODIES.value, "original_chars": len(message.content)}))
            else:
                result.append(message)
        return tuple(result)

    def _truncate_tool_result_messages(self, messages: Sequence[ContextMessage], max_chars: int, truncation_indicator: str) -> tuple[ContextMessage, ...]:
        # Truncates tool-result message bodies that exceed the configured limit.
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        result = []
        for message in messages:
            if message.kind == "tool_result" and len(message.content) > max_chars:
                count = len(message.content) - max_chars
                formatted = truncation_indicator.replace("{count}", str(count))
                result.append(dataclasses.replace(message, content=message.content[:max_chars] + formatted, metadata={**dict(message.metadata), "compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value, "original_chars": len(message.content), "truncated_chars": count}))
            else:
                result.append(message)
        return tuple(result)

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

    def _deduplicate_tool_calls(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Removes duplicate tool-call/result pairs while keeping the first occurrence.
        seen_call_content: set[str] = set()
        remove_indexes: set[int] = set()
        for index, message in enumerate(messages):
            if message.kind == "tool_call":
                if message.content in seen_call_content:
                    remove_indexes.add(index)
                    if index + 1 < len(messages) and messages[index + 1].kind == "tool_result":
                        remove_indexes.add(index + 1)
                else:
                    seen_call_content.add(message.content)
        return tuple(message for index, message in enumerate(messages) if index not in remove_indexes)

    async def _summarize_range(self, messages: Sequence[ContextMessage], keep_last: int) -> tuple[ContextMessage, ...]:
        # Summarizes middle history while preserving system and recent messages.
        self._require_summarizer("summarize_range")
        keep_last = max(0, keep_last)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        recent = non_system[-keep_last:] if keep_last else ()
        middle = non_system[:-keep_last] if keep_last else non_system
        if not middle:
            return tuple(messages)
        summary_text = await self.summarizer.summarize(middle)  # type: ignore[union-attr]
        summary = ContextMessage(role="assistant", content=summary_text, kind="summary", metadata={"compaction": CompactionMode.SUMMARIZE_RANGE.value})
        return system + (summary,) + tuple(recent)

    async def _summarize_oldest_n(self, messages: Sequence[ContextMessage], n: int) -> tuple[ContextMessage, ...]:
        # Summarizes the oldest n non-system messages and keeps the rest verbatim.
        self._require_summarizer("summarize_oldest_n")
        n = max(0, n)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        to_summarize = non_system[:n]
        rest = non_system[n:]
        if not to_summarize:
            return tuple(messages)
        summary_text = await self.summarizer.summarize(to_summarize)  # type: ignore[union-attr]
        summary = ContextMessage(role="assistant", content=summary_text, kind="summary", metadata={"compaction": CompactionMode.SUMMARIZE_OLDEST_N.value})
        return system + (summary,) + rest

    async def _summarize_by_topic_blocks(self, messages: Sequence[ContextMessage], block_size: int) -> tuple[ContextMessage, ...]:
        # Splits non-system history into blocks and summarizes each block.
        self._require_summarizer("summarize_by_topic_blocks")
        block_size = max(1, block_size)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        if not non_system:
            return tuple(messages)
        blocks = [non_system[index : index + block_size] for index in range(0, len(non_system), block_size)]
        summaries = []
        for block_index, block in enumerate(blocks):
            summary_text = await self.summarizer.summarize(block)  # type: ignore[union-attr]
            summaries.append(ContextMessage(role="assistant", content=summary_text, kind="summary", metadata={"compaction": CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS.value, "block_index": block_index}))
        return system + tuple(summaries)

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
        tool_before = sum(1 for message in before if self._is_tool_message(message))
        tool_after = sum(1 for message in after if self._is_tool_message(message))
        return CompactionStats(mode=mode.value, before_count=len(before), after_count=len(after), removed_count=len(before) - len(after), removed_tool_messages=tool_before - tool_after)

    def _progress_log(self, raw_log: object) -> ProgressLog:
        # Converts mapping-like progress-log input into a ProgressLog dataclass.
        if not isinstance(raw_log, Mapping):
            return ProgressLog()
        return ProgressLog(completed_tasks=tuple(str(item) for item in raw_log.get("completed_tasks", ())), touched_files=tuple(str(item) for item in raw_log.get("touched_files", ())), decisions=tuple(str(item) for item in raw_log.get("decisions", ())), errors=tuple(str(item) for item in raw_log.get("errors", ())), next_steps=tuple(str(item) for item in raw_log.get("next_steps", ())))

    def _require_summarizer(self, mode: str) -> None:
        # Raises when a summary mode is requested without an injected summarizer.
        if self.summarizer is None:
            raise ValueError(f"{mode} requires an injected summarizer.")

    def _is_tool_message(self, message: ContextMessage) -> bool:
        # Returns whether a generic context message represents a tool trace.
        return message.kind in {"tool_call", "tool_result"}

    def _replace_tool_result(self, result: ToolResult, output: str, metadata: Mapping[str, Any]) -> ToolResult:
        # Returns a ToolResult with replaced output and merged metadata.
        return ToolResult(tool_name=result.tool_name, status=result.status, output=output, metadata={**dict(result.metadata), **dict(metadata)})

    def _coerce_mode(self, mode: CompactionMode | str) -> CompactionMode:
        # Normalizes enum objects and raw strings into a CompactionMode.
        if isinstance(mode, CompactionMode):
            return mode
        return CompactionMode(str(mode))


__all__ = [
    "CompactionMode",
    "CompactionStats",
    "ContextCompactionEngine",
    "Summarizer",
]
