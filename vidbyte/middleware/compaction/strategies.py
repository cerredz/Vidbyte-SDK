from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Mapping, Sequence

from vidbyte.lib.dataclasses.context import ContextMessage, ProgressLog
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, Summarizer, TokenCounter


_ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_BASE64_PATTERN = re.compile(r"\b[A-Za-z0-9+/]+={0,2}\b")
_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _is_tool_message(message: ContextMessage) -> bool:
    # Returns true for context records that represent tool calls or tool outputs.
    return message.kind in {"tool_call", "tool_result"}


def _build_progress_log(raw_log: object) -> ProgressLog:
    # Coerces loose mapping data into the structured progress-log dataclass.
    if not isinstance(raw_log, Mapping):
        return ProgressLog()
    return ProgressLog(
        completed_tasks=tuple(str(item) for item in raw_log.get("completed_tasks", ())),
        touched_files=tuple(str(item) for item in raw_log.get("touched_files", ())),
        decisions=tuple(str(item) for item in raw_log.get("decisions", ())),
        errors=tuple(str(item) for item in raw_log.get("errors", ())),
        next_steps=tuple(str(item) for item in raw_log.get("next_steps", ())),
    )


def _approximate_token_count(text: str) -> int:
    # Estimates tokens deterministically with the common four-characters-per-token heuristic.
    return max(1, math.ceil(len(text) / 4)) if text else 0


def _message_tokens(message: ContextMessage, token_counter: TokenCounter | None) -> int:
    # Counts one message body using an injected counter when available, otherwise the local heuristic.
    counter = token_counter or _approximate_token_count
    return max(0, int(counter(message.content)))


def _message_identifier(message: ContextMessage, fallback_index: int) -> str:
    # Extracts a stable message identifier from metadata, falling back to the provider index.
    metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
    for key in ("provider_id", "provider_index", "id", "message_id", "call_id", "tool_call_id"):
        value = metadata.get(key)
        if value is not None:
            return str(value)
    raw = metadata.get("provider_message")
    if isinstance(raw, Mapping):
        for key in ("id", "message_id", "call_id", "tool_call_id"):
            value = raw.get(key)
            if value is not None:
                return str(value)
    return str(fallback_index)


def _message_tool_name(message: ContextMessage) -> str | None:
    # Pulls a tool name from normalized metadata or common provider-message shapes.
    metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
    value = metadata.get("tool_name")
    if value is not None:
        return str(value)
    raw = metadata.get("provider_message")
    if not isinstance(raw, Mapping):
        return None
    for key in ("name", "tool_name"):
        if raw.get(key) is not None:
            return str(raw[key])
    tool_calls = raw.get("tool_calls")
    if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
        for call in tool_calls:
            if isinstance(call, Mapping):
                function = call.get("function")
                if isinstance(function, Mapping) and function.get("name") is not None:
                    return str(function["name"])
                if call.get("name") is not None:
                    return str(call["name"])
    return None


def _message_terms(message: ContextMessage) -> set[str]:
    # Tokenizes message content into lowercase terms for deterministic relevance scoring.
    return {match.group(0).lower() for match in _TERM_PATTERN.finditer(message.content)}


def _replace_message_content(message: ContextMessage, content: str, metadata: Mapping[str, object]) -> ContextMessage:
    # Returns a copied message with replaced body text and merged compaction metadata.
    return dataclasses.replace(message, content=content, metadata={**dict(message.metadata), **dict(metadata)})


def _head_tail_text(content: str, head_chars: int, tail_chars: int, indicator: str) -> tuple[str, int]:
    # Builds a deterministic head/tail preview and returns the omitted character count.
    head = max(0, head_chars)
    tail = max(0, tail_chars)
    if len(content) <= head + tail:
        return content, 0
    omitted = len(content) - head - tail
    marker = indicator.replace("{count}", str(omitted))
    if tail:
        return content[:head].rstrip() + marker + content[-tail:].lstrip(), omitted
    return content[:head].rstrip() + marker, omitted


def _scrub_bloat_text(content: str, *, base64_min_chars: int, max_repeated_lines: int, placeholder: str) -> tuple[str, dict[str, int]]:
    # Removes common mechanical bloat patterns while reporting what was scrubbed.
    stats = {"ansi_sequences": 0, "base64_spans": 0, "repeated_lines": 0}

    def replace_ansi(match: re.Match[str]) -> str:
        # Replaces one ANSI escape sequence and increments the scrub counter.
        stats["ansi_sequences"] += 1
        return ""

    scrubbed = _ANSI_PATTERN.sub(replace_ansi, content)

    def replace_base64(match: re.Match[str]) -> str:
        # Replaces one long base64-like span with a bounded placeholder.
        text = match.group(0)
        if len(text) < base64_min_chars:
            return text
        stats["base64_spans"] += 1
        return placeholder.replace("{kind}", "base64").replace("{count}", str(len(text)))

    scrubbed = _BASE64_PATTERN.sub(replace_base64, scrubbed)
    if max_repeated_lines >= 0:
        lines = scrubbed.splitlines()
        counts: dict[str, int] = {}
        kept: list[str] = []
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
            if counts[line] <= max_repeated_lines:
                kept.append(line)
            else:
                stats["repeated_lines"] += 1
        scrubbed = "\n".join(kept)
    return scrubbed, stats


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


class TrimToTokenBudgetCompaction(BaseCompaction):
    """Keeps highest-recency messages within a deterministic token budget."""

    def __init__(self, max_tokens: int, token_counter: TokenCounter | None = None, preserve_system: bool = True) -> None:
        # Stores the token budget and optional exact counter used for trimming.
        if max_tokens < 0:
            raise ValueError("max_tokens must be non-negative.")
        self.max_tokens = max_tokens
        self.token_counter = token_counter
        self.preserve_system = preserve_system

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Selects system messages first, then newest messages that still fit the budget.
        remaining = self.max_tokens
        keep_indexes: set[int] = set()
        if self.preserve_system:
            for index, message in enumerate(messages):
                if message.role == "system":
                    keep_indexes.add(index)
                    remaining -= _message_tokens(message, self.token_counter)
        if remaining < 0:
            return tuple(message for index, message in enumerate(messages) if index in keep_indexes)
        for index in range(len(messages) - 1, -1, -1):
            if index in keep_indexes:
                continue
            cost = _message_tokens(messages[index], self.token_counter)
            if cost <= remaining:
                keep_indexes.add(index)
                remaining -= cost
        return tuple(message for index, message in enumerate(messages) if index in keep_indexes)


class TrimWithProviderBoundariesCompaction(BaseCompaction):
    """Trims message history while avoiding orphaned tool-call/result boundaries."""

    def __init__(self, max_messages: int | None = None, max_tokens: int | None = None, token_counter: TokenCounter | None = None) -> None:
        # Stores count and token bounds used after provider-boundary repair.
        if max_messages is not None and max_messages < 0:
            raise ValueError("max_messages must be non-negative.")
        if max_tokens is not None and max_tokens < 0:
            raise ValueError("max_tokens must be non-negative.")
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.token_counter = token_counter

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Trims from the oldest side, repairs tool boundaries, then optionally applies token trimming.
        if self.max_messages is None:
            selected = tuple(messages)
        else:
            selected_indexes = set(range(max(0, len(messages) - self.max_messages), len(messages)))
            selected_indexes.update(self._boundary_repairs(messages, selected_indexes))
            selected = tuple(message for index, message in enumerate(messages) if index in selected_indexes)
        if self.max_tokens is None:
            return selected
        return await TrimToTokenBudgetCompaction(self.max_tokens, self.token_counter, preserve_system=True).compact(selected)

    def _boundary_repairs(self, messages: Sequence[ContextMessage], selected_indexes: set[int]) -> set[int]:
        # Finds adjacent call/result records needed to avoid broken provider transcript shapes.
        repairs: set[int] = set()
        for index in tuple(selected_indexes):
            message = messages[index]
            if message.kind == "tool_result" and index > 0 and messages[index - 1].kind == "tool_call":
                repairs.add(index - 1)
            if message.kind == "tool_call" and index + 1 < len(messages) and messages[index + 1].kind == "tool_result":
                repairs.add(index + 1)
        return repairs


class DeleteMessagesByIdOrRangeCompaction(BaseCompaction):
    """Deletes explicitly identified messages or a zero-based index range."""

    def __init__(self, message_ids: Sequence[str] = (), start: int | None = None, end: int | None = None) -> None:
        # Stores explicit message identifiers and optional inclusive index range.
        self.message_ids = {str(item) for item in message_ids}
        self.start = start
        self.end = end

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Removes messages matching the configured ID set or inclusive range.
        return tuple(message for index, message in enumerate(messages) if not self._should_delete(message, index))

    def _should_delete(self, message: ContextMessage, index: int) -> bool:
        # Checks whether one message is targeted by ID or by configured range.
        if self.message_ids and _message_identifier(message, index) in self.message_ids:
            return True
        if self.start is None and self.end is None:
            return False
        start = 0 if self.start is None else self.start
        end = math.inf if self.end is None else self.end
        return start <= index <= end


class ToolOutputSlidingWindowCompaction(BaseCompaction):
    """Compacts older tool outputs while preserving the most recent outputs per tool."""

    def __init__(self, keep_recent: int = 2, mode: CompactionMode = CompactionMode.TRUNCATE_TOOL_RESULTS, max_chars: int = 600, placeholder: str = "[older tool result cleared by compaction]", head_chars: int = 400, tail_chars: int = 200) -> None:
        # Stores the per-tool sliding-window size and the compaction style for older results.
        if keep_recent < 0:
            raise ValueError("keep_recent must be non-negative.")
        self.keep_recent = keep_recent
        self.mode = mode
        self.max_chars = max_chars
        self.placeholder = placeholder
        self.head_chars = head_chars
        self.tail_chars = tail_chars

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Counts tool outputs from newest to oldest and compacts those outside each tool window.
        remaining: dict[str, int] = {}
        result: list[ContextMessage] = list(messages)
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.kind != "tool_result":
                continue
            tool_name = _message_tool_name(message) or "_unknown"
            seen = remaining.get(tool_name, 0)
            remaining[tool_name] = seen + 1
            if seen >= self.keep_recent:
                result[index] = self._compact_older_result(message)
        return tuple(result)

    def _compact_older_result(self, message: ContextMessage) -> ContextMessage:
        # Applies the configured deterministic compaction to one older tool result.
        if self.mode is CompactionMode.STRIP_TOOL_RESULT_BODIES:
            return _replace_message_content(message, self.placeholder, {"compaction": self.mode.value, "original_chars": len(message.content)})
        if self.mode is CompactionMode.HEAD_TAIL_TOOL_PREVIEW:
            preview, omitted = _head_tail_text(message.content, self.head_chars, self.tail_chars, "\n...[omitted {count} characters]...\n")
            if omitted:
                return _replace_message_content(message, preview, {"compaction": self.mode.value, "original_chars": len(message.content), "omitted_chars": omitted})
            return message
        if len(message.content) <= self.max_chars:
            return message
        omitted = len(message.content) - self.max_chars
        content = message.content[:self.max_chars] + f" [... truncated {omitted} characters ...]"
        return _replace_message_content(message, content, {"compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value, "original_chars": len(message.content), "truncated_chars": omitted})


class ToolResultClearingWithExclusionsCompaction(BaseCompaction):
    """Clears tool results except for explicitly excluded tool names."""

    def __init__(self, exclude_tools: Sequence[str] = (), placeholder: str = "[tool result cleared by compaction]") -> None:
        # Stores the allow-list of tool names whose outputs must remain visible.
        self.exclude_tools = {str(name) for name in exclude_tools}
        self.placeholder = placeholder

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Replaces non-excluded tool result bodies with a small placeholder.
        result = []
        for message in messages:
            tool_name = _message_tool_name(message)
            if message.kind == "tool_result" and tool_name not in self.exclude_tools:
                result.append(_replace_message_content(message, self.placeholder, {"compaction": CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS.value, "original_chars": len(message.content), "raw_output_cleared": True}))
            else:
                result.append(message)
        return tuple(result)


class HeadTailToolPreviewCompaction(BaseCompaction):
    """Replaces long tool results with head/tail previews."""

    def __init__(self, head_chars: int = 400, tail_chars: int = 200, indicator: str = "\n...[omitted {count} characters]...\n") -> None:
        # Stores the preview bounds and omission marker for tool-result bodies.
        if head_chars < 0 or tail_chars < 0:
            raise ValueError("head_chars and tail_chars must be non-negative.")
        self.head_chars = head_chars
        self.tail_chars = tail_chars
        self.indicator = indicator

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Applies head/tail previews to oversized tool-result messages only.
        result = []
        for message in messages:
            if message.kind == "tool_result":
                preview, omitted = _head_tail_text(message.content, self.head_chars, self.tail_chars, self.indicator)
                if omitted:
                    result.append(_replace_message_content(message, preview, {"compaction": CompactionMode.HEAD_TAIL_TOOL_PREVIEW.value, "original_chars": len(message.content), "omitted_chars": omitted}))
                    continue
            result.append(message)
        return tuple(result)


class MechanicalBloatScrubberCompaction(BaseCompaction):
    """Scrubs deterministic mechanical bloat from message bodies."""

    def __init__(self, base64_min_chars: int = 80, max_repeated_lines: int = 3, placeholder: str = "[scrubbed {kind}: {count} chars]") -> None:
        # Stores bloat scrubber thresholds and placeholder formatting.
        if base64_min_chars < 1:
            raise ValueError("base64_min_chars must be positive.")
        if max_repeated_lines < 0:
            raise ValueError("max_repeated_lines must be non-negative.")
        self.base64_min_chars = base64_min_chars
        self.max_repeated_lines = max_repeated_lines
        self.placeholder = placeholder

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Scrubs ANSI escapes, long base64-like spans, and excess repeated lines.
        result = []
        for message in messages:
            scrubbed, stats = _scrub_bloat_text(message.content, base64_min_chars=self.base64_min_chars, max_repeated_lines=self.max_repeated_lines, placeholder=self.placeholder)
            if scrubbed != message.content:
                result.append(_replace_message_content(message, scrubbed, {"compaction": CompactionMode.MECHANICAL_BLOAT_SCRUBBER.value, **stats}))
            else:
                result.append(message)
        return tuple(result)


class SummaryWithBackrefsCompaction(BaseCompaction):
    """Creates a deterministic excerpt summary that references source message IDs."""

    def __init__(self, start: int | None = None, end: int | None = None, excerpt_chars: int = 120) -> None:
        # Stores the inclusive range to summarize and the maximum excerpt size.
        if excerpt_chars < 0:
            raise ValueError("excerpt_chars must be non-negative.")
        self.start = start
        self.end = end
        self.excerpt_chars = excerpt_chars

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Replaces a range with a deterministic backreference summary message.
        if not messages:
            return ()
        start = max(0, self.start or 0)
        end = len(messages) - 1 if self.end is None else min(len(messages) - 1, self.end)
        if start > end:
            return tuple(messages)
        selected = tuple(messages[start:end + 1])
        summary = ContextMessage(role="assistant", content=self._summary_text(selected, start), kind="summary", metadata={"compaction": CompactionMode.SUMMARY_WITH_BACKREFS.value, "source_ids": tuple(_message_identifier(message, start + offset) for offset, message in enumerate(selected))})
        return tuple(messages[:start]) + (summary,) + tuple(messages[end + 1:])

    def _summary_text(self, messages: Sequence[ContextMessage], offset: int) -> str:
        # Builds compact Markdown lines that include role, kind, ID, and excerpt.
        lines = ["# Deterministic Context Summary"]
        for local_index, message in enumerate(messages):
            identifier = _message_identifier(message, offset + local_index)
            excerpt = message.content.replace("\n", " ")[:self.excerpt_chars]
            lines.append(f"- [{identifier}] {message.role}/{message.kind}: {excerpt}")
        return "\n".join(lines)


class SelectiveContextPruningCompaction(BaseCompaction):
    """Prunes empty, duplicate, boilerplate, or low-information messages."""

    def __init__(self, remove_empty: bool = True, remove_duplicates: bool = True, boilerplate_patterns: Sequence[str] = (), min_unique_terms: int = 0) -> None:
        # Stores deterministic pruning switches and literal/regex boilerplate patterns.
        if min_unique_terms < 0:
            raise ValueError("min_unique_terms must be non-negative.")
        self.remove_empty = remove_empty
        self.remove_duplicates = remove_duplicates
        self.patterns = tuple(re.compile(pattern) for pattern in boilerplate_patterns)
        self.min_unique_terms = min_unique_terms

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Removes messages that match low-signal pruning criteria while preserving system messages.
        seen: set[tuple[str, str, str]] = set()
        result = []
        for message in messages:
            if message.role == "system":
                result.append(message)
                continue
            key = (message.role, message.kind, message.content)
            if self.remove_empty and not message.content.strip():
                continue
            if self.remove_duplicates and key in seen:
                continue
            if self.patterns and any(pattern.search(message.content) for pattern in self.patterns):
                continue
            if self.min_unique_terms and len(_message_terms(message)) < self.min_unique_terms:
                continue
            seen.add(key)
            result.append(message)
        return tuple(result)


class SalienceScoreEvictionCompaction(BaseCompaction):
    """Evicts low-salience messages using deterministic role, recency, and metadata scores."""

    def __init__(self, max_messages: int, max_tokens: int | None = None, token_counter: TokenCounter | None = None) -> None:
        # Stores message and optional token caps for score-based eviction.
        if max_messages < 0:
            raise ValueError("max_messages must be non-negative.")
        if max_tokens is not None and max_tokens < 0:
            raise ValueError("max_tokens must be non-negative.")
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.token_counter = token_counter

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Selects the highest-scoring messages and returns them in original order.
        ranked = sorted(enumerate(messages), key=lambda item: (-self._score(item[1], item[0], len(messages)), item[0]))
        keep_indexes: set[int] = set()
        remaining_tokens = self.max_tokens
        for index, message in ranked:
            if len(keep_indexes) >= self.max_messages:
                break
            cost = _message_tokens(message, self.token_counter)
            if remaining_tokens is not None and cost > remaining_tokens and message.role != "system":
                continue
            keep_indexes.add(index)
            if remaining_tokens is not None:
                remaining_tokens -= cost
        return tuple(message for index, message in enumerate(messages) if index in keep_indexes)

    def _score(self, message: ContextMessage, index: int, total: int) -> float:
        # Computes a stable salience score from role, kind, recency, and explicit metadata.
        metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
        score = float(metadata.get("salience", 0) or 0)
        if metadata.get("pinned"):
            score += 1_000
        if message.role == "system":
            score += 10_000
        if message.kind == "summary":
            score += 100
        if message.kind in {"tool_call", "tool_result"}:
            score -= 10
        if message.kind == "tool_result" and str(metadata.get("status", "")).lower() == "error":
            score += 20
        score += index / max(1, total)
        return score


class QueryRelevanceFilterCompaction(BaseCompaction):
    """Keeps messages with deterministic lexical overlap against the current query."""

    def __init__(self, query: str = "", max_messages: int | None = None, min_score: int = 1, keep_recent: int = 0) -> None:
        # Stores the query terms, score threshold, and recency override.
        if max_messages is not None and max_messages < 0:
            raise ValueError("max_messages must be non-negative.")
        if min_score < 0:
            raise ValueError("min_score must be non-negative.")
        if keep_recent < 0:
            raise ValueError("keep_recent must be non-negative.")
        self.query_terms = {match.group(0).lower() for match in _TERM_PATTERN.finditer(query)}
        self.max_messages = max_messages
        self.min_score = min_score
        self.keep_recent = keep_recent

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Filters messages by lexical overlap while preserving system and configured recent messages.
        recent_start = max(0, len(messages) - self.keep_recent)
        selected: list[tuple[int, int, ContextMessage]] = []
        for index, message in enumerate(messages):
            score = len(self.query_terms.intersection(_message_terms(message)))
            if message.role == "system" or index >= recent_start or (self.query_terms and score >= self.min_score):
                selected.append((index, score, message))
        if self.max_messages is not None and len(selected) > self.max_messages:
            selected = sorted(selected, key=lambda item: (item[2].role != "system", -item[1], -item[0]))[:self.max_messages]
        return tuple(message for _, _, message in sorted(selected, key=lambda item: item[0]))


class ContextSnapshotBranchTrimCompaction(BaseCompaction):
    """Keeps messages belonging to an active context branch and optional ancestors."""

    def __init__(self, active_branch: str, include_ancestors: bool = True) -> None:
        # Stores the active branch ID and whether parent branch chains are retained.
        if not str(active_branch).strip():
            raise ValueError("active_branch must be provided.")
        self.active_branch = str(active_branch)
        self.include_ancestors = include_ancestors

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Filters branch-tagged messages to the active branch, ancestors, and untagged system context.
        allowed = {self.active_branch}
        if self.include_ancestors:
            allowed.update(self._ancestor_branches(messages))
        result = []
        for message in messages:
            branch = self._branch_id(message)
            if message.role == "system" or branch is None or branch in allowed:
                result.append(message)
        return tuple(result)

    def _ancestor_branches(self, messages: Sequence[ContextMessage]) -> set[str]:
        # Builds an ancestor set from message metadata parent_branch_id pointers.
        parents: dict[str, str] = {}
        for message in messages:
            metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
            branch = metadata.get("branch_id") or metadata.get("snapshot_branch")
            parent = metadata.get("parent_branch_id")
            if branch is not None and parent is not None:
                parents[str(branch)] = str(parent)
        ancestors: set[str] = set()
        current = self.active_branch
        while current in parents and parents[current] not in ancestors:
            current = parents[current]
            ancestors.add(current)
        return ancestors

    def _branch_id(self, message: ContextMessage) -> str | None:
        # Reads a branch ID from supported context snapshot metadata keys.
        metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
        value = metadata.get("branch_id") or metadata.get("snapshot_branch")
        return str(value) if value is not None else None


class NoOpCompaction(BaseCompaction):
    """Returns messages unchanged; used as a safe fallback for unknown modes."""

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        return tuple(messages)


__all__ = [
    "ClearExceptSystemAndLogCompaction",
    "ContextSnapshotBranchTrimCompaction",
    "DeduplicateToolCallsCompaction",
    "DeleteMessagesByIdOrRangeCompaction",
    "HeadTailToolPreviewCompaction",
    "KeepLastNMessagesCompaction",
    "MechanicalBloatScrubberCompaction",
    "NoOpCompaction",
    "QueryRelevanceFilterCompaction",
    "RemoveAllToolCallsCompaction",
    "RemoveLastNCompaction",
    "RemoveToolCallPercentageCompaction",
    "SalienceScoreEvictionCompaction",
    "SelectiveContextPruningCompaction",
    "StripToolResultBodiesCompaction",
    "SummaryWithBackrefsCompaction",
    "SummarizeByTopicBlocksCompaction",
    "SummarizeOldestNCompaction",
    "SummarizeRangeCompaction",
    "ToolOutputSlidingWindowCompaction",
    "ToolResultClearingWithExclusionsCompaction",
    "TrimToTokenBudgetCompaction",
    "TrimWithProviderBoundariesCompaction",
    "TruncateToolResultMessagesCompaction",
]
