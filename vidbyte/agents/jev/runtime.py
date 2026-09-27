"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Runs Jev preflight and tool selection, then applies Jev completion policy around the shared agent loop.
ROLE IN CODEBASE: RuntimeRegistry resolves AgentRuntimeType.JEV here; JevAgent supplies validated settings, a preflight gate, and response writer.
ARCHITECTURE NOTE: JevRuntime owns feature-specific orchestration while AgentRuntime retains iteration, tool, middleware, fallback, and result lifecycle mechanics.
FUNCTION INVENTORY: __init__ retains Jev policy objects; arun runs preflight and tool selection; _continue_finish_attempt gates finish attempts; _finish_result adds criterion metadata; _elapsed_seconds reads the run's monotonic start.
COMMON MODIFICATION PATTERNS: Add typed policy in its Jev package and adapt it here without copying the shared runtime loop.
WHAT NOT TO DO: Do not construct provider runners, duplicate the shared loop, or store per-attempt timestamps on the runtime instance.
KNOWN EDGE CASES: Both plain final responses and isDone are gated; elapsed time alone never completes the task; unavailable preflight/selector paths preserve their fail-open behavior.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_done_criteria.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, scripts/test-jev-done-criteria.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.done_criteria import JevDoneCriteria
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(
        self,
        *,
        jev_settings: JevAgentSettings | None = None,
        preflight: JevPreflightGate | None = None,
        response: JevResponse | None = None,
        **kwargs: Any,
    ) -> None:
        # Retains the validated settings, the gate, and the response writer JevAgent built, and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without them; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings) or not isinstance(preflight, JevPreflightGate) or not isinstance(response, JevResponse):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={
                    "received_jev_settings": type(jev_settings).__name__,
                    "received_preflight": type(preflight).__name__,
                    "received_response": type(response).__name__,
                },
            )
        self.jev_settings = jev_settings
        self.done_criteria = JevDoneCriteria(jev_settings.done_criteria)
        self.preflight = preflight
        self.response = response
        super().__init__(**kwargs)

    # @intent minimum-duration-is-an-earliest-finish-boundary
    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        # A duration blocks early finish attempts but never proves that the user's task is complete.
        # Feedback resumes the shared loop under its existing budgets rather than sleeping or ending it.
        del result
        evaluation = self.done_criteria.evaluate(elapsed_seconds=self._elapsed_seconds(state))
        if evaluation.is_met:
            return False
        messages.append({"role": "user", "content": evaluation.continuation_prompt or "Continue working on the task."})
        return True

    async def _finish_result(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> AgentResult:
        # Adds criterion status to results from completion, budget, and middleware exit paths.
        metadata = self.done_criteria.evaluate(elapsed_seconds=self._elapsed_seconds(state)).metadata
        if metadata:
            result = AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata={**dict(result.metadata), **metadata}, structured=result.structured)
        return await super()._finish_result(result, state)

    def _elapsed_seconds(self, state: BaseAgentRuntimeLoopState) -> float:
        # Computes elapsed run time in the runtime's monotonic clock domain.
        return max(0.0, self.middleware.clock() - state.started_at)

    async def arun(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        """Run the preflight gate, then apply enabled run-local preflights before entering the inherited agent loop."""
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        if not await self.preflight.pass_(message):
            return self.response.stopped()
        if JevPreflightPreset.TOOL_SELECTOR not in self.jev_settings.preflight:
            return self.response.finished(await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            ))

        candidate_tool_count = len(self.user_tools)
        selector = JevPreflightTools(
            self.jev_settings.decision,
            self.jev_settings.tool_selector_threshold,
        )
        self.user_tools = await selector.run(message, self.user_tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=run_options,
            trace_context=trace_context,
        )
        selector_metadata: dict[str, Any] = {
            "available": selector.available,
            "candidate_tool_count": candidate_tool_count,
            "selected_tool_count": len(self.user_tools),
        }
        if selector.usage is not None:
            selector_metadata["usage"] = {
                "input_tokens": selector.usage.input_tokens,
                "output_tokens": selector.usage.output_tokens,
            }
        return self.response.finished(replace(
            result,
            metadata={
                **dict(result.metadata),
                "jev_tool_selector": selector_metadata,
            },
        ))


__all__ = ["JevRuntime"]
