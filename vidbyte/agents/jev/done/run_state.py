"""FILE: vidbyte/agents/jev/done/run_state.py

PURPOSE: Implements JevRunState, the class that owns JevAgent's done checks: it writes request-derived run state once, has JevHandoff compile final-answer evidence at every finish attempt, asks every enabled check's fixed questions in one request, and returns the checks that failed.
ROLE IN CODEBASE: JevAgent builds one JevRunState at construction when JevRuntimeSettings.continual enables a done check and passes it to JevRuntime, which calls begin() before the main loop, and JevDoneContinuation (vidbyte/agents/jev/continuation/) calls check() each time the main agent tries to finish; outcomes reach the user through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The run state combines request-derived checks with post-run claims, observed problems, and discovered collection items compiled by JevHandoff at each finish attempt. It batches all enabled check questions into one Jev request; deterministic code measures recorded discovery-output bounds, while Jev checks source inventory fidelity and completion evidence.
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
    JEV_DONE_DISCOVERED_ITEM_ACTION_FIELD,
    JEV_DONE_DISCOVERED_ITEM_CANDIDATES_FIELD,
    JEV_DONE_DISCOVERED_ITEM_CRITERIA_FIELD,
    JEV_DONE_DISCOVERED_ITEM_EVIDENCE_FIELD,
    JEV_DONE_DISCOVERED_ITEM_FIELD,
    JEV_DONE_DISCOVERED_ITEM_IDENTITY_FIELD,
    JEV_DONE_DISCOVERED_ITEM_INVENTORY_FIELD,
    JEV_DONE_DISCOVERED_ITEM_SOURCE_FIELD,
    JEV_DONE_DISCOVERED_ITEMS_FIELD,
    JEV_DONE_EVIDENCE_FIELD,
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
    JevDecisionRequest,
    JevDeliverable,
    JevDoneResult,
    JevHandoffRecord,
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
        JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomePayload,
    })

    def __init__(
        self,
        settings: JevAgentSettings,
        runtime_settings: JevRuntimeSettings,
        response: JevResponse,
    ) -> None:
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
            agent_loop_settings=AgentLoopSettings(
                max_iterations=continual.run_state_max_iterations,
                max_tokens=continual.run_state_max_tokens,
            ),
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
        sections: dict[str, Any] = {
            check.value: (
                cls._SECTIONS[check],
                Field(description=cls._SECTIONS[check].SECTION),
            )
            for check in checks
            if check in cls._SECTIONS
        }
        return create_model(
            "JevRunStatePayload", __base__=JevRunStatePayload, **sections
        )

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

    # @intent a-failed-evidence-path-never-blocks-the-agent
    # Every finish attempt resets and rebuilds its handoff, then records each enabled check's verdict.
    # Missing state or an unavailable handoff leaves the check unavailable and must not strand the main run.
    async def check(
        self,
        final_answer: str,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
    ) -> tuple[JevDoneResult, ...]:
        """Run every enabled done check on this finish attempt, record every result, and return the checks that failed."""
        self.handoff_record = None
        if self.record is None:
            return ()
        window = JevHandoff.window(
            self.rendered, responses, calls, final_answer, sender=self.sender
        )
        source_outputs = {
            f"tool_call_{index}": call.output
            for index, call in enumerate(calls)
            if isinstance(call.output, str)
        }
        self.handoff_record = await self.handoff_writer.compile(
            self.request, self.record, window, source_outputs
        )
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

    async def _ask(
        self, handoff: JevHandoffRecord | None
    ) -> DecisionModelResponse | None:
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

    def _section(
        self, check: JevDoneCheck, handoff: JevHandoffRecord
    ) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project one enabled check into the shared state and its fixed questions."""
        match check:
            case JevDoneCheck.MULTI_PART:
                return self._multi_part_section(handoff)
            case JevDoneCheck.CLAIMS:
                return self._claims_section(handoff)
            case JevDoneCheck.DISCOVERED_ITEM_COVERAGE:
                return self._discovered_item_section(handoff)
            case JevDoneCheck.TARGET_OUTCOME:
                return self._target_outcome_section(handoff)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                return self._problems_resolved_section(handoff)
        return {}, ()

    def _multi_part_section(
        self, handoff: JevHandoffRecord
    ) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project request deliverables with their attempt-specific evidence."""
        state = None if self.record is None else self.record.multi_part
        evidence = handoff.multi_part
        if state is None or evidence is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        evidence_by_id = {item.id: item.evidence for item in evidence.deliverables}
        entries: dict[str, object] = {
            deliverable.id: {
                JEV_DONE_DELIVERABLE_FIELD: deliverable.description,
                JEV_DONE_COMPLETION_SIGNAL_FIELD: deliverable.completion_signal,
                JEV_DONE_EVIDENCE_FIELD: evidence_by_id[deliverable.id],
            }
            for deliverable in state.deliverables
        }
        return {JEV_DONE_DELIVERABLES_FIELD: entries}, tuple(
            question.to_question(identifier) for identifier in state.ids()
        )

    def _claims_section(
        self, handoff: JevHandoffRecord
    ) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project final-answer assertions with their claim context and evidence."""
        claims = handoff.claims
        if claims is None:
            return {}, ()
        question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
        entries: dict[str, object] = {}
        for claim in claims.claims:
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
        return {JEV_DONE_CLAIMS_FIELD: entries}, tuple(
            question.to_question(identifier) for identifier in claims.assertion_ids()
        )

    def _discovered_item_section(
        self, handoff: JevHandoffRecord
    ) -> tuple[Mapping[str, object], tuple[JevQuestion, ...]]:
        """Project each bounded source inventory and discovered item with its own question."""
        evidence = handoff.discovered_item_coverage
        if evidence is None:
            return {}, ()
        inventory_question = JevDoneRegistry.inventory_question(JevDoneCheck.DISCOVERED_ITEM_COVERAGE)
        item_question = JevDoneRegistry.question(JevDoneCheck.DISCOVERED_ITEM_COVERAGE)
        inventories: dict[str, object] = {
            batch.source_id: {
                JEV_DONE_DISCOVERED_ITEM_SOURCE_FIELD: batch.source_output,
                JEV_DONE_DISCOVERED_ITEM_CANDIDATES_FIELD: [
                    {JEV_DONE_DISCOVERED_ITEM_IDENTITY_FIELD: item.identity}
                    for item in batch.candidates
                ],
            }
            for batch in evidence.batches
        }
        items: dict[str, object] = {
            item.id: {
                JEV_DONE_DISCOVERED_ITEM_FIELD: item.identity,
                JEV_DONE_DISCOVERED_ITEM_ACTION_FIELD: item.requested_processing,
                JEV_DONE_DISCOVERED_ITEM_CRITERIA_FIELD: item.completion_criteria,
                JEV_DONE_DISCOVERED_ITEM_EVIDENCE_FIELD: item.processing_evidence,
            }
            for item in evidence.items()
        }
        questions = tuple(
            inventory_question.to_question(batch.source_id) for batch in evidence.batches
        ) + tuple(
            item_question.to_question(identifier) for identifier in evidence.item_ids()
        )
        return {
            JEV_DONE_DISCOVERED_ITEM_INVENTORY_FIELD: inventories,
            JEV_DONE_DISCOVERED_ITEMS_FIELD: items,
        }, questions

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

    def _judge(
        self,
        check: JevDoneCheck,
        handoff: JevHandoffRecord | None,
        decision: DecisionModelResponse | None,
    ) -> JevDoneResult:
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
            case JevDoneCheck.DISCOVERED_ITEM_COVERAGE:
                # Every candidate and every source inventory must independently meet the same threshold.
                return self._discovered_item_coverage(handoff, decision)
            case JevDoneCheck.TARGET_OUTCOME:
                # Each requested target outcome must be demonstrated on its actual target; a proxy alone is insufficient.
                return self._target_outcome(handoff, decision)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                # Every observed issue and the separate original-request item must pass independently.
                return self._problems_resolved(handoff, decision)

    def _multi_part(
        self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None
    ) -> JevDoneResult:
        # Turns Jev's answers about each deliverable into the multi-part result, scored by DecisionModelHelper.
        # The deliverables the run state listed are what this check judges; without them, or without the
        # handoff's evidence for them, there is nothing to judge, so the check is unavailable and fails open.
        state = None if self.record is None else self.record.multi_part
        if state is None or handoff is None or handoff.multi_part is None:
            return JevDoneResult(
                check=JevDoneCheck.MULTI_PART, score=None, available=False
            )
        # A request that asks for no output (a greeting, a plain question) has no deliverable to miss, so it
        # passes; combine() asked Jev nothing for it, so there is no score.
        if not state.deliverables:
            return JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None)
        # Deliverables were asked about, but the one combined Jev request failed: fail open like preflight.
        if decision is None:
            return JevDoneResult(
                check=JevDoneCheck.MULTI_PART, score=None, available=False
            )
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.MULTI_PART)
        # The combined reply holds every enabled check's answers under their question names; pick out this
        # check's answers and key them by deliverable id, which is how the result and the continuation name them.
        answers = {
            identifier: decision.answers[question.name(identifier)]
            for identifier in state.ids()
            if question.name(identifier) in decision.answers
        }
        # The threshold is both the mean threshold and the veto, so every deliverable must reach it on its own
        # and one clear no is never averaged away by the others. A missing answer makes score_noul return None.
        verdict = DecisionModelHelper.score_noul(
            answers, state.ids(), threshold, threshold
        )
        if verdict is None:
            return JevDoneResult(
                check=JevDoneCheck.MULTI_PART, score=None, available=False
            )
        # The deliverables below the threshold are the ones the continuation sends the main agent back to finish.
        incomplete = tuple(
            identifier
            for identifier in state.ids()
            if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold)
            is False
        )
        # One request answered every enabled check, so its usage is the cost of this finish attempt's checks.
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(
            check=JevDoneCheck.MULTI_PART,
            score=verdict.score,
            passed=verdict.passed,
            answers=verdict.answers,
            incomplete=incomplete,
            usage=usage,
        )

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
    def _claims(
        self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None
    ) -> JevDoneResult:
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
        answers = {
            identifier: decision.answers[question.name(identifier)]
            for identifier in assertion_ids
            if question.name(identifier) in decision.answers
        }
        # The threshold is also the veto, so one unsupported assertion cannot be hidden by sibling assertions.
        verdict = DecisionModelHelper.score_noul(
            answers, assertion_ids, threshold, threshold
        )
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
                )
                is False
                for assertion in claim.claim.assertions
            )
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(
            check=JevDoneCheck.CLAIMS,
            score=verdict.score,
            passed=verdict.passed,
            answers=verdict.answers,
            incomplete=incomplete,
            usage=usage,
        )

    def _discovered_item_coverage(
        self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None
    ) -> JevDoneResult:
        """Score inventory fidelity and item processing answers, keeping each failure addressable to continuation."""
        evidence = None if handoff is None else handoff.discovered_item_coverage
        if evidence is None:
            return JevDoneResult(
                check=JevDoneCheck.DISCOVERED_ITEM_COVERAGE, score=None, available=False
            )
        identifiers = tuple(
            f"inventory:{batch.source_id}" for batch in evidence.batches
        )
        identifiers += tuple(f"item:{identifier}" for identifier in evidence.item_ids())
        if not identifiers:
            return JevDoneResult(
                check=JevDoneCheck.DISCOVERED_ITEM_COVERAGE, score=None
            )
        if decision is None:
            return JevDoneResult(
                check=JevDoneCheck.DISCOVERED_ITEM_COVERAGE, score=None, available=False
            )
        question = JevDoneRegistry.question(JevDoneCheck.DISCOVERED_ITEM_COVERAGE)
        inventory_question = JevDoneRegistry.inventory_question(
            JevDoneCheck.DISCOVERED_ITEM_COVERAGE
        )
        question_names = {
            **{
                f"inventory:{batch.source_id}": inventory_question.name(batch.source_id)
                for batch in evidence.batches
            },
            **{
                f"item:{item_id}": question.name(item_id)
                for item_id in evidence.item_ids()
            },
        }
        answers = {
            identifier: decision.answers[name]
            for identifier, name in question_names.items()
            if name in decision.answers
        }
        threshold = JevDoneRegistry.threshold(JevDoneCheck.DISCOVERED_ITEM_COVERAGE)
        verdict = DecisionModelHelper.score_noul(
            answers, identifiers, threshold, threshold
        )
        if verdict is None:
            return JevDoneResult(
                check=JevDoneCheck.DISCOVERED_ITEM_COVERAGE, score=None, available=False
            )
        incomplete = tuple(
            identifier
            for identifier in identifiers
            if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold)
            is False
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(
            check=JevDoneCheck.DISCOVERED_ITEM_COVERAGE,
            score=verdict.score,
            passed=verdict.passed,
            answers=verdict.answers,
            incomplete=incomplete,
            usage=usage,
        )

    def _target_outcome(
        self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None
    ) -> JevDoneResult:
        """Score every request-derived target outcome independently with the check's veto threshold."""
        state = None if self.record is None else self.record.target_outcome
        evidence = None if handoff is None else handoff.target_outcome
        if state is None or evidence is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        if not state.items:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None)
        if decision is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.TARGET_OUTCOME)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.TARGET_OUTCOME)
        answers = {
            identifier: decision.answers[question.name(identifier)]
            for identifier in state.ids()
            if question.name(identifier) in decision.answers
        }
        verdict = DecisionModelHelper.score_noul(answers, state.ids(), threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.TARGET_OUTCOME, score=None, available=False)
        incomplete = tuple(
            identifier for identifier in state.ids()
            if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(
            check=JevDoneCheck.TARGET_OUTCOME, score=verdict.score, passed=verdict.passed,
            answers=verdict.answers, incomplete=incomplete, usage=usage,
        )

    def _problems_resolved(
        self, handoff: JevHandoffRecord | None, decision: DecisionModelResponse | None
    ) -> JevDoneResult:
        """Score every dynamic problem item and the original-request completion item with a veto threshold."""
        # @intent every-observed-problem-and-the-original-task-are-required
        # Dynamic failures cannot be predicted before the work, so every finish attempt must score the handoff's
        # fresh item set. Requiring each answer independently prevents one repaired issue from hiding another
        # unresolved issue or the original request's unfinished work; a missing answer remains unavailable.
        evidence = None if handoff is None else handoff.problems_resolved
        if evidence is None or decision is None:
            return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=None, available=False)
        question = JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED)
        threshold = JevDoneRegistry.threshold(JevDoneCheck.PROBLEMS_RESOLVED)
        ids = evidence.ids()
        answers = {
            identifier: decision.answers[question.name(identifier)]
            for identifier in ids
            if question.name(identifier) in decision.answers
        }
        verdict = DecisionModelHelper.score_noul(answers, ids, threshold, threshold)
        if verdict is None:
            return JevDoneResult(check=JevDoneCheck.PROBLEMS_RESOLVED, score=None, available=False)
        incomplete = tuple(
            identifier for identifier in ids
            if DecisionModelHelper.noul_passes(verdict.answers, identifier, threshold) is False
        )
        usage = JevUsage.from_usage_payload(decision.usage or {})
        return JevDoneResult(
            check=JevDoneCheck.PROBLEMS_RESOLVED, score=verdict.score, passed=verdict.passed,
            answers=verdict.answers, incomplete=incomplete, usage=usage,
        )

    def _record(self, payload: JevRunStatePayload) -> JevRunStateRecord:
        # Converts the validated reply into the frozen record the response exposes and the checks read.
        multi_part = None
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if isinstance(section, JevMultiPartPayload):
            multi_part = JevMultiPart(
                tuple(
                    JevDeliverable(
                        item.id,
                        item.description.strip(),
                        item.completion_signal.strip(),
                    )
                    for item in section.deliverables
                )
            )
            multi_part = JevMultiPart(tuple(JevDeliverable(item.id, item.description.strip(), item.completion_signal.strip()) for item in section.deliverables))
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
            what_not_to_do=tuple(
                limit.strip() for limit in payload.what_not_to_do if limit.strip()
            ),
            multi_part=multi_part,
            target_outcome=target_outcome,
            usage=self.get_usage(),
        )


__all__ = ["JevRunState"]
