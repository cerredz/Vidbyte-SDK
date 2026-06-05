from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping, Sequence

from vidbyte.lib.dataclasses.context import ContextMessage, ProgressLog
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, Summarizer


def _is_tool_message(message: ContextMessage) -> bool:
    return message.kind in {"tool_call", "tool_result"}


def _provider_groups(messages: Sequence[ContextMessage]) -> tuple[tuple[ContextMessage, ...], ...]:
    # Groups messages into logical units, pairing each tool call with its immediate result.
    groups: list[tuple[ContextMessage, ...]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.kind == "tool_call" and index + 1 < len(messages) and messages[index + 1].kind == "tool_result":
            groups.append((message, messages[index + 1]))
            index += 2
        else:
            groups.append((message,))
            index += 1
    return tuple(groups)


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


_VALID_TRACE_SCOPES = {"all_non_system", "oldest_n_groups", "oldest_percentage", "middle_keep_bookends"}
_VALID_TRACE_PLACEMENTS = {"summary", "system_suffix", "synthetic_user"}


class ReplaceWithTraceCompaction(BaseCompaction):
    """Replaces a selected region of non-system history with one rendered trace message."""

    def __init__(self, trace_text: str, *, scope: str = "all_non_system", n: int = 0, percentage: float = 0.0, keep_last_groups: int = 0, keep_last_user: bool = False, keep_pinned: bool = False, keep_errors: bool = False, keep_active_branch: str | None = None, placement: str = "summary", trace_marker: str = "continual_trace") -> None:
        # Stores replacement settings and validates scope, placement, and numeric bounds eagerly.
        self.trace_text = trace_text
        self.scope = scope
        self.n = n
        self.percentage = percentage
        self.keep_last_groups = keep_last_groups
        self.keep_last_user = keep_last_user
        self.keep_pinned = keep_pinned
        self.keep_errors = keep_errors
        self.keep_active_branch = keep_active_branch
        self.placement = placement
        self.trace_marker = trace_marker
        self._validate()

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Replaces the scope-selected, unprotected non-system groups with a single trace message.
        if not self.trace_text.strip():
            return tuple(messages)
        system = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        groups = _provider_groups(non_system)
        replaced = self._replaced_group_indices(groups)
        if groups and not replaced:
            return tuple(messages)
        trace_message = self._build_trace_message(sum(len(groups[i]) for i in replaced))
        system_out = system + ([trace_message] if self.placement == "system_suffix" else [])
        body_trace = None if self.placement == "system_suffix" else trace_message
        return tuple(system_out + self._assemble_body(groups, replaced, body_trace))

    def _validate(self) -> None:
        # Raises ValueError for any unsupported scope, placement, or out-of-range numeric option.
        if self.scope not in _VALID_TRACE_SCOPES:
            raise ValueError(f"scope must be one of {sorted(_VALID_TRACE_SCOPES)}.")
        if self.placement not in _VALID_TRACE_PLACEMENTS:
            raise ValueError(f"placement must be one of {sorted(_VALID_TRACE_PLACEMENTS)}.")
        if not 0 <= self.percentage <= 1:
            raise ValueError("percentage must be between 0 and 1.")
        if self.n < 0 or self.keep_last_groups < 0:
            raise ValueError("n and keep_last_groups must be non-negative.")

    def _replaced_group_indices(self, groups: Sequence[tuple[ContextMessage, ...]]) -> set[int]:
        # Selects replaced groups from unprotected candidates, always re-including stale trace markers.
        protected = self._protected_group_indices(groups)
        candidates = [i for i in range(len(groups)) if i not in protected]
        replaced = self._select_by_scope(candidates)
        return replaced | self._groups_matching(groups, self._is_stale_trace)

    def _protected_group_indices(self, groups: Sequence[tuple[ContextMessage, ...]]) -> set[int]:
        # Computes the groups protected from replacement by the configured retention flags.
        protected: set[int] = set()
        if self.keep_last_groups > 0:
            protected |= set(range(max(0, len(groups) - self.keep_last_groups), len(groups)))
        if self.keep_last_user:
            last_user = self._last_user_group(groups)
            if last_user is not None:
                protected.add(last_user)
        if self.keep_pinned:
            protected |= self._groups_matching(groups, self._is_pinned)
        if self.keep_errors:
            protected |= self._groups_matching(groups, self._is_error_result)
        if self.keep_active_branch is not None:
            protected |= self._groups_matching(groups, self._on_active_branch)
        return protected

    def _select_by_scope(self, candidates: Sequence[int]) -> set[int]:
        # Picks which unprotected candidate groups to replace according to the configured scope.
        if self.scope == "oldest_n_groups":
            return set(candidates[: self.n])
        if self.scope == "oldest_percentage":
            return set(candidates[: math.ceil(len(candidates) * self.percentage)])
        if self.scope == "middle_keep_bookends":
            return set(candidates[1:]) if len(candidates) > 1 else set()
        return set(candidates)

    def _assemble_body(self, groups: Sequence[tuple[ContextMessage, ...]], replaced: set[int], trace_message: ContextMessage | None) -> list[ContextMessage]:
        # Rebuilds non-system messages, collapsing the replaced groups into the trace at their position.
        body: list[ContextMessage] = []
        inserted = False
        for index, group in enumerate(groups):
            if index in replaced:
                if trace_message is not None and not inserted:
                    body.append(trace_message)
                    inserted = True
                continue
            body.extend(group)
        if trace_message is not None and not inserted:
            body.append(trace_message)
        return body

    def _build_trace_message(self, replaced_count: int) -> ContextMessage:
        # Builds the single trace message with role/kind chosen by the configured placement.
        metadata = {"compaction": CompactionMode.REPLACE_WITH_TRACE.value, "trace_marker": self.trace_marker, "original_count": replaced_count}
        if self.placement == "synthetic_user":
            return ContextMessage(role="user", content="Continual trace (state so far):\n" + self.trace_text, kind="message", metadata=metadata)
        if self.placement == "system_suffix":
            return ContextMessage(role="system", content=self.trace_text, kind="summary", metadata=metadata)
        return ContextMessage(role="assistant", content=self.trace_text, kind="summary", metadata=metadata)

    def _groups_matching(self, groups: Sequence[tuple[ContextMessage, ...]], predicate: Callable[[ContextMessage], bool]) -> set[int]:
        # Returns indices of groups containing at least one message matching the predicate.
        return {index for index, group in enumerate(groups) if any(predicate(message) for message in group)}

    @staticmethod
    def _last_user_group(groups: Sequence[tuple[ContextMessage, ...]]) -> int | None:
        # Returns the index of the newest group containing a user message, or None.
        for index in range(len(groups) - 1, -1, -1):
            if any(message.role == "user" for message in groups[index]):
                return index
        return None

    @staticmethod
    def _is_pinned(message: ContextMessage) -> bool:
        # Returns whether a message is explicitly pinned via metadata.
        return bool(dict(message.metadata).get("pinned"))

    @staticmethod
    def _is_error_result(message: ContextMessage) -> bool:
        # Returns whether a message is a failed tool result worth preserving.
        return message.kind == "tool_result" and dict(message.metadata).get("status") == "error"

    def _is_stale_trace(self, message: ContextMessage) -> bool:
        # Returns whether a message is a previously injected trace with this strategy's marker.
        return dict(message.metadata).get("trace_marker") == self.trace_marker

    def _on_active_branch(self, message: ContextMessage) -> bool:
        # Returns whether a message belongs to the active snapshot branch or is unbranched.
        metadata = dict(message.metadata)
        branch = metadata.get("branch") or metadata.get("snapshot_branch")
        ancestors = tuple(str(item) for item in metadata.get("branch_ancestors", ()))
        return branch is None or str(branch) == self.keep_active_branch or self.keep_active_branch in ancestors


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
    "ReplaceWithTraceCompaction",
    "StripToolResultBodiesCompaction",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "TruncateToolResultMessagesCompaction",
]
