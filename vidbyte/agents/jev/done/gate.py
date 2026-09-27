"""FILE: vidbyte/agents/jev/done/gate.py

PURPOSE: Implements JevDoneGate, the gate at the end of JevAgent's generative agent: it builds the run state before the loop, and at each finish attempt builds a handoff from the loop state, lets every active done check review it, and decides whether the run may finish.
ROLE IN CODEBASE: JevAgent builds one JevDoneGate from its settings at construction and passes it to JevRuntime, which calls start() before the inherited linear loop and delegates AgentRuntime.review_finish_attempt to review(); every outcome is written through JevResponse, so callers read it as JevAgent.response.run_report.
ARCHITECTURE NOTE: This is the finish-time counterpart of JevPreflightGate (vidbyte/agents/jev/gate/): it owns building, failing open, and the continue-or-stop decision, while each done check's facts and Jev questions stay in its JevRunSection module. The runtime never reads the settings for done checks.
COMMON MODIFICATION PATTERNS: Enable a new done check by returning its JevRunSection from sections(); keep the check's own logic in its section module.
KNOWN EDGE CASES: With no done check enabled start() and review() do nothing. Builder failures leave the run ungated and are recorded; a missing TypeSafe key leaves only the code checks. The agent is sent back at most JEV_MAX_FINISH_REVIEW_CONTINUATIONS times before a failing review stops the run. Like the JevAgent that owns it, one instance serves one run at a time, and start() resets the previous run's state.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.agents.jev.done.builders import JevRunHandoffAgent, JevRunStateAgent
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.done.required_sequence import JevRequiredSequence
from vidbyte.agents.jev.done.run_state import (
    JevFinishReviewRecord,
    JevRunHandoff,
    JevRunReport,
    JevRunSection,
    JevRunState,
    JevSectionReview,
)
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev import (
    JEV_HANDOFF_BUILD_ATTEMPTS,
    JEV_MAX_FINISH_REVIEW_CONTINUATIONS,
)
from vidbyte.lib.dataclasses.agents import FinishReview, FinishReviewAction
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.errors import VidbyteSdkError

_RUN_STATE_BUILD_FAILED = "run_state_build_failed"
_HANDOFF_BUILD_FAILED = "handoff_build_failed"


class JevDoneGate:
    """Gate at the end of JevAgent's generative agent: one run state per run, then a reviewed handoff at every finish attempt."""

    def __init__(self, settings: JevAgentSettings, response: JevResponse) -> None:
        # Fixes every done-check input when JevAgent is built; nothing about done checks is read at run time.
        # @intent done-checks-are-configured-once
        # Mirrors JevPreflightGate: the runtime receives this finished gate and never looks at settings itself.
        self.settings = settings
        self.response = response
        self.sections: tuple[JevRunSection, ...] = self.enabled_sections(settings)
        self._handle: RunnerHandle | None = None
        self._run_state: JevRunState | None = None
        self._review_feedback: list[tuple[int, str]] = []
        self._finish_reviews: list[JevFinishReviewRecord] = []
        self._builder_usage: list[UsageRollup] = []
        self._continuations = 0

    @staticmethod
    def enabled_sections(settings: JevAgentSettings) -> tuple[JevRunSection, ...]:
        """Map each named done-check setting to its section, in a fixed order."""
        return (JevRequiredSequence(),) if settings.required_sequence else ()

    async def start(self, message: str, handle: RunnerHandle, context: BaseAgentContext) -> BaseAgentContext:
        """Build the run state once before the loop and return the context with each active section's instructions."""
        self._handle = handle
        self._run_state = None
        self._review_feedback = []
        self._finish_reviews = []
        self._builder_usage = []
        self._continuations = 0
        if not self.sections:
            return context
        self._run_state = await self._abuild_run_state(message, handle)
        self._report()
        active = self._active_sections()
        if not active:
            return context
        instructions = "\n\n".join(section.agent_instructions(self._run_state.sections[section.key]) for section in active)
        return replace(context, system_prompt=f"{context.system_prompt or self.settings.system_prompt}\n\n{instructions}")

    async def review(self, candidate_output: str, state: BaseAgentRuntimeLoopState) -> FinishReview:
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
            self._report()
            return FinishReview.accept()
        reviews: list[JevSectionReview] = []
        for section in active:
            reviews.append(await section.areview(state=self._run_state.sections[section.key], handoff=handoff.sections[section.key], decision=self.settings.decision))
        decision = self._decide(tuple(reviews), state.iteration_count)
        self._finish_reviews.append(JevFinishReviewRecord(event_log.last_event_id(), decision.action, handoff=handoff, reviews=tuple(reviews)))
        self._report()
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
        builder = JevRunStateAgent(settings=self.settings, handle=handle, sections=self.sections)
        try:
            return await builder.abuild(message)
        except VidbyteSdkError as exc:
            return JevRunState.unavailable(message, self.sections, f"{_RUN_STATE_BUILD_FAILED}:{type(exc).__name__}")
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
            builder = JevRunHandoffAgent(settings=self.settings, handle=self._handle, run_state=self._run_state, sections=active)
            try:
                return await builder.abuild(proposed_answer=candidate_output, event_log=event_log, correction=correction), ""
            except VidbyteSdkError as exc:
                correction = getattr(exc, "validation_error", None) or exc.message
                failure = f"{_HANDOFF_BUILD_FAILED}:{type(exc).__name__}"
            finally:
                self._builder_usage.append(builder.usage())
        return None, failure

    def _report(self) -> None:
        # Writes the run state, every finish review so far, and builder usage to JevAgent.response.
        # @intent done-checks-report-through-jev-response
        # JevResponse is the one writer of JevAgent.response; the report is refreshed after every event, so a
        # run that ends on any path (accept, stop, budget, error) leaves the latest record readable.
        if self._run_state is not None:
            self.response.run_report(JevRunReport(run_state=self._run_state, finish_reviews=tuple(self._finish_reviews), builder_usage=tuple(self._builder_usage)))

    def _active_sections(self) -> tuple[JevRunSection, ...]:
        # Sections whose state gates this run; empty before the run state exists.
        if self._run_state is None:
            return ()
        keys = set(self._run_state.active_section_keys())
        return tuple(section for section in self.sections if section.key in keys)


__all__ = ["JevDoneGate"]
