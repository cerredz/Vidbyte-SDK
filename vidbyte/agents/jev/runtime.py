"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent and orchestrates its named done-criteria presets.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: The ordinary linear loop is inherited unchanged; presets hook in before the loop (state building) and at AgentRuntime._finish_attempt_feedback (review and continuation).
COMMON MODIFICATION PATTERNS: Add a preset's run-local record and its two hooks here; keep its questions, thresholds, and records in its own subpackage.
KNOWN EDGE CASES: Without a preset no Jev call is made and no TypeSafe credential is needed. JevAgent refuses to construct an enabled preset without a TypeSafe key. Builder, provider, and schema failures fail open and are recorded in result metadata. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-motivating-case.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_motivating_case.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.motivating_case import (
    MotivatingCaseHandoffBuilderAgent,
    MotivatingCasePolicy,
    MotivatingCaseState,
    MotivatingCaseStateBuilderAgent,
    RunEventLedger,
)
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev import JEV_MOTIVATING_CASE_MAX_CONTINUATIONS
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.tools import ToolPermission
from vidbyte.lib.enums import AgentRuntimeStateKey
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext

_RECALL_NOTE = "A reviewer found that this request names an unusual situation, such as an empty, missing, retried, failing, or conflicting case. List the boundary conditions it names."


@dataclass(slots=True)
class _MotivatingCaseRun:
    """Mutable record of the motivating-case check for one run; the runtime instance itself is per run."""

    policy: MotivatingCasePolicy
    request: str
    state: MotivatingCaseState | None = None
    continuations: int = 0
    report: dict[str, Any] = field(default_factory=lambda: {"preset": JevPresets.MotivatingCase.value})

    def active(self) -> bool:
        # The finish check runs only when a valid, non-empty state was built.
        return self.state is not None and not self.state.is_empty()


class JevRuntime(AgentRuntime):
    """Linear runtime seam that adds fixed Jev policies around the ordinary tool loop."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, done_criteria: JevPresets | None = None, source_agent: BaseAgent | None = None, **kwargs: Any) -> None:
        # Retains the validated settings and preset by identity and delegates loop construction to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        if done_criteria is not None and not isinstance(done_criteria, JevPresets):
            raise ConfigurationError("JevRuntime.done_criteria must be a JevPresets member or None.")
        if done_criteria is not None and not isinstance(source_agent, BaseAgent):
            raise ConfigurationError("A Jev done-criteria preset needs its source JevAgent to build helper agents.")
        self.jev_settings = jev_settings
        self.done_criteria = done_criteria
        self.source_agent = source_agent
        self._motivating_case: _MotivatingCaseRun | None = None
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Builds the preset's run state once, before the inherited loop starts.
        if self.done_criteria is JevPresets.MotivatingCase:
            self._motivating_case = await self._prepare_motivating_case(message)
        return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

    async def _prepare_motivating_case(self, message: str) -> _MotivatingCaseRun:
        # Builds and validates the scenario state; asks the recall guard when the builder found no scenario.
        # @intent state-built-once-per-run
        # The state is built before the loop and reused at every finish attempt, so only the handoff costs a generative call per review.
        # JevAgent already validated the TypeSafe key; every infrastructure failure from here on fails open.
        if self.source_agent is None:
            raise ConfigurationError("The motivating-case preset has no source JevAgent.")
        run = _MotivatingCaseRun(policy=MotivatingCasePolicy(DecisionModelRunner(self.jev_settings.decision)), request=message)
        builder = MotivatingCaseStateBuilderAgent(source_agent=self.source_agent)
        try:
            state = await builder.build_state(message)
            if state.is_empty():
                flagged, probability = await run.policy.request_names_boundary(message)
                run.report["recall_guard"] = {"probability": probability, "rebuilt": flagged}
                if flagged:
                    state = await builder.build_state(message, note=_RECALL_NOTE)
                    run.report["recall_guard"]["builder_disagreement"] = state.is_empty()
        except VidbyteSdkError as exc:
            run.report.update(status="state_unavailable", error=type(exc).__name__)
            return run
        run.state = state
        run.report.update(status="active" if run.active() else "inactive", state=state.to_payload())
        return run

    async def _finish_attempt_feedback(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> str | None:
        # Reviews a finish attempt against the motivating-case state and returns feedback to continue, or None to accept.
        # @intent review-fails-open-and-is-capped
        # Infrastructure failures accept the attempt and continuations are capped, so the check can delay but never trap or break a run.
        run = self._motivating_case
        if run is None or not run.active() or run.state is None or self.source_agent is None:
            return None
        ledger = RunEventLedger.from_contexts(state.call_contexts, self._permission_for_tool)
        try:
            handoff = await MotivatingCaseHandoffBuilderAgent(source_agent=self.source_agent, state=run.state).build_handoff(run.request, ledger, result.output or "")
            decision = await run.policy.evaluate(run.state, ledger, handoff, result.output or "", prior_continuations=run.continuations)
        except VidbyteSdkError as exc:
            run.report.update(status="review_failed", error=type(exc).__name__)
            return None
        run.report.update(status="evaluated", review=decision.metadata(), continuations=run.continuations)
        if decision.accepted():
            return None
        if run.continuations >= JEV_MOTIVATING_CASE_MAX_CONTINUATIONS:
            run.report["status"] = "unresolved_at_limit"
            return None
        run.continuations += 1
        run.report["continuations"] = run.continuations
        return decision.feedback()

    async def _finish_result(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> AgentResult:
        # Publishes the latest done-criteria report on every exit path, including budget stops.
        if self._motivating_case is not None:
            published = state.run_state.get(AgentRuntimeStateKey.RESULT_METADATA.value)
            merged = dict(published) if isinstance(published, Mapping) else {}
            merged["done_criteria"] = dict(self._motivating_case.report)
            state.run_state[AgentRuntimeStateKey.RESULT_METADATA.value] = merged
        return await super()._finish_result(result, state)

    def _permission_for_tool(self, tool_name: str) -> ToolPermission | None:
        # Reads a tool's declared permission so code, not Jev, decides which events count as runs or writes.
        # @intent unknown-permission-is-not-evidence
        # A tool without a readable permission yields None, which no evidence role accepts, so unknown tools can never count as runs.
        try:
            permission = getattr(self.tools._get(tool_name).spec(), "permission", None)
        except Exception:
            return None
        if isinstance(permission, ToolPermission):
            return permission
        try:
            return ToolPermission(str(permission)) if permission is not None else None
        except ValueError:
            return None


__all__ = ["JevRuntime"]
