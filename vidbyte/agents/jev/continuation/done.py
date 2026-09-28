"""FILE: vidbyte/agents/jev/continuation/done.py

PURPOSE: Implements JevDoneContinuation, the continuation for JevAgent's done checks: at every finish attempt it has JevRunState run the enabled checks, and when one fails it sends the main agent back to work with the original request, the run state, the handoff, and the Jev questions that failed, with more focus on what is missing.
ROLE IN CODEBASE: JevAgent builds one JevDoneContinuation over its JevRunState when JevRuntimeSettings.continual enables a done check, and JevRuntime calls should_continue() and continue_() from its finish-attempt hook; each continuation is recorded through JevResponse on JevAgent.response.
ARCHITECTURE NOTE: The message is the vidbyte/prompts asset jev_continuation/continue_prompt.md, filled with the run's own text; what one failed check contributes to it is one commented case in _explain(). The cap on continuations is JevContinualSettings.max_continuations.
COMMON MODIFICATION PATTERNS: Add a done check's failed questions and focus to _explain(); change the message's instructions in vidbyte/prompts/prompts/jev_continuation/continue_prompt.md.
KNOWN EDGE CASES: A failed check whose handoff is missing never continues, because there is no evidence to hand back. Expert depth lists every shallow detail under Failed checks, weakest first, but names only the JEV_EXPERT_DEPTH_FOCUS_LIMIT weakest under Focus. After max_continuations continuations the latest verdict stays on JevAgent.response, but the main agent's answer stands.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-expert-depth-done-criteria.md, skills/jev-continuation/SKILL.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinualSettings
from vidbyte.lib.constants.jev import JEV_EXPERT_DEPTH_FOCUS_LIMIT, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.jev import JevDoneResult
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.jev import JevDoneRegistry
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
            case JevDoneCheck.EXPERT_DEPTH:
                # Every shallow detail's question, Jev's answer, and the handoff's words for what a deeper handling
                # still needs, weakest first; then only the weakest few, in the run state's terms, as the points to
                # go deeper on, each with its quick version to move past, why it matters, and when it is done.
                # @intent go-deep-on-the-weakest-few
                # Naming every shallow point under Focus would spread the next round thin, which is the shallow work
                # this check exists to catch; the next finish attempt re-ranks, so each round takes the weakest now.
                question = JevDoneRegistry.question(JevDoneCheck.EXPERT_DEPTH)
                state = None if self.run_state.record is None else self.run_state.record.expert_depth
                handoff = None if self.run_state.handoff is None else self.run_state.handoff.expert_depth
                details = {} if state is None else {detail.id: (deliverable, detail) for deliverable, detail in state.entries()}
                missing = {} if handoff is None else {item.id: item.missing for item in handoff.details}
                failed = [question.gap]
                focus = []
                for rank, identifier in enumerate(result.incomplete):
                    yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
                    failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still needed for depth: {missing[identifier]}")
                    if rank < JEV_EXPERT_DEPTH_FOCUS_LIMIT:
                        deliverable, detail = details[identifier]
                        focus.append(f"- Go deeper on: {detail.detail} Deliverable: {deliverable.description} Quick version to move past: {detail.shallow_version} Why it matters: {detail.risk} Done when: {detail.done_when}")
                return "\n".join(failed), "\n".join(focus)


__all__ = ["JevDoneContinuation"]
