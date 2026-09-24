"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Coordinates Jev-specific state generation and named done-criteria checks around the direct loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV here; JevAgent supplies validated settings, enabled presets, and itself.
ARCHITECTURE NOTE: The runtime builds one stable state and at most one handoff per finish attempt; JevDoneCheck subclasses own each policy.
COMMON MODIFICATION PATTERNS: Register a new preset's JevDoneCheck in _build_checks without exposing caller-authored Jev questions or hooks.
KNOWN EDGE CASES: Disabled criteria makes no extra model call; enabled provider/schema failures propagate without success.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-scope-coverage-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, scripts/test-jev-multipart-done-criteria.py, and scripts/test-jev-scope-coverage-done-criteria.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.builders import (
    JevRunHandoffBuilderAgent,
    JevRunStateBuilderAgent,
)
from vidbyte.agents.jev.done_checks import (
    JevDoneCheck,
    JevDoneCheckContext,
    JevDoneCheckResult,
)
from vidbyte.agents.jev.multi_part import MultiPartDoneCheck
from vidbyte.agents.jev.presets import JevPresets, normalize_done_criteria
from vidbyte.agents.jev.run_state import JevRunHandoff, JevRunSnapshot, JevRunState
from vidbyte.agents.jev.scope_coverage.check import (
    ScopeBreadthReview,
    ScopeCoverageDoneCheck,
)
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev import (
    JEV_MULTIPART_ATTEMPT_INCREMENT,
    JEV_MULTIPART_INITIAL_ATTEMPT,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import AgentRuntimeStateKey
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext


class _DecisionRunnerCache:
    """Creates the run's TypeSafe decision runner on first use and reuses it afterwards."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Retains decision settings without resolving credentials until a check actually asks Jev.
        self._settings = settings
        self._runner: DecisionModelRunner | None = None

    def __call__(self) -> DecisionModelRunner:
        # Returns the one runner shared by every check in this run.
        if self._runner is None:
            self._runner = DecisionModelRunner(self._settings.decision)
        return self._runner


@dataclass(slots=True)
class _JevDoneCriteriaRun:
    """Mutable state scoped to one JevRuntime.arun context."""

    state: JevRunState
    checks: tuple[JevDoneCheck, ...]
    decision_runner: _DecisionRunnerCache
    # @intent start-evaluation-at-zero
    # The first normal finish boundary is attempt one after the runtime increments this run-local count.
    attempt: int = JEV_MULTIPART_INITIAL_ATTEMPT


class JevRuntime(AgentRuntime):
    """Linear runtime seam for fixed Jev policies around the ordinary tool loop."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, done_criteria: JevPresets | tuple[JevPresets, ...] | None = None, source_agent: BaseAgent | None = None, **kwargs: Any) -> None:
        # Validates specialized runtime dependencies before delegating ordinary loop construction.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        presets = normalize_done_criteria(done_criteria)
        if presets and not isinstance(source_agent, BaseAgent):
            raise ConfigurationError("The Jev done-criteria runtime requires its source JevAgent.")
        self.jev_settings = jev_settings
        self.done_criteria = presets
        self.source_agent = source_agent
        self._done_run: ContextVar[_JevDoneCriteriaRun | None] = ContextVar(f"jev_done_criteria_run_{id(self)}", default=None)
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Creates one immutable request state before the main loop when any done criteria is enabled.
        run = await self._prepare_run(message) if self.done_criteria else None
        token = self._done_run.set(run)
        try:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        finally:
            self._done_run.reset(token)

    async def _prepare_run(self, message: str) -> _JevDoneCriteriaRun:
        # Builds the shared state once, widens narrow scope labels, and creates this run's checks.
        if self.source_agent is None:
            raise ConfigurationError("The Jev done-criteria runtime has no source agent.")
        state_builder = JevRunStateBuilderAgent(source_agent=self.source_agent, settings=self.jev_settings, presets=self.done_criteria)
        try:
            state = await state_builder.build_state(message)
        finally:
            self.usage_tracker.merge(state_builder.get_usage())
        decision_runner = _DecisionRunnerCache(self.jev_settings)
        if state.scope is not None:
            state = state.with_scope(await ScopeBreadthReview(decision_runner).review(state.scope))
        return _JevDoneCriteriaRun(state=state, checks=self._build_checks(), decision_runner=decision_runner)

    def _build_checks(self) -> tuple[JevDoneCheck, ...]:
        # Creates fresh per-run check instances in preset declaration order.
        checks: list[JevDoneCheck] = []
        if JevPresets.MultiPart in self.done_criteria:
            checks.append(MultiPartDoneCheck())
        if JevPresets.ScopeCoverage in self.done_criteria:
            checks.append(ScopeCoverageDoneCheck())
        return tuple(checks)

    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        # Runs every enabled check against one shared handoff and continues the loop when any check rejects the finish.
        # @intent keep-incomplete-run-active
        # A failed check adds concrete gaps and continues this exact loop with its run-local history intact.
        run = self._done_run.get()
        if run is None or self.source_agent is None:
            return False
        run.attempt += JEV_MULTIPART_ATTEMPT_INCREMENT
        snapshot = JevRunSnapshot.from_runtime(
            original_request=state.message,
            state=run.state,
            iteration_outputs=state.iteration_outputs,
            tool_calls=state.call_contexts,
            final_output=result.output,
        )
        handoff = await self._build_handoff(run, snapshot)
        context = JevDoneCheckContext(state=run.state, handoff=handoff, snapshot=snapshot, attempt=run.attempt, decision_runner=run.decision_runner)
        results = tuple([await check.evaluate(context) for check in run.checks])
        self._publish_done_criteria_metadata(state, self._metadata(run, results))
        rejected = [item for item in results if not item.accepted]
        if not rejected:
            return False
        messages.append({"role": "user", "content": "\n\n".join(item.feedback for item in rejected if item.feedback)})
        return True

    async def _build_handoff(self, run: _JevDoneCriteriaRun, snapshot: JevRunSnapshot) -> JevRunHandoff | None:
        # Generates one handoff covering every section the enabled checks read, or none when no check needs one.
        if self.source_agent is None or not any(check.needs_handoff(run.state) for check in run.checks):
            return None
        handoff_builder = JevRunHandoffBuilderAgent(source_agent=self.source_agent, settings=self.jev_settings, state=run.state)
        try:
            return await handoff_builder.build_handoff(snapshot)
        finally:
            self.usage_tracker.merge(handoff_builder.get_usage())

    @staticmethod
    def _metadata(run: _JevDoneCriteriaRun, results: tuple[JevDoneCheckResult, ...]) -> dict[str, Any]:
        # Reports the latest attempt: shared counters at the top, one subsection per enabled preset.
        # @intent expose-final-check-only
        # Report the latest decision without serializing prompts, provider bodies, or credentials.
        metadata: dict[str, Any] = {
            "presets": [item.preset.value for item in results],
            "attempts": run.attempt,
            "complete": all(item.complete for item in results),
        }
        for item in results:
            metadata[item.preset.value] = dict(item.metadata)
        return metadata

    @staticmethod
    def _publish_done_criteria_metadata(state: BaseAgentRuntimeLoopState, metadata: Mapping[str, Any]) -> None:
        # Stores only the latest completion attempt in AgentRuntime's normal result-metadata channel.
        published = state.run_state.get(AgentRuntimeStateKey.RESULT_METADATA.value)
        existing = dict(published) if isinstance(published, Mapping) else {}
        existing["done_criteria"] = dict(metadata)
        state.run_state[AgentRuntimeStateKey.RESULT_METADATA.value] = existing


__all__ = ["JevRuntime"]
