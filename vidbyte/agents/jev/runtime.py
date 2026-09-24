"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides Jev-owned finish-attempt policy around the shared direct agent loop.
ROLE IN CODEBASE: RuntimeRegistry resolves AgentRuntimeType.JEV here; JevAgent supplies validated settings, criteria evaluate elapsed time, and AgentRuntime invokes the subclass hook for both ordinary finish paths.
ARCHITECTURE NOTE: This subclass keeps completion policy Jev-specific while leaving iteration, tool, middleware, fallback, and result lifecycle mechanics in AgentRuntime.
FUNCTION INVENTORY: __init__ validates and retains Jev settings; _continue_finish_attempt may append continuation feedback; _finish_result adds criterion metadata; _elapsed_seconds uses the runtime monotonic clock.
COMMON MODIFICATION PATTERNS: Add a done-criterion subclass in done_criteria/ and keep this runtime as the clock/message adapter for that policy.
WHAT NOT TO DO: Do not copy the shared runtime loop, make provider requests, or store per-attempt timestamps on the runtime instance.
KNOWN EDGE CASES: Both plain final responses and isDone are gated; budget and middleware exits still finalize with minimum_duration_met metadata.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_done_criteria.py, and scripts/test-jev-done-criteria.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.jev.done_criteria import JevDoneCriteria
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates all current behavior to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        self.jev_settings = jev_settings
        self.done_criteria = JevDoneCriteria(jev_settings.done_criteria)
        super().__init__(**kwargs)

    # @intent minimum-duration-is-an-earliest-finish-boundary
    # A configured duration prevents Jev from accepting either normal completion path before the
    # required elapsed time, but time passing never proves that the user's task is complete.
    #
    # The shared runtime owns both model-originated finish boundaries: a plain final response and
    # the internal isDone tool. Gating only one would let the other bypass the configured policy.
    # Returning True means the prompt was extended and the same attempt must continue under its
    # existing iteration and timeout budgets; this hook must never sleep or mark the task finished.
    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        # Applies every configured Jev criterion and appends feedback only when a requirement is unmet.
        del result
        evaluation = self.done_criteria.evaluate(elapsed_seconds=self._elapsed_seconds(state))
        if evaluation.is_met:
            return False
        messages.append({"role": "user", "content": evaluation.continuation_prompt or "Continue working on the task."})
        return True

    async def _finish_result(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> AgentResult:
        # Adds exact criterion status to every returned result, including budget and middleware stops.
        metadata = self.done_criteria.evaluate(elapsed_seconds=self._elapsed_seconds(state)).metadata
        if metadata:
            result = AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata={**dict(result.metadata), **metadata}, structured=result.structured)
        return await super()._finish_result(result, state)

    def _elapsed_seconds(self, state: BaseAgentRuntimeLoopState) -> float:
        # Computes elapsed run time in the runtime's monotonic clock domain.
        return max(0.0, self.middleware.clock() - state.started_at)


__all__ = ["JevRuntime"]
