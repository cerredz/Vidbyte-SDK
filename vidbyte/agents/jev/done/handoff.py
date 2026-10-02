"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context window at each finish attempt, compiles request-derived evidence, and extracts final-answer claims, changed-assumption evidence, phase evidence, run-observed problem episodes, whole-task completion status, and explicit plan/account comparisons for dynamic checks.
ROLE IN CODEBASE: JevRunState builds one JevHandoff at construction and calls compile() from its check(); Jev then answers one question per item, all in one request, over the compiled evidence.
ARCHITECTURE NOTE: The handoff is general: its output schema is JevHandoffPayload plus one field per enabled check, typed as that check's evidence payload and described by its SECTION text. It reads the user's request as its message and the run state and main agent's window as standard `vidbyte.context` primitives, including every `ToolCallContextItem`; it reuses the JevAgent's generative model, has no tools, and is constrained by the composed schema. Phase progress evidence is matched to the request-derived stages; claims, changed assumptions, observed problems, completion status, and report/action alignment are derived after work.
COMMON MODIFICATION PATTERNS: Change field instructions in `vidbyte/lib/dataclasses/jev.py`; add an enabled handoff section to _SECTIONS and convert it in _record(). Compare ids to run-state items for request-derived candidates, including phase stages; dynamic post-run items follow their own validation rules.
KNOWN EDGE CASES: A generative failure, a reply that never matches the schema, or invalid handoff evidence returns None, so checks fail open. Phase evidence must contain exactly the request-derived stage ids. Claims and problem items have no pre-run id list; generated ids must be valid and unique, and problem evidence must include exactly one original-request completion item. Completion evidence has one stable `task_completion` item. History is cleared before each call, so an earlier finish attempt's handoff never leaks into a later one.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-assumption-reconciliation-done-criteria.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
from vidbyte.lib.constants.jev import (
    JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS,
    JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS,
    JEV_DONE_COMPLETION_ITEM_INDEX,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevAssumptionEvidence,
    JevAssumptionsReconciledEvidence,
    JevAssumptionsReconciledPayload,
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimScope,
    JevClaimsEvidence,
    JevClaimsEvidencePayload,
    JevCompletionEvidence,
    JevCompletionEvidenceSectionPayload,
    JevCumulativeObligationEvidence,
    JevCumulativeObligationEvidencePayload,
    JevCumulativeObligationsEvidence,
    JevCumulativeUserTurnEvidence,
    JevDeliverableEvidence,
    JevDiscoveredItem,
    JevDiscoveredItemBatch,
    JevDiscoveredItemBatchEntryPayload,
    JevDiscoveredItemBatchPayload,
    JevDiscoveredItemEvidence,
    JevExpertDepthEvidence,
    JevExpertDepthEvidencePayload,
    JevExpertDetailEvidence,
    JevFaithfulScopeEvidence,
    JevFaithfulScopeEvidencePayload,
    JevGuaranteedNextAction,
    JevGuaranteedNextActions,
    JevGuaranteedNextActionsEvidencePayload,
    JevHandoffPayload,
    JevHandoffRecord,
    JevInputExhaustionEvidence,
    JevInputExhaustionEvidenceSection,
    JevInputExhaustionEvidenceSet,
    JevInputSetCoverageEvidence,
    JevInputSetCoverageEvidencePayload,
    JevInputTargetEvidence,
    JevMotivatingCaseEvidence,
    JevMotivatingCaseEvidencePayload,
    JevMotivatingScenarioEvidence,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevNegativeCoverageEvidence,
    JevNegativeCoverageEvidenceItem,
    JevNegativeCoverageEvidencePayload,
    JevObjectionEvidence,
    JevOutputCountEntry,
    JevOutputCountEvidence,
    JevOutputCountEvidenceItem,
    JevOutputCountEvidencePayload,
    JevOutputExtentEvidence,
    JevOutputExtentEvidenceItem,
    JevOutputExtentEvidencePayload,
    JevPhaseProgressEvidence,
    JevPhaseProgressEvidencePayload,
    JevPhaseStageEvidence,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevProblemsResolvedEvidencePayload,
    JevReportActionAlignment,
    JevReportActionAlignmentEvidenceSectionPayload,
    JevReportActionAlignmentItem,
    JevRequiredActionEvidence,
    JevRequiredActionEvidencePayload,
    JevRequiredActionsEvidence,
    JevRequiredActionsEvidencePayload,
    JevReviewRecord,
    JevRunStateRecord,
    JevScopeCoverageEvidence,
    JevScopeCoverageEvidencePayload,
    JevSectionPayload,
    JevSelfReviewEvidence,
    JevSelfReviewEvidencePayload,
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
REVIEW_TITLE = "Strict review"
FINAL_ANSWER_TITLE = "Final answer"
NO_FINAL_ANSWER = "The main agent gave no final answer."
HANDOFF_SOURCE = "jev_done"


class JevHandoff(BaseAgent):
    """Generative agent that compiles, from the main agent's context window, the evidence every enabled done check needs."""

    # One evidence section per done check; the field name is the check's value, so the reply mirrors the run state.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload, JevDoneCheck.CLAIMS: JevClaimsEvidencePayload, JevDoneCheck.COMPLETION_EVIDENCE: JevCompletionEvidenceSectionPayload, JevDoneCheck.PHASE_PROGRESS: JevPhaseProgressEvidencePayload, JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomeEvidencePayload, JevDoneCheck.MOTIVATING_CASE: JevMotivatingCaseEvidencePayload, JevDoneCheck.SCOPE_COVERAGE: JevScopeCoverageEvidencePayload, JevDoneCheck.PROBLEMS_RESOLVED: JevProblemsResolvedEvidencePayload, JevDoneCheck.INPUT_SET_COVERAGE: JevInputSetCoverageEvidencePayload, JevDoneCheck.OUTPUT_COUNT: JevOutputCountEvidencePayload, JevDoneCheck.OUTPUT_EXTENT: JevOutputExtentEvidencePayload, JevDoneCheck.REPORT_ACTION_ALIGNMENT: JevReportActionAlignmentEvidenceSectionPayload, JevDoneCheck.ASSUMPTIONS_RECONCILED: JevAssumptionsReconciledPayload, JevDoneCheck.INPUT_EXHAUSTION: JevInputExhaustionEvidenceSection, JevDoneCheck.NEGATIVE_COVERAGE: JevNegativeCoverageEvidencePayload, JevDoneCheck.FAITHFUL_SCOPE: JevFaithfulScopeEvidencePayload})

    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.GUARANTEED_NEXT_ACTIONS: JevGuaranteedNextActionsEvidencePayload})
    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.REQUIRED_ACTIONS: JevRequiredActionsEvidencePayload})
    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.CUMULATIVE_OBLIGATIONS: JevCumulativeObligationEvidencePayload})
    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.DISCOVERED_ITEM_COVERAGE: JevDiscoveredItemBatchPayload})
    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.EXPERT_DEPTH: JevExpertDepthEvidencePayload})
    _SECTIONS = MappingProxyType({**_SECTIONS, JevDoneCheck.SELF_REVIEW: JevSelfReviewEvidencePayload})


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
    def window(run_state: str, responses: Sequence[str], calls: Sequence[ToolCallContext], final_answer: str, *, sender: str, user_turns: Sequence[str] = (), review: str = "") -> ContextManager:
        """Build the handoff's context: run state, any strict review, the main agent's work, and its final answer."""
        # @intent the-handoff-reads-the-main-agents-window
        # The owner asked for the main agent's context window to reach the handoff through vidbyte.context, so the
        # run is passed as the SDK's own response and tool-call primitives instead of a hand-built transcript.
        items: list[ContextItem] = [TextContextItem(title=RUN_STATE_TITLE, content=run_state, source=HANDOFF_SOURCE)]
        if review.strip():
            items.append(TextContextItem(title=REVIEW_TITLE, content=review, source=HANDOFF_SOURCE))
        if user_turns:
            turns = "\n\n".join(f"User turn {index}:\n{text}" for index, text in enumerate(user_turns))
            items.append(TextContextItem(title="Exact user turns for cumulative obligations", content=turns, source=HANDOFF_SOURCE))
        for index, text in enumerate(responses):
            if not text.strip():
                continue
            items.append(TextContextItem(title=f"Response source response[{index}]", content="The immediately following response retains this exact source index."))
            items.append(ResponseContextItem(content=text, sender=sender, metadata={"response_index": index}))
        items.extend(
            ToolCallContextItem(
                name=f"trace[{index}] {call.name} state={getattr(call.state, 'value', call.state)}",
                arguments=dict(call.arguments),
                output=call.output,
                metadata={"state": str(getattr(call.state, "value", call.state)), "trace_index": index, "source_id": f"tool_call_{index}"},
            )
            for index, call in enumerate(calls)
        )
        items.append(TextContextItem(title=FINAL_ANSWER_TITLE, content=final_answer if final_answer.strip() else NO_FINAL_ANSWER, source=HANDOFF_SOURCE))
        return ContextManager(items)

    async def compile(
        self,
        request: str,
        state: JevRunStateRecord,
        window: ContextManager,
        calls: Sequence[ToolCallContext] = (),
        responses: Sequence[str] = (),
        final_answer: str = "",
        review: JevReviewRecord | None = None,
    ) -> JevHandoffRecord | None:
        """Return evidence for every enabled check, or None when a request-derived section does not match run state."""
        self.history.clear()
        self.rendered = ""
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=window))
            if not isinstance(reply.structured, self.payload):
                return None
            record = self._record(reply.structured, state, calls, responses, final_answer, review)
            # The continuation hands this text back to the main agent when a check fails.
            self.rendered = "" if record is None else reply.structured.model_dump_json()
            return record
        except VidbyteSdkError:
            # A handoff outage, a reply that never matched the schema, or evidence that fails its record's
            # validation fails the done check open, exactly as a Jev outage does.
            return None

    def _record(
        self,
        payload: JevHandoffPayload,
        state: JevRunStateRecord,
        calls: Sequence[ToolCallContext] = (),
        responses: Sequence[str] = (),
        final_answer: str = "",
        review: JevReviewRecord | None = None,
    ) -> JevHandoffRecord | None:
        # Converts the validated reply into the frozen record, requiring one evidence entry per run-state deliverable.
        # @intent evidence-covers-exactly-the-run-state
        # Jev judges each deliverable by id, so evidence for a deliverable the state never listed, or
        # no evidence for one it did, would silently skip a check; either one makes the handoff unavailable.
        request_records = self._request_evidence_records(payload, state)
        self_review_valid, self_review = self._self_review_evidence(payload, review)
        if request_records is None or not self_review_valid:
            return None
        claims = self._claims_record(payload)
        guaranteed_next_actions = self._guaranteed_next_actions_record(payload)
        required_actions = self._required_actions_record(payload, state, calls, responses, final_answer)
        if JevDoneCheck.REQUIRED_ACTIONS in self.checks and required_actions is None:
            return None
        discovered_item_coverage = self._discovered_item_coverage_record(payload, calls)
        if JevDoneCheck.DISCOVERED_ITEM_COVERAGE in self.checks and discovered_item_coverage is None:
            return None
        report_action_alignment = self._report_action_alignment_record(payload)
        assumptions_reconciled = None
        assumptions_section = getattr(payload, JevDoneCheck.ASSUMPTIONS_RECONCILED.value, None)
        if JevDoneCheck.ASSUMPTIONS_RECONCILED in self.checks:
            if not isinstance(assumptions_section, JevAssumptionsReconciledPayload):
                return None
            # @intent changed-assumptions-are-derived-after-work
            # Keep every qualifying premise, including one whose dependent work was later corrected or made irrelevant.
            # These candidates are created after work, so validate unique ids here rather than matching a pre-run list.
            assumptions_reconciled = JevAssumptionsReconciledEvidence(tuple(
                JevAssumptionEvidence(
                    item.id,
                    item.original_assumption.strip(),
                    item.original_basis.strip(),
                    item.later_observation.strip(),
                    item.affected_work.strip(),
                    item.revision.strip(),
                    item.evidence.strip(),
                    item.missing.strip(),
                )
                for item in assumptions_section.items
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
        faithful_scope = self._faithful_scope_record(payload)
        return JevHandoffRecord(
            multi_part=request_records.multi_part,
            cumulative_obligations=request_records.cumulative_obligations,
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
            output_extent=request_records.output_extent,
            report_action_alignment=report_action_alignment,
            assumptions_reconciled=assumptions_reconciled,
            input_exhaustion=request_records.input_exhaustion,
            negative_coverage=request_records.negative_coverage,
            guaranteed_next_actions=guaranteed_next_actions,
            required_actions=required_actions,
            discovered_item_coverage=discovered_item_coverage,
            faithful_scope=faithful_scope,
            expert_depth=request_records.expert_depth,
            self_review=self_review,
        )

    @staticmethod
    def _faithful_scope_record(payload: JevHandoffPayload) -> JevFaithfulScopeEvidence | None:
        """Convert the one post-run evidence section without adding a duplicate run-state section."""
        section = getattr(payload, JevDoneCheck.FAITHFUL_SCOPE.value, None)
        if not isinstance(section, JevFaithfulScopeEvidencePayload):
            return None
        return JevFaithfulScopeEvidence(section.evidence.strip(), section.missing.strip())

    @staticmethod
    def _report_action_alignment_record(payload: JevHandoffPayload) -> JevReportActionAlignment | None:
        """Convert only the dynamically observed plan, execution, and final-account comparisons."""
        alignment_section = getattr(payload, JevDoneCheck.REPORT_ACTION_ALIGNMENT.value, None)
        if not isinstance(alignment_section, JevReportActionAlignmentEvidenceSectionPayload):
            return None
        # @intent report-action-candidates-are-post-run
        # These candidates are created from post-run plans, execution, and the final account, so no request-state id list exists.
        return JevReportActionAlignment(tuple(
            JevReportActionAlignmentItem(
                item.id,
                item.plan.strip(),
                item.execution.strip(),
                item.final_account.strip(),
                item.request_relevance.strip(),
                item.evidence.strip(),
                item.missing.strip(),
            )
            for item in alignment_section.items
        ))

    def _discovered_item_coverage_record(
        self, payload: JevHandoffPayload, calls: Sequence[ToolCallContext]
    ) -> JevDiscoveredItemEvidence | None:
        """Match the handoff inventory against every string output from the current tool-call sequence."""
        if JevDoneCheck.DISCOVERED_ITEM_COVERAGE not in self.checks:
            return None
        source_outputs = {
            f"tool_call_{index}": call.output
            for index, call in enumerate(calls)
            if isinstance(call.output, str)
        }
        return self._discovered_items(
            getattr(payload, JevDoneCheck.DISCOVERED_ITEM_COVERAGE.value, None),
            source_outputs,
        )

    @staticmethod
    def _claims_record(payload: JevHandoffPayload) -> JevClaimsEvidence | None:
        """Convert post-run claims while keeping their nested assertions and source context intact."""
        section = getattr(payload, JevDoneCheck.CLAIMS.value, None)
        if not isinstance(section, JevClaimsEvidencePayload):
            return None
        # Claim ids come from the final answer, so validate uniqueness without matching them to a pre-run list.
        # @intent claims-are-derived-after-the-work
        return JevClaimsEvidence(tuple(
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
                        JevClaimAssertion(assertion.id, assertion.statement.strip(), assertion.completion_criteria.strip())
                        for assertion in item.claim.assertions
                    ),
                ),
                item.evidence.strip(),
                item.missing.strip(),
            )
            for item in section.claims
        ))

    def _required_actions_record(
        self,
        payload: JevHandoffPayload,
        state: JevRunStateRecord,
        calls: Sequence[ToolCallContext],
        responses: Sequence[str],
        final_answer: str,
    ) -> JevRequiredActionsEvidence | None:
        """Convert evidence only when its ids, trace indices, and quoted output match the run."""
        section = getattr(payload, JevDoneCheck.REQUIRED_ACTIONS.value, None)
        if not isinstance(section, JevRequiredActionsEvidencePayload):
            return None
        items = tuple(
            self._required_action_evidence(item, responses, final_answer)
            for item in section.actions
        )
        evidence = JevRequiredActionsEvidence(items)
        expected = () if state.required_actions is None else state.required_actions.ids()
        if evidence.ids() != expected:
            return None
        if any(not self._valid_required_action_trace(item, calls) for item in evidence.actions):
            return None
        return evidence

    @classmethod
    def _required_action_evidence(
        cls,
        item: JevRequiredActionEvidencePayload,
        responses: Sequence[str],
        final_answer: str,
    ) -> JevRequiredActionEvidence:
        """Keep only output excerpts that occur in the exact raw source named by the handoff."""
        output_is_cited = cls._valid_output_excerpt(item.output_source, item.output_excerpt, responses, final_answer)
        return JevRequiredActionEvidence(
            item.id,
            item.evidence.strip(),
            tuple(item.trace_indices),
            item.completion_trace_index,
            item.missing.strip(),
            item.output_source if output_is_cited else None,
            item.output_excerpt.strip() if output_is_cited and item.output_excerpt is not None else None,
        )

    @staticmethod
    def _valid_required_action_trace(item: JevRequiredActionEvidence, calls: Sequence[ToolCallContext]) -> bool:
        """Reject nonexistent trace indices and completion citations that point to unsuccessful calls."""
        if any(index >= len(calls) for index in item.trace_indices):
            return False
        if item.completion_trace_index is None:
            return True
        call = calls[item.completion_trace_index]
        return str(getattr(call.state, "value", call.state)) == "succeeded"

    @staticmethod
    def _valid_output_excerpt(
        source: str | None,
        excerpt: str | None,
        responses: Sequence[str],
        final_answer: str,
    ) -> bool:
        """Check an excerpt against the unmodified response or final-answer text it cites."""
        if source is None or excerpt is None or not excerpt.strip():
            return False
        if source == "final_answer":
            text = final_answer
        elif source.startswith("response[") and source.endswith("]"):
            try:
                index = int(source[9:-1])
                text = responses[index]
            except (ValueError, IndexError):
                return False
        else:
            return False
        return excerpt.strip() in text

    def _guaranteed_next_actions_record(self, payload: JevHandoffPayload) -> JevGuaranteedNextActions | None:
        """Convert dynamic candidates without copying their private necessity rationale into Jev evidence."""
        actions_section = getattr(payload, JevDoneCheck.GUARANTEED_NEXT_ACTIONS.value, None)
        if not isinstance(actions_section, JevGuaranteedNextActionsEvidencePayload):
            return None
        # @intent generated-necessity-basis-is-not-run-evidence
        # The record contains candidate context and direct run evidence only; Jev must decide necessity for itself.
        return JevGuaranteedNextActions(tuple(
            JevGuaranteedNextAction(
                item.id,
                item.outcome.strip(),
                item.trigger.strip(),
                item.action.strip(),
                item.evidence.strip(),
                item.missing.strip(),
            )
            for item in actions_section.actions
        ))

    # @intent request-derived-evidence-covers-exactly-the-state
    # Each pre-run item gets exactly one handoff entry; an omission or invented id makes all evidence unavailable.
    def _request_evidence_records(self, payload: JevHandoffPayload, state: JevRunStateRecord) -> JevHandoffRecord | None:
        multi_part_valid, multi_part = self._multi_part_evidence_record(payload, state)
        if not multi_part_valid:
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
        expert_depth_valid, expert_depth = self._expert_depth_evidence_record(payload, state)
        if not expert_depth_valid:
            return None
        cumulative_obligations = self._cumulative_obligations_evidence(payload, state)
        additional_records = self._request_derived_evidence_records(payload, state)
        if additional_records is None:
            return None
        return JevHandoffRecord(
            multi_part=multi_part,
            phase_progress=phase_progress,
            target_outcome=target_outcome,
            motivating_case=motivating_case,
            cumulative_obligations=cumulative_obligations,
            input_exhaustion=additional_records.input_exhaustion,
            input_set_coverage=additional_records.input_set_coverage,
            output_count=additional_records.output_count,
            output_extent=additional_records.output_extent,
            negative_coverage=additional_records.negative_coverage,
            expert_depth=expert_depth,
        )

    @staticmethod
    def _self_review_evidence(
        payload: JevHandoffPayload, review: JevReviewRecord | None
    ) -> tuple[bool, JevSelfReviewEvidence | None]:
        """Match handoff evidence to the reviewer's exact objection ids, or drop the section when no review exists."""
        section = getattr(payload, JevDoneCheck.SELF_REVIEW.value, None)
        if review is None:
            return True, None
        if not isinstance(section, JevSelfReviewEvidencePayload):
            return False, None
        evidence = JevSelfReviewEvidence(tuple(
            JevObjectionEvidence(item.id, item.evidence.strip(), item.missing.strip())
            for item in section.objections
        ))
        return sorted(evidence.ids()) == sorted(review.ids()), evidence

    @staticmethod
    def _multi_part_evidence_record(
        payload: JevHandoffPayload, state: JevRunStateRecord
    ) -> tuple[bool, JevMultiPartEvidence | None]:
        """Match multi-part evidence to every request-derived deliverable id."""
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if not isinstance(section, JevMultiPartEvidencePayload):
            return True, None
        evidence = JevMultiPartEvidence(tuple(
            JevDeliverableEvidence(item.id, item.evidence.strip(), item.missing.strip())
            for item in section.deliverables
        ))
        expected = () if state.multi_part is None else state.multi_part.ids()
        valid = sorted(evidence.ids()) == sorted(expected)
        return valid, evidence if valid else None

    @staticmethod
    def _expert_depth_evidence_record(
        payload: JevHandoffPayload, state: JevRunStateRecord
    ) -> tuple[bool, JevExpertDepthEvidence | None]:
        """Match the per-detail evidence to exactly the request-derived detail ids."""
        section = getattr(payload, JevDoneCheck.EXPERT_DEPTH.value, None)
        if not isinstance(section, JevExpertDepthEvidencePayload):
            return True, None
        evidence = JevExpertDepthEvidence(tuple(
            JevExpertDetailEvidence(item.id, item.evidence.strip(), item.missing.strip())
            for item in section.details
        ))
        expected = () if state.expert_depth is None else state.expert_depth.ids()
        if sorted(evidence.ids()) != sorted(expected):
            return False, None
        return True, evidence

    @staticmethod
    def _cumulative_obligations_evidence(payload: JevHandoffPayload, state: JevRunStateRecord) -> JevCumulativeObligationsEvidence | None:
        """Keep generated obligation and turn evidence aligned to each supplied source index."""
        section = getattr(payload, JevDoneCheck.CUMULATIVE_OBLIGATIONS.value, None)
        if not isinstance(section, JevCumulativeObligationEvidencePayload):
            return None
        evidence = JevCumulativeObligationsEvidence(
            tuple(JevCumulativeObligationEvidence(item.id, item.evidence.strip(), item.missing.strip()) for item in section.obligations),
            tuple(JevCumulativeUserTurnEvidence(item.id, item.evidence.strip()) for item in section.turns),
        )
        request_state = state.cumulative_obligations
        expected_obligations = () if request_state is None else request_state.ids()
        expected_turns = () if request_state is None else tuple(f"turn_{index}" for index in range(len(request_state.user_turns)))
        if evidence.ids() != expected_obligations or evidence.turn_ids() != expected_turns:
            return None
        return evidence

    # @intent request-derived-evidence-covers-exactly-the-state
    # New request-derived input and output obligations must remain complete when copied into the handoff.
    def _request_derived_evidence_records(
        self,
        payload: JevHandoffPayload,
        state: JevRunStateRecord,
    ) -> JevHandoffRecord | None:
        input_exhaustion = None
        exhaustion_section = getattr(payload, JevDoneCheck.INPUT_EXHAUSTION.value, None)
        if isinstance(exhaustion_section, JevInputExhaustionEvidenceSection):
            input_exhaustion = JevInputExhaustionEvidenceSet(tuple(
                JevInputExhaustionEvidence(
                    item.id,
                    item.evidence.strip(),
                    None if item.unit_type is None else item.unit_type.strip(),
                    tuple(value.strip() for value in item.visited_unit_ids),
                    item.source_reported_total,
                    None if item.last_position is None else item.last_position.strip(),
                    None if item.outstanding_continuation is None else item.outstanding_continuation.strip(),
                    None if item.terminal_evidence is None else item.terminal_evidence.strip(),
                    tuple(value.strip() for value in item.failed_retrievals),
                    item.missing.strip(),
                    item.next_step.strip(),
                )
                for item in exhaustion_section.collections
            ))
            expected = () if state.input_exhaustion is None else state.input_exhaustion.ids()
            if sorted(input_exhaustion.ids()) != sorted(expected):
                return None
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
        output_extent = None
        extent_section = getattr(payload, JevDoneCheck.OUTPUT_EXTENT.value, None)
        if isinstance(extent_section, JevOutputExtentEvidencePayload):
            output_extent = JevOutputExtentEvidence(tuple(
                JevOutputExtentEvidenceItem(item.id, item.evidence.strip(), item.missing.strip())
                for item in extent_section.items
            ))
            expected = () if state.output_extent is None else state.output_extent.ids()
            if output_extent.ids() != expected:
                return None
        negative_valid, negative_coverage = self._negative_coverage_evidence_record(payload, state)
        if not negative_valid:
            return None
        return JevHandoffRecord(
            input_exhaustion=input_exhaustion,
            input_set_coverage=input_set_coverage,
            output_count=output_count,
            output_extent=output_extent,
            negative_coverage=negative_coverage,
        )

    @staticmethod
    def _negative_coverage_evidence_record(
        payload: JevHandoffPayload,
        state: JevRunStateRecord,
    ) -> tuple[bool, JevNegativeCoverageEvidence | None]:
        section = getattr(payload, JevDoneCheck.NEGATIVE_COVERAGE.value, None)
        if not isinstance(section, JevNegativeCoverageEvidencePayload):
            return state.negative_coverage is None, None
        evidence = JevNegativeCoverageEvidence(tuple(
            JevNegativeCoverageEvidenceItem(
                item.id,
                item.inspection.strip(),
                item.negative_conclusion.strip(),
                item.incomplete_report.strip(),
                item.missing.strip(),
            )
            for item in section.inspections
        ))
        expected = () if state.negative_coverage is None else state.negative_coverage.ids()
        return evidence.ids() == expected, evidence

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

    @staticmethod
    def _discovered_items(
        section: object, source_outputs: Mapping[str, str]
    ) -> JevDiscoveredItemEvidence | None:
        """Build item evidence only when each bounded raw tool output has one exact handoff batch."""
        if not isinstance(section, JevDiscoveredItemBatchPayload):
            return None
        if any(not isinstance(output, str) for output in source_outputs.values()):
            return None
        if sum(len(output) for output in source_outputs.values()) > JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS:
            return None
        if any(len(output) > JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS for output in source_outputs.values()):
            return None
        entries = {entry.source_id: entry for entry in section.batches}
        if len(entries) != len(section.batches) or set(entries) != set(source_outputs):
            return None
        batches = []
        for source_id, source_output in source_outputs.items():
            entry: JevDiscoveredItemBatchEntryPayload = entries[source_id]
            candidates = tuple(
                JevDiscoveredItem(
                    item.id,
                    item.identity.strip(),
                    item.requested_processing.strip(),
                    item.completion_criteria.strip(),
                    item.processing_evidence.strip(),
                    item.missing.strip(),
                )
                for item in entry.candidates
            )
            batches.append(JevDiscoveredItemBatch(source_id, source_output, candidates))
        try:
            return JevDiscoveredItemEvidence(tuple(batches))
        except VidbyteSdkError:
            return None



__all__ = ["JevHandoff"]
