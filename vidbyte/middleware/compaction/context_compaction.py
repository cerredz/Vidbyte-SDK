from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.middleware.compaction.base import CompactionMode, Summarizer, TokenCounter
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
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

    @classmethod
    def clear_except(cls, exclude_tools: tuple[str, ...] = (), placeholder: str = "[tool result cleared by compaction]") -> "ToolResultCompactionMiddleware":
        # Builds middleware that clears tool outputs except for named tools.
        return cls(mode=CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS, exclude_tools=exclude_tools, placeholder=placeholder)

    @classmethod
    def head_tail_preview(cls, head_chars: int = 400, tail_chars: int = 200, indicator: str = "\n...[omitted {count} characters]...\n") -> "ToolResultCompactionMiddleware":
        # Builds middleware that exposes only the head and tail of long tool outputs.
        return cls(mode=CompactionMode.HEAD_TAIL_TOOL_PREVIEW, head_chars=head_chars, tail_chars=tail_chars, indicator=indicator)

    @classmethod
    def scrub_bloat(cls, base64_min_chars: int = 80, max_repeated_lines: int = 3, placeholder: str = "[scrubbed {kind}: {count} chars]") -> "ToolResultCompactionMiddleware":
        # Builds middleware that removes mechanical bloat from model-visible tool outputs.
        return cls(mode=CompactionMode.MECHANICAL_BLOAT_SCRUBBER, base64_min_chars=base64_min_chars, max_repeated_lines=max_repeated_lines, placeholder=placeholder)

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
        if "head_chars" in self.options and int(self.options["head_chars"]) < 0:
            raise ValueError("head_chars must be non-negative.")
        if "tail_chars" in self.options and int(self.options["tail_chars"]) < 0:
            raise ValueError("tail_chars must be non-negative.")
        if "base64_min_chars" in self.options and int(self.options["base64_min_chars"]) < 1:
            raise ValueError("base64_min_chars must be positive.")
        if "max_repeated_lines" in self.options and int(self.options["max_repeated_lines"]) < 0:
            raise ValueError("max_repeated_lines must be non-negative.")


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

    @classmethod
    def trim_to_token_budget(cls, max_tokens: int, token_counter: TokenCounter | None = None, preserve_system: bool = True) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that keeps newest messages within a token budget.
        return cls(mode=CompactionMode.TRIM_TO_TOKEN_BUDGET, max_tokens=max_tokens, token_counter=token_counter, preserve_system=preserve_system)

    @classmethod
    def trim_with_provider_boundaries(cls, max_messages: int | None = None, max_tokens: int | None = None, token_counter: TokenCounter | None = None) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that trims history while preserving adjacent tool boundaries.
        return cls(mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, max_messages=max_messages, max_tokens=max_tokens, token_counter=token_counter)

    @classmethod
    def delete_messages(cls, message_ids: tuple[str, ...] = (), start: int | None = None, end: int | None = None) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that deletes explicitly targeted messages or an inclusive range.
        return cls(mode=CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE, message_ids=message_ids, start=start, end=end)

    @classmethod
    def tool_output_sliding_window(cls, keep_recent: int = 2, window_mode: CompactionMode | str = CompactionMode.TRUNCATE_TOOL_RESULTS, max_chars: int = 600) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that compacts older tool outputs per tool name.
        return cls(mode=CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW, keep_recent=keep_recent, window_mode=window_mode, max_chars=max_chars)

    @classmethod
    def clear_tool_results_except(cls, exclude_tools: tuple[str, ...] = (), placeholder: str = "[tool result cleared by compaction]") -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that clears tool-result messages except for named tools.
        return cls(mode=CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS, exclude_tools=exclude_tools, placeholder=placeholder)

    @classmethod
    def head_tail_tool_preview(cls, head_chars: int = 400, tail_chars: int = 200, indicator: str = "\n...[omitted {count} characters]...\n") -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that previews long tool-result messages with head and tail text.
        return cls(mode=CompactionMode.HEAD_TAIL_TOOL_PREVIEW, head_chars=head_chars, tail_chars=tail_chars, indicator=indicator)

    @classmethod
    def scrub_bloat(cls, base64_min_chars: int = 80, max_repeated_lines: int = 3, placeholder: str = "[scrubbed {kind}: {count} chars]") -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that strips ANSI escapes, base64-like spans, and repeated lines.
        return cls(mode=CompactionMode.MECHANICAL_BLOAT_SCRUBBER, base64_min_chars=base64_min_chars, max_repeated_lines=max_repeated_lines, placeholder=placeholder)

    @classmethod
    def summary_with_backrefs(cls, start: int | None = None, end: int | None = None, excerpt_chars: int = 120) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that replaces a range with deterministic backreferenced excerpts.
        return cls(mode=CompactionMode.SUMMARY_WITH_BACKREFS, start=start, end=end, excerpt_chars=excerpt_chars)

    @classmethod
    def selective_prune(cls, remove_empty: bool = True, remove_duplicates: bool = True, boilerplate_patterns: tuple[str, ...] = (), min_unique_terms: int = 0) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that removes low-signal messages with deterministic checks.
        return cls(mode=CompactionMode.SELECTIVE_CONTEXT_PRUNING, remove_empty=remove_empty, remove_duplicates=remove_duplicates, boilerplate_patterns=boilerplate_patterns, min_unique_terms=min_unique_terms)

    @classmethod
    def salience_score_eviction(cls, max_messages: int, max_tokens: int | None = None, token_counter: TokenCounter | None = None) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that keeps the highest deterministic salience scores.
        return cls(mode=CompactionMode.SALIENCE_SCORE_EVICTION, max_messages=max_messages, max_tokens=max_tokens, token_counter=token_counter)

    @classmethod
    def query_relevance_filter(cls, query: str | None = None, max_messages: int | None = None, min_score: int = 1, keep_recent: int = 0) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that filters messages by lexical overlap with a query.
        return cls(mode=CompactionMode.QUERY_RELEVANCE_FILTER, query=query, max_messages=max_messages, min_score=min_score, keep_recent=keep_recent)

    @classmethod
    def context_snapshot_branch_trim(cls, active_branch: str, include_ancestors: bool = True) -> "MessageHistoryCompactionMiddleware":
        # Builds middleware that keeps the active context branch and optional ancestors.
        return cls(mode=CompactionMode.CONTEXT_SNAPSHOT_BRANCH_TRIM, active_branch=active_branch, include_ancestors=include_ancestors)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Compacts current provider messages before the runner invocation.
        if not ctx.provider_messages:
            return MiddlewareDecision.continue_()
        options = dict(self.options)
        if self.mode is CompactionMode.QUERY_RELEVANCE_FILTER and options.get("query") is None:
            options["query"] = ctx.message
        messages, stats = await self.engine.compact_provider_messages(ctx.provider_messages, mode=self.mode, options=options)
        transform = MiddlewareTransform(provider_messages=messages, metadata={"compaction": stats.mode, "before_count": stats.before_count, "after_count": stats.after_count})
        return MiddlewareDecision.continue_(transform=transform)

    def _validate_options(self) -> None:
        # Raises ValueError for invalid message compaction constructor options.
        if "percentage" in self.options and not 0 <= float(self.options["percentage"]) <= 1:
            raise ValueError("percentage must be between 0 and 1.")
        if "order" in self.options and self.options["order"] not in {"oldest", "newest"}:
            raise ValueError("order must be 'oldest' or 'newest'.")
        for key in ("n", "max_chars", "max_tokens", "max_messages", "keep_recent", "head_chars", "tail_chars", "min_score", "excerpt_chars", "min_unique_terms"):
            if key in self.options and self.options[key] is not None and int(self.options[key]) < 0:
                raise ValueError(f"{key} must be non-negative.")
        if "base64_min_chars" in self.options and int(self.options["base64_min_chars"]) < 1:
            raise ValueError("base64_min_chars must be positive.")
        if "max_repeated_lines" in self.options and int(self.options["max_repeated_lines"]) < 0:
            raise ValueError("max_repeated_lines must be non-negative.")
        if self.mode is CompactionMode.CONTEXT_SNAPSHOT_BRANCH_TRIM and not str(self.options.get("active_branch", "")).strip():
            raise ValueError("active_branch must be provided.")


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
