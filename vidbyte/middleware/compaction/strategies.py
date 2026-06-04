from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence

from vidbyte.lib.dataclasses.context import ContextMessage, ProgressLog
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, Summarizer


def _is_tool_message(message: ContextMessage) -> bool:
    return message.kind in {"tool_call", "tool_result"}


def _build_progress_log(raw_log: object) -> ProgressLog:
    if not isinstance(raw_log, Mapping):
        return ProgressLog()
    return ProgressLog(
        completed_tasks=tuple(str(item) for item in raw_log.get("completed_tasks", ())),
        touched_files=tuple(str(item) for item in raw_log.get("touched_files", ())),
        decisions=tuple(str(item) for item in raw_log.get("decisions", ())),
        errors=tuple(str(item) for item in raw_log.get("errors", ())),
        next_steps=tuple(str(item) for item in raw_log.get("next_steps", ())),
    )


class ClearExceptSystemAndLogCompaction(BaseCompaction):
    """Keeps system messages and appends one compact progress summary."""

    def __init__(self, progress_log: object = None) -> None:
        self.raw_log = progress_log

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        system_messages = tuple(m for m in messages if m.role == "system")
        log = _build_progress_log(self.raw_log)
        summary = ContextMessage(
            role="assistant",
            content=log.to_markdown(),
            kind="summary",
            metadata={"compaction": CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG.value},
        )
        return system_messages + (summary,)


class RemoveAllToolCallsCompaction(BaseCompaction):
    """Removes all tool-call and tool-result messages."""

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        return tuple(m for m in messages if not _is_tool_message(m))


class RemoveLastNCompaction(BaseCompaction):
    """Removes the newest n tool-call or tool-result messages."""

    def __init__(self, n: int) -> None:
        self.n = n

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        if self.n <= 0:
            return tuple(messages)
        remove_indexes: set[int] = set()
        for index in range(len(messages) - 1, -1, -1):
            if _is_tool_message(messages[index]):
                remove_indexes.add(index)
                if len(remove_indexes) >= self.n:
                    break
        return tuple(m for i, m in enumerate(messages) if i not in remove_indexes)


class RemoveToolCallPercentageCompaction(BaseCompaction):
    """Removes a percentage of tool messages from the oldest or newest side."""

    def __init__(self, percentage: float, order: str = "oldest") -> None:
        if not 0 <= percentage <= 1:
            raise ValueError("percentage must be between 0 and 1.")
        if order not in {"oldest", "newest"}:
            raise ValueError("order must be 'oldest' or 'newest'.")
        self.percentage = percentage
        self.order = order

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        tool_indexes = [i for i, m in enumerate(messages) if _is_tool_message(m)]
        count = math.ceil(len(tool_indexes) * self.percentage)
        if self.order == "newest":
            selected = set(tool_indexes[-count:] if count else ())
        else:
            selected = set(tool_indexes[:count])
        return tuple(m for i, m in enumerate(messages) if i not in selected)


class KeepLastNMessagesCompaction(BaseCompaction):
    """Keeps system messages and the last n non-system messages."""

    def __init__(self, n: int) -> None:
        self.n = max(0, n)

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        system = tuple(m for m in messages if m.role == "system")
        non_system = tuple(m for m in messages if m.role != "system")
        return system + non_system[-self.n:] if self.n else system


class StripToolResultBodiesCompaction(BaseCompaction):
    """Replaces tool-result message bodies with a compact placeholder."""

    def __init__(self, placeholder: str = "[tool result stripped by compaction]") -> None:
        self.placeholder = placeholder

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        result = []
        for message in messages:
            if message.kind == "tool_result":
                result.append(dataclasses.replace(
                    message,
                    content=self.placeholder,
                    metadata={
                        **dict(message.metadata),
                        "compaction": CompactionMode.STRIP_TOOL_RESULT_BODIES.value,
                        "original_chars": len(message.content),
                    },
                ))
            else:
                result.append(message)
        return tuple(result)


class TruncateToolResultMessagesCompaction(BaseCompaction):
    """Truncates tool-result message bodies that exceed the configured limit."""

    def __init__(self, max_chars: int = 1000, truncation_indicator: str = " [... truncated {count} characters ...]") -> None:
        if max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        self.max_chars = max_chars
        self.truncation_indicator = truncation_indicator

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        result = []
        for message in messages:
            if message.kind == "tool_result" and len(message.content) > self.max_chars:
                count = len(message.content) - self.max_chars
                formatted = self.truncation_indicator.replace("{count}", str(count))
                result.append(dataclasses.replace(
                    message,
                    content=message.content[:self.max_chars] + formatted,
                    metadata={
                        **dict(message.metadata),
                        "compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                        "original_chars": len(message.content),
                        "truncated_chars": count,
                    },
                ))
            else:
                result.append(message)
        return tuple(result)


class DeduplicateToolCallsCompaction(BaseCompaction):
    """Removes duplicate tool-call/result pairs while keeping the first occurrence."""

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
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
        return tuple(m for i, m in enumerate(messages) if i not in remove_indexes)


class SummarizeRangeCompaction(BaseCompaction):
    """Summarizes middle history while preserving system and recent messages."""

    def __init__(self, summarizer: Summarizer, keep_last: int = 3) -> None:
        if summarizer is None:
            raise ValueError("summarize_range requires an injected summarizer.")
        self.summarizer = summarizer
        self.keep_last = max(0, keep_last)

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        system = tuple(m for m in messages if m.role == "system")
        non_system = tuple(m for m in messages if m.role != "system")
        recent = non_system[-self.keep_last:] if self.keep_last else ()
        middle = non_system[:-self.keep_last] if self.keep_last else non_system
        if not middle:
            return tuple(messages)
        summary_text = await self.summarizer.summarize(middle)
        summary = ContextMessage(
            role="assistant",
            content=summary_text,
            kind="summary",
            metadata={"compaction": CompactionMode.SUMMARIZE_RANGE.value},
        )
        return system + (summary,) + tuple(recent)


class SummarizeOldestNCompaction(BaseCompaction):
    """Summarizes the oldest n non-system messages and keeps the rest verbatim."""

    def __init__(self, summarizer: Summarizer, n: int = 5) -> None:
        if summarizer is None:
            raise ValueError("summarize_oldest_n requires an injected summarizer.")
        self.summarizer = summarizer
        self.n = max(0, n)

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        system = tuple(m for m in messages if m.role == "system")
        non_system = tuple(m for m in messages if m.role != "system")
        to_summarize = non_system[:self.n]
        rest = non_system[self.n:]
        if not to_summarize:
            return tuple(messages)
        summary_text = await self.summarizer.summarize(to_summarize)
        summary = ContextMessage(
            role="assistant",
            content=summary_text,
            kind="summary",
            metadata={"compaction": CompactionMode.SUMMARIZE_OLDEST_N.value},
        )
        return system + (summary,) + rest


class SummarizeByTopicBlocksCompaction(BaseCompaction):
    """Splits non-system history into blocks and summarizes each block."""

    def __init__(self, summarizer: Summarizer, block_size: int = 10) -> None:
        if summarizer is None:
            raise ValueError("summarize_by_topic_blocks requires an injected summarizer.")
        self.summarizer = summarizer
        self.block_size = max(1, block_size)

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        system = tuple(m for m in messages if m.role == "system")
        non_system = tuple(m for m in messages if m.role != "system")
        if not non_system:
            return tuple(messages)
        blocks = [non_system[i:i + self.block_size] for i in range(0, len(non_system), self.block_size)]
        summaries = []
        for block_index, block in enumerate(blocks):
            summary_text = await self.summarizer.summarize(block)
            summaries.append(ContextMessage(
                role="assistant",
                content=summary_text,
                kind="summary",
                metadata={"compaction": CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS.value, "block_index": block_index},
            ))
        return system + tuple(summaries)


class NoOpCompaction(BaseCompaction):
    """Returns messages unchanged; used as a safe fallback for unknown modes."""

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        return tuple(messages)


__all__ = [
    "ClearExceptSystemAndLogCompaction",
    "DeduplicateToolCallsCompaction",
    "KeepLastNMessagesCompaction",
    "NoOpCompaction",
    "RemoveAllToolCallsCompaction",
    "RemoveLastNCompaction",
    "RemoveToolCallPercentageCompaction",
    "StripToolResultBodiesCompaction",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "TruncateToolResultMessagesCompaction",
]
