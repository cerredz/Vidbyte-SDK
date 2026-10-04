"""FILE: vidbyte/agents/jev/continuation/done.py

PURPOSE: Implements JevDoneContinuation, the continuation for JevAgent's done checks: at every finish attempt it has JevRunState run enabled checks, and on failure it sends the original request, run state, handoff, failed Jev questions, and focused missing work back to the main agent.
ROLE IN CODEBASE: JevAgent builds one JevDoneContinuation over its JevRunState when JevRuntimeSettings.continual enables a done check, and JevRuntime calls should_continue() and continue_() from its finish-attempt hook; each continuation is recorded through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The message is the vidbyte/prompts asset jev_continuation/continue_prompt.md, filled with the run's own text; it opens with general Goal and Instructions sections, and under Failed checks each failed check renders its JevDoneRegistry.description() (shared with the fresh continuation) followed by what its own helper in _explain() found. Phase progress feedback names only request-required stages Jev did not see entered; whole-task completion feedback compares final status with requested outcomes and run evidence; report/action alignment feedback names only plan/account mismatches Jev did not recognize as aligned; changed-assumption feedback names only failed premises and their dependent work. The cap on continuations is JevContinuationGateSettings.max_continuations.
COMMON MODIFICATION PATTERNS: Add a done check's failed questions and focus to _explain(); change the message's instructions in vidbyte/prompts/prompts/jev_continuation/continue_prompt.md.
KNOWN EDGE CASES: A failed check whose handoff is missing never continues, because there is no evidence to hand back. After max_continuations continuations the latest verdict stays on JevAgent.response, but the main agent's answer stands.
RELATED DOCS: docs/design/jev-can-simplify-done-criteria.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-assumption-reconciliation-done-criteria.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinuationGateSettings
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives.documents import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.jev import (
    JEV_CONTINUATION_GATE_CONTEXT_ID,
    JEV_DONE_CLAIM_ASSERTION_SEPARATOR,
    JEV_DONE_COMPLETION_ITEM_ID,
    JEV_DONE_HARD_PART_FIELD,
    JEV_DONE_IMPLEMENTATION_FIELD,
    JEV_EXPERT_DEPTH_FOCUS_LIMIT,
    JEV_HANDOFF_CONTEXT_ID,
    JEV_NOUL_TRUE,
)
from vidbyte.lib.dataclasses.jev import (
    JevClaimAssertion,
    JevClaimEvidence,
    JevCompletionEvidence,
    JevContinuationGateResult,
    JevDoneQuestion,
    JevProblemResolutionItem,
    JevRequiredAction,
    JevRequiredActionEvidence,
)
from vidbyte.lib.enums.jev import (
    JevContinuationGate,
    JevDoneQuestionKey,
    JevProblemCheckItemType,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext


def _event_position(event_id: str) -> int:
    if not event_id.startswith("E") or not event_id[1:].isdigit():
        return 0
    return int(event_id[1:])


class JevDoneContinuation(JevContinuation):
    """Continuation that sends the main agent back to finish what a failed done check found missing."""

    def __init__(self, run_state: JevRunState, continual: JevContinuationGateSettings, response: JevResponse) -> None:
        # Fixes the done checks' run state, the continuation cap, and the response writer when JevAgent is built.
        self.run_state = run_state
        self.max_continuations = continual.max_continuations
        self.settings = continual
        self.response = response
        self.failed: tuple[JevContinuationGateResult, ...] = ()

    def budget_extension(self) -> tuple[int, int, int]:
        """Grant the configured bounded extension only when faithful-scope evidence failed."""
        if not any(result.check is JevContinuationGate.FAITHFUL_SCOPE for result in self.failed):
            return 0, 0, 0
        return (
            self.settings.faithful_scope_extra_iterations,
            self.settings.faithful_scope_extra_tokens,
            self.settings.faithful_scope_extra_tool_calls,
        )

    async def should_continue(
        self,
        final_answer: str,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
        context_manager: ContextManager,
    ) -> bool:
        """Run every enabled done check and return True when one failed and continuations remain."""
        self.failed = await self.run_state.check(final_answer, responses, calls)
        self._update_context(context_manager)
        # @intent continuations-are-bounded
        # A check that keeps failing must not trap the run: after the cap the latest verdict stays on the
        # response for the caller to read, but the main agent's answer stands.
        return bool(self.failed) and self.run_state.handoff is not None and self.response.state.continuations < self.max_continuations

    def continue_(self, messages: list[dict[str, Any]], context_manager: ContextManager) -> None:
        """Record the continuation; its current slots are rendered with every subsequent provider call."""
        # @intent same-context-continuation-replaces-managed-snapshots
        # The existing history stays in place while the overlay supplies one current state, handoff, and assessment.
        self.response.continued()

    def _update_context(self, context_manager: ContextManager) -> None:
        """Replace this attempt's handoff and assessment in the runtime-owned overlay."""
        handoff = self.run_state.handoff_writer.rendered
        if self.run_state.handoff is None or not handoff:
            context_manager.remove_by_id(JEV_HANDOFF_CONTEXT_ID)
        else:
            context_manager.upsert(
                TextContextItem(
                    primitive_id=JEV_HANDOFF_CONTEXT_ID,
                    title="Latest JEV handoff observed evidence",
                    content=f"<jev_handoff_observed_evidence>\n{handoff}\n</jev_handoff_observed_evidence>",
                ),
                placement=ContextWindowPlacement.END_OF_CONVERSATION,
            )
        context_manager.upsert(
            TextContextItem(
                primitive_id=JEV_CONTINUATION_GATE_CONTEXT_ID,
                title="Latest JEV continuation gate assessment",
                content=self._render_gate_assessment(),
            ),
            placement=ContextWindowPlacement.END_OF_CONVERSATION,
        )

    def _render_gate_assessment(self) -> str:
        """Render current status for every gate and question/focus detail for failures only."""
        results = {result.check: result for result in self.run_state.latest_results}
        sections = []
        for check in self.run_state.checks:
            result = results.get(check)
            if result is None or not result.available:
                status = "Status: unavailable; do not rely on an earlier assessment."
                detail = ""
            elif result.passed:
                status = "Status: passed; no questions failed."
                detail = ""
            else:
                status = "Status: failed; address the current missing work before finishing."
                failed, focus = self._explain(result)
                detail = f"\n\nDescription and failed questions:\n{self._failed_check(check, failed)}\n\nFocus:\n{focus}"
            sections.append(f"## {check.value.replace('_', ' ').title()}\n\n{JevDoneRegistry.description(check)}\n\n{status}{detail}")
        assessment = "\n\n".join(sections)
        directive = Prompts().get(Prompt.JEV_CONTINUATION_CONTINUE_PROMPT)
        return (
            f"<jev_continuation_directive>\n{directive}\n</jev_continuation_directive>\n\n"
            f"<jev_gate_assessment_reference_data>\n{assessment}\n</jev_gate_assessment_reference_data>"
        )

    @staticmethod
    def _failed_check(check: JevContinuationGate, failed: str) -> str:
        """Render one failed check: its heading, its shared gate description, then its failed Jev questions."""
        # @intent each-failed-check-is-explained-before-its-questions
        # The owner asked for every failed check to open with paragraphs on what follows and what its failed Jev
        # questions mean, with the questions after them; the text is the same registry description the fresh
        # continuation renders, so both continuations explain a gate the same way.
        title = check.value.replace("_", " ").title()
        return f"## {title}\n\n{JevDoneRegistry.description(check)}\n\nWhat the check found:\n{failed}"

    def _explain(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # @intent each-failed-check-keeps-its-own-feedback
        # One typed formatter per check keeps feedback aligned with that check's evidence and gap rules.
        handlers: Mapping[JevContinuationGate, Callable[[JevContinuationGateResult], tuple[str, str]]] = {
            JevContinuationGate.MULTI_PART: self._explain_multi_part,
            JevContinuationGate.CAN_SIMPLIFY: self._explain_can_simplify,
            JevContinuationGate.CLAIMS: self._explain_claims,
            JevContinuationGate.COMPLETION_EVIDENCE: self._explain_completion_evidence,
            JevContinuationGate.PHASE_PROGRESS: self._explain_phase_progress,
            JevContinuationGate.TARGET_OUTCOME: self._explain_target_outcome,
            JevContinuationGate.SCOPE_COVERAGE: self._explain_scope_coverage,
            JevContinuationGate.MOTIVATING_CASE: self._explain_motivating_case,
            JevContinuationGate.PROBLEMS_RESOLVED: self._explain_problems_resolved,
            JevContinuationGate.INPUT_SET_COVERAGE: self._explain_input_set_coverage,
            JevContinuationGate.OUTPUT_COUNT: self._explain_output_count,
            JevContinuationGate.OUTPUT_EXTENT: self._explain_output_extent,
            JevContinuationGate.REPORT_ACTION_ALIGNMENT: self._explain_report_action_alignment,
            JevContinuationGate.ASSUMPTIONS_RECONCILED: self._explain_assumptions_reconciled,
            JevContinuationGate.INPUT_EXHAUSTION: self._explain_input_exhaustion,
            JevContinuationGate.NEGATIVE_COVERAGE: self._explain_negative_coverage,
            JevContinuationGate.GUARANTEED_NEXT_ACTIONS: self._explain_guaranteed_next_actions,
            JevContinuationGate.REQUIRED_ACTIONS: self._explain_required_actions,
            JevContinuationGate.CUMULATIVE_OBLIGATIONS: self._explain_cumulative_obligations,
            JevContinuationGate.DISCOVERED_ITEM_COVERAGE: self._explain_discovered_items,
            JevContinuationGate.FAITHFUL_SCOPE: self._explain_faithful_scope,
            JevContinuationGate.EXPERT_DEPTH: self._explain_expert_depth,
            JevContinuationGate.SELF_REVIEW: self._explain_self_review,
            JevContinuationGate.REQUIRED_SEQUENCE: self._explain_required_sequence,
        }
        return handlers[result.check](result)

    def _explain_required_sequence(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Name each stage that lacks shown work, dependency evidence, or strict event order."""
        state = None if self.run_state.record is None else self.run_state.record.required_sequence
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.required_sequence
        if state is None or handoff is None:
            return "The required sequence could not be reviewed.", "Repeat the requested stages in order and leave their outputs visible."
        stages = {item.id: item for item in state.stages}
        evidence = {item.stage_id: item for item in handoff.stages}
        failed = ["The request requires its stages to be completed in order."]
        focus = []
        work_question = JevDoneRegistry.question_for_key(JevDoneQuestionKey.REQUIRED_SEQUENCE_WORK_SHOWN)
        previous_question = JevDoneRegistry.question_for_key(JevDoneQuestionKey.REQUIRED_SEQUENCE_USES_PREVIOUS_OUTPUT)
        for stage_id in result.incomplete:
            stage = stages[stage_id]
            item = evidence.get(stage_id)
            if item is None:
                failed.append(f"- {stage.label()} has no validated event evidence.")
                focus.append(f"- {stage.label()}: {stage.completion_criterion} Record its result in the run.")
                continue
            work_answer = result.answers.get(f"{stage_id}.work_shown")
            previous_answer = result.answers.get(f"{stage_id}.uses_previous_output")
            if not item.observed_work:
                failed.append(f"- {stage.label()} has no recorded work.")
            elif work_answer is not None and work_answer.probabilities.get(JEV_NOUL_TRUE, 0.0) < JevDoneRegistry.threshold(JevContinuationGate.REQUIRED_SEQUENCE):
                failed.append(f"- {work_question.instructions.question.format(item=stage_id)} Jev's answer: no.")
            elif previous_answer is not None and previous_answer.probabilities.get(JEV_NOUL_TRUE, 0.0) < JevDoneRegistry.threshold(JevContinuationGate.REQUIRED_SEQUENCE):
                failed.append(f"- {previous_question.instructions.question.format(item=stage_id)} Jev's answer: no.")
            else:
                previous_index = stage.position - 2
                previous_item = evidence.get(state.stages[previous_index].id) if previous_index >= 0 else None
                began_before_previous_finished = (
                    previous_item is not None
                    and previous_item.observed_work
                    and _event_position(item.first_event_id) <= _event_position(previous_item.last_work_event_id)
                )
                failed.append(
                    f"- {stage.label()} began before {state.stages[previous_index].label()} finished."
                    if began_before_previous_finished
                    else f"- {stage.label()} is not shown complete."
                )
            missing = "; ".join(item.missing_or_uncertain) or "No specific missing detail was identified."
            focus.append(f"- {stage.label()}: {stage.completion_criterion} Still missing or uncertain: {missing} Finish this stage before moving to later stages.")
        return "\n".join(failed), "\n".join(focus)

    def _explain_self_review(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Return unresolved reviewer objections in their original severity order."""
        resolved, in_scope = JevDoneRegistry.questions(JevContinuationGate.SELF_REVIEW)
        review = self.run_state.review
        handoff_record = self.run_state.handoff
        handoff = None if handoff_record is None else handoff_record.self_review
        objections = {} if review is None else {item.id: item for item in review.objections}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.objections}
        failed = [resolved.gap, in_scope.gap]
        focus = []
        for identifier in result.incomplete:
            resolved_answer = result.answers[resolved.name(identifier)]
            scope_answer = result.answers[in_scope.name(identifier)]
            cleared = resolved_answer.probabilities[JEV_NOUL_TRUE]
            in_scope_probability = scope_answer.probabilities[JEV_NOUL_TRUE]
            objection = objections[identifier]
            failed.append(
                f"""- Objection `{identifier}`: {objection.objection} Jev's answers: the work does not yet show it resolved (P(resolved) = {cleared:.2f}), and fixing it is within the request (P(in scope) = {in_scope_probability:.2f}). Still missing: {missing[identifier]}"""
            )
            focus.append(f"- A strict reviewer would reject this: {objection.objection} Accept when: {objection.resolved_when}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_faithful_scope(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Keep continuation feedback focused on the saved hard part and its evidence gap."""
        question = JevDoneRegistry.question(JevContinuationGate.FAITHFUL_SCOPE)
        answer = result.answers.get(JEV_DONE_HARD_PART_FIELD)
        probability = None if answer is None else answer.probabilities.get(JEV_NOUL_TRUE)
        answer_text = "Jev's answer was unavailable." if probability is None else f"Jev's answer: no (P(yes) = {probability:.2f})."
        failed = f"{question.gap}\n- {question.instructions.question.format(item=JEV_DONE_HARD_PART_FIELD)} {answer_text}"
        record = self.run_state.record
        if record is None:
            return failed, "- Recover the saved run state before changing scope."
        evidence = None if self.run_state.handoff is None else self.run_state.handoff.faithful_scope
        if evidence is not None and evidence.evidence:
            failed += f" Evidence reported: {evidence.evidence}"
        if evidence is not None and evidence.missing:
            failed += f" Missing: {evidence.missing}"
        limits = ", ".join(record.what_not_to_do) or "none were stated"
        focus = f"- Complete the saved hard part in the user's intended scope: {record.hard_part}. Preserve these limits: {limits}."
        return failed, focus

    # @intent go-deep-on-the-weakest-few
    # List every shallow point weakest first, but focus the next round on only the weakest few; it will re-rank after more work.
    def _explain_expert_depth(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Keep the failed-point list complete while concentrating recovery on its weakest details."""
        question = JevDoneRegistry.question(JevContinuationGate.EXPERT_DEPTH)
        record = self.run_state.record
        state = None if record is None else record.expert_depth
        handoff_record = self.run_state.handoff
        evidence = None if handoff_record is None else handoff_record.expert_depth
        details = {} if state is None else {detail.id: (deliverable, detail) for deliverable, detail in state.entries()}
        missing = {} if evidence is None else {item.id: item.missing for item in evidence.details}
        failed = [question.gap]
        focus = []
        for rank, identifier in enumerate(result.incomplete):
            answer = result.answers[identifier]
            yes = answer.probabilities[JEV_NOUL_TRUE]
            missing_work = missing[identifier]
            failed_line = f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still needed for depth: {missing_work}"
            failed.append(failed_line)
            if rank < JEV_EXPERT_DEPTH_FOCUS_LIMIT:
                deliverable, detail = details[identifier]
                focus_line = f"- Go deeper on: {detail.detail} Deliverable: {deliverable.description} Quick version to move past: {detail.shallow_version} Why it matters: {detail.risk} Done when: {detail.done_when}"
                focus.append(focus_line)
        return "\n".join(failed), "\n".join(focus)

    # @intent discovered-inventory-and-item-gaps-stay-separate
    # Source inventory failures need the original bounded output, while item failures need the specific requested action still missing.
    def _explain_discovered_items(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Describe each failed source inventory or discovered item with its own evidence and recovery focus."""
        handoff = self.run_state.handoff
        evidence = None if handoff is None else handoff.discovered_item_coverage
        batches = {} if evidence is None else {batch.source_id: batch for batch in evidence.batches}
        items = {} if evidence is None else {item.id: item for item in evidence.items()}
        item_question = JevDoneRegistry.question(JevContinuationGate.DISCOVERED_ITEM_COVERAGE)
        inventory_question = JevDoneRegistry.inventory_question(JevContinuationGate.DISCOVERED_ITEM_COVERAGE)
        failed = [item_question.gap]
        focus = []
        for identifier in result.incomplete:
            kind, item_id = identifier.split(":", 1)
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            if kind == "inventory":
                batch = batches[item_id]
                failed.append(f"- {inventory_question.instructions.question.format(item=item_id)} Jev's answer: no (P(yes) = {yes:.2f}). Source output:\n{batch.source_output}")
                listed = ", ".join(candidate.identity for candidate in batch.candidates) or "No candidates were listed."
                focus.append(f"- Review the complete source output for every in-scope discovered item, add any omitted item, and process each one. Current candidate inventory: {listed}")
                continue
            item = items[item_id]
            failed.append(f"- {item_question.instructions.question.format(item=item_id)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {item.missing}")
            focus.append(f"- {item.identity}. Requested: {item.requested_processing} Done when: {item.completion_criteria}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_cumulative_obligations(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Name only failed obligations or user-turn inventories and reconnect them to the user's words."""
        question = JevDoneRegistry.question(JevContinuationGate.CUMULATIVE_OBLIGATIONS)
        inventory_question = JevDoneRegistry.inventory_question(JevContinuationGate.CUMULATIVE_OBLIGATIONS)
        state = None if self.run_state.record is None else self.run_state.record.cumulative_obligations
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.cumulative_obligations
        obligations = {} if state is None else {item.id: item for item in state.obligations}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.obligations}
        failed: list[str] = []
        focus: list[str] = []
        for identifier in result.incomplete:
            if identifier.startswith("__inventory_turn_") and identifier.endswith("__"):
                index = int(identifier.removeprefix("__inventory_turn_").removesuffix("__"))
                failed.append(inventory_question.gap)
                yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
                failed.append(f"- The inventory for supplied user turn {index} was not confirmed complete (P(yes) = {yes:.2f}).")
                focus.append("- Re-read the supplied user turn; restore every direct requirement or explicit change, preserve actual cancellations and incompatible replacements, and finish any still-active requirement not shown in the latest run evidence. Do not invent a specific missing task from this finding alone.")
                continue
            if not failed:
                failed.append(question.gap)
            item = obligations[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            if item.active:
                focus.append(f"- From user turn {item.source_turn}: {item.instruction} Done when: {item.completion_signal}")
            else:
                focus.append(f"- Treat this earlier obligation as active because no supported cancellation or incompatible replacement is shown: {item.instruction} Done when: {item.completion_signal}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_guaranteed_next_actions(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Focus only on candidates Jev found both necessary and unfinished."""
        necessary, unfinished = JevDoneRegistry.questions(JevContinuationGate.GUARANTEED_NEXT_ACTIONS)
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.guaranteed_next_actions
        actions = {} if handoff is None else {item.id: item for item in handoff.actions}
        failed = [unfinished.gap]
        focus = []
        for identifier in result.incomplete:
            item = actions[identifier]
            necessary_yes = result.answers[necessary.name(identifier)].probabilities[JEV_NOUL_TRUE]
            unfinished_yes = result.answers[unfinished.name(identifier)].probabilities[JEV_NOUL_TRUE]
            failed.append("- Necessity passed: {necessary_question} Jev P(yes) = {necessary_yes:.2f}; unfinished confirmed: {unfinished_question} Jev P(yes) = {unfinished_yes:.2f}. Evidence gap: {missing}".format(
                necessary_question=necessary.instructions.question.format(item=identifier),
                necessary_yes=necessary_yes,
                unfinished_question=unfinished.instructions.question.format(item=identifier),
                unfinished_yes=unfinished_yes,
                missing=item.missing,
            ))
            focus.append(f"- Requested outcome: {item.outcome}\n  Observed trigger: {item.trigger}\n  Necessary action: {item.action}\n  Evidence gap: {item.missing}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_required_actions(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Focus feedback on explicitly requested actions that remain incomplete or out of order."""
        question = JevDoneRegistry.question(JevContinuationGate.REQUIRED_ACTIONS)
        state = None if self.run_state.record is None else self.run_state.record.required_actions
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.required_actions
        actions = {} if state is None else {item.id: item for item in state.actions}
        evidence = {} if handoff is None else {item.id: item for item in handoff.actions}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            action = actions[identifier]
            observed = evidence[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            missing = observed.missing
            order_gap = self._required_action_order_gap(action, evidence, result.incomplete)
            if order_gap:
                missing = f"{missing} {order_gap}" if missing else order_gap
            failed.append(
                f"- {question.instructions.question.format(item=identifier)} Gate result: incomplete (P(yes) = {yes:.2f}). Still missing: {missing}"
            )
            focus.append(f"- Required action: {action.action} Completion condition: {action.completion_signal}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_negative_coverage(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Name requested inspection targets whose reported conclusions lack run evidence."""
        question = JevDoneRegistry.question(JevContinuationGate.NEGATIVE_COVERAGE)
        state = None if self.run_state.record is None else self.run_state.record.negative_coverage
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.negative_coverage
        targets = {} if state is None else {item.id: item for item in state.inspections}
        evidence = {} if handoff is None else {item.id: item for item in handoff.inspections}
        failed, focus = [question.gap], []
        for identifier in result.incomplete:
            target, observed = targets[identifier], evidence[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {observed.missing}")
            focus.append(f"- Inspect the requested target: {target.target}. Evidence that meets the request: {target.inspection_signal}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_input_exhaustion(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Give each incomplete traversal's boundary, last position, and next action."""
        question = JevDoneRegistry.question(JevContinuationGate.INPUT_EXHAUSTION)
        state = None if self.run_state.record is None else self.run_state.record.input_exhaustion
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.input_exhaustion
        obligations = {} if state is None else {item.id: item for item in state.collections}
        observations = {} if handoff is None else {item.id: item for item in handoff.collections}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item, observation = obligations[identifier], observations[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev P(yes) = {yes:.2f}; this obligation remains incomplete. Still missing: {observation.missing}")
            position = "No successful traversal position is recorded." if observation.last_position is None else f"Last known position: {observation.last_position}."
            focus.append(f"- Collection: {item.collection}. Scope: {item.scope}. {position} Next step: {observation.next_step} Exhaustion condition: {item.exhaustion_condition}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_multi_part(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # Keep each incomplete deliverable's answer, handoff gap, and request wording together.
        question = JevDoneRegistry.question(JevContinuationGate.MULTI_PART)
        state = None if self.run_state.record is None else self.run_state.record.multi_part
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.multi_part
        deliverables = {} if state is None else {item.id: item for item in state.deliverables}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.deliverables}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            focus.append(f"- {deliverables[identifier].description} Done when: {deliverables[identifier].completion_signal}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_can_simplify(self, result: JevContinuationGateResult) -> tuple[str, str]:
        """Return the candidate and original preservation requirements as one failed prompt and one focus string."""
        question = JevDoneRegistry.question(JevContinuationGate.CAN_SIMPLIFY)
        record = self.run_state.record
        state = None if record is None else record.can_simplify
        handoff_record = self.run_state.handoff
        evidence = None if handoff_record is None else handoff_record.can_simplify
        if state is None or evidence is None:
            return question.gap, "Review the requested implementation and preserve every stated requirement."
        identifier = JEV_DONE_IMPLEMENTATION_FIELD
        yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
        failed = f"""{question.gap}
- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Simplification to make: {evidence.missing}"""
        focus = f"""Implementation scope: {state.scope}
Preserve: {state.preserve}
Apply this smaller approach: {evidence.missing}"""
        return failed, focus

    def _explain_claims(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # Keep unsupported assertions paired with their exact tool-call evidence and gap.
        question = JevDoneRegistry.question(JevContinuationGate.CLAIMS)
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.claims
        claims = {} if handoff is None else {item.id: item for item in handoff.claims}
        failed = [question.gap]
        focus = []
        threshold = JevDoneRegistry.threshold(JevContinuationGate.CLAIMS)
        for claim_id in result.incomplete:
            item = claims[claim_id]
            assertion_failures, assertion_focus = self._claim_assertion_feedback(item, result, question, threshold)
            failed.extend(assertion_failures)
            focus.extend(assertion_focus)
        return "\n".join(failed), "\n".join(focus)

    def _explain_completion_evidence(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # The final answer's overall completion status is a claim; show the run-evidence gap to correct it.
        item = None if self.run_state.handoff is None else self.run_state.handoff.completion_evidence
        failed = [JevDoneRegistry.question(JevContinuationGate.COMPLETION_EVIDENCE).gap]
        if item is None:
            return "\n".join(failed), "Review the original request and make the final answer accurately reflect the work shown in the run."
        yes = result.answers[JEV_DONE_COMPLETION_ITEM_ID].probabilities[JEV_NOUL_TRUE]
        failed.append(f"- The final answer communicates {item.completion_status.value} status. Jev's answer: unsupported (P(yes) = {yes:.2f}). Still missing: {item.missing}")
        return "\n".join(failed), self._completion_focus(item)

    def _explain_phase_progress(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # @intent phase-progress-focuses-only-failed-stages
        # Send back only required phases that lack evidence of substantive requested work.
        question = JevDoneRegistry.question(JevContinuationGate.PHASE_PROGRESS)
        state = None if self.run_state.record is None else self.run_state.record.phase_progress
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.phase_progress
        stages = {} if state is None else {item.id: item for item in state.stages}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.stages}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            stage = stages[identifier]
            focus.append(f"- Requested stage: {stage.stage}. Required result: {stage.required_result}. Scope: {stage.request_scope}. Output criterion: {stage.output_criterion}.")
        return "\n".join(failed), "\n".join(focus)

    def _explain_target_outcome(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # Return only target outcomes Jev could not recognize in direct evidence, with the proxy and gap visible.
        question = JevDoneRegistry.question(JevContinuationGate.TARGET_OUTCOME)
        state = None if self.run_state.record is None else self.run_state.record.target_outcome
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.target_outcome
        items = {} if state is None else {item.id: item for item in state.items}
        evidence = {} if handoff is None else {item.id: item for item in handoff.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = items[identifier]
            observed = evidence[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {observed.missing}")
            focus.append("\n".join((
                f"- Outcome: {item.outcome}",
                f"  Actual target: {item.target}",
                f"  Scope: {item.scope}",
                f"  Completion criterion: {item.completion_criterion}",
                f"  Observed proxy milestone: {observed.observed_proxy}",
                f"  Direct target evidence: {observed.direct_evidence}",
                f"  Still missing: {observed.missing}",
            )))
        return "\n".join(failed), "\n".join(focus)

    def _explain_problems_resolved(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # Name only failed dynamic items, with the handoff gap and repair/revalidation focus.
        question = JevDoneRegistry.question(JevContinuationGate.PROBLEMS_RESOLVED)
        evidence = None if self.run_state.handoff is None else self.run_state.handoff.problems_resolved
        items = {} if evidence is None else {item.id: item for item in evidence.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = items[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {item.missing}")
            focus.append(self._problem_focus(item))
        return "\n".join(failed), "\n".join(focus)

    # @intent input-target-feedback-is-limited-to-incomplete-targets
    # Keep the original boundary and each missing-work note beside only the target Jev did not recognize.
    def _explain_input_set_coverage(self, result: JevContinuationGateResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevContinuationGate.INPUT_SET_COVERAGE)
        state = None if self.run_state.record is None else self.run_state.record.input_set_coverage
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.input_set_coverage
        targets = {} if state is None else {item.id: item for item in state.targets}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.targets}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            target = targets[identifier]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            focus.append(f"- {target.action} {target.identity} within {target.scope}. Done when: {target.engagement_signal}")
        return "\n".join(failed), "\n".join(focus)

    # @intent output-count-focus-names-only-incomplete-quantities
    # Keep the requested unit and group boundary beside only the counts Jev did not recognize.
    def _explain_output_count(self, result: JevContinuationGateResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevContinuationGate.OUTPUT_COUNT)
        state = None if self.run_state.record is None else self.run_state.record.output_count
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.output_count
        obligations = {} if state is None else {item.id: item for item in state.obligations}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.obligations}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = obligations[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            focus.append(f"- {item.description} Target: {item.target_count} {item.unit}; scope: {item.scope}; distinctness: {item.distinctness}. Done when: {item.completion_criteria}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_output_extent(self, result: JevContinuationGateResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevContinuationGate.OUTPUT_EXTENT)
        state = None if self.run_state.record is None else self.run_state.record.output_extent
        evidence = None if self.run_state.handoff is None else self.run_state.handoff.output_extent
        items = {} if state is None else {item.id: item for item in state.items}
        missing = {} if evidence is None else {item.id: item.missing for item in evidence.items}
        failed = [question.gap]
        focus = []
        threshold = JevDoneRegistry.threshold(JevContinuationGate.OUTPUT_EXTENT)
        for identifier in result.incomplete:
            item = items[identifier]
            observed = self.run_state._observed_extent.get(identifier)
            amount = "unmeasured" if observed is None else str(observed)
            probability = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            verdict = "yes" if DecisionModelHelper.noul_passes(result.answers, identifier, threshold) else "no"
            if observed is None or self.run_state._satisfies(observed, item.amount, item.comparator):
                gap = missing[identifier]
            else:
                gap = f"The final answer has {observed} {item.unit.value}; the request requires {item.comparator.value} {item.amount} {item.unit.value}."
            failed.append(
                f"- {question.instructions.question.format(item=identifier)} Jev's answer: {verdict} (P(yes) = {probability:.2f}). Observed amount: {amount} {item.unit.value}; requested {item.comparator.value} {item.amount} {item.unit.value}. Still missing: {gap}"
            )
            focus.append(
                f"- Output target: {item.target}\n  Requested extent: {item.comparator.value} {item.amount} {item.unit.value}\n  Observed extent: {amount} {item.unit.value}"
            )
        return "\n".join(failed), "\n".join(focus)

    def _explain_report_action_alignment(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # @intent a-report-mismatch-focuses-one-plan-item
        # A planned route is not a user requirement by itself; repair only a still-required outcome or an inaccurate account.
        # Only failed account comparisons are sent back, with the original request relevance and evidence gap.
        alignment = None if self.run_state.handoff is None else self.run_state.handoff.report_action_alignment
        candidates = {} if alignment is None else {item.id: item for item in alignment.items}
        question = JevDoneRegistry.question(JevContinuationGate.REPORT_ACTION_ALIGNMENT)
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = candidates[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {item.missing}")
            focus.append("\n".join((
                f"- Earlier plan or commitment: {item.plan}",
                f"  Recorded execution: {item.execution}",
                f"  Final account: {item.final_account}",
                f"  Relevance to the original request: {item.request_relevance}",
                f"  Recorded evidence: {item.evidence}",
                f"  Reconcile by completing any still-required result or correcting the account: {item.missing}",
            )))
        return "\n".join(failed), "\n".join(focus)

    def _explain_assumptions_reconciled(self, result: JevContinuationGateResult) -> tuple[str, str]:
        # @intent changed-assumption-feedback-names-failed-premises
        # Keep continuation feedback scoped to failed items, with source context and the separate missing note.
        # Return only failed changed premises, with dependent work and the handoff's separate gap.
        question = JevDoneRegistry.question(JevContinuationGate.ASSUMPTIONS_RECONCILED)
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.assumptions_reconciled
        assumptions = {} if handoff is None else {item.id: item for item in handoff.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = assumptions[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {item.missing}")
            focus.append("\n".join((
                f"- Original assumption: {item.original_assumption}",
                f"  Original basis: {item.original_basis}",
                f"  Later observation: {item.later_observation}",
                f"  Affected work: {item.affected_work}",
                f"  Later actions or results: {item.revision}",
                f"  Run evidence: {item.evidence}",
            )))
        return "\n".join(failed), "\n".join(focus)

    # @intent scope-coverage-focus-names-every-missing-member
    # An omitted workspace inventory is a separate gap from missing evidence for any member already enumerated.
    def _explain_scope_coverage(self, result: JevContinuationGateResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevContinuationGate.SCOPE_COVERAGE)
        state = None if self.run_state.record is None else self.run_state.record.scope_coverage
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.scope_coverage
        if state is None or handoff is None:
            return "The scope coverage evidence is unavailable.", "Continue the requested scope coverage and provide evidence for each required member."
        items = {identifier: (dimension, unit) for identifier, dimension, unit in handoff.question_items(state)}
        dimensions = {dimension.id: dimension for dimension in state.checked_dimensions()}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            if identifier.endswith(".inventory"):
                dimension_id = identifier[:-len(".inventory")]
                dimension = dimensions[dimension_id]
                failed.append(f"- No workspace enumeration is shown for all requested {dimension.unit_noun} (request: \"{dimension.request_quote}\").")
                focus.append(f"- List every {dimension.unit_noun} found in the workspace, then apply the requested change to each one: {dimension.requested_change}")
                continue
            dimension, unit = items[identifier]
            answer = result.answers.get(identifier)
            if answer is None:
                failed.append(f"- No work evidence is recorded for {unit.unit} ({dimension.unit_noun}) in the group named by \"{dimension.request_quote}\".")
            else:
                yes = answer.probabilities[JEV_NOUL_TRUE]
                failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's P(yes) was {yes:.2f}, below the required threshold.")
            focus.append(f"- Complete {dimension.requested_change} for {unit.unit} ({dimension.unit_noun}); show the resulting work in the run.")
        return "\n".join(failed), "\n".join(focus)

    # @intent motivating-case-focus-names-only-failed-user-scenarios
    # The handoff gap and request-derived boundary details let the main agent exercise only the missing scenario.
    def _explain_motivating_case(self, result: JevContinuationGateResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevContinuationGate.MOTIVATING_CASE)
        state = None if self.run_state.record is None else self.run_state.record.motivating_case
        handoff = None if self.run_state.handoff is None else self.run_state.handoff.motivating_case
        scenarios = {} if state is None else {item.id: item for item in state.scenarios}
        missing = {} if handoff is None else {item.id: item.missing for item in handoff.scenarios}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            scenario = scenarios[identifier]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
            expected = f" Expected behavior: {scenario.expected_behavior}." if scenario.expected_behavior else ""
            focus.append(f"- Exercise {scenario.condition} for {scenario.target}; the nearby case that does not count is {scenario.near_miss}.{expected} Allowed mode: {scenario.exercise_mode.value}.")
        return "\n".join(failed), "\n".join(focus)

    @staticmethod
    def _required_action_order_gap(
        action: JevRequiredAction,
        evidence: Mapping[str, JevRequiredActionEvidence],
        incomplete: tuple[str, ...],
    ) -> str:
        """Describe an explicit predecessor order that the successful trace indices do not establish."""
        if not action.predecessors:
            return ""
        own_index = evidence[action.id].completion_trace_index
        predecessor_indices = [evidence[identifier].completion_trace_index for identifier in action.predecessors]
        if any(identifier in incomplete for identifier in action.predecessors) or own_index is None or any(
            index is None or index >= own_index for index in predecessor_indices
        ):
            return f"The run does not show successful completion of {', '.join(action.predecessors)} before {action.id} in the requested order."
        return ""

    def _claim_assertion_feedback(self, claim: JevClaimEvidence, result: JevContinuationGateResult, question: JevDoneQuestion, threshold: float) -> tuple[list[str], list[str]]:
        """Return failed-question text and focus only for assertions below the threshold in one parent claim."""
        failed = []
        focus = []
        for assertion in claim.claim.assertions:
            identifier = f"{claim.id}{JEV_DONE_CLAIM_ASSERTION_SEPARATOR}{assertion.id}"
            if DecisionModelHelper.noul_passes(result.answers, identifier, threshold) is not False:
                continue
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {claim.missing}")
            focus.append(self._claim_focus(claim, assertion))
        return failed, focus

    @staticmethod
    def _claim_focus(claim: JevClaimEvidence, assertion: JevClaimAssertion) -> str:
        """Render one unsupported assertion together with its parent claim context and evidence gap."""
        intent = "None stated" if claim.claim.identity.intent is None else claim.claim.identity.intent
        qualifications = ", ".join(claim.claim.scope.qualifications) or "None stated"
        output = "No output claimed" if claim.claim.output is None else claim.claim.output
        return "\n".join((
            f"- Claim: {claim.claim.identity.title}",
            f"  Description: {claim.claim.identity.description}",
            f"  Intent: {intent}",
            f"  Scope: {claim.claim.scope.scope}",
            f"  Qualifications: {qualifications}",
            f"  Kind: {claim.claim.kind.value}",
            f"  Output: {output}",
            f"  Unsupported assertion ({assertion.id}): {assertion.statement}",
            f"  Completion criteria: {assertion.completion_criteria}",
            f"  Tool-call evidence: {claim.evidence}",
            f"  Still missing: {claim.missing}",
        ))

    @staticmethod
    def _completion_focus(item: JevCompletionEvidence) -> str:
        """Render the requested outcomes the final answer must finish or accurately describe."""
        requested = "; ".join(item.requested_outcomes) or "No outcome was requested."
        completed = "; ".join(item.completed_work) or "None shown."
        unfinished = "; ".join(item.unfinished_or_blocked) or "No unfinished outcome was identified."
        return "\n".join((
            f"- Requested outcomes: {requested}",
            f"  Work shown: {completed}",
            f"  Unfinished or blocked: {unfinished}",
            f"  Evidence gap: {item.missing}",
        ))

    @staticmethod
    def _problem_focus(item: JevProblemResolutionItem) -> str:
        """Render the failed issue or original-request item with its repair and evidence gap."""
        directive = "Fully repair this problem and successfully revalidate the affected behavior, then return to the original request and complete all remaining requested work." if item.kind is JevProblemCheckItemType.PROBLEM else "Return to the original request and complete every remaining requested part after any repairs."
        return "\n".join((
            f"- Item: {item.title} ({item.kind.value})",
            f"  Description: {item.description}",
            f"  Scope: {item.scope}",
            f"  Repair reported: {item.repair}",
            f"  Verification: {item.verification}",
            f"  Run evidence: {item.evidence}",
            f"  Still missing: {item.missing}",
            f"  {directive}",
        ))


__all__ = ["JevDoneContinuation"]
