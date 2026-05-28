"""Context Protocol Header

Description:
    Implements context compaction strategies for long-running agents.
Purpose:
    Gives agent loops explicit tools to reduce context size by clearing,
    summarizing, or removing tool-call traces while preserving system prompts.
Architecture:
    - CompactionMode: Enum listing supported compaction strategy names, now including truncate_tool_results.
    - Summarizer: Optional async protocol for model-backed summaries.
    - ContextCompactionTool: Core tool class applying compaction strategies to an injected ContextState.
Functions:
    - ContextCompactionTool.spec: Defines the model-facing compaction tool declaration.
    - ContextCompactionTool.execute: Dispatches the chosen compaction strategy.
    - ContextCompactionTool._truncate_tool_results: Truncates tool-result bodies exceeding a threshold character count.
Relations:
    Uses context data contracts defined in vidbyte.tools.builtins.context.types, mutates
    agent ContextState, and is tested in tests.test_context_compaction_tools.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from enum import Enum
from typing import Protocol

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.context.types import ContextMessage, ContextState, ProgressLog
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


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


class Summarizer(Protocol):
    """Protocol for optional async model-backed summarizers."""

    async def summarize(self, messages: Sequence[ContextMessage]) -> str:
        """Return a compact summary of the supplied messages."""


class ContextCompactionTool(BaseTool):
    """Apply named compaction strategies to an injected context state."""

    def __init__(self, state: ContextState, *, summarizer: Summarizer | None = None) -> None:
        """Store the mutable state and optional summarizer."""
        self.state = state
        self.summarizer = summarizer

    def spec(self) -> ToolSpec:
        # Returns the model-facing schema and declaration for the compaction tool.
        return ToolSpec(
            name="compact_context",
            description=(
                "Compact agent context by clearing, summarizing, or removing tool traces. "
                "Modes: clear_except_system_and_log, remove_all_tool_calls, "
                "remove_last_n_tool_calls, remove_tool_call_percentage, summarize_range, "
                "keep_last_n_messages, summarize_oldest_n, strip_tool_result_bodies, "
                "deduplicate_tool_calls, summarize_by_topic_blocks, truncate_tool_results."
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
                ToolParameter("truncation_indicator", "string", "Custom indicator suffix or replacement text.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Dispatches the requested compaction strategy and applies the updates to the context state.
        try:
            mode = CompactionMode(str(call.arguments["mode"]))
        except ValueError:
            return ToolResult.error(self.name, "Unknown compaction mode.", metadata={"error": "bad_mode"})

        before = tuple(self.state.messages())
        if mode is CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG:
            after = self._clear_except_system_and_log(before, call.arguments.get("progress_log"))
        elif mode is CompactionMode.REMOVE_ALL_TOOL_CALLS:
            after = tuple(message for message in before if not self._is_tool_message(message))
        elif mode is CompactionMode.REMOVE_LAST_N_TOOL_CALLS:
            after = self._remove_last_n(before, int(call.arguments.get("n", 0)))
        elif mode is CompactionMode.REMOVE_TOOL_CALL_PERCENTAGE:
            percentage = float(call.arguments.get("percentage", 0))
            order = str(call.arguments.get("order", "oldest"))
            if not 0 <= percentage <= 1:
                return ToolResult.error(self.name, "percentage must be between 0 and 1.")
            after = self._remove_percentage(before, percentage, order)
        elif mode is CompactionMode.KEEP_LAST_N_MESSAGES:
            after = self._keep_last_n_messages(before, int(call.arguments.get("n", 10)))
        elif mode is CompactionMode.STRIP_TOOL_RESULT_BODIES:
            after = self._strip_tool_result_bodies(before)
        elif mode is CompactionMode.DEDUPLICATE_TOOL_CALLS:
            after = self._deduplicate_tool_calls(before)
        elif mode is CompactionMode.TRUNCATE_TOOL_RESULTS:
            max_chars = call.arguments.get("max_chars", 1000)
            if max_chars is None:
                max_chars = 1000
            else:
                try:
                    max_chars = int(max_chars)
                except (ValueError, TypeError):
                    return ToolResult.error(self.name, "max_chars must be a valid integer.")
            if max_chars < 0:
                return ToolResult.error(self.name, "max_chars must be non-negative.")
            truncation_indicator = str(call.arguments.get("truncation_indicator", " [... truncated {count} characters ...]"))
            after = self._truncate_tool_results(before, max_chars, truncation_indicator)
        elif mode is CompactionMode.SUMMARIZE_OLDEST_N:
            result = await self._summarize_oldest_n(before, int(call.arguments.get("n", 5)))
            if isinstance(result, ToolResult):
                return result
            after = result
        elif mode is CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS:
            result = await self._summarize_by_topic_blocks(before, int(call.arguments.get("block_size", 10)))
            if isinstance(result, ToolResult):
                return result
            after = result
        else:
            result = await self._summarize_range(before, int(call.arguments.get("keep_last", 3)))
            if isinstance(result, ToolResult):
                return result
            after = result

        self.state.replace_messages(after)
        removed = len(before) - len(after)
        tool_before = sum(1 for message in before if self._is_tool_message(message))
        tool_after = sum(1 for message in after if self._is_tool_message(message))
        return ToolResult.success(
            self.name,
            f"Context compacted. Messages: {len(before)} -> {len(after)}.",
            metadata={
                "before_count": len(before),
                "after_count": len(after),
                "removed_count": removed,
                "removed_tool_messages": tool_before - tool_after,
            },
        )

    def _clear_except_system_and_log(
        self,
        messages: Sequence[ContextMessage],
        raw_log: object,
    ) -> tuple[ContextMessage, ...]:
        """Keep system messages and append one structured progress summary."""
        system_messages = tuple(message for message in messages if message.role == "system")
        progress_log = self._progress_log(raw_log)
        summary = ContextMessage(
            role="assistant",
            content=progress_log.to_markdown(),
            kind="summary",
            metadata={"compaction": CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG.value},
        )
        return system_messages + (summary,)

    def _remove_last_n(
        self,
        messages: Sequence[ContextMessage],
        n: int,
    ) -> tuple[ContextMessage, ...]:
        """Remove the last n tool-call or tool-result messages."""
        if n <= 0:
            return tuple(messages)
        remove_indexes: set[int] = set()
        for index in range(len(messages) - 1, -1, -1):
            if self._is_tool_message(messages[index]):
                remove_indexes.add(index)
                if len(remove_indexes) >= n:
                    break
        return tuple(message for index, message in enumerate(messages) if index not in remove_indexes)

    def _remove_percentage(
        self,
        messages: Sequence[ContextMessage],
        percentage: float,
        order: str,
    ) -> tuple[ContextMessage, ...]:
        """Remove a percentage of tool messages from oldest or newest side."""
        tool_indexes = [index for index, message in enumerate(messages) if self._is_tool_message(message)]
        count = math.ceil(len(tool_indexes) * percentage)
        if order == "newest":
            selected = set(tool_indexes[-count:] if count else ())
        else:
            selected = set(tool_indexes[:count])
        return tuple(message for index, message in enumerate(messages) if index not in selected)

    async def _summarize_range(
        self,
        messages: Sequence[ContextMessage],
        keep_last: int,
    ) -> tuple[ContextMessage, ...] | ToolResult:
        """Summarize middle history while preserving system and recent messages."""
        if self.summarizer is None:
            return ToolResult.error(
                self.name,
                "summarize_range requires an injected summarizer.",
                metadata={"error": "missing_summarizer"},
            )
        keep_last = max(0, keep_last)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        recent = non_system[-keep_last:] if keep_last else ()
        middle = non_system[:-keep_last] if keep_last else non_system
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

    def _keep_last_n_messages(
        self,
        messages: Sequence[ContextMessage],
        n: int,
    ) -> tuple[ContextMessage, ...]:
        """Keep system messages and the last n non-system messages."""
        n = max(0, n)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        return system + non_system[-n:] if n else system

    def _strip_tool_result_bodies(
        self,
        messages: Sequence[ContextMessage],
    ) -> tuple[ContextMessage, ...]:
        """Replace tool-result content with a compact placeholder, preserving the record."""
        placeholder = "[tool result stripped by compaction]"
        result = []
        for message in messages:
            if message.kind == "tool_result":
                result.append(
                    dataclasses.replace(
                        message,
                        content=placeholder,
                        metadata={
                            **dict(message.metadata),
                            "compaction": CompactionMode.STRIP_TOOL_RESULT_BODIES.value,
                            "original_chars": len(message.content),
                        },
                    )
                )
            else:
                result.append(message)
        return tuple(result)

    def _truncate_tool_results(self, messages: Sequence[ContextMessage], max_chars: int, truncation_indicator: str) -> tuple[ContextMessage, ...]:
        # Truncates large tool-result message bodies and appends an indicator with the count of truncated characters.
        result = []
        for message in messages:
            if message.kind == "tool_result" and len(message.content) > max_chars:
                count = len(message.content) - max_chars
                formatted = truncation_indicator.replace("{count}", str(count))
                truncated_content = message.content[:max_chars] + formatted
                result.append(
                    dataclasses.replace(
                        message,
                        content=truncated_content,
                        metadata={
                            **dict(message.metadata),
                            "compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                            "original_chars": len(message.content),
                            "truncated_chars": count,
                        },
                    )
                )
            else:
                result.append(message)
        return tuple(result)

    def _deduplicate_tool_calls(
        self,
        messages: Sequence[ContextMessage],
    ) -> tuple[ContextMessage, ...]:
        """Remove duplicate tool-call/result pairs, keeping the first occurrence of each."""
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

    async def _summarize_oldest_n(
        self,
        messages: Sequence[ContextMessage],
        n: int,
    ) -> tuple[ContextMessage, ...] | ToolResult:
        """Summarize the oldest n non-system messages and keep the rest verbatim."""
        if self.summarizer is None:
            return ToolResult.error(
                self.name,
                "summarize_oldest_n requires an injected summarizer.",
                metadata={"error": "missing_summarizer"},
            )
        n = max(0, n)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        to_summarize = non_system[:n]
        rest = non_system[n:]
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

    async def _summarize_by_topic_blocks(
        self,
        messages: Sequence[ContextMessage],
        block_size: int,
    ) -> tuple[ContextMessage, ...] | ToolResult:
        """Chunk non-system history into blocks and summarize each block independently."""
        if self.summarizer is None:
            return ToolResult.error(
                self.name,
                "summarize_by_topic_blocks requires an injected summarizer.",
                metadata={"error": "missing_summarizer"},
            )
        block_size = max(1, block_size)
        system = tuple(message for message in messages if message.role == "system")
        non_system = tuple(message for message in messages if message.role != "system")
        if not non_system:
            return tuple(messages)
        blocks = [non_system[i : i + block_size] for i in range(0, len(non_system), block_size)]
        summaries: list[ContextMessage] = []
        for block_index, block in enumerate(blocks):
            summary_text = await self.summarizer.summarize(block)
            summaries.append(
                ContextMessage(
                    role="assistant",
                    content=summary_text,
                    kind="summary",
                    metadata={
                        "compaction": CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS.value,
                        "block_index": block_index,
                    },
                )
            )
        return system + tuple(summaries)

    def _progress_log(self, raw_log: object) -> ProgressLog:
        """Convert a mapping-like object into a ProgressLog."""
        if not isinstance(raw_log, dict):
            return ProgressLog()
        return ProgressLog(
            completed_tasks=tuple(str(item) for item in raw_log.get("completed_tasks", ())),
            touched_files=tuple(str(item) for item in raw_log.get("touched_files", ())),
            decisions=tuple(str(item) for item in raw_log.get("decisions", ())),
            errors=tuple(str(item) for item in raw_log.get("errors", ())),
            next_steps=tuple(str(item) for item in raw_log.get("next_steps", ())),
        )

    def _is_tool_message(self, message: ContextMessage) -> bool:
        """Return whether a message is a tool call/result trace."""
        return message.kind in {"tool_call", "tool_result"}
