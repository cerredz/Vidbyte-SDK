"""Context Protocol Header

Description:
    Provides built-in middleware for deterministic context compaction.
Purpose:
    Lets agents compact model-visible tool results and message history at the
    middleware layer without exposing compaction as a model-callable tool.
Architecture:
    - ToolResultCompactionMiddleware: Rewrites model-visible tool outputs.
    - MessageHistoryCompactionMiddleware: Rewrites provider message history.
    - SummaryCompactionMiddleware: Summarizes provider message history using an injected summarizer.
Relations:
    Uses vidbyte.context.compaction and middleware transform contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine, Summarizer
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision, MiddlewareTransform
from vidbyte.middleware.base import AgentMiddleware


class ToolResultCompactionMiddleware(AgentMiddleware):
    """Compact model-visible tool results after tool execution."""

    name = "ToolResultCompactionMiddleware"

    def __init__(self, *, mode: CompactionMode | str, skip_internal_tools: bool = True, **options: Any) -> None:
        # Stores tool-result compaction settings and validates bounds eagerly.
        self.mode = mode if isinstance(mode, CompactionMode) else CompactionMode(str(mode))
        self.skip_internal_tools = skip_internal_tools
        self.options = dict(options)
        self.engine = ContextCompactionEngine()
        self._validate_options()

    @classmethod
    def raw(cls) -> "ToolResultCompactionMiddleware":
        # Builds a no-op tool-result compaction middleware for explicit composition.
        return cls(mode=CompactionMode.TRUNCATE_TOOL_RESULTS, skip_internal_tools=True, enabled=False)

    @classmethod
    def truncate(cls, max_chars: int = 600, truncation_indicator: str = "\n...[tool output compacted]") -> "ToolResultCompactionMiddleware":
        # Builds middleware that truncates long tool outputs before model visibility.
        return cls(mode=CompactionMode.TRUNCATE_TOOL_RESULTS, max_chars=max_chars, truncation_indicator=truncation_indicator)

    @classmethod
    def strip(cls, placeholder: str = "[tool result stripped by compaction]") -> "ToolResultCompactionMiddleware":
        # Builds middleware that strips tool-result bodies to a placeholder.
        return cls(mode=CompactionMode.STRIP_TOOL_RESULT_BODIES, placeholder=placeholder)

    @classmethod
    def hide(cls) -> "ToolResultCompactionMiddleware":
        # Builds middleware that withholds raw tool outputs from model context.
        return cls(mode=CompactionMode.HIDE_TOOL_RESULTS)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Replaces the model-visible tool result while preserving raw runtime metadata.
        if not self.options.get("enabled", True):
            return MiddlewareDecision.continue_()
        if self.skip_internal_tools and ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        if ctx.tool_call is None or ctx.tool_result is None:
            return MiddlewareDecision.continue_()
        visible_result, stats = self.engine.compact_tool_result(ctx.tool_call, ctx.tool_result, mode=self.mode, options=self.options)
        transform = MiddlewareTransform(model_visible_tool_result=visible_result, metadata={"compaction": stats.mode, **dict(stats.metadata)})
        return MiddlewareDecision.continue_(transform=transform)

    def _validate_options(self) -> None:
        # Raises ValueError for invalid constructor options before runtime starts.
        if "max_chars" in self.options and int(self.options["max_chars"]) < 0:
            raise ValueError("max_chars must be non-negative.")


class MessageHistoryCompactionMiddleware(AgentMiddleware):
    """Compact provider message history before model calls."""

    name = "MessageHistoryCompactionMiddleware"

    def __init__(self, *, mode: CompactionMode | str, **options: Any) -> None:
        # Stores provider-message compaction settings and validates them eagerly.
        self.mode = mode if isinstance(mode, CompactionMode) else CompactionMode(str(mode))
        self.options = dict(options)
        self.engine = ContextCompactionEngine()
        self._validate_options()

    @classmethod
    def keep_last(cls, n: int) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that keeps only the last n non-system messages.
        return cls(mode=CompactionMode.KEEP_LAST_N_MESSAGES, n=n)

    @classmethod
    def remove_all_tool_calls(cls) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that removes all tool trace messages.
        return cls(mode=CompactionMode.REMOVE_ALL_TOOL_CALLS)

    @classmethod
    def remove_last_n_tool_calls(cls, n: int) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that removes the newest n tool trace messages.
        return cls(mode=CompactionMode.REMOVE_LAST_N_TOOL_CALLS, n=n)

    @classmethod
    def remove_tool_call_percentage(cls, percentage: float, order: str = "oldest") -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that removes a percentage of tool trace messages.
        return cls(mode=CompactionMode.REMOVE_TOOL_CALL_PERCENTAGE, percentage=percentage, order=order)

    @classmethod
    def clear_except_system_and_log(cls, progress_log: Mapping[str, object] | None = None) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that collapses history to system messages and a progress log.
        return cls(mode=CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG, progress_log=dict(progress_log or {}))

    @classmethod
    def deduplicate_tool_calls(cls) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that removes duplicate tool-call/result pairs.
        return cls(mode=CompactionMode.DEDUPLICATE_TOOL_CALLS)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Compacts current provider messages before the runner invocation.
        if not ctx.provider_messages:
            return MiddlewareDecision.continue_()
        messages, stats = await self.engine.compact_provider_messages(ctx.provider_messages, mode=self.mode, options=self.options)
        transform = MiddlewareTransform(provider_messages=messages, metadata={"compaction": stats.mode, "before_count": stats.before_count, "after_count": stats.after_count})
        return MiddlewareDecision.continue_(transform=transform)

    def _validate_options(self) -> None:
        # Raises ValueError for invalid message compaction constructor options.
        if "percentage" in self.options and not 0 <= float(self.options["percentage"]) <= 1:
            raise ValueError("percentage must be between 0 and 1.")
        if "order" in self.options and self.options["order"] not in {"oldest", "newest"}:
            raise ValueError("order must be 'oldest' or 'newest'.")


class SummaryCompactionMiddleware(MessageHistoryCompactionMiddleware):
    """Summarize provider message history before model calls."""

    name = "SummaryCompactionMiddleware"

    def __init__(self, *, mode: CompactionMode | str, summarizer: Summarizer, **options: Any) -> None:
        # Stores summary compaction settings and requires an explicit summarizer.
        if summarizer is None:
            raise ValueError("Summary compaction requires an injected summarizer.")
        self.mode = mode if isinstance(mode, CompactionMode) else CompactionMode(str(mode))
        self.options = dict(options)
        self.engine = ContextCompactionEngine(summarizer=summarizer)
        self._validate_options()

    @classmethod
    def summarize_range(cls, summarizer: Summarizer, keep_last: int = 3) -> "SummaryCompactionMiddleware":
        # Builds middleware that summarizes older history while preserving recent messages.
        return cls(mode=CompactionMode.SUMMARIZE_RANGE, summarizer=summarizer, keep_last=keep_last)

    @classmethod
    def summarize_oldest_n(cls, summarizer: Summarizer, n: int = 5) -> "SummaryCompactionMiddleware":
        # Builds middleware that summarizes the oldest n non-system messages.
        return cls(mode=CompactionMode.SUMMARIZE_OLDEST_N, summarizer=summarizer, n=n)

    @classmethod
    def summarize_by_topic_blocks(cls, summarizer: Summarizer, block_size: int = 10) -> "SummaryCompactionMiddleware":
        # Builds middleware that summarizes non-system history in fixed-size blocks.
        return cls(mode=CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS, summarizer=summarizer, block_size=block_size)


__all__ = [
    "MessageHistoryCompactionMiddleware",
    "SummaryCompactionMiddleware",
    "ToolResultCompactionMiddleware",
]
