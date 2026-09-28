"""FILE: vidbyte/agents/jev/done/run_state.py

PURPOSE: Implements JevRunState, the class that owns JevAgent's done checks: it builds the structured run-state schema the enabled checks need, runs the generative model once to write the run state from the user's request, and at every finish attempt has JevReviewer list what a strict reviewer would reject (when self-review is enabled) and JevHandoff compile the evidence, asks Jev every enabled check's fixed questions in one request, and returns the checks that failed.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.continual enables a done check and passes it to JevRuntime, which calls begin() before the main loop, and JevDoneContinuation (vidbyte/agents/jev/continuation/) calls check() each time the main agent tries to finish; outcomes reach the user through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus one field per enabled JevDoneCheck, typed as that check's section payload and described by its SECTION text, so a new check adds one entry to _SECTIONS and one case each to _section() and _judge() instead of a new class; a check whose items come from somewhere other than the request, like self-review's objections, adds no run-state section; what the main agent reads when a check fails belongs to JevDoneContinuation. Every enabled check's questions go to Jev in one request (combine()), over one shared state. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelRunner.score_noul turns answers into a pass or fail. Writing the state, the review, and the evidence is generation, so it belongs to generative agents (this class, JevReviewer, and JevHandoff, skills/asking-jev-questions/SKILL.md strategy 16); Jev only recognizes whether the evidence shows each item.
COMMON MODIFICATION PATTERNS: Change what the agent writes in vidbyte/prompts/prompts/jev_run_state/system_prompt.md and each field's description in vidbyte/lib/dataclasses/jev.py; add a done check's section to _SECTIONS, its record conversion to _record(), and its commented case to _section() and _judge().
KNOWN EDGE CASES: Every failure fails open: no run state means no check, and an unavailable handoff or Jev answer marks the check unavailable and lets the answer stand. A request with no deliverables, or a review with no objections, passes with nothing to ask; a failed review makes only the self-review check unavailable. Like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-self-review-done-criteria.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import Field, create_model

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.done.handoff import JevHandoff
from vidbyte.agents.jev.done.reviewer import JevReviewer
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_OBJECTION_FIELD,
    JEV_DONE_OBJECTIONS_FIELD,
    JEV_DONE_REQUEST_FIELD,
    JEV_DONE_RESOLVED_WHEN_FIELD,
    JEV_NOUL_TRUE,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevDeliverable,
    JevDoneResult,
    JevHandoffRecord,
    JevMultiPart,
    JevMultiPartPayload,
    JevQuestion,
    JevReviewRecord,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
)
from vidbyte.lib.enums.jev import JevDoneCheck, JevQuestionType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext


class JevRunState(BaseAgent):
    """Generative agent that writes the run state the enabled done checks read, and runs those checks at every finish attempt."""

    # One run-state section per done check whose items come from the request; the field name is the check's value.
    # SELF_REVIEW has none: its items are the objections JevReviewer raises after the work, not before it.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartPayload})

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse) -> None:
        # Reuses the JevAgent's generative model and key; the prompt, limits, schema, and empty tool list are fixed here.
        # @intent done-checks-are-configured-once
        # Like the preflight gate, every done-check input is fixed when JevAgent is built, so the runtime only
        # calls begin() and check() and never reads settings to decide what to ask.
        continual = runtime_settings.continual
        payload = self.schema(continual.checks)
        super().__init__(
            name=f"{settings.name}-run-state",
            system_prompt=Prompts().get(Prompt.JEV_RUN_STATE_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=continual.run_state_max_iterations, max_tokens=continual.run_state_max_tokens),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=payload,
        )
        self.checks = continual.checks
        self.decision = runtime_settings.decision
        self.response = response
        self.payload = payload
        self.sender = settings.name
        self.handoff_writer = JevHandoff(settings, continual)
        self.reviewer = JevReviewer(settings, continual) if JevDoneCheck.SELF_REVIEW in continual.checks else None
        self.review: JevReviewRecord | None = None
        self.request = ""
        self.record: JevRunStateRecord | None = None
        self.rendered = ""
        self.handoff: JevHandoffRecord | None = None

    @classmethod
    def schema(cls, checks: tuple[JevDoneCheck, ...]) -> type[JevRunStatePayload]:
        """Return the run state's output schema: the central JevRunStatePayload plus one described section per enabled check that has one."""
        sections: dict[str, Any] = {check.value: (cls._SECTIONS[check], Field(description=cls._SECTIONS[check].SECTION)) for check in checks if check in cls._SECTIONS}
        return create_model("JevRunStatePayload", __base__=JevRunStatePayload, **sections)

    async def begin(self, request: str) -> None:
        """Write this run's state from the user's request and record it; a failure leaves no state, so no check runs."""
        self.request = request
        self.record = None
        self.rendered = ""
        self.history.clear()
        try:
            reply = await self.arun(AgentInput(prompt=request))
            if isinstance(reply.structured, self.payload):
                self.record = self._record(reply.structured)
                self.rendered = reply.structured.model_dump_json()
        except VidbyteSdkError:
            # @intent a-missing-run-state-fails-open
            # Done checks are advisory, like preflight: without a state there is nothing to check against,
            # so the main agent runs and finishes exactly as it would with no done check enabled.
            self.record = None
        self.response.run_state(self.record)

    async def check(self, final_answer: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> tuple[JevDoneResult, ...]:
        """Run every enabled done check on this finish attempt, record every result, and return the checks that failed."""
        self.handoff = None
        self.review = None
        if self.record is None:
            return ()
        if self.reviewer is not None:
            # @intent the-strict-review-runs-before-the-checks
            # The owner asked for one tool-free turn, before the checks run, that asks what a strict reviewer would
            # reject; its objections become the items the handoff gathers evidence for and Jev judges.
            self.review = await self.reviewer.review(self.request, JevHandoff.window(self.rendered, responses, calls, final_answer, sender=self.sender))
            self.response.review(self.review)
        review = "" if self.reviewer is None else self.reviewer.rendered
        window = JevHandoff.window(self.rendered, responses, calls, final_answer, sender=self.sender, review=review)
        self.handoff = await self.handoff_writer.compile(self.request, self.record, window, self.review)
        self.response.handoff(self.handoff)
        decision = await self._ask(self.handoff)
        failed: list[JevDoneResult] = []
        for check in self.checks:
            result = self._judge(check, self.handoff, decision)
            self.response.done(result)
            if not result.passed:
                failed.append(result)
        return tuple(failed)

    def combine(self, handoff: JevHandoffRecord) -> JevDecisionRequest | None:
        """Return one Jev request holding every enabled check's questions over one shared state, or None when no check has a question to ask."""
        # @intent every-done-check-asks-in-one-request
        # The owner asked for the enabled checks' questions to be combined and sent to Jev at once, like the
        # preflight gate; each question names the item it judges, so they all read the same state.
        state: dict[str, object] = {JEV_DONE_REQUEST_FIELD: self.request}
        questions: list[JevQuestion] = []
        for check in self.checks:
            section, asked = self._section(check, handoff)
            state.update(section)
            questions.extend(asked)
        if not questions:
            return None
        return JevDecisionRequest(state=state, questions=tuple(questions))

    async def _ask(self, handoff: JevHandoffRecord | None) -> DecisionModelResponse | None:
        # Sends the one combined request and returns Jev's reply, or None when there was nothing to ask or Jev failed.
        # @intent done-checks-fail-open
        # Done checks are advisory, like preflight: a missing TypeSafe key, a provider failure, or a request Jev
        # cannot accept returns None, which marks every check that asked a question unavailable instead of
        # blocking the main agent's answer.
        if handoff is None:
            return None
        try:
            request = self.combine(handoff)
            if request is None:
                return None
            return await DecisionModelRunner(self.decision).arun(request)
        except VidbyteSdkError:
            return None

    def _section(self, check: JevDoneCheck, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        # Returns one enabled check's part of the shared state and its questions; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # One entry per deliverable, keyed by id, holds the defining material and only that deliverable's
                # evidence (skills/asking-jev-questions T13); the handoff's own `missing` text stays out because it
                # is the handoff writer's judgment, not the run. One question per deliverable names its id.
                state = None if self.record is None else self.record.multi_part
                if state is None or handoff.multi_part is None:
                    return {}, ()
                (question,) = JevDoneRegistry.questions(JevDoneCheck.MULTI_PART)
                evidence = {item.id: item.evidence for item in handoff.multi_part.deliverables}
                entries = {
                    deliverable.id: {
                        JEV_DONE_DELIVERABLE_FIELD: deliverable.description,
                        JEV_DONE_COMPLETION_SIGNAL_FIELD: deliverable.completion_signal,
                        JEV_DONE_EVIDENCE_FIELD: evidence[deliverable.id],
                    }
                    for deliverable in state.deliverables
                }
                return {JEV_DONE_DELIVERABLES_FIELD: entries}, tuple(question.to_question(identifier) for identifier in state.ids())
            case JevDoneCheck.SELF_REVIEW:
                # One entry per objection, keyed by id, holds the reviewer's objection and acceptance condition as the
                # defining material beside that objection's evidence (T13); the handoff's `missing` text stays out.
                # Both questions are asked per objection, since "does it still stand" splits into two recognitions.
                if self.review is None or handoff.self_review is None or not self.review.objections:
                    return {}, ()
                questions = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
                evidence = {item.id: item.evidence for item in handoff.self_review.objections}
                entries = {
                    objection.id: {
                        JEV_DONE_OBJECTION_FIELD: objection.objection,
                        JEV_DONE_RESOLVED_WHEN_FIELD: objection.resolved_when,
                        JEV_DONE_EVIDENCE_FIELD: evidence[objection.id],
                    }
                    for objection in self.review.objections
                }
                return {JEV_DONE_OBJECTIONS_FIELD: entries}, tuple(question.to_question(identifier) for identifier in self.review.ids() for question in questions)

    def _judge(self, check: JevDoneCheck, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Scores one enabled done check from the combined request's answers; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # Every deliverable the request asks for must be shown produced in full: Jev answered one
                # question per deliverable, and code joins them with a veto so one clear no is never averaged away.
                return self._multi_part(handoff, decision)
            case JevDoneCheck.SELF_REVIEW:
                # An objection stands unless Jev is confident the work already meets its acceptance condition or
                # confident that condition asks for work the request does not; the check passes when none stands.
                return self._self_review(handoff, decision)

    def _multi_part(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Turns Jev's answers about each deliverable into the multi-part result, scored with score_noul.
        # The deliverables the run state listed are what this check judges; without them, or without the
        # handoff's evidence for them, there is nothing to judge, so the check is unavailable and fails open.
        state = None if self.record is None else self.record.multi_part
        if state is None or handoff is None or handoff.multi_part is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        # A request that asks for no output (a greeting, a plain question) has no deliverable to miss, so it
        # passes; combine() asked Jev nothing for it, so there is no score.
        if not state.deliverables:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None)
        # Deliverables were asked about, but the one combined Jev request failed: fail open like preflight.
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        (question,) = JevDoneRegistry.questions(JevDoneCheck.MULTI_PART)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART)
        # The combined reply holds every enabled check's answers under their question names; pick out this
        # check's answers and key them by deliverable id, which is how the result and the continuation name them.
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in state.ids() if question.name(identifier) in decision.answers}
        # The threshold is both the mean threshold and the veto, so every deliverable must reach it on its own
        # and one clear no is never averaged away by the others. A missing answer makes score_noul return None.
        verdict = DecisionModelRunner.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        # The deliverables below the threshold are the ones the continuation sends the main agent back to finish.
        incomplete = tuple(identifier for identifier in state.ids() if verdict.answers[identifier].probabilities[JEV_NOUL_TRUE] < threshold)
        # One request answered every enabled check, so its usage is the cost of this finish attempt's checks.
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

    def _self_review(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Turns Jev's two answers about each objection into the self-review result.
        # Without a review, a handoff, or its evidence for the objections, there is nothing to judge: fail open.
        if self.review is None or handoff is None or handoff.self_review is None:
            return JevDoneResult(check=JevDoneCheck.SELF_REVIEW, score=None, available=False)
        # A strict reviewer who would approve the work as it stands raised nothing, so the check passes unasked.
        if not self.review.objections:
            return JevDoneResult(check=JevDoneCheck.SELF_REVIEW, score=None)
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.SELF_REVIEW, score=None, available=False)
        resolved, in_scope = JevDoneRegistry.questions(JevDoneCheck.SELF_REVIEW)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.SELF_REVIEW)
        # The combined reply holds every enabled check's answers; pick out both answers per objection by question
        # name. A missing or non-noul answer would hide a judgment, so the check is unavailable instead.
        names = [question.name(identifier) for identifier in self.review.ids() for question in (resolved, in_scope)]
        answers = {name: decision.answers[name] for name in names if name in decision.answers}
        if len(answers) != len(names) or any(answer.question_type is not JevQuestionType.NOUL for answer in answers.values()):
            return JevDoneResult(check=JevDoneCheck.SELF_REVIEW, score=None, available=False)
        # @intent doubt-keeps-an-objection-standing
        # The strict stance puts the burden on setting an objection aside: it is cleared only when Jev is confident
        # the work meets its acceptance condition (a real, unresolved objection fails this) or confident the
        # condition asks for work the request does not; a clearance below the threshold keeps it in the Focus.
        clearance = {
            identifier: max(answers[resolved.name(identifier)].probabilities[JEV_NOUL_TRUE], 1.0 - answers[in_scope.name(identifier)].probabilities[JEV_NOUL_TRUE])
            for identifier in self.review.ids()
        }
        # Standing objections keep the reviewer's order, most serious first, which is the order the Focus lists them.
        standing = tuple(identifier for identifier in self.review.ids() if clearance[identifier] < threshold)
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.SELF_REVIEW, score=math.fsum(clearance.values()) / len(clearance), passed=not standing, answers=answers, incomplete=standing, usage=usage)

    def _record(self, payload: JevRunStatePayload) -> JevRunStateRecord:
        # Converts the validated reply into the frozen record the response exposes and the checks read.
        multi_part = None
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if isinstance(section, JevMultiPartPayload):
            multi_part = JevMultiPart(tuple(JevDeliverable(item.id, item.description.strip(), item.completion_signal.strip()) for item in section.deliverables))
        return JevRunStateRecord(
            goal=payload.goal.strip(),
            objective=payload.objective.strip(),
            mission=payload.mission.strip(),
            what_not_to_do=tuple(limit.strip() for limit in payload.what_not_to_do if limit.strip()),
            multi_part=multi_part,
            usage=self.get_usage(),
        )


__all__ = ["JevRunState"]
