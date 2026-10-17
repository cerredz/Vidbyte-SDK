"""FILE: vidbyte/middleware/compaction/windows.py

PURPOSE: Defines the two history-window strategies an agent runs on every model call: TrimWithProviderBoundariesCompaction, which drops the oldest whole call/result groups to fit a token or message budget (optionally cut down to a low watermark, so the cut moves rarely), and ToolOutputSlidingWindowCompaction, which compacts every tool output older than the newest few per tool (optionally only for named tools).
ROLE IN CODEBASE: Built by vidbyte/middleware/compaction/engine.py (ContextCompactionEngine._build_strategy) for the trim_with_provider_boundaries and tool_output_sliding_window modes, validated once by vidbyte/middleware/compaction/context_compaction.py (MessageHistoryCompactionMiddleware._validate_options), and exported unchanged from vidbyte/middleware/compaction/__init__.py. It imports the shared message helpers from vidbyte/middleware/compaction/strategies.py; strategies never imports this module.
ARCHITECTURE NOTE: The engine builds a new strategy on every call, so both strategies are pure functions of the history they receive: the same messages always give the same view, and nothing is remembered between calls. The low watermark is therefore a quantized cut, not a stored cut point: with S = max_tokens - low_watermark_tokens, the trim drops the shortest prefix of non-system groups whose tokens reach the next whole multiple of S above the overflow, so the first kept message moves about once per S tokens of growth. A low watermark of None, or one at or above max_tokens, keeps the original newest-first greedy fit exactly.
FUNCTION INVENTORY: TrimWithProviderBoundariesCompaction.__init__ checks the bounds; compact is the narrated main function; _group_tokens costs one group; _greedy_keep is the original fit; _quantized_keep is the low-watermark cut. ToolOutputSlidingWindowCompaction.__init__ checks the window, mode, and scope; compact walks the outputs newest first; _compact_older_result applies the mode to one output.
COMMON MODIFICATION PATTERNS: A new option gets a keyword with a default that keeps today's output, a check in __init__, a forwarding line in the engine branch, and a keyword on the middleware builder. Keep compact's helpers flat (none calls another).
WHAT NOT TO DO IN THIS FILE: 1. Do not keep state between calls; the engine rebuilds the strategy every call. 2. Do not split a call from its results; trim whole provider groups only. 3. Do not import this module from strategies.py (it would make a cycle). 4. Do not change the defaults' output; every caller that sets no new option must see main's view.
KNOWN EDGE CASES: Without a low watermark, the greedy fit can keep an older small group after skipping a newer large one, so its output is not always a suffix; with one, the kept non-system groups are always one contiguous suffix, and a newest group larger than the budget drops every non-system group. System groups larger than max_tokens make the budget negative, which drops every non-system group. A tool result whose name cannot be read is outside every non-empty scope, so it is never compacted by a scoped window.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md (INV-2.1 to INV-2.5, INV-4.1 to INV-4.4, D-3, D-5, D-6); vidbyte/middleware/README.md
TESTS: tests/test_compaction_windows.py, tests/test_deterministic_compaction_middleware.py, tests/test_context_compaction_middleware.py
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.middleware.compaction.base import BaseCompaction, CompactionMode, TokenCounter
from vidbyte.middleware.compaction.strategies import _head_tail_text, _message_tokens, _message_tool_name, _provider_groups, _replace_message_content


class TrimWithProviderBoundariesCompaction(BaseCompaction):
    """Trims message history while avoiding orphaned tool-call/result boundaries."""

    def __init__(self, max_messages: int | None = None, max_tokens: int | None = None, token_counter: TokenCounter | None = None, low_watermark_tokens: int | None = None) -> None:
        # Stores count and token bounds used after provider-boundary repair.
        if max_messages is not None and max_messages < 0:
            raise ValueError("max_messages must be non-negative.")
        if max_tokens is not None and max_tokens < 0:
            raise ValueError("max_tokens must be non-negative.")
        if low_watermark_tokens is not None and (isinstance(low_watermark_tokens, bool) or not isinstance(low_watermark_tokens, int) or low_watermark_tokens < 0):
            raise ValueError(f"low_watermark_tokens must be None or a non-negative int, got {low_watermark_tokens!r}.")
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.token_counter = token_counter
        self.low_watermark_tokens = low_watermark_tokens

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Trims whole call/result groups by count, then by token budget, so no tool boundary is ever split.
        # @intent parallel-tool-turns-are-kept-or-dropped-whole
        groups = _provider_groups(messages)
        # Drop the oldest groups that start before the newest
        # max_messages messages.
        if self.max_messages is not None:
            first_kept = max(0, len(messages) - self.max_messages)
            kept: list[tuple[ContextMessage, ...]] = []
            offset = 0
            for group in groups:
                if offset + len(group) > first_kept:
                    kept.append(group)
                offset += len(group)
            groups = tuple(kept)
        if self.max_tokens is None:
            return tuple(message for group in groups for message in group)
        # Cost every group once, then keep the groups the token budget
        # allows: the original newest-first fit, or the low-watermark
        # cut when a watermark below the cap is set.
        costs = [self._group_tokens(group) for group in groups]
        low = self.low_watermark_tokens
        if low is None or low >= self.max_tokens:
            keep = self._greedy_keep(groups, costs, self.max_tokens)
        else:
            keep = self._quantized_keep(groups, costs, self.max_tokens, low)
        return tuple(message for index, group in enumerate(groups) if index in keep for message in group)

    def _group_tokens(self, group: tuple[ContextMessage, ...]) -> int:
        # Sums the token cost of every record in one call/result group.
        return sum(_message_tokens(message, self.token_counter) for message in group)

    def _greedy_keep(self, groups: Sequence[tuple[ContextMessage, ...]], costs: Sequence[int], max_tokens: int) -> set[int]:
        # Keeps system groups first, then the newest whole groups that still fit the token budget.
        keep = {index for index, group in enumerate(groups) if group[0].role == "system"}
        remaining = max_tokens - sum(costs[index] for index in keep)
        for index in range(len(groups) - 1, -1, -1):
            if remaining >= 0 and index not in keep and costs[index] <= remaining:
                keep.add(index)
                remaining -= costs[index]
        return keep

    def _quantized_keep(self, groups: Sequence[tuple[ContextMessage, ...]], costs: Sequence[int], max_tokens: int, low_watermark_tokens: int) -> set[int]:
        # Keeps system groups and one contiguous suffix of the others,
        # dropping the oldest groups in whole steps of max - low tokens.
        # @intent the-trim-cut-moves-once-per-step
        # An exact-cap trim drops the oldest group on almost every call,
        # so the first history message keeps changing and the provider's
        # cached prefix never matches. Dropping in whole steps of
        # max - low tokens moves the cut about once per step of growth,
        # with no state kept between calls.
        system = {index for index, group in enumerate(groups) if group[0].role == "system"}
        others = [index for index in range(len(groups)) if index not in system]
        budget = max_tokens - sum(costs[index] for index in system)
        overflow = sum(costs[index] for index in others) - budget
        if overflow <= 0:
            return set(range(len(groups)))
        step = max_tokens - low_watermark_tokens
        target = math.ceil(overflow / step) * step
        dropped = 0
        for position, index in enumerate(others):
            dropped += costs[index]
            if dropped >= target:
                return system | set(others[position + 1 :])
        return system


class ToolOutputSlidingWindowCompaction(BaseCompaction):
    """Compacts older tool outputs while preserving the most recent outputs per tool."""

    WINDOW_MODES = (CompactionMode.TRUNCATE_TOOL_RESULTS, CompactionMode.STRIP_TOOL_RESULT_BODIES, CompactionMode.HEAD_TAIL_TOOL_PREVIEW)

    def __init__(self, keep_recent: int = 2, mode: CompactionMode | str = CompactionMode.TRUNCATE_TOOL_RESULTS, max_chars: int = 600, placeholder: str = "[older tool result cleared by compaction]", head_chars: int = 400, tail_chars: int = 200, tools: Sequence[str] = ()) -> None:
        # Stores the per-tool sliding-window size, the compaction style for older results, and the tools it applies to.
        if keep_recent < 0:
            raise ValueError("keep_recent must be non-negative.")
        # @intent sliding-window-refuses-modes-it-cannot-apply
        # Older results are only stripped, previewed, or truncated, so any other mode would silently become truncation.
        if mode not in self.WINDOW_MODES:
            raise ValueError(f"window_mode must be one of {[item.value for item in self.WINDOW_MODES]}, got {getattr(mode, 'value', mode)!r}.")
        # @intent a-scope-names-real-tools
        # An empty scope means every tool, so a blank name would read as
        # a scope that matches nothing; refuse it instead.
        if any(not isinstance(name, str) or not name.strip() for name in tools):
            raise ValueError(f"tools must hold only non-blank tool names, got {tuple(tools)!r}.")
        self.keep_recent = keep_recent
        self.mode = CompactionMode(mode)
        self.max_chars = max_chars
        self.placeholder = placeholder
        self.head_chars = head_chars
        self.tail_chars = tail_chars
        self.tools = tuple(tools)

    async def compact(self, messages: Sequence[ContextMessage]) -> tuple[ContextMessage, ...]:
        # Counts tool outputs from newest to oldest and compacts those outside each tool window.
        remaining: dict[str, int] = {}
        result: list[ContextMessage] = list(messages)
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.kind != "tool_result":
                continue
            # With a scope, only the named tools' outputs are counted and
            # compacted; every other result is left as it is.
            name = _message_tool_name(message)
            if self.tools and name not in self.tools:
                continue
            tool_name = name or "_unknown"
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


__all__ = [
    "ToolOutputSlidingWindowCompaction",
    "TrimWithProviderBoundariesCompaction",
]
