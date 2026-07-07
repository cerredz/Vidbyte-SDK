"""
FILE: vidbyte/middleware/continual_trace.py

PURPOSE:
    Implements continual trace scheduling as agent runtime middleware. Injects continual trace updates at fixed lifecycle points (every N iterations and once at run end), accumulating the artifact in run_state and publishing it for the runtime to surface, while never writing the trace into the context window.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.lib.dataclasses.trace: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - ContinualTraceMiddleware (class): public or navigational symbol owned here.
    - ContinualTraceMiddleware (export): public or navigational symbol owned here.
    - RESULT_METADATA_KEY (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.middleware.base import AgentMiddleware

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent

RESULT_METADATA_KEY = "__result_metadata__"


@dataclass
class _TraceRunState:
    # Per-run trace accumulation and bookkeeping kept in MiddlewareContext.run_state.
    artifact: dict[str, Any] = field(default_factory=dict)
    update_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    last_updated_iteration: int = -1
    finalized: bool = False


class ContinualTraceMiddleware(AgentMiddleware):
    """Fail-open middleware that runs periodic and final continual trace updates."""

    fail_closed = False

    def __init__(self, option: TraceOption, *, source_agent: "BaseAgent") -> None:
        # Stores the trace option and the source agent whose runner/provider is reused.
        self.option = option
        self.source_agent = source_agent

    @property
    def middleware_name(self) -> str:
        # Stable display name for middleware metadata and audit events.
        return "ContinualTraceMiddleware"

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Seed a fresh per-run trace artifact in ctx.run_state."""
        state = _TraceRunState(artifact=self.option.schema.initial_artifact())
        ctx.run_state[self.__class__] = state
        self._publish(ctx, state)
        return MiddlewareDecision.continue_()

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run a trace update when the configured iteration interval is reached."""
        state = self._state(ctx)
        if self._is_interval_due(state, ctx.iteration_count):
            await self._run_update(ctx, state)
        return MiddlewareDecision.continue_()

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run one final trace update unless this iteration was already traced."""
        state = self._state(ctx)
        if not state.finalized:
            if state.last_updated_iteration != ctx.iteration_count:
                await self._run_update(ctx, state)
            state.finalized = True
        return MiddlewareDecision.continue_()

    def _state(self, ctx: MiddlewareContext) -> _TraceRunState:
        # Returns the per-run trace state, recreating it if a hook ran before before_run.
        state = ctx.run_state.get(self.__class__)
        if not isinstance(state, _TraceRunState):
            state = _TraceRunState(artifact=self.option.schema.initial_artifact())
            ctx.run_state[self.__class__] = state
        return state

    def _is_interval_due(self, state: _TraceRunState, iteration_count: int) -> bool:
        # Decides whether the current completed iteration should trigger an update.
        if iteration_count <= 0 or iteration_count % self.option.every_n_iterations != 0:
            return False
        return state.last_updated_iteration != iteration_count

    async def _run_update(self, ctx: MiddlewareContext, state: _TraceRunState) -> None:
        # Delegates one fail-open trace update to ContinualTraceAgent and records the result.
        from vidbyte.agents.continual_trace import ContinualTraceAgent

        try:
            artifact, error = await ContinualTraceAgent.run_update(
                self.source_agent,
                self.option.schema,
                context_window=self._render_context_window(ctx),
                trace_so_far=state.artifact,
                max_trace_iterations=self.option.max_trace_iterations,
                runtime_metadata=self._runtime_facts(ctx),
            )
            state.artifact = artifact
            if error:
                state.error_count += 1
                state.last_error = error
            else:
                state.update_count += 1
                state.last_error = None
        except Exception as exc:
            state.error_count += 1
            state.last_error = f"{type(exc).__name__}: {exc}"
        state.last_updated_iteration = ctx.iteration_count
        self._publish(ctx, state)

    def _publish(self, ctx: MiddlewareContext, state: _TraceRunState) -> None:
        # Publishes the artifact to run_state for the runtime to lift; never touches the context window.
        published = ctx.run_state.get(RESULT_METADATA_KEY)
        if not isinstance(published, dict):
            published = {}
        published["trace"] = dict(state.artifact)
        published["trace_metadata"] = self._summary(state)
        ctx.run_state[RESULT_METADATA_KEY] = published

    def _summary(self, state: _TraceRunState) -> dict[str, Any]:
        # Returns compact trace bookkeeping for AgentResult metadata.
        summary: dict[str, Any] = {
            "mode": self.option.mode.value,
            "schema": self.option.schema.name,
            "update_count": state.update_count,
            "error_count": state.error_count,
        }
        if state.last_error:
            summary["last_error"] = state.last_error
        return summary

    def _render_context_window(self, ctx: MiddlewareContext) -> str:
        # Renders a read-only snapshot of the main agent context plus provider messages.
        sections: list[str] = []
        if ctx.agent_context is not None:
            try:
                sections.append(ctx.agent_context.build_context())
            except Exception:
                sections.append("")
        messages = self._provider_messages(ctx)
        if messages:
            sections.append("Provider messages:\n" + json.dumps(messages, indent=2, sort_keys=True, default=str))
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _provider_messages(ctx: MiddlewareContext) -> tuple[Mapping[str, Any], ...]:
        # Extracts provider messages from the middleware context as plain mappings.
        raw = ctx.provider_messages
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return ()
        return tuple(dict(message) for message in raw if isinstance(message, Mapping))

    @staticmethod
    def _runtime_facts(ctx: MiddlewareContext) -> dict[str, Any]:
        # Builds compact runtime facts passed to the trace agent prompt.
        return {
            "iteration_count": ctx.iteration_count,
            "model_call_count": ctx.model_call_count,
            "tool_call_count": ctx.tool_call_count,
            "tokens_used": ctx.tokens_used,
            "elapsed_seconds": round(ctx.elapsed_seconds, 3),
        }


__all__ = [
    "ContinualTraceMiddleware",
    "RESULT_METADATA_KEY",
]
