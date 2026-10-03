"""FILE: vidbyte/agents/jev/continuation/done.py

PURPOSE: Implements JevDoneContinuation, the continuation for JevAgent's done checks: at every finish attempt it has JevRunState run enabled checks, and on failure it sends the original request, run state, handoff, failed Jev questions, and focused missing work back to the main agent.
ROLE IN CODEBASE: JevAgent builds one JevDoneContinuation over its JevRunState when JevRuntimeSettings.continual enables a done check, and JevRuntime calls should_continue() and continue_() from its finish-attempt hook; each continuation is recorded through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The message is the vidbyte/prompts asset jev_continuation/continue_prompt.md, filled with the run's own text; what one failed check contributes to it is one commented case in _explain(). Problem repair feedback requires relevant successful revalidation and then directs the agent back to the original request. The cap on continuations is JevContinualSettings.max_continuations.
COMMON MODIFICATION PATTERNS: Add a done check's failed questions and focus to _explain(); change the message's instructions in vidbyte/prompts/prompts/jev_continuation/continue_prompt.md.
KNOWN EDGE CASES: A failed check whose handoff is missing never continues, because there is no evidence to hand back. After max_continuations continuations the latest verdict stays on JevAgent.response, but the main agent's answer stands.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinualSettings
from vidbyte.lib.constants.jev import JEV_DONE_CLAIM_ASSERTION_SEPARATOR, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import (
    JevClaimAssertion,
    JevClaimEvidence,
    JevDoneQuestion,
    JevDoneResult,
    JevProblemResolutionItem,
)
from vidbyte.lib.enums.jev import JevDoneCheck, JevProblemCheckItemType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext


class JevDoneContinuation(JevContinuation):
    """Continuation that sends the main agent back to finish what a failed done check found missing."""

    def __init__(self, run_state: JevRunState, continual: JevContinualSettings, response: JevResponse) -> None:
        # Fixes the done checks' run state, the continuation cap, and the response writer when JevAgent is built.
        self.run_state = run_state
        self.max_continuations = continual.max_continuations
        self.response = response
        self.failed: tuple[JevDoneResult, ...] = ()

    async def should_continue(self, final_answer: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> bool:
        """Run every enabled done check and return True when one failed and continuations remain."""
        self.failed = await self.run_state.check(final_answer, responses, calls)
        # @intent continuations-are-bounded
        # A check that keeps failing must not trap the run: after the cap the latest verdict stays on the
        # response for the caller to read, but the main agent's answer stands.
        return bool(self.failed) and self.run_state.handoff_record is not None and self.response.state.continuations < self.max_continuations

    def continue_(self, messages: list[dict[str, Any]]) -> None:
        """Record the continuation and append the message that sends the main agent back to finish the missing parts."""
        # @intent a-failed-done-check-keeps-the-same-loop
        # The message joins this loop's own messages, so the main agent keeps its history, tools, and budgets
        # and finishes the missing work instead of starting a second run that has forgotten the first.
        self.response.continued()
        messages.append({"role": "user", "content": self.message()})

    def message(self) -> str:
        """Return what the main agent reads: the original request, the run state, the handoff, the failed questions, and the focus."""
        # @intent the-continuation-message-is-a-prompt-asset
        # The owner asked for the main agent to get the original prompt, the run state, the handoff, and the failed
        # Jev questions with more focus on what is missing; the instructions live in the prompt asset so they stay
        # reviewable, and only the run's own text is filled in here.
        explained = [self._explain(result) for result in self.failed]
        return Prompts().get(Prompt.JEV_CONTINUATION_CONTINUE_PROMPT).format(
            request=self.run_state.request,
            run_state=self.run_state.rendered,
            handoff=self.run_state.handoff_writer.rendered,
            failed="\n\n".join(failed for failed, _ in explained),
            focus="\n".join(focus for _, focus in explained),
        )

    def _explain(self, result: JevDoneResult) -> tuple[str, str]:
        """Dispatch failed checks to focused continuation feedback renderers."""
        match result.check:
            case JevDoneCheck.MULTI_PART:
                return self._explain_multi_part(result)
            case JevDoneCheck.CLAIMS:
                return self._explain_claims(result)
            case JevDoneCheck.OUTPUT_EXTENT:
                return self._explain_output_extent(result)
            case JevDoneCheck.TARGET_OUTCOME:
                return self._explain_target_outcome(result)
            case JevDoneCheck.PROBLEMS_RESOLVED:
                return self._explain_problems_resolved(result)
        raise ValueError(f"Unsupported Jev done check: {result.check!r}")

    def _explain_multi_part(self, result: JevDoneResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
        state = None if self.run_state.record is None else self.run_state.record.multi_part
        evidence_record = None if self.run_state.handoff_record is None else self.run_state.handoff_record.multi_part
        deliverables = {} if state is None else {item.id: item for item in state.deliverables}
        missing_by_id = {} if evidence_record is None else {item.id: item.missing for item in evidence_record.deliverables}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing_by_id[identifier]}")
            item = deliverables[identifier]
            focus.append(f"- {item.description} Done when: {item.completion_signal}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_claims(self, result: JevDoneResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
        handoff_record = None if self.run_state.handoff_record is None else self.run_state.handoff_record.claims
        claims_by_id = {} if handoff_record is None else {item.id: item for item in handoff_record.claims}
        failed = [question.gap]
        focus = []
        threshold = JevDoneRegistry.threshold(JevDoneCheck.CLAIMS)
        for claim_id in result.incomplete:
            failures, assertion_focus = self._claim_assertion_feedback(claims_by_id[claim_id], result, question, threshold)
            failed.extend(failures)
            focus.extend(assertion_focus)
        return "\n".join(failed), "\n".join(focus)

    def _explain_output_extent(self, result: JevDoneResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevDoneCheck.OUTPUT_EXTENT)
        state = None if self.run_state.record is None else self.run_state.record.output_extent
        evidence_record = None if self.run_state.handoff_record is None else self.run_state.handoff_record.output_extent
        items_by_id = {} if state is None else {item.id: item for item in state.items}
        missing_by_id = {} if evidence_record is None else {item.id: item.missing for item in evidence_record.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = items_by_id[identifier]
            observed_count = self.run_state._observed_extent.get(identifier)
            observed = "unmeasured" if observed_count is None else str(observed_count)
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            passed = DecisionModelHelper.noul_passes(result.answers, identifier, JevDoneRegistry.threshold(JevDoneCheck.OUTPUT_EXTENT))
            answer = "yes" if passed else "no"
            gap = missing_by_id[identifier]
            if observed_count is not None and self.run_state._satisfies(observed_count, item.amount, item.comparator):
                gap = f"Jev did not recognize the measured extent; the final answer has {observed_count} {item.unit.value}, and the request requires {item.comparator.value} {item.amount} {item.unit.value}."
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: {answer} (P(yes) = {yes:.2f}). Observed amount: {observed} {item.unit.value}; requested {item.comparator.value} {item.amount} {item.unit.value}. Still missing: {gap}")
            focus.append(f"- Output target: {item.target}\n  Requested extent: {item.comparator.value} {item.amount} {item.unit.value}\n  Observed extent: {observed} {item.unit.value}")
        return "\n".join(failed), "\n".join(focus)

    def _explain_target_outcome(self, result: JevDoneResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevDoneCheck.TARGET_OUTCOME)
        state = None if self.run_state.record is None else self.run_state.record.target_outcome
        evidence_record = None if self.run_state.handoff_record is None else self.run_state.handoff_record.target_outcome
        items_by_id = {} if state is None else {item.id: item for item in state.items}
        evidence_by_id = {} if evidence_record is None else {item.id: item for item in evidence_record.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = items_by_id[identifier]
            observed = evidence_by_id[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {observed.missing}")
            focus.append("\n".join((
                f"- Outcome: {item.outcome}", f"  Actual target: {item.target}", f"  Scope: {item.scope}",
                f"  Completion criterion: {item.completion_criterion}", f"  Observed proxy milestone: {observed.observed_proxy}",
                f"  Direct target evidence: {observed.direct_evidence}", f"  Still missing: {observed.missing}",
            )))
        return "\n".join(failed), "\n".join(focus)

    def _explain_problems_resolved(self, result: JevDoneResult) -> tuple[str, str]:
        question = JevDoneRegistry.question(JevDoneCheck.PROBLEMS_RESOLVED)
        evidence_record = None if self.run_state.handoff_record is None else self.run_state.handoff_record.problems_resolved
        items_by_id = {} if evidence_record is None else {item.id: item for item in evidence_record.items}
        failed = [question.gap]
        focus = []
        for identifier in result.incomplete:
            item = items_by_id[identifier]
            yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
            failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {item.missing}")
            focus.append(self._problem_focus(item))
        return "\n".join(failed), "\n".join(focus)

    def _claim_assertion_feedback(self, claim: JevClaimEvidence, result: JevDoneResult, question: JevDoneQuestion, threshold: float) -> tuple[list[str], list[str]]:
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
