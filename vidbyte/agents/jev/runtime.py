"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs the JevPreflightGate, applies the tool selector, and orchestrates the run-state done checks around the inherited linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate and the JevResponse writer at construction and passes both in, and the runtime keeps run-local tool selection and finish review around the inherited agent loop.
ARCHITECTURE NOTE: With a run-state section enabled (JevAgentSettings.required_sequence), the runtime builds a JevRunState before the inherited loop, adds each active section's instructions to the system prompt, and overrides AgentRuntime.review_finish_attempt to build a JevRunHandoff from the loop state and let each section decide.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: A closed gate never reaches the generative runner. An unavailable selector keeps the original tool catalog. Builder failures leave the run ungated and are recorded; a missing TypeSafe key leaves only the code checks. A plain BaseAgent(runtime="jev") is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-required-sequence.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_required_sequence.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.builders import JevRunHandoffAgent, JevRunStateAgent
from vidbyte.agents.jev.event_log import JevRunEventLog
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.required_sequence import JevRequiredSequence
from vidbyte.agents.jev.response import JevResponse
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
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools

_RUN_STATE_BUILD_FAILED = "run_state_build_failed"
_HANDOFF_BUILD_FAILED = "handoff_build_failed"


class JevRuntime(AgentRuntime):
    """Linear runtime that gates completion on the run-state sections JevAgentSettings enables."""

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
        self.preflight = preflight
        self.response = response
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

    def _with_report(self, result: AgentResult) -> AgentResult:
        # Attaches the run state, every finish review, and builder usage under one metadata key.
        if self._run_state is None:
            return result
        report = JevRunReport(run_state=self._run_state, finish_reviews=tuple(self._finish_reviews), builder_usage=tuple(self._builder_usage))
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata={**dict(result.metadata), JEV_RUN_REPORT_METADATA_KEY: report},
            structured=result.structured,
        )

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
        context = await self._aprepare_done_checks(message, handle, context)
        if JevPreflightPreset.TOOL_SELECTOR not in self.jev_settings.preflight:
            return self.response.finished(self._with_report(await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )))

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
        return self.response.finished(self._with_report(replace(
            result,
            metadata={
                **dict(result.metadata),
                "jev_tool_selector": selector_metadata,
            },
        )))

    async def _aprepare_done_checks(self, message: str, handle: RunnerHandle, context: BaseAgentContext) -> BaseAgentContext:
        # Builds the run state once before the loop and adds each active section's instructions to the system prompt.
        if not self._sections:
            return context
        self._handle = handle
        self._run_state = await self._abuild_run_state(message, handle)
        active = self._active_sections()
        if not active:
            return context
        instructions = "\n\n".join(section.agent_instructions(self._run_state.sections[section.key]) for section in active)
        return replace(context, system_prompt=f"{context.system_prompt or self.system_prompt}\n\n{instructions}")


__all__ = ["JevRuntime"]
