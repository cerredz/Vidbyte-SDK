"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent and orchestrates its run-state done checks.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: With a run-state section enabled (JevAgentSettings.required_sequence), the runtime builds a JevRunState before the inherited loop, adds each active section's instructions to the system prompt, and overrides AgentRuntime.review_finish_attempt to build a JevRunHandoff from the loop state and let each section decide. With none enabled it is the plain linear loop.
COMMON MODIFICATION PATTERNS: Enable a new done check by returning its JevRunSection from _enabled_sections; keep the check's own logic in its section module.
KNOWN EDGE CASES: A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here. Builder failures leave the run ungated and are recorded; a missing TypeSafe key leaves only the code checks. The agent is sent back at most JEV_MAX_FINISH_REVIEW_CONTINUATIONS times before a failing review stops the run.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-required-sequence.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_required_sequence.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.builders import JevRunHandoffAgent, JevRunStateAgent
from vidbyte.agents.jev.event_log import JevRunEventLog
from vidbyte.agents.jev.required_sequence import JevRequiredSequence
from vidbyte.agents.jev.run_state import (
    JevFinishReviewRecord,
    JevRunHandoff,
    JevRunReport,
    JevRunSection,
    JevRunState,
    JevSectionReview,
)
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev import (
    JEV_HANDOFF_BUILD_ATTEMPTS,
    JEV_MAX_FINISH_REVIEW_CONTINUATIONS,
    JEV_RUN_REPORT_METADATA_KEY,
)
from vidbyte.lib.dataclasses.agents import FinishReview, FinishReviewAction
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext

_RUN_STATE_BUILD_FAILED = "run_state_build_failed"
_HANDOFF_BUILD_FAILED = "handoff_build_failed"


class JevRuntime(AgentRuntime):
    """Linear runtime that gates completion on the run-state sections JevAgentSettings enables."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and prepares run-local done-check state.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        self.jev_settings = jev_settings
        super().__init__(**kwargs)
        self._sections: tuple[JevRunSection, ...] = self._enabled_sections(jev_settings)
        self._handle: RunnerHandle | None = None
        self._run_state: JevRunState | None = None
        self._finish_reviews: list[JevFinishReviewRecord] = []
        self._review_feedback: list[tuple[int, str]] = []
        self._builder_usage: list[UsageRollup] = []
        self._continuations = 0
        self._decider: DecisionModelRunner | None = None
        self._decider_resolved = False

    @staticmethod
    def _enabled_sections(settings: JevAgentSettings) -> tuple[JevRunSection, ...]:
        # Maps each named setting to its done-check section, in a fixed order.
        return (JevRequiredSequence(),) if settings.required_sequence else ()

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
        """Build the run state, run the inherited loop under finish review, and attach the run report."""
        if not self._sections:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        self._handle = handle
        self._run_state = await self._abuild_run_state(message, handle)
        active = self._active_sections()
        if active:
            instructions = "\n\n".join(section.agent_instructions(self._run_state.sections[section.key]) for section in active)
            context = replace(context, system_prompt=f"{context.system_prompt or self.system_prompt}\n\n{instructions}")
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        return self._with_report(result, self._run_state)

    async def review_finish_attempt(self, candidate_output: str, state: BaseAgentRuntimeLoopState) -> FinishReview:
        """Build a handoff from the loop state, let every active section review it, and decide the attempt."""
        # @intent finish-gate-fails-open-only-on-builder-failure
        # A handoff that cannot be built even after one corrected rebuild says nothing about the agent's
        # work, so the attempt is accepted and flagged; any section failure on a valid handoff is enforced.
        active = self._active_sections()
        if not active or self._run_state is None:
            return FinishReview.accept()
        event_log = JevRunEventLog.from_loop_state(state, review_feedback=self._review_feedback)
        handoff, failure = await self._abuild_handoff(candidate_output, event_log, active)
        if handoff is None:
            self._finish_reviews.append(JevFinishReviewRecord(event_log.last_event_id(), FinishReviewAction.ACCEPT, handoff_failure=failure))
            return FinishReview.accept()
        decider = self._decision_runner()
        reviews: list[JevSectionReview] = []
        for section in active:
            reviews.append(await section.areview(state=self._run_state.sections[section.key], handoff=handoff.sections[section.key], decider=decider))
        decision = self._decide(tuple(reviews), state.iteration_count)
        self._finish_reviews.append(JevFinishReviewRecord(event_log.last_event_id(), decision.action, handoff=handoff, reviews=tuple(reviews)))
        return decision

    def _decide(self, reviews: tuple[JevSectionReview, ...], iteration: int) -> FinishReview:
        # Accepts when every section passed; otherwise continues with the feedback, bounded.
        # @intent bounded-finish-continuations
        # max_iterations defaults to unbounded, so a stubborn agent could loop forever on a failing
        # check; after the configured number of continuations the next failure stops the run instead.
        feedback = "\n\n".join(review.feedback for review in reviews if not review.passed)
        if not feedback:
            return FinishReview.accept()
        if self._continuations >= JEV_MAX_FINISH_REVIEW_CONTINUATIONS:
            return FinishReview.stop(feedback)
        self._continuations += 1
        self._review_feedback.append((iteration, feedback))
        return FinishReview.continue_with(feedback)

    async def _abuild_run_state(self, message: str, handle: RunnerHandle) -> JevRunState:
        # One generative call before the loop; a failed build leaves the run ungated and says why.
        builder = JevRunStateAgent(settings=self.jev_settings, handle=handle, sections=self._sections)
        try:
            return await builder.abuild(message)
        except VidbyteSdkError as exc:
            return JevRunState.unavailable(message, self._sections, f"{_RUN_STATE_BUILD_FAILED}:{type(exc).__name__}")
        finally:
            self._builder_usage.append(builder.usage())

    async def _abuild_handoff(self, candidate_output: str, event_log: JevRunEventLog, active: tuple[JevRunSection, ...]) -> tuple[JevRunHandoff | None, str]:
        # Builds the handoff, rebuilding with the validation error when the first answer is invalid.
        # @intent one-corrected-rebuild
        # The validation error is fed back once so a fixable handoff (unknown event ID, missing stage) is
        # repaired; more attempts would multiply generative cost on every finish attempt.
        assert self._run_state is not None and self._handle is not None
        correction = ""
        failure = ""
        for _attempt in range(JEV_HANDOFF_BUILD_ATTEMPTS):
            builder = JevRunHandoffAgent(settings=self.jev_settings, handle=self._handle, run_state=self._run_state, sections=active)
            try:
                return await builder.abuild(proposed_answer=candidate_output, event_log=event_log, correction=correction), ""
            except VidbyteSdkError as exc:
                correction = getattr(exc, "validation_error", None) or exc.message
                failure = f"{_HANDOFF_BUILD_FAILED}:{type(exc).__name__}"
            finally:
                self._builder_usage.append(builder.usage())
        return None, failure

    def _decision_runner(self) -> DecisionModelRunner | None:
        # Resolves Jev once per run; a missing key disables only the Jev questions, not the code checks.
        if not self._decider_resolved:
            self._decider_resolved = True
            try:
                self._decider = DecisionModelRunner(self.jev_settings.decision)
            except ConfigurationError:
                self._decider = None
        return self._decider

    def _active_sections(self) -> tuple[JevRunSection, ...]:
        # Sections whose state gates this run; empty before the run state exists.
        if self._run_state is None:
            return ()
        keys = set(self._run_state.active_section_keys())
        return tuple(section for section in self._sections if section.key in keys)

    def _with_report(self, result: AgentResult, run_state: JevRunState) -> AgentResult:
        # Attaches the run state, every finish review, and builder usage under one metadata key.
        report = JevRunReport(run_state=run_state, finish_reviews=tuple(self._finish_reviews), builder_usage=tuple(self._builder_usage))
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata={**dict(result.metadata), JEV_RUN_REPORT_METADATA_KEY: report},
            structured=result.structured,
        )


__all__ = ["JevRuntime"]
