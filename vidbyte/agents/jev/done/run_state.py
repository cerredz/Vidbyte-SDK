"""FILE: vidbyte/agents/jev/done/run_state.py

PURPOSE: Implements JevRunState, the class that owns JevAgent's done checks: it writes request-derived run state once, has JevHandoff compile final-answer evidence at every finish attempt, asks every enabled check's fixed questions in one request, and returns the checks that failed.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.continual enables a done check and passes it to JevRuntime, which calls begin() before the main loop, and JevDoneContinuation (vidbyte/agents/jev/continuation/) calls check() each time the main agent tries to finish; outcomes reach the user through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus request-derived sections for enabled checks, while claims that do not exist until the final answer are extracted by JevHandoff and added to the shared Jev state at check time. Every enabled check's questions go to Jev in one request (combine()), and what the main agent reads on failure belongs to JevDoneContinuation. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelHelper sends requests and scores answers. Generative agents write the state and evidence; code computes exact counts; Jev recognizes whether evidence shows each item.
COMMON MODIFICATION PATTERNS: Add request-derived sections to _SECTIONS, _record(), and the commented _section() case; OUTPUT_COUNT derives observed counts from the handoff's candidate keys before projection. Add post-run-derived sections to JevHandoff and build their claims and questions in _section() from its typed record. Add every check's commented case to _judge() and its continuation explanation to JevDoneContinuation._explain().
ARCHITECTURE NOTE: The run state is general: its schema is the central JevRunStatePayload plus request-derived sections for enabled checks, while claims and observed problems that do not exist until work is underway are extracted by JevHandoff and added to the shared Jev state at check time. Every enabled check's questions go to Jev in one request (combine()), and what the main agent reads on failure belongs to JevDoneContinuation. Question text and thresholds stay in vidbyte/lib/jev/done/ (JevDoneRegistry), and DecisionModelHelper sends requests and scores answers. Generative agents write the state and evidence; Jev only recognizes whether the evidence shows each item.
COMMON MODIFICATION PATTERNS: Add request-derived sections to _SECTIONS, _record(), and the commented _section() case; add post-run-derived sections to JevHandoff and build their claims and questions in _section() from its typed record. Add every check's commented case to _judge() and its continuation explanation to JevDoneContinuation._explain().
KNOWN EDGE CASES: Every failure fails open: no run state means no check, and an unavailable handoff or Jev answer marks the check unavailable and lets the answer stand. An empty request-derived item list or an empty post-run claim list passes with nothing to ask. Like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
    JEV_DONE_COMPLETION_SIGNAL_FIELD,
    JEV_DONE_DELIVERABLE_FIELD,
    JEV_DONE_DELIVERABLES_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
    JEV_DONE_OUTPUT_COUNT_COMPLETION_FIELD,
    JEV_DONE_OUTPUT_COUNT_DESCRIPTION_FIELD,
    JEV_DONE_OUTPUT_COUNT_DISTINCT_FIELD,
    JEV_DONE_OUTPUT_COUNT_DISTINCTNESS_FIELD,
    JEV_DONE_OUTPUT_COUNT_ENTRIES_FIELD,
    JEV_DONE_OUTPUT_COUNT_ENTRY_EVIDENCE_FIELD,
    JEV_DONE_OUTPUT_COUNT_ENTRY_ID_FIELD,
    JEV_DONE_OUTPUT_COUNT_ENTRY_KEY_FIELD,
    JEV_DONE_OUTPUT_COUNT_ENTRY_VALUE_FIELD,
    JEV_DONE_OUTPUT_COUNT_MET_FIELD,
    JEV_DONE_OUTPUT_COUNT_OBLIGATION_FIELD,
    JEV_DONE_OUTPUT_COUNT_OBSERVED_FIELD,
    JEV_DONE_OUTPUT_COUNT_SCOPE_FIELD,
    JEV_DONE_OUTPUT_COUNT_TARGET_FIELD,
    JEV_DONE_OUTPUT_COUNT_UNIT_FIELD,
    JEV_DONE_OUTPUT_COUNTS_FIELD,
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
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevDeliverable,
    JevDoneResult,
    JevHandoffRecord,
    JevMultiPart,
    JevMultiPartPayload,
    JevOutputCount,
    JevOutputCountEvidenceItem,
    JevOutputCountObligation,
    JevOutputCountPayload,
    JevQuestion,
    JevRunStatePayload,
    JevRunStateRecord,
    JevSectionPayload,
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

    # Request-derived checks add sections here; CLAIMS items are extracted after work by the handoff instead.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartPayload, JevDoneCheck.OUTPUT_COUNT: JevOutputCountPayload})

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse) -> None:
        # Reuses the JevAgent's generative model and key; the prompt, limits, schema, and empty tool list are fixed here.
        # @intent done-checks-are-configured-once
        # Like the preflight gate, every done-check input is fixed when JevAgent is built, so the runtime only
        # calls begin() and check() and never reads settings to decide what to ask.
        continual = runtime_settings.continual
        checks = JevDoneRegistry.validate(continual.checks)
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
        # Returns one enabled check's part of the shared state and its questions; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # One entry per deliverable, keyed by id, holds the defining material and only that deliverable's
                # evidence (skills/asking-jev-questions T13); the handoff's own `missing` text stays out because it
                # is the handoff writer's judgment, not the run. One question per deliverable names its id.
                state = None if self.record is None else self.record.multi_part
                if state is None or handoff.multi_part is None:
                    return {}, ()
                question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
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
            case JevDoneCheck.OUTPUT_COUNT:
                return self._output_count_section(handoff)
            case JevDoneCheck.CLAIMS:
                # Claims are only knowable from the final answer, so repeat each parent context beside one
                # atomic assertion and its tool evidence; the handoff's `missing` judgment stays out of Jev's state.
                # @intent claims-come-from-finished-answer
                # Generating these candidates before the main agent works would make them predictions, not claims.
                return self._claims_section(handoff)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                return self._problems_resolved_section(handoff)

    def _output_count_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Build deterministic candidate counts and a Jev question for each request obligation."""
        # Count observed values and distinct keys in code; Jev recognizes whether evidence and scope are adequate.
        output_state = None if self.record is None else self.record.output_count
        output_evidence = handoff.output_count
        if output_state is None or output_evidence is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.OUTPUT_COUNT)
        evidence_by_id = {item.id: item for item in output_evidence.obligations}
        entries: dict[str, object] = {}
        for obligation in output_state.obligations:
            item = evidence_by_id[obligation.id]
            observed = self._observed_count(item, obligation.distinct)
            entries[obligation.id] = {
                JEV_DONE_OUTPUT_COUNT_OBLIGATION_FIELD: {
                    JEV_DONE_OUTPUT_COUNT_DESCRIPTION_FIELD: obligation.description,
                    JEV_DONE_OUTPUT_COUNT_TARGET_FIELD: obligation.target_count,
                    JEV_DONE_OUTPUT_COUNT_DISTINCT_FIELD: obligation.distinct,
                    JEV_DONE_OUTPUT_COUNT_UNIT_FIELD: obligation.unit,
                    JEV_DONE_OUTPUT_COUNT_SCOPE_FIELD: obligation.scope,
                    JEV_DONE_OUTPUT_COUNT_DISTINCTNESS_FIELD: obligation.distinctness,
                    JEV_DONE_OUTPUT_COUNT_COMPLETION_FIELD: obligation.completion_criteria,
                },
                JEV_DONE_OUTPUT_COUNT_ENTRIES_FIELD: [{
                    JEV_DONE_OUTPUT_COUNT_ENTRY_ID_FIELD: candidate.id,
                    JEV_DONE_OUTPUT_COUNT_ENTRY_VALUE_FIELD: candidate.value,
                    JEV_DONE_OUTPUT_COUNT_ENTRY_KEY_FIELD: candidate.distinct_key,
                    JEV_DONE_OUTPUT_COUNT_ENTRY_EVIDENCE_FIELD: candidate.evidence,
                } for candidate in item.entries],
                JEV_DONE_OUTPUT_COUNT_OBSERVED_FIELD: observed,
                JEV_DONE_OUTPUT_COUNT_MET_FIELD: observed >= obligation.target_count,
            }
        return {JEV_DONE_OUTPUT_COUNTS_FIELD: entries}, tuple(question.to_question(identifier) for identifier in output_state.ids())

    def _claims_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Build one evidence-backed Jev entry and question per assertion extracted from the final answer."""
        if handoff.claims is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
        entries: dict[str, object] = {}
        for claim in handoff.claims.claims:
            for assertion in claim.claim.assertions:
                identifier = f"{claim.id}{JEV_DONE_CLAIM_ASSERTION_SEPARATOR}{assertion.id}"
                entries[identifier] = {
                    JEV_DONE_CLAIM_FIELD: {
                        JEV_DONE_CLAIM_IDENTITY_FIELD: {
                            JEV_DONE_CLAIM_TITLE_FIELD: claim.claim.identity.title,
                            JEV_DONE_CLAIM_DESCRIPTION_FIELD: claim.claim.identity.description,
                            JEV_DONE_CLAIM_INTENT_FIELD: claim.claim.identity.intent,
                        },
                        JEV_DONE_CLAIM_SCOPE_FIELD: {
                            JEV_DONE_CLAIM_SCOPE_FIELD: claim.claim.scope.scope,
                            JEV_DONE_CLAIM_QUALIFICATIONS_FIELD: list(claim.claim.scope.qualifications),
                        },
                        JEV_DONE_CLAIM_KIND_FIELD: claim.claim.kind.value,
                        JEV_DONE_CLAIM_OUTPUT_FIELD: claim.claim.output,
                        JEV_DONE_CLAIM_ASSERTION_FIELD: {
                            JEV_DONE_CLAIM_ASSERTION_ID_FIELD: assertion.id,
                            JEV_DONE_CLAIM_ASSERTION_STATEMENT_FIELD: assertion.statement,
                            JEV_DONE_CLAIM_COMPLETION_CRITERIA_FIELD: assertion.completion_criteria,
                        },
                    },
                    JEV_DONE_EVIDENCE_FIELD: claim.evidence,
                }
        return {JEV_DONE_CLAIMS_FIELD: entries}, tuple(question.to_question(identifier) for identifier in handoff.claims.assertion_ids())

    def _problems_resolved_section(self, handoff: JevHandoffRecord) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Build one question per observed problem and original-request completion item from this handoff."""
        if handoff.problems_resolved is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED)
        entries: dict[str, object] = {
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
            for item in handoff.problems_resolved.items
        }
        return {JEV_DONE_PROBLEMS_RESOLVED_FIELD: {JEV_DONE_PROBLEM_ITEMS_FIELD: entries}}, tuple(question.to_question(identifier) for identifier in handoff.problems_resolved.ids())

    def _judge(self, check: JevDoneCheck, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Scores one enabled done check from the combined request's answers; one commented case per check.
        match check:
            case JevDoneCheck.MULTI_PART:
                # Every deliverable the request asks for must be shown produced in full: Jev answered one
                # question per deliverable, and code joins them with a veto so one clear no is never averaged away.
                return self._multi_part(handoff, decision)
            case JevDoneCheck.OUTPUT_COUNT:
                # Each requested numeric obligation must meet its own target; the veto prevents another group
                # or an easy count from averaging away one incomplete quantity.
                return self._output_count(handoff, decision)
            case JevDoneCheck.CLAIMS:
                # Each extracted final-answer claim must independently reach the support threshold, so one
                # unsupported assertion sends the agent back to that claim rather than averaging it away.
                return self._claims(handoff, decision)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                # Every observed issue and the separate original-request item must pass independently.
                return self._problems_resolved(handoff, decision)

    @staticmethod
    def _observed_count(item: JevOutputCountEvidenceItem, distinct: bool) -> int:
        """Count candidate output units deterministically from handoff keys."""
        # @intent repeated-output-units-do-not-inflate-distinct-targets
        # A quantity like "25 distinct examples" is not met by repeating one example under new list numbers or
        # alternate wording. The handoff supplies semantic keys and Jev checks their fidelity against the values.
        if not distinct:
            return len(item.entries)
        keys = {" ".join(entry.distinct_key.casefold().split()) for entry in item.entries}
        return len(keys)

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

    def _output_count(self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None) -> JevDoneResult:
        # Scores one recognition answer per numeric obligation, while all arithmetic remains in this layer.
        state = None if self.record is None else self.record.output_count
        if state is None or handoff is None or handoff.output_count is None:
            return JevDoneResult(check=JevDoneCheck.OUTPUT_COUNT, score=None, available=False)
        if not state.obligations:
            return JevDoneResult(check=JevDoneCheck.OUTPUT_COUNT, score=None)
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.OUTPUT_COUNT, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.OUTPUT_COUNT)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.OUTPUT_COUNT)
        answers = {identifier: decision.answers[question.name(identifier)] for identifier in state.ids() if question.name(identifier) in decision.answers}
        verdict = DecisionModelHelper.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.OUTPUT_COUNT, score=None, available=False)
        incomplete = tuple(identifier for identifier in state.ids() if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False)
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(check=JevDoneCheck.OUTPUT_COUNT, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)

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
        output_count = None
        count_section = getattr(payload, JevDoneCheck.OUTPUT_COUNT.value, None)
        if isinstance(count_section, JevOutputCountPayload):
            output_count = JevOutputCount(tuple(JevOutputCountObligation(
                item.id, item.description.strip(), item.target_count, item.distinct, item.unit.strip(), item.scope.strip(), item.distinctness.strip(), item.completion_criteria.strip()
            ) for item in count_section.obligations))
        return JevRunStateRecord(
            goal=payload.goal.strip(),
            objective=payload.objective.strip(),
            mission=payload.mission.strip(),
            what_not_to_do=tuple(limit.strip() for limit in payload.what_not_to_do if limit.strip()),
            multi_part=multi_part,
            output_count=output_count,
            usage=self.get_usage(),
        )


__all__ = ["JevRunState"]
