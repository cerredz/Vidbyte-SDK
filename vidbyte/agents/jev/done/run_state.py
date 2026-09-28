"""FILE: vidbyte/agents/jev/done/run_state.py

PURPOSE: Implements JevRunState, the class that owns JevAgent's done checks: it builds the structured run-state schema the enabled checks need, runs the generative model once to write the run state from the user's request, and at every finish attempt has JevHandoff compile the evidence, asks Jev the checks' fixed questions, and decides whether the main agent goes back to work.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.done is set and passes it to JevRuntime, which calls begin() before the main loop and check() each time the main agent tries to finish; outcomes reach the user through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus one field per enabled JevDoneCheck, typed as that check's section payload and described by its SECTION text, so a new check adds one entry to _SECTIONS, one case to _judge(), and one to _feedback() instead of a new class. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelRunner.score_noul turns answers into a pass or fail. Writing the state and the evidence is generation, so it belongs to generative agents (this class and JevHandoff, skills/asking-jev-questions/SKILL.md strategy 16); Jev only recognizes whether the evidence shows each item.
COMMON MODIFICATION PATTERNS: Change what the agent writes in vidbyte/prompts/prompts/jev_run_state/system_prompt.md and each field's description in vidbyte/lib/dataclasses/jev.py; add a done check's section to _SECTIONS, its record conversion to _record(), and its commented case to _judge() and _feedback().
KNOWN EDGE CASES: Every failure fails open: no run state means no check, and an unavailable handoff or Jev answer marks the check unavailable and lets the answer stand. A request with no deliverables passes with nothing to ask. After JEV_DONE_MAX_CONTINUATIONS continuations the latest verdict is still recorded but the answer stands. Like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import Field, create_model

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.done.handoff import JevHandoff
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_MAX_CONTINUATIONS,
    JEV_DONE_REQUEST_FIELD,
    JEV_NOUL_TRUE,
    JEV_RUN_STATE_MAX_ITERATIONS,
    JEV_RUN_STATE_MAX_TOKENS,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevDeliverable,
    JevDoneResult,
    JevHandoffRecord,
    JevMultiPart,
    JevMultiPartPayload,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
)
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext

# The label in front of what the handoff says is missing, in the feedback the main agent reads.
MISSING_LABEL = "Still missing:"


class JevRunState(BaseAgent):
    """Generative agent that writes the run state the enabled done checks read, and runs those checks at every finish attempt."""

    # One run-state section per done check; the field name is the check's value, and the enum is the only option list.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartPayload})

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse) -> None:
        # Reuses the JevAgent's generative model and key; the prompt, limits, schema, and empty tool list are fixed here.
        # @intent done-checks-are-configured-once
        # Like the preflight gate, every done-check input is fixed when JevAgent is built, so the runtime only
        # calls begin() and check() and never reads settings to decide what to ask.
        payload = self.schema(runtime_settings.done)
        super().__init__(
            name=f"{settings.name}-run-state",
            system_prompt=Prompts().get(Prompt.JEV_RUN_STATE_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_RUN_STATE_MAX_ITERATIONS, max_tokens=JEV_RUN_STATE_MAX_TOKENS),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=payload,
        )
        self.checks = runtime_settings.done
        self.decision = runtime_settings.decision
        self.response = response
        self.payload = payload
        self.sender = settings.name
        self.handoff_writer = JevHandoff(settings, self.checks)
        self.request = ""
        self.record: JevRunStateRecord | None = None
        self.rendered = ""

    @classmethod
    def schema(cls, checks: tuple[JevDoneCheck, ...]) -> type[JevRunStatePayload]:
        """Return the run state's output schema: the central JevRunStatePayload plus one described section per enabled check."""
        sections: dict[str, Any] = {check.value: (cls._SECTIONS[check], Field(description=cls._SECTIONS[check].SECTION)) for check in checks}
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

    async def check(self, final_answer: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> str | None:
        """Run every enabled done check on this finish attempt and return feedback when the main agent must keep working."""
        if self.record is None:
            return None
        window = JevHandoff.window(self.rendered, responses, calls, final_answer, sender=self.sender)
        handoff = await self.handoff_writer.compile(self.request, self.record, window)
        self.response.handoff(handoff)
        failed: list[JevDoneResult] = []
        for check in self.checks:
            result = await self._judge(check, handoff)
            self.response.done(result)
            if not result.passed:
                failed.append(result)
        # @intent continuations-are-bounded
        # A check that keeps failing must not trap the run: after the cap the latest verdict stays on the
        # response for the caller to read, but the main agent's answer stands.
        if not failed or handoff is None or self.response.state.continuations >= JEV_DONE_MAX_CONTINUATIONS:
            return None
        self.response.continued()
        return "\n\n".join(self._feedback(result, handoff) for result in failed)

    async def _judge(self, check: JevDoneCheck, handoff: JevHandoffRecord | None) -> JevDoneResult:
        # Runs one enabled done check against the compiled evidence; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # Every deliverable the request asks for must be shown produced in full: one Jev request per
                # deliverable, joined in code with a veto so one clear no is never averaged away.
                return await self._multi_part(handoff)

    async def _multi_part(self, handoff: JevHandoffRecord | None) -> JevDoneResult:
        # Asks Jev whether the evidence shows each deliverable produced in full and scores the answers with score_noul.
        # @intent one-deliverable-per-request
        # Each request's state holds one deliverable, its completion signal, and only its own evidence, so Jev
        # never has to find its item in a list or combine verdicts (skills/asking-jev-questions strategy 11, T15).
        state = None if self.record is None else self.record.multi_part
        if state is None or handoff is None or handoff.multi_part is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        if not state.deliverables:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None)
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART)
        evidence = {item.id: item.evidence for item in handoff.multi_part.deliverables}
        try:
            runner = DecisionModelRunner(self.decision)
            decisions = await asyncio.gather(*(runner.arun(JevDecisionRequest(state=self._state(deliverable, evidence[deliverable.id]), questions=(question.to_question(),))) for deliverable in state.deliverables))
        except VidbyteSdkError:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        answers: dict[str, JevAnswer] = {}
        for deliverable, decision in zip(state.deliverables, decisions, strict=True):
            answer = decision.answers.get(question.key.value)
            if answer is not None:
                answers[deliverable.id] = answer
        verdict = DecisionModelRunner.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        incomplete = tuple(identifier for identifier in state.ids() if verdict.answers[identifier].probabilities[JEV_NOUL_TRUE] < threshold)
        return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=self._usage(decisions))

    def _feedback(self, result: JevDoneResult, handoff: JevHandoffRecord) -> str:
        # Returns what the main agent reads for one failed check: the question's gap and what the handoff says is missing.
        match result.check:
            case JevDoneCheck.MULTI_PART:
                # Names each incomplete deliverable in the user's terms, then the handoff's own list of what is missing.
                gap = JevDoneRegistry.question(JevDoneCheck.MULTI_PART).gap
                state = None if self.record is None else self.record.multi_part
                deliverables = {} if state is None else {item.id: item for item in state.deliverables}
                missing = {} if handoff.multi_part is None else {item.id: item.missing for item in handoff.multi_part.deliverables}
                return "\n\n".join(f"{deliverables[identifier].description}\n{gap}\n{MISSING_LABEL} {missing[identifier]}" for identifier in result.incomplete)

    def _state(self, deliverable: JevDeliverable, evidence: str) -> Mapping[str, object]:
        # Builds the four-field state every done question reads, described in vidbyte/lib/jev/done/multi_part.py.
        # @intent the-state-defines-the-right-answer
        # The deliverable and its completion signal define what counts as done (skills/asking-jev-questions T13),
        # and the handoff's own `missing` text stays out because it is the handoff writer's judgment, not the run.
        return {
            JEV_DONE_REQUEST_FIELD: self.request,
            JEV_DONE_DELIVERABLE_FIELD: deliverable.description,
            JEV_DONE_COMPLETION_SIGNAL_FIELD: deliverable.completion_signal,
            JEV_DONE_EVIDENCE_FIELD: evidence,
        }

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

    @staticmethod
    def _usage(decisions: Sequence[DecisionModelResponse]) -> JevUsage | None:
        # Sums the usage of every Jev request one check sent, or returns None when TypeSafe reported none.
        reported = [usage for usage in (JevUsage.from_usage_payload(decision.usage or {}) for decision in decisions) if usage is not None]
        if not reported:
            return None
        return JevUsage.from_usage_payload({"input_tokens": sum(usage.input_tokens or 0 for usage in reported), "output_tokens": sum(usage.output_tokens or 0 for usage in reported)})


__all__ = ["JevRunState"]
