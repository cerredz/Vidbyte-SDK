"""Context Protocol Header

Description:
    Implements context compaction strategies for long-running agents.
Purpose:
    Gives agent loops explicit tools to reduce context size by clearing,
    summarizing, or removing tool-call traces while preserving system prompts.
Architecture:
    - CompactionMode: Supported compaction strategy names.
    - Summarizer: Optional async protocol for model-backed summaries.
    - ContextCompactionTool: Applies compaction to an injected ContextState.
Relations:
    Related to vidbyte.tools.builtins.context.types and future harness state objects.
"""

from __future__ import annotations

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
        """Return the model-facing compaction tool declaration."""
        return ToolSpec(
            name="compact_context",
            description="Compact agent context by clearing, summarizing, or removing tool traces.",
            permission=ToolPermission.SAFE,
            parameters=(
                ToolParameter("mode", "string", "Compaction strategy name."),
                ToolParameter("n", "integer", "Number of tool messages to remove.", required=False),
                ToolParameter("percentage", "number", "Fraction of tool messages to remove.", required=False),
                ToolParameter("order", "string", "'oldest' or 'newest' for percentage removal.", required=False),
                ToolParameter("keep_last", "integer", "Recent messages to preserve for summarization.", required=False),
                ToolParameter("progress_log", "object", "Structured progress log fields.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Dispatch the requested compaction strategy and update state."""
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
