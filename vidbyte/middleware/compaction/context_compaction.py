from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.middleware.compaction.base import CompactionMode, Summarizer, TokenCounter
from vidbyte.middleware.compaction.engine import ContextCompactionEngine
from vidbyte.middleware.compaction.strategies import ReplaceWithTraceCompaction, _provider_groups
from vidbyte.middleware.compaction.trace_render import TraceArtifactRenderer
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


class TraceReplacementCompactionMiddleware(AgentMiddleware):
    """Replace provider message history with a rendered continual-trace artifact before model calls."""

    name = "TraceReplacementCompactionMiddleware"
    fail_closed = False

    def __init__(self, *, scope: str = "all_non_system", placement: str = "summary", run_state_key: str = "__result_metadata__", trace_key: str = "trace", artifact: Mapping[str, Any] | None = None, artifact_provider: Callable[[MiddlewareContext], Mapping[str, Any]] | None = None, refresh_callback: Callable[[MiddlewareContext], Awaitable[Mapping[str, Any]]] | None = None, fallback_mode: CompactionMode | str | None = None, fallback_options: Mapping[str, Any] | None = None, compose_after: CompactionMode | str | None = None, compose_after_options: Mapping[str, Any] | None = None, render: Mapping[str, Any] | None = None, summarizer: Summarizer | None = None, **options: Any) -> None:
        # Stores artifact sources, render bounds, replacement options, and validates them eagerly.
        self.strategy_options = {"scope": scope, "placement": placement, **options}
        self.run_state_key = run_state_key
        self.trace_key = trace_key
        self.artifact = artifact
        self.artifact_provider = artifact_provider
        self.refresh_callback = refresh_callback
        self.fallback_mode = self._coerce_mode(fallback_mode)
        self.fallback_options = dict(fallback_options or {})
        self.compose_after = self._coerce_mode(compose_after)
        self.compose_after_options = dict(compose_after_options or {})
        self.render = dict(render or {})
        self.engine = ContextCompactionEngine(summarizer=summarizer)
        self._validate_options()

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Resolves the trace artifact and replaces history with it, guarding the empty/cold-start case.
        if not ctx.provider_messages:
            return MiddlewareDecision.continue_()
        artifact = await self._resolve_artifact(ctx)
        if TraceArtifactRenderer.is_empty(artifact):
            return await self._apply_fallback(ctx)
        trace_text = self._render_trace(artifact)
        messages, stats = await self._replace_history(ctx, trace_text)
        messages, stats = await self._compose(messages, stats)
        transform = MiddlewareTransform(provider_messages=messages, metadata={"compaction": stats.mode, "scope": self.strategy_options["scope"], "before_count": stats.before_count, "after_count": stats.after_count, "trace_chars": len(trace_text), "fallback_used": False})
        return MiddlewareDecision.continue_(transform=transform)

    # Family A — scope/retention presets
    @classmethod
    def replace_all_with_trace(cls, *, keep_last_user: bool = True, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces all non-system history with the trace, keeping the live user turn by default.
        return cls(scope="all_non_system", keep_last_user=keep_last_user, **kw)

    @classmethod
    def keep_recent_tail(cls, keep_last_groups: int = 2, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces old history with the trace while keeping the newest K tool groups verbatim.
        return cls(scope="all_non_system", keep_last_groups=keep_last_groups, **kw)

    @classmethod
    def replace_oldest_n_iterations(cls, n: int, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces the oldest n logical groups with the trace, keeping newer history verbatim.
        return cls(scope="oldest_n_groups", n=n, **kw)

    @classmethod
    def replace_oldest_percentage(cls, percentage: float, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces the oldest ceil(percentage * groups) groups with the trace.
        return cls(scope="oldest_percentage", percentage=percentage, **kw)

    @classmethod
    def replace_middle_keep_bookends(cls, keep_last_groups: int = 2, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Keeps the first group and the recent tail, replacing the middle with the trace.
        return cls(scope="middle_keep_bookends", keep_last_groups=keep_last_groups, **kw)

    @classmethod
    def replace_keep_last_user(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces history with the trace but always preserves the most recent user message.
        return cls(scope="all_non_system", keep_last_user=True, **kw)

    # Family B — placement presets
    @classmethod
    def trace_as_summary(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Injects the trace as an assistant summary message (default placement).
        return cls(placement="summary", **kw)

    @classmethod
    def trace_as_system_suffix(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Appends the trace to the system block instead of the conversation body.
        return cls(placement="system_suffix", **kw)

    @classmethod
    def trace_as_synthetic_user(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Injects the trace as a synthetic user message for stronger model attention.
        return cls(placement="synthetic_user", **kw)

    # Family C — render presets
    @classmethod
    def trace_truncated_chars(cls, max_chars: int, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Truncates the rendered trace payload to the first max_chars characters.
        render = {**dict(kw.pop("render", {})), "max_chars": max_chars}
        return cls(render=render, **kw)

    @classmethod
    def trace_field_subset(cls, fields: Sequence[str], **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Renders only the named trace fields, in order.
        render = {**dict(kw.pop("render", {})), "fields": tuple(fields)}
        return cls(render=render, **kw)

    # Family E — freshness presets
    @classmethod
    def stale_ok(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Uses whatever trace artifact is already published in run_state (default).
        return cls(**kw)

    @classmethod
    def with_refresh(cls, refresh_callback: Callable[[MiddlewareContext], Awaitable[Mapping[str, Any]]], **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Awaits a fresh artifact from the callback before replacing, falling back to stale on error.
        return cls(refresh_callback=refresh_callback, **kw)

    # Family F — composition presets
    @classmethod
    def trace_fallback_to_mechanical(cls, fallback_mode: CompactionMode | str = CompactionMode.KEEP_LAST_N_MESSAGES, fallback_options: Mapping[str, Any] | None = None, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Falls back to a mechanical mode when no usable trace artifact exists yet.
        return cls(fallback_mode=fallback_mode, fallback_options=dict(fallback_options or {"n": 6}), **kw)

    @classmethod
    def trace_plus_strip_tool_results(cls, keep_last_groups: int = 2, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces old history with the trace and strips tool-result bodies in the kept tail.
        return cls(scope="all_non_system", keep_last_groups=keep_last_groups, compose_after=CompactionMode.STRIP_TOOL_RESULT_BODIES, **kw)

    # Family G — protected-retention presets
    @classmethod
    def replace_keep_pinned(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces history with the trace but protects pinned messages.
        return cls(scope="all_non_system", keep_pinned=True, **kw)

    @classmethod
    def replace_keep_errors(cls, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces history with the trace but protects error tool results.
        return cls(scope="all_non_system", keep_errors=True, **kw)

    @classmethod
    def replace_keep_active_branch(cls, branch: str, **kw: Any) -> "TraceReplacementCompactionMiddleware":
        # Replaces history with the trace but protects the active snapshot branch and unbranched messages.
        return cls(scope="all_non_system", keep_active_branch=branch, **kw)

    async def _resolve_artifact(self, ctx: MiddlewareContext) -> Mapping[str, Any] | None:
        # Resolves the artifact by precedence: injected, refreshed, provided, then run_state.
        if self.artifact is not None:
            return self.artifact
        if self.refresh_callback is not None:
            refreshed = await self._safe_refresh(ctx)
            if refreshed is not None:
                return refreshed
        if self.artifact_provider is not None:
            candidate = self.artifact_provider(ctx)
            if isinstance(candidate, Mapping):
                return candidate
        return self._artifact_from_run_state(ctx)

    async def _safe_refresh(self, ctx: MiddlewareContext) -> Mapping[str, Any] | None:
        # Awaits the refresh callback, returning None on failure so callers fall back to stale state.
        try:
            candidate = await self.refresh_callback(ctx)  # type: ignore[misc]
        except Exception:
            return None
        return candidate if isinstance(candidate, Mapping) else None

    def _artifact_from_run_state(self, ctx: MiddlewareContext) -> Mapping[str, Any] | None:
        # Reads the published trace artifact from the configured run_state bucket and key.
        bucket = ctx.run_state.get(self.run_state_key) if isinstance(ctx.run_state, Mapping) else None
        candidate = bucket.get(self.trace_key) if isinstance(bucket, Mapping) else None
        return candidate if isinstance(candidate, Mapping) else None

    def _render_trace(self, artifact: Mapping[str, Any]) -> str:
        # Renders the artifact to bounded text using the configured render options.
        return TraceArtifactRenderer(**self.render).render(artifact)

    async def _replace_history(self, ctx: MiddlewareContext, trace_text: str):
        # Applies the trace-replacement strategy to the current provider messages.
        options = {**self.strategy_options, "trace_text": trace_text}
        return await self.engine.compact_provider_messages(ctx.provider_messages, mode=CompactionMode.REPLACE_WITH_TRACE, options=options)

    async def _compose(self, messages: Sequence[Mapping[str, Any]], stats):
        # Optionally applies a second compaction mode over the replacement result.
        if self.compose_after is None:
            return messages, stats
        return await self.engine.compact_provider_messages(messages, mode=self.compose_after, options=self.compose_after_options)

    async def _apply_fallback(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Applies the configured fallback mode (or no-ops) when no usable trace artifact exists.
        if self.fallback_mode is None:
            return MiddlewareDecision.continue_()
        messages, stats = await self.engine.compact_provider_messages(ctx.provider_messages, mode=self.fallback_mode, options=self.fallback_options)
        transform = MiddlewareTransform(provider_messages=messages, metadata={"compaction": stats.mode, "fallback_used": True, "before_count": stats.before_count, "after_count": stats.after_count})
        return MiddlewareDecision.continue_(transform=transform)

    def _validate_options(self) -> None:
        # Validates render bounds and replacement options by constructing them once at init time.
        TraceArtifactRenderer(**self.render)
        ReplaceWithTraceCompaction("validation", **self.strategy_options)

    @staticmethod
    def _coerce_mode(mode: CompactionMode | str | None) -> CompactionMode | None:
        # Normalizes an optional mode argument into a CompactionMode or None.
        if mode is None or isinstance(mode, CompactionMode):
            return mode
        return CompactionMode(str(mode))


class TraceSummaryTailCompactionMiddleware(TraceReplacementCompactionMiddleware):
    """Replace old history with the trace and summarize the kept recent tail via an injected summarizer."""

    name = "TraceSummaryTailCompactionMiddleware"

    def __init__(self, *, summarizer: Summarizer, keep_last_groups: int = 2, **kw: Any) -> None:
        # Stores the tail summarizer and the number of recent groups to summarize.
        if summarizer is None:
            raise ValueError("trace_then_summarize_tail requires an injected summarizer.")
        self._summarizer = summarizer
        self.keep_last_groups = keep_last_groups
        super().__init__(scope="all_non_system", keep_last_groups=keep_last_groups, summarizer=summarizer, **kw)

    @classmethod
    def trace_then_summarize_tail(cls, summarizer: Summarizer, keep_last_groups: int = 2, **kw: Any) -> "TraceSummaryTailCompactionMiddleware":
        # Builds middleware that collapses old history to the trace and summarizes the recent tail.
        return cls(summarizer=summarizer, keep_last_groups=keep_last_groups, **kw)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Replaces old history with the structured trace and the recent tail with a freeform summary.
        if not ctx.provider_messages:
            return MiddlewareDecision.continue_()
        artifact = await self._resolve_artifact(ctx)
        if TraceArtifactRenderer.is_empty(artifact):
            return await self._apply_fallback(ctx)
        trace_text = self._render_trace(artifact)
        context_messages = self.engine.to_context_messages(ctx.provider_messages)
        rebuilt = await self._replace_and_summarize_tail(context_messages, trace_text)
        provider = self.engine.from_context_messages(rebuilt)
        transform = MiddlewareTransform(provider_messages=provider, metadata={"compaction": CompactionMode.REPLACE_WITH_TRACE.value, "tail_summarized": True, "before_count": len(context_messages), "after_count": len(provider)})
        return MiddlewareDecision.continue_(transform=transform)

    async def _replace_and_summarize_tail(self, messages: Sequence[ContextMessage], trace_text: str) -> list[ContextMessage]:
        # Collapses old groups into the trace message and summarizes the newest K groups into one summary.
        system = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        groups = _provider_groups(non_system)
        tail = [message for group in (groups[-self.keep_last_groups:] if self.keep_last_groups else ()) for message in group]
        marker = self.strategy_options.get("trace_marker", "continual_trace")
        rebuilt: list[ContextMessage] = list(system)
        rebuilt.append(ContextMessage(role="assistant", content=trace_text, kind="summary", metadata={"compaction": CompactionMode.REPLACE_WITH_TRACE.value, "trace_marker": marker}))
        if tail:
            summary_text = await self._summarizer.summarize(tuple(tail))
            rebuilt.append(ContextMessage(role="assistant", content=summary_text, kind="summary", metadata={"compaction": CompactionMode.SUMMARIZE_RANGE.value, "tail_summary": True}))
        return rebuilt


__all__ = [
    "MessageHistoryCompactionMiddleware",
    "SummaryCompactionMiddleware",
    "ToolResultCompactionMiddleware",
    "TraceReplacementCompactionMiddleware",
    "TraceSummaryTailCompactionMiddleware",
]
