"""FILE: vidbyte/agents/jev/done/run_state.py

PURPOSE: Implements JevRunState, the class that owns JevAgent's done checks: it writes request-derived run state once, has JevHandoff compile final-answer evidence at every finish attempt, asks every enabled check's fixed questions in one request, and returns the checks that failed.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.continual enables a done check and passes it to JevRuntime, which calls begin() before the main loop, and JevDoneContinuation (vidbyte/agents/jev/continuation/) calls check() each time the main agent tries to finish; outcomes reach the user through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus request-derived sections for enabled checks, while claims that do not exist until the final answer are extracted by JevHandoff and added to the shared Jev state at check time. Every enabled check's questions go to Jev in one request (combine()), and what the main agent reads on failure belongs to JevDoneContinuation. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelHelper sends requests and scores answers. Generative agents write the state and evidence; Jev only recognizes whether the evidence shows each item.
COMMON MODIFICATION PATTERNS: Add request-derived sections to _SECTIONS, _record(), and the commented _section() case; add post-run-derived sections to JevHandoff and build their claims and questions in _section() from its typed record. Add every check's commented case to _judge() and its continuation explanation to JevDoneContinuation._explain(). INPUT_EXHAUSTION also derives count and traversal status from handoff observations before Jev judges each collection.
KNOWN EDGE CASES: Every failure fails open: no run state means no check, and an unavailable handoff or Jev answer marks the check unavailable and lets the answer stand. An empty request-derived item list or an empty post-run claim list passes with nothing to ask. Like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-input-exhaustion-done-criteria.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus request-derived sections for enabled checks, while claims and observed problems that do not exist until work is underway are extracted by JevHandoff and added to the shared Jev state at check time. Every enabled check's questions go to Jev in one request (combine()), and what the main agent reads on failure belongs to JevDoneContinuation. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelHelper sends requests and scores answers. Generative agents write the state and evidence; Jev only recognizes whether the evidence shows each item.
COMMON MODIFICATION PATTERNS: Add request-derived sections to _SECTIONS, _record(), and the commented _section() case; add post-run-derived sections to JevHandoff and build their claims and questions in _section() from its typed record. Add every check's commented case to _judge() and its continuation explanation to JevDoneContinuation._explain().
KNOWN EDGE CASES: Every failure fails open: no run state means no check, and an unavailable handoff or Jev answer marks the check unavailable and lets the answer stand. An empty request-derived item list or an empty post-run claim list passes with nothing to ask. Like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

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
    JEV_DONE_CLAIM_ASSERTION_FIELD,
    JEV_DONE_CLAIM_ASSERTION_ID_FIELD,
    JEV_DONE_CLAIM_ASSERTION_SEPARATOR,
    JEV_DONE_CLAIM_ASSERTION_STATEMENT_FIELD,
    JEV_DONE_CLAIM_COMPLETION_CRITERIA_FIELD,
    JEV_DONE_CLAIM_DESCRIPTION_FIELD,
    JEV_DONE_CLAIM_FIELD,
    JEV_DONE_CLAIM_IDENTITY_FIELD,
    JEV_DONE_CLAIM_INTENT_FIELD,
    JEV_DONE_CLAIM_KIND_FIELD,
    JEV_DONE_CLAIM_OUTPUT_FIELD,
    JEV_DONE_CLAIM_QUALIFICATIONS_FIELD,
    JEV_DONE_CLAIM_SCOPE_FIELD,
    JEV_DONE_CLAIM_TITLE_FIELD,
    JEV_DONE_CLAIMS_FIELD,
    JEV_DONE_COMPLETION_CRITERION_FIELD,
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_INPUT_EXHAUSTION_FIELD,
    JEV_DONE_OBSERVED_PROXY_FIELD,
    JEV_DONE_PROBLEM_ASSERTION_FIELD,
    JEV_DONE_PROBLEM_DESCRIPTION_FIELD,
    JEV_DONE_PROBLEM_ITEMS_FIELD,
    JEV_DONE_PROBLEM_KIND_FIELD,
    JEV_DONE_PROBLEM_QUALIFICATIONS_FIELD,
    JEV_DONE_PROBLEM_REPAIR_FIELD,
    JEV_DONE_PROBLEM_SCOPE_FIELD,
    JEV_DONE_PROBLEM_TITLE_FIELD,
    JEV_DONE_PROBLEMS_RESOLVED_FIELD,
    JEV_DONE_REQUEST_FIELD,
    JEV_DONE_TARGET_FIELD,
    JEV_DONE_TARGET_OUTCOME_FIELD,
    JEV_DONE_TARGET_OUTCOMES_FIELD,
    JEV_DONE_TARGET_SCOPE_FIELD,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevClaimAssertion,
    JevClaimEvidence,
    JevDecisionRequest,
    JevDeliverable,
    JevDoneResult,
    JevHandoffRecord,
    JevInputExhaustion,
    JevInputExhaustionEvidence,
    JevInputExhaustionObligation,
    JevInputExhaustionPayload,
    JevMultiPart,
    JevMultiPartPayload,
    JevQuestion,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
    JevTargetOutcome,
    JevTargetOutcomeItem,
    JevTargetOutcomePayload,
)
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext


class JevRunState(BaseAgent):
    """Generative agent that writes the run state the enabled done checks read, and runs those checks at every finish attempt."""

    # Request-derived checks add a section here; CLAIMS items are extracted after work by the handoff instead.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({
        JevDoneCheck.MULTI_PART: JevMultiPartPayload,
        JevDoneCheck.INPUT_EXHAUSTION: JevInputExhaustionPayload,
        JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomePayload,
    })

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse) -> None:
        # Reuses the JevAgent's generative model and key; the prompt, limits, schema, and empty tool list are fixed here.
        # @intent done-checks-are-configured-once
        # Like the preflight gate, every done-check input is fixed when JevAgent is built, so the runtime only
        # calls begin() and check() and never reads settings to decide what to ask.
        continual = runtime_settings.continual
        checks = tuple(JevDoneCheck(check) for check in continual.checks)
        payload = self.schema(checks)
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
        self.checks = checks
        self.decision = runtime_settings.decision
        self.response = response
        self.payload = payload
        self.sender = settings.name
        self.handoff_writer = JevHandoff(settings, continual)
        self.request = ""
        self.record: JevRunStateRecord | None = None
        self.rendered = ""
        self.handoff_record: JevHandoffRecord | None = None

    @classmethod
    def schema(cls, checks: tuple[JevDoneCheck, ...]) -> type[JevRunStatePayload]:
        """Return the central request-derived state plus described sections for enabled checks with pre-run items."""
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
        self.handoff_record = None
        if self.record is None:
            return ()
        window = JevHandoff.window(self.rendered, responses, calls, final_answer, sender=self.sender)
        self.handoff_record = await self.handoff_writer.compile(self.request, self.record, window)
        self.response.handoff(self.handoff_record)
        decision = await self._ask(self.handoff_record)
        failed: list[JevDoneResult] = []
        for check in self.checks:
            result = self._judge(check, self.handoff_record, decision)
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
            return await DecisionModelHelper(self.decision).arun(request)
        except VidbyteSdkError:
            return None

    def _section(self, check: JevDoneCheck, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Return the shared-state projection and questions for one enabled check."""
        match check:
            case JevDoneCheck.MULTI_PART:
                return self._multi_part_section(handoff)
            case JevDoneCheck.CLAIMS:
                return self._claims_section(handoff)
            case JevDoneCheck.INPUT_EXHAUSTION:
                return self._input_exhaustion_section(handoff)
            case JevDoneCheck.TARGET_OUTCOME:
                return self._target_outcome_section(handoff)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                return self._problems_resolved_section(handoff)

    def _multi_part_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Pair each requested deliverable with only its run evidence."""
        state = None if self.record is None else self.record.multi_part
        evidence_section = handoff.multi_part
        if state is None or evidence_section is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        evidence = {item.id: item.evidence for item in evidence_section.deliverables}
        entries = {item.id: {JEV_DONE_DELIVERABLE_FIELD: item.description, JEV_DONE_COMPLETION_SIGNAL_FIELD: item.completion_signal, JEV_DONE_EVIDENCE_FIELD: evidence[item.id]} for item in state.deliverables}
        return {JEV_DONE_DELIVERABLES_FIELD: entries}, tuple(question.to_question(identifier) for identifier in state.ids())

    # @intent claims-come-from-finished-answer
    # Claims cannot be known before the main agent works. Each final-answer assertion therefore gets its own question
    # beside its parent context and tool evidence; the handoff's `missing` judgment stays out of Jev's state.
    def _claims_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project final-answer assertions into separate evidence entries and questions."""
        claims = handoff.claims
        if claims is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
        entries = {f"{claim.id}{JEV_DONE_CLAIM_ASSERTION_SEPARATOR}{assertion.id}": self._claim_entry(claim, assertion) for claim in claims.claims for assertion in claim.claim.assertions}
        return {JEV_DONE_CLAIMS_FIELD: entries}, tuple(question.to_question(identifier) for identifier in claims.assertion_ids())

    @staticmethod
    def _claim_entry(claim: JevClaimEvidence, assertion: JevClaimAssertion) -> Mapping[str, object]:
        """Build the Jev-visible context and trace evidence for one atomic claim assertion."""
        return {
            JEV_DONE_CLAIM_FIELD: {
                JEV_DONE_CLAIM_IDENTITY_FIELD: {JEV_DONE_CLAIM_TITLE_FIELD: claim.claim.identity.title, JEV_DONE_CLAIM_DESCRIPTION_FIELD: claim.claim.identity.description, JEV_DONE_CLAIM_INTENT_FIELD: claim.claim.identity.intent},
                JEV_DONE_CLAIM_SCOPE_FIELD: {JEV_DONE_CLAIM_SCOPE_FIELD: claim.claim.scope.scope, JEV_DONE_CLAIM_QUALIFICATIONS_FIELD: list(claim.claim.scope.qualifications)},
                JEV_DONE_CLAIM_KIND_FIELD: claim.claim.kind.value,
                JEV_DONE_CLAIM_OUTPUT_FIELD: claim.claim.output,
                JEV_DONE_CLAIM_ASSERTION_FIELD: {JEV_DONE_CLAIM_ASSERTION_ID_FIELD: assertion.id, JEV_DONE_CLAIM_ASSERTION_STATEMENT_FIELD: assertion.statement, JEV_DONE_CLAIM_COMPLETION_CRITERIA_FIELD: assertion.completion_criteria},
            },
            JEV_DONE_EVIDENCE_FIELD: claim.evidence,
        }

    def _input_exhaustion_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Pair each traversal obligation with its observations and deterministic boundary assessment."""
        state, evidence = (None if self.record is None else self.record.input_exhaustion), handoff.input_exhaustion
        if state is None or evidence is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.INPUT_EXHAUSTION)
        evidence_by_id = {item.id: item for item in evidence.collections}
        entries = {item.id: self._input_exhaustion_entry(item, evidence_by_id[item.id]) for item in state.collections}
        return {JEV_DONE_INPUT_EXHAUSTION_FIELD: entries}, tuple(question.to_question(identifier) for identifier in state.ids())

    def _input_exhaustion_entry(self, item: JevInputExhaustionObligation, observation: JevInputExhaustionEvidence) -> Mapping[str, object]:
        """Build Jev's evidence-only view for one dynamic traversal obligation."""
        assessment, _ = self._input_exhaustion_assessment(item, observation)
        return {"collection": item.collection, "scope": item.scope, "unit": item.unit, "expected_total": item.expected_total, "exhaustion_condition": item.exhaustion_condition, JEV_DONE_EVIDENCE_FIELD: observation.evidence, "visited_unit_ids": list(observation.visited_unit_ids), "source_reported_total": observation.source_reported_total, "unit_type": observation.unit_type, "last_position": observation.last_position, "outstanding_continuation": observation.outstanding_continuation, "terminal_evidence": observation.terminal_evidence, "failed_retrievals": list(observation.failed_retrievals), "deterministic_assessment": assessment}

    # @intent target-outcome-evidence
    # A requested target result must be judged against direct evidence for that target, not inferred from a proxy milestone.
    # Keeping request-derived criteria beside attempt-specific evidence prevents a plan or setup step from masquerading as completion.
    def _target_outcome_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Join request-derived target outcomes with this attempt's proxy and direct run evidence."""
        state = None if self.record is None else self.record.target_outcome
        evidence = handoff.target_outcome
        if state is None or evidence is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.TARGET_OUTCOME)
        evidence_by_id = {item.id: item for item in evidence.items}
        entries = {
            item.id: {
                JEV_DONE_TARGET_OUTCOME_FIELD: item.outcome,
                JEV_DONE_TARGET_FIELD: item.target,
                JEV_DONE_TARGET_SCOPE_FIELD: item.scope,
                JEV_DONE_COMPLETION_CRITERION_FIELD: item.completion_criterion,
                JEV_DONE_OBSERVED_PROXY_FIELD: evidence_by_id[item.id].observed_proxy,
                JEV_DONE_EVIDENCE_FIELD: evidence_by_id[item.id].direct_evidence,
            }
            for item in state.items
        }
        return {JEV_DONE_TARGET_OUTCOMES_FIELD: entries}, tuple(question.to_question(identifier) for identifier in state.ids())

    # @intent repair-verification-boundary
    # Each observed issue and the original request must remain independently judged; otherwise fixing one issue can hide unfinished work.
    # Only run evidence enters Jev's state because the handoff's `missing` summary is a model judgment, not independent evidence.
    def _problems_resolved_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project observed problem episodes and the required original-request check into shared Jev state."""
        evidence = handoff.problems_resolved
        if evidence is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED)
        entries = {
            item.id: {
                "identity": {JEV_DONE_PROBLEM_TITLE_FIELD: item.title, JEV_DONE_PROBLEM_DESCRIPTION_FIELD: item.description},
                JEV_DONE_PROBLEM_SCOPE_FIELD: {JEV_DONE_PROBLEM_SCOPE_FIELD: item.scope, JEV_DONE_PROBLEM_QUALIFICATIONS_FIELD: item.qualifications},
                JEV_DONE_PROBLEM_KIND_FIELD: item.kind.value,
                JEV_DONE_PROBLEM_REPAIR_FIELD: {"attempt_and_outcome": item.repair, "verification": item.verification},
                JEV_DONE_PROBLEM_ASSERTION_FIELD: {
                    "statement": "This observed problem was fully repaired and successfully revalidated." if item.kind.value == "problem" else "The original user request was completed after any repairs.",
                    "completion_criteria": "Run evidence shows the complete repair and a relevant successful revalidation after it." if item.kind.value == "problem" else "Run evidence shows every part of the original user request completed after the repair work.",
                },
                JEV_DONE_EVIDENCE_FIELD: item.evidence,
            }
            for item in evidence.items
        }
        return {JEV_DONE_PROBLEMS_RESOLVED_FIELD: {JEV_DONE_PROBLEM_ITEMS_FIELD: entries}}, tuple(question.to_question(identifier) for identifier in evidence.ids())

    def _judge(self, check: JevDoneCheck, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Scores one enabled done check from the combined request's answers; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # Every deliverable the request asks for must be shown produced in full: Jev answered one
                # question per deliverable, and code joins them with a veto so one clear no is never averaged away.
                return self._multi_part(handoff, decision)
            case JevDoneCheck.CLAIMS:
                # Each extracted final-answer claim must independently reach the support threshold, so one
                # unsupported assertion sends the agent back to that claim rather than averaging it away.
                return self._claims(handoff, decision)
            case JevDoneCheck.INPUT_EXHAUSTION:
                # Count checks stay deterministic; Jev recognizes whether the trace evidence meets the named boundary.
                return self._input_exhaustion(handoff, decision)
            case JevDoneCheck.TARGET_OUTCOME:
                # Each requested target outcome must be demonstrated on its actual target; a proxy alone is insufficient.
                return self._target_outcome(handoff, decision)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                # Every observed issue and the separate original-request item must pass independently.
                return self._problems_resolved(handoff, decision)

    def _multi_part(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Turns Jev's answers about each deliverable into the multi-part result, scored by DecisionModelHelper.
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
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART)
        # The combined reply holds every enabled check's answers under their question names; pick out this
        # check's answers and key them by deliverable id, which is how the result and the continuation name them.
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in state.ids() if question.name(identifier) in decision.answers}
        # The threshold is both the mean threshold and the veto, so every deliverable must reach it on its own
        # and one clear no is never averaged away by the others. A missing answer makes score_noul return None.
        verdict = DecisionModelHelper.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False)
        # The deliverables below the threshold are the ones the continuation sends the main agent back to finish.
        incomplete = tuple(identifier for identifier in state.ids() if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False)
        # One request answered every enabled check, so its usage is the cost of this finish attempt's checks.
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

    # @intent final-answer-claims-need-independent-evidence
    # CLAIMS guards the trust boundary between an agent's self-report and the work the run actually records.
    # A polished final answer can claim edits or passing tests that were never made, and a run-wide average
    # could hide one unsupported statement among several true ones. Each claim therefore gets its own Jev
    # answer and must independently reach the threshold; only the unsupported claims are sent back as focus.
    # The claim list comes from this finish attempt's final answer, not the request: precomputing it would turn
    # expected work into claims the agent never made, while using the handoff's own `missing` verdict would let
    # one generative model validate its own judgment. Keep Jev's input to the claim and tool-call evidence.
    # A rewrite that checks only the final answer or merges claims can let an unperformed change or failed test
    # pass without evidence, misleading the SDK caller about what this run actually accomplished.
    def _claims(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Uses only claims extracted from this finish attempt's final answer and paired with the run's tool-call evidence.
        if handoff is None or handoff.claims is None:
            return JevDoneResult(check=JevDoneCheck.CLAIMS, score=None, available=False)
        # A final answer with no concrete, checkable claims has nothing for Jev to check and passes without a call.
        if not handoff.claims.claims:
            return JevDoneResult(check=JevDoneCheck.CLAIMS, score=None)
        # Missing credentials or a failed combined Jev request leaves the main agent's answer standing.
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.CLAIMS, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.CLAIMS)
        # The combined reply holds every enabled check's answers; keep one answer for each parent.assertion id.
        assertion_ids = handoff.claims.assertion_ids()
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in assertion_ids if question.name(identifier) in decision.answers}
        # The threshold is also the veto, so one unsupported assertion cannot be hidden by sibling assertions.
        verdict = DecisionModelHelper.score_noul(answers, assertion_ids, threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.CLAIMS, score=None, available=False)
        # Answers remain assertion-keyed; the continuation receives parent ids if any child assertion fails.
        incomplete = tuple(
            claim.id
            for claim in handoff.claims.claims
            if any(
                DecisionModelHelper.noul_passes(
                    verdict.answers,
                    f"{claim.id}{JEV_DONE_CLAIM_ASSERTION_SEPARATOR}{assertion.id}",
                    threshold,
                ) is False
                for assertion in claim.claim.assertions
            )
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.CLAIMS, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

    def _input_exhaustion_assessment(self, obligation: JevInputExhaustionObligation, evidence: JevInputExhaustionEvidence) -> tuple[str, bool]:
        """Describe deterministic traversal evidence and return whether it fails the requested stopping condition."""
        distinct_count = len(set(evidence.visited_unit_ids))
        if evidence.outstanding_continuation is not None or evidence.failed_retrievals:
            return "Traversal is incomplete: an outstanding continuation or failed retrieval remains in the trace.", True
        if evidence.unit_type != obligation.unit:
            if obligation.expected_total is not None:
                return f"The user explicitly requested {obligation.expected_total} {obligation.unit} units, but the handoff's identifiers are typed as {evidence.unit_type or 'unknown'}; code cannot compare these units, and terminal evidence does not establish the requested count.", True
            if evidence.terminal_evidence is None:
                return "The handoff does not establish that visited identifiers use the requested unit type, and no affirmative terminal signal establishes exhaustion.", True
            return "Code did not compare visited identifiers with a total because their unit type does not match the obligation; Jev must judge the supplied affirmative terminal signal against the requested scope.", False
        if obligation.expected_total is not None:
            return self._requested_total_assessment(obligation, evidence, distinct_count)
        if evidence.source_reported_total is not None:
            return self._source_total_assessment(obligation, evidence, distinct_count)
        if evidence.terminal_evidence is not None:
            return "The trace includes an affirmative terminal signal for Jev to recognize against the stated exhaustion condition.", False
        return "The handoff has no comparable source total or affirmative terminal signal, so the requested exhaustion condition is not established.", True

    @staticmethod
    def _requested_total_assessment(obligation: JevInputExhaustionObligation, evidence: JevInputExhaustionEvidence, distinct_count: int) -> tuple[str, bool]:
        """Compare trace-backed units to the explicit total in the original request."""
        expected = obligation.expected_total
        if distinct_count != expected:
            return f"Code compared {distinct_count} distinct visited {obligation.unit} identifiers with the user's requested total of {expected}; the counts do not match.", True
        if expected == 0 and evidence.terminal_evidence is None and not (evidence.unit_type == obligation.unit and evidence.source_reported_total == 0):
            return "The user requested an empty collection, but the trace has no affirmative source evidence of zero results or terminal exhaustion.", True
        if evidence.source_reported_total is not None and evidence.unit_type == obligation.unit and evidence.source_reported_total != expected:
            return f"Code matched the user's requested total of {expected} {obligation.unit} identifiers, while the source reports {evidence.source_reported_total}; Jev must assess this conflict against the stated scope.", False
        return f"Code compared {distinct_count} distinct visited {obligation.unit} identifiers with the user's requested total of {expected}; the counts match.", False

    @staticmethod
    def _source_total_assessment(obligation: JevInputExhaustionObligation, evidence: JevInputExhaustionEvidence, distinct_count: int) -> tuple[str, bool]:
        """Compare units to a source total or require terminal evidence for a mismatched unit type."""
        if evidence.unit_type != obligation.unit:
            if evidence.terminal_evidence is None:
                return "The reported total uses a different unit type, and no affirmative terminal signal establishes the requested boundary.", True
            return "The reported total uses a different unit type; Jev must judge the supplied affirmative terminal signal against the requested condition.", False
        total = evidence.source_reported_total
        if distinct_count != total:
            return f"Code compared {distinct_count} distinct visited {obligation.unit} identifiers with the source-reported total of {total}; the counts do not match.", True
        return f"Code compared {distinct_count} distinct visited {obligation.unit} identifiers with the source-reported total of {total}; the counts match.", False

    def _input_exhaustion(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        """Score each traversal; readable evidence without a completion boundary is incomplete, while model failures fail open."""
        state = None if self.record is None else self.record.input_exhaustion
        evidence = None if handoff is None else handoff.input_exhaustion
        if state is None or evidence is None:
            return JevDoneResult(check=JevDoneCheck.INPUT_EXHAUSTION, score=None, available=False)
        if not state.collections:
            return JevDoneResult(check=JevDoneCheck.INPUT_EXHAUSTION, score=None)
        observations = {item.id: item for item in evidence.collections}
        assessments = {item.id: self._input_exhaustion_assessment(item, observations[item.id]) for item in state.collections}
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.INPUT_EXHAUSTION, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.INPUT_EXHAUSTION)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.INPUT_EXHAUSTION)
        identifiers = state.ids()
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in identifiers if question.name(identifier) in decision.answers}
        verdict = DecisionModelHelper.score_noul(answers, identifiers, threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.INPUT_EXHAUSTION, score=None, available=False)
        incomplete = tuple(
            identifier
            for identifier in identifiers
            if assessments[identifier][1] or DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.INPUT_EXHAUSTION, score=verdict.score, passed=not incomplete, answers=verdict.answers, incomplete=incomplete, usage=usage)
    def _target_outcome(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Missing records or evidence make the check unavailable; done checks are advisory and always fail open.
        state = None if self.record is None else self.record.target_outcome
        if state is None or handoff is None or handoff.target_outcome is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        # Requests without a distinct, sufficiently specified real target have no outcomes to judge and pass cleanly.
        if not state.items:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None)
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.TARGET_OUTCOME)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.TARGET_OUTCOME)
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in state.ids() if question.name(identifier) in decision.answers}
        verdict = DecisionModelHelper.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        incomplete = tuple(identifier for identifier in state.ids() if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False)
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

    def _problems_resolved(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        """Score every dynamic problem item and the original-request completion item with a veto threshold."""
        # @intent every-observed-problem-and-the-original-task-are-required
        # Dynamic failures cannot be predicted before the work, so every finish attempt must score the handoff's
        # fresh item set. Requiring each answer independently prevents one repaired issue from hiding another
        # unresolved issue or the original request's unfinished work; a missing answer remains unavailable.
        evidence = None if handoff is None else handoff.problems_resolved
        if evidence is None:
            return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=None, available=False)
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.PROBLEMS_RESOLVED)
        ids = evidence.ids()
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in ids if question.name(identifier) in decision.answers}
        verdict = DecisionModelHelper.score_noul(answers, ids, threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=None, available=False)
        incomplete = tuple(identifier for identifier in ids if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False)
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

    def _record(self, payload: JevRunStatePayload) -> JevRunStateRecord:
        # Converts the validated reply into the frozen record the response exposes and the checks read.
        multi_part = None
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if isinstance(section, JevMultiPartPayload):
            multi_part = JevMultiPart(tuple(JevDeliverable(item.id, item.description.strip(), item.completion_signal.strip()) for item in section.deliverables))
        input_exhaustion = None
        exhaustion_section = getattr(payload, JevDoneCheck.INPUT_EXHAUSTION.value, None)
        if isinstance(exhaustion_section, JevInputExhaustionPayload):
            input_exhaustion = JevInputExhaustion(tuple(
                JevInputExhaustionObligation(item.id, item.collection.strip(), item.scope.strip(), item.unit.strip(), item.expected_total, item.exhaustion_condition.strip())
                for item in exhaustion_section.collections
            ))
        target_outcome = None
        outcome_section = getattr(payload, JevDoneCheck.TARGET_OUTCOME.value, None)
        if isinstance(outcome_section, JevTargetOutcomePayload):
            target_outcome = JevTargetOutcome(tuple(
                JevTargetOutcomeItem(item.id, item.outcome.strip(), item.target.strip(), item.scope.strip(), item.completion_criterion.strip())
                for item in outcome_section.items
            ))
        return JevRunStateRecord(
            goal=payload.goal.strip(),
            objective=payload.objective.strip(),
            mission=payload.mission.strip(),
            what_not_to_do=tuple(limit.strip() for limit in payload.what_not_to_do if limit.strip()),
            multi_part=multi_part,
            input_exhaustion=input_exhaustion,
            target_outcome=target_outcome,
            usage=self.get_usage(),
        )


__all__ = ["JevRunState"]
