"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context window at each finish attempt, compiles request-derived evidence, and extracts final-answer claims, phase evidence, run-observed problem episodes, and whole-task completion status for dynamic checks.
ROLE IN CODEBASE: JevRunState builds one JevHandoff at construction and calls compile() from its check(); Jev then answers one question per item, all in one request, over the compiled evidence.
ARCHITECTURE NOTE: The handoff is general: its output schema is JevHandoffPayload plus one field per enabled check, typed as that check's evidence payload and described by its SECTION text. It reads the user's request as its message and the run state and main agent's window as standard `vidbyte.context` primitives, including every `ToolCallContextItem`; it reuses the JevAgent's generative model, has no tools, and is constrained by the composed schema. Phase progress evidence is matched to the request-derived stages; claims, observed problems, and completion status are derived after work.
COMMON MODIFICATION PATTERNS: Change field instructions in `vidbyte/lib/dataclasses/jev.py`; add an enabled handoff section to _SECTIONS and convert it in _record(). Compare ids to run-state items for request-derived candidates, including phase stages; dynamic post-run items follow their own validation rules.
KNOWN EDGE CASES: A generative failure, a reply that never matches the schema, or invalid handoff evidence returns None, so checks fail open. Phase evidence must contain exactly the request-derived stage ids. Claims and problem items have no pre-run id list; generated ids must be valid and unique, and problem evidence must include exactly one original-request completion item. Completion evidence has one stable `task_completion` item. History is cleared before each call, so an earlier finish attempt's handoff never leaks into a later one.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import Field, create_model

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings, JevContinualSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context import ContextManager
from vidbyte.context.primitives import (
    ContextItem,
    ResponseContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.lib.constants.jev import JEV_DONE_COMPLETION_ITEM_INDEX
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimScope,
    JevClaimsEvidence,
    JevClaimsEvidencePayload,
    JevCompletionEvidence,
    JevCompletionEvidenceSectionPayload,
    JevDeliverableEvidence,
    JevHandoffPayload,
    JevHandoffRecord,
    JevInputSetCoverageEvidence,
    JevInputSetCoverageEvidencePayload,
    JevInputTargetEvidence,
    JevMotivatingCaseEvidence,
    JevMotivatingCaseEvidencePayload,
    JevMotivatingScenarioEvidence,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevOutputCountEntry,
    JevOutputCountEvidence,
    JevOutputCountEvidenceItem,
    JevOutputCountEvidencePayload,
    JevPhaseProgressEvidence,
    JevPhaseProgressEvidencePayload,
    JevPhaseStageEvidence,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevProblemsResolvedEvidencePayload,
    JevRunStateRecord,
    JevScopeCoverageEvidence,
    JevScopeCoverageEvidencePayload,
    JevSectionPayload,
    JevTargetOutcomeEvidence,
    JevTargetOutcomeEvidenceItem,
    JevTargetOutcomeEvidencePayload,
)
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext

# The titles and source of the context items that frame the main agent's window, named in the system prompt.
RUN_STATE_TITLE = "Run state"
FINAL_ANSWER_TITLE = "Final answer"
NO_FINAL_ANSWER = "The main agent gave no final answer."
HANDOFF_SOURCE = "jev_done"


class JevHandoff(BaseAgent):
    """Generative agent that compiles, from the main agent's context window, the evidence every enabled done check needs."""

    # One evidence section per done check; the field name is the check's value, so the reply mirrors the run state.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload, JevDoneCheck.CLAIMS: JevClaimsEvidencePayload, JevDoneCheck.COMPLETION_EVIDENCE: JevCompletionEvidenceSectionPayload, JevDoneCheck.PHASE_PROGRESS: JevPhaseProgressEvidencePayload, JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomeEvidencePayload, JevDoneCheck.MOTIVATING_CASE: JevMotivatingCaseEvidencePayload, JevDoneCheck.SCOPE_COVERAGE: JevScopeCoverageEvidencePayload, JevDoneCheck.PROBLEMS_RESOLVED: JevProblemsResolvedEvidencePayload, JevDoneCheck.INPUT_SET_COVERAGE: JevInputSetCoverageEvidencePayload, JevDoneCheck.OUTPUT_COUNT: JevOutputCountEvidencePayload})


    def __init__(self, settings: JevAgentSettings, continual: JevContinualSettings) -> None:
        # Reuses the JevAgent's generative model and key and takes its limits from the continuation settings; the prompt, schema, and empty tool list are fixed here.
        # @intent handoff-can-only-report
        # The handoff writer compiles evidence for a checker; with no tools and a fixed prompt it can neither
        # continue the user's work nor be steered by the caller into judging it.
        payload = self.schema(continual.checks)
        super().__init__(
            name=f"{settings.name}-handoff",
            system_prompt=Prompts().get(Prompt.JEV_HANDOFF_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=continual.handoff_max_iterations, max_tokens=continual.handoff_max_tokens),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=payload,
        )
        self.checks = continual.checks
        self.payload = payload
        self.rendered = ""

    @classmethod
    def schema(cls, checks: tuple[JevDoneCheck, ...]) -> type[JevHandoffPayload]:
        """Return the handoff's output schema: JevHandoffPayload plus one described evidence section per enabled check."""
        sections: dict[str, Any] = {check.value: (cls._SECTIONS[check], Field(description=cls._SECTIONS[check].SECTION)) for check in checks}
        return create_model("JevHandoffPayload", __base__=JevHandoffPayload, **sections)

    @staticmethod
    def window(run_state: str, responses: Sequence[str], calls: Sequence[ToolCallContext], final_answer: str, *, sender: str) -> ContextManager:
        """Build the handoff's context: the run state, then the main agent's responses and tool calls, then its final answer."""
        # @intent the-handoff-reads-the-main-agents-window
        # The owner asked for the main agent's context window to reach the handoff through vidbyte.context, so the
        # run is passed as the SDK's own response and tool-call primitives instead of a hand-built transcript.
        items: list[ContextItem] = [TextContextItem(title=RUN_STATE_TITLE, content=run_state, source=HANDOFF_SOURCE)]
        items.extend(ResponseContextItem(content=text, sender=sender) for text in responses if text.strip())
        items.extend(ToolCallContextItem(name=call.name, arguments=dict(call.arguments), output=call.output, metadata={"state": str(getattr(call.state, "value", call.state))}) for call in calls)
        items.append(TextContextItem(title=FINAL_ANSWER_TITLE, content=final_answer if final_answer.strip() else NO_FINAL_ANSWER, source=HANDOFF_SOURCE))
        return ContextManager(items)

    async def compile(self, request: str, state: JevRunStateRecord, window: ContextManager) -> JevHandoffRecord | None:
        """Return evidence for every enabled check, or None when a request-derived section does not match run state."""
        self.history.clear()
        self.rendered = ""
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=window))
            if not isinstance(reply.structured, self.payload):
                return None
            record = self._record(reply.structured, state)
            # The continuation hands this text back to the main agent when a check fails.
            self.rendered = "" if record is None else reply.structured.model_dump_json()
            return record
        except VidbyteSdkError:
            # A handoff outage, a reply that never matched the schema, or evidence that fails its record's
            # validation fails the done check open, exactly as a Jev outage does.
            return None

    def _record(self, payload: JevHandoffPayload, state: JevRunStateRecord) -> JevHandoffRecord | None:
        # Converts the validated reply into the frozen record, requiring one evidence entry per run-state deliverable.
        # @intent evidence-covers-exactly-the-run-state
        # Jev judges each deliverable by id, so evidence for a deliverable the state never listed, or
        # no evidence for one it did, would silently skip a check; either one makes the handoff unavailable.
        request_records = self._request_evidence_records(payload, state)
        if request_records is None:
            return None
        claims = None
        claims_section = getattr(payload, JevDoneCheck.CLAIMS.value, None)
        if isinstance(claims_section, JevClaimsEvidencePayload):
            # The claim ids are created from this final answer, so validate uniqueness here instead of matching
            # them to a pre-run list that cannot contain statements the main agent has not made yet.
            # @intent claims-are-derived-after-the-work
            claims = JevClaimsEvidence(tuple(
                JevClaimEvidence(
                    item.id,
                    JevClaimContext(
                        identity=JevClaimIdentity(
                            title=item.claim.identity.title.strip(),
                            description=item.claim.identity.description.strip(),
                            intent=None if item.claim.identity.intent is None else item.claim.identity.intent.strip(),
                        ),
                        scope=JevClaimScope(
                            scope=item.claim.scope.scope.strip(),
                            qualifications=tuple(value.strip() for value in item.claim.scope.qualifications),
                        ),
                        kind=item.claim.kind,
                        output=None if item.claim.output is None else item.claim.output.strip(),
                        assertions=tuple(
                            JevClaimAssertion(
                                assertion.id,
                                assertion.statement.strip(),
                                assertion.completion_criteria.strip(),
                            )
                            for assertion in item.claim.assertions
                        ),
                    ),
                    item.evidence.strip(),
                    item.missing.strip(),
                )
                for item in claims_section.claims
            ))
        completion_evidence = None
        completion_section = getattr(payload, JevDoneCheck.COMPLETION_EVIDENCE.value, None)
        if isinstance(completion_section, JevCompletionEvidenceSectionPayload):
            item = completion_section.items[JEV_DONE_COMPLETION_ITEM_INDEX]
            completion_evidence = JevCompletionEvidence(
                id=item.id,
                completion_status=item.completion_status,
                requested_outcomes=tuple(value.strip() for value in item.requested_outcomes if value.strip()),
                completed_work=tuple(value.strip() for value in item.completed_work if value.strip()),
                unfinished_or_blocked=tuple(value.strip() for value in item.unfinished_or_blocked if value.strip()),
                evidence=item.evidence.strip(),
                missing=item.missing.strip(),
            )
        problems_resolved = None
        problem_section = getattr(payload, JevDoneCheck.PROBLEMS_RESOLVED.value, None)
        if isinstance(problem_section, JevProblemsResolvedEvidencePayload):
            problems_resolved = JevProblemsResolvedEvidence(tuple(
                JevProblemResolutionItem(
                    item.id,
                    item.kind,
                    item.title.strip(),
                    item.description.strip(),
                    item.scope.strip(),
                    item.qualifications.strip(),
                    item.repair.strip(),
                    item.verification.strip(),
                    item.evidence.strip(),
                    item.missing.strip(),
                )
                for item in problem_section.items
            ))
        scope_coverage = None
        scope_section = getattr(payload, JevDoneCheck.SCOPE_COVERAGE.value, None)
        if isinstance(scope_section, JevScopeCoverageEvidencePayload):
            if state.scope_coverage is None:
                return None
            scope_coverage = JevScopeCoverageEvidence.from_payload(scope_section, state.scope_coverage)
        return JevHandoffRecord(
            multi_part=request_records.multi_part,
            claims=claims,
            completion_evidence=completion_evidence,
            phase_progress=request_records.phase_progress,
            target_outcome=request_records.target_outcome,
            problems_resolved=problems_resolved,
            scope_coverage=scope_coverage,
            usage=self.get_usage(),
            motivating_case=request_records.motivating_case,
            input_set_coverage=request_records.input_set_coverage,
            output_count=request_records.output_count,
        )

    # @intent request-derived-evidence-covers-exactly-the-state
    # Each pre-run item gets exactly one handoff entry; an omission or invented id makes all evidence unavailable.
    def _request_evidence_records(self, payload: JevHandoffPayload, state: JevRunStateRecord) -> JevHandoffRecord | None:
        multi_part = None
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if isinstance(section, JevMultiPartEvidencePayload):
            multi_part = JevMultiPartEvidence(tuple(JevDeliverableEvidence(item.id, item.evidence.strip(), item.missing.strip()) for item in section.deliverables))
            expected = () if state.multi_part is None else state.multi_part.ids()
            if sorted(multi_part.ids()) != sorted(expected):
                return None
        phase_progress = None
        phase_section = getattr(payload, JevDoneCheck.PHASE_PROGRESS.value, None)
        if isinstance(phase_section, JevPhaseProgressEvidencePayload):
            phase_progress = self._phase_progress_record(phase_section, state)
            if phase_progress is None:
                return None
        target_outcome = None
        outcome_section = getattr(payload, JevDoneCheck.TARGET_OUTCOME.value, None)
        if isinstance(outcome_section, JevTargetOutcomeEvidencePayload):
            target_outcome = JevTargetOutcomeEvidence(tuple(
                JevTargetOutcomeEvidenceItem(item.id, item.observed_proxy.strip(), item.direct_evidence.strip(), item.missing.strip())
                for item in outcome_section.items
            ))
            expected = () if state.target_outcome is None else state.target_outcome.ids()
            if sorted(target_outcome.ids()) != sorted(expected):
                return None
        motivating_case = None
        motivating_section = getattr(payload, JevDoneCheck.MOTIVATING_CASE.value, None)
        if isinstance(motivating_section, JevMotivatingCaseEvidencePayload):
            motivating_case = JevMotivatingCaseEvidence(tuple(
                JevMotivatingScenarioEvidence(item.id, item.evidence.strip(), item.missing.strip())
                for item in motivating_section.scenarios
            ))
            expected = () if state.motivating_case is None else state.motivating_case.ids()
            if motivating_case.ids() != expected:
                return None
        additional_records = self._input_output_evidence_records(payload, state)
        if additional_records is None:
            return None
        return JevHandoffRecord(
            multi_part=multi_part,
            phase_progress=phase_progress,
            target_outcome=target_outcome,
            motivating_case=motivating_case,
            input_set_coverage=additional_records.input_set_coverage,
            output_count=additional_records.output_count,
        )

    # @intent request-derived-evidence-covers-exactly-the-state
    # New request-derived input and output obligations must remain complete when copied into the handoff.
    def _input_output_evidence_records(
        self,
        payload: JevHandoffPayload,
        state: JevRunStateRecord,
    ) -> JevHandoffRecord | None:
        input_set_coverage = None
        input_section = getattr(payload, JevDoneCheck.INPUT_SET_COVERAGE.value, None)
        if isinstance(input_section, JevInputSetCoverageEvidencePayload):
            input_set_coverage = JevInputSetCoverageEvidence(tuple(
                JevInputTargetEvidence(item.id, item.evidence.strip(), item.missing.strip())
                for item in input_section.targets
            ))
            expected = () if state.input_set_coverage is None else state.input_set_coverage.ids()
            # @intent no-requested-input-can-disappear-from-the-check
            # A handoff omission would remove its question, so accept only the exact request-derived ids in order.
            if input_set_coverage.ids() != expected:
                return None
        output_count = None
        count_section = getattr(payload, JevDoneCheck.OUTPUT_COUNT.value, None)
        if isinstance(count_section, JevOutputCountEvidencePayload):
            output_count = JevOutputCountEvidence(tuple(
                JevOutputCountEvidenceItem(
                    item.id,
                    tuple(JevOutputCountEntry(entry.id, entry.value.strip(), entry.distinct_key.strip(), entry.evidence.strip()) for entry in item.entries),
                    item.missing.strip(),
                )
                for item in count_section.obligations
            ))
            expected = () if state.output_count is None else state.output_count.ids()
            # @intent every-requested-output-count-remains-in-the-check
            # Missing or invented obligation evidence would change the count question set, so fail open on either.
            if sorted(output_count.ids()) != sorted(expected):
                return None
        return JevHandoffRecord(
            input_set_coverage=input_set_coverage,
            output_count=output_count,
        )

    # @intent phase-evidence-matches-request-stages
    # Jev must judge every request-derived stage exactly once; a handoff omission or invented id fails open as a whole.
    def _phase_progress_record(self, section: JevPhaseProgressEvidencePayload, state: JevRunStateRecord) -> JevPhaseProgressEvidence | None:
        evidence = JevPhaseProgressEvidence(tuple(
            JevPhaseStageEvidence(item.id, item.evidence.strip(), item.missing.strip())
            for item in section.stages
        ))
        expected = () if state.phase_progress is None else state.phase_progress.ids()
        if sorted(evidence.ids()) != sorted(expected):
            return None
        return evidence



__all__ = ["JevHandoff"]
