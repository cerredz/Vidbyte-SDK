"""FILE: vidbyte/agents/jev/continuation/done.py

PURPOSE: Implements JevDoneContinuation, the continuation for JevAgent's done checks: at every finish attempt it has JevRunState run the enabled checks, and when one fails it sends the main agent back to work with the original request, the run state, the handoff, and the Jev questions that failed, with more focus on what is missing.
ROLE IN CODEBASE: JevAgent builds one JevDoneContinuation over its JevRunState when JevRuntimeSettings.continual enables a done check, and JevRuntime calls should_continue() and continue_() from its finish-attempt hook; each continuation is recorded through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The message is the vidbyte/prompts asset jev_continuation/continue_prompt.md, filled with the run's own text; what one failed check contributes to it is one commented case in _explain(). The cap on continuations is JevContinualSettings.max_continuations.
COMMON MODIFICATION PATTERNS: Add a done check's failed questions and focus to _explain(); change the message's instructions in vidbyte/prompts/prompts/jev_continuation/continue_prompt.md.
KNOWN EDGE CASES: A failed check whose handoff is missing never continues, because there is no evidence to hand back. After max_continuations continuations the latest verdict stays on JevAgent.response, but the main agent's answer stands.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

import re
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
)
from vidbyte.lib.enums.jev import JevDoneCheck, JevDoneQuestionKey
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext

_EVENT_POSITION = re.compile(r"^E([1-9][0-9]*)$")


def _event_position(event_id: str) -> int:
    """Return the numeric position of an event id for ordered feedback."""
    match = _EVENT_POSITION.fullmatch(event_id)
    return 0 if match is None else int(match.group(1))


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
        return bool(self.failed) and self.run_state.handoff is not None and self.response.state.continuations < self.max_continuations

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
        # Returns one failed check's part of the message: its failed Jev questions, and the focus lines; one commented case per check.
        match result.check:
            case JevDoneCheck.MULTI_PART:
                # Each incomplete deliverable's question, Jev's answer, and the handoff's own words for what is missing,
                # then the deliverables themselves, in the user's terms, as the parts to focus on.
                question = JevDoneRegistry.question(JevDoneCheck.MULTI_PART)
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
            case JevDoneCheck.CLAIMS:
                # Give the main agent only the factual assertions Jev found unsupported, paired with their
                # exact tool-call evidence and gap so it can finish requested work or correct its final answer.
                question = JevDoneRegistry.question(JevDoneCheck.CLAIMS)
                handoff = None if self.run_state.handoff is None else self.run_state.handoff.claims
                claims = {} if handoff is None else {item.id: item for item in handoff.claims}
                failed = [question.gap]
                focus = []
                threshold = JevDoneRegistry.threshold(JevDoneCheck.CLAIMS)
                for claim_id in result.incomplete:
                    item = claims[claim_id]
                    assertion_failures, assertion_focus = self._claim_assertion_feedback(item, result, question, threshold)
                    failed.extend(assertion_failures)
                    focus.extend(assertion_focus)
                return "\n".join(failed), "\n".join(focus)
            case JevDoneCheck.REQUIRED_SEQUENCE:
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
                    stage, item = stages[stage_id], evidence[stage_id]
                    work_answer = result.answers.get(f"{stage_id}.work_shown")
                    previous_answer = result.answers.get(f"{stage_id}.uses_previous_output")
                    if not item.observed_work:
                        failed.append(f"- {stage.label()} has no recorded work.")
                    elif work_answer is not None and work_answer.probabilities.get(JEV_NOUL_TRUE, 0.0) < JevDoneRegistry.threshold(JevDoneCheck.REQUIRED_SEQUENCE):
                        failed.append(f"- {work_question.instructions.question.format(item=stage_id)} Jev's answer: no.")
                    elif previous_answer is not None and previous_answer.probabilities.get(JEV_NOUL_TRUE, 0.0) < JevDoneRegistry.threshold(JevDoneCheck.REQUIRED_SEQUENCE):
                        failed.append(f"- {previous_question.instructions.question.format(item=stage_id)} Jev's answer: no.")
                    else:
                        previous_index = stage.position - 2
                        if previous_index >= 0:
                            previous_stage = state.stages[previous_index]
                            previous_item = evidence[previous_stage.id]
                            if previous_item.observed_work and _event_position(item.first_event_id) <= _event_position(previous_item.last_work_event_id):
                                failed.append(f"- {stage.label()} began before {previous_stage.label()} finished.")
                            else:
                                failed.append(f"- {stage.label()} is not shown complete.")
                        else:
                            failed.append(f"- {stage.label()} is not shown complete.")
                    missing = "; ".join(item.missing_or_uncertain) or "No specific missing detail was identified."
                    focus.append(f"- {stage.label()}: {stage.completion_criterion} Still missing or uncertain: {missing} Finish this stage before moving to later stages.")
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


__all__ = ["JevDoneContinuation"]
