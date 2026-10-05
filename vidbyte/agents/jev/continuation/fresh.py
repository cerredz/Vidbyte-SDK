"""FILE: vidbyte/agents/jev/continuation/fresh.py

PURPOSE: Implements the opt-in fresh-context continuation: when a done check fails, it sends the original request, run state, and handoff to a clean agent context, then returns that work to JevAgent's main loop.
ROLE IN CODEBASE: JevAgent builds this continuation when JevContinualSettings.gate is FRESH; JevRuntime calls it at the same finish-attempt seam as JevDoneContinuation.
ARCHITECTURE NOTE: The clean agent uses the configured JevAgent model, tools, and policy but has a fresh history; the existing loop receives its response as the next user message.
COMMON MODIFICATION PATTERNS: Keep the context template in vidbyte/prompts/prompts/jev_fresh_continuation/ and preserve the existing done-check trigger and continuation cap.
KNOWN EDGE CASES: A missing state, handoff, failed done check, exhausted limit, or fresh-agent error leaves the original answer in place.
RELATED DOCS: docs/design/jev-fresh-continuation.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_fresh_continuation.py.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.continuation.done import JevDoneContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinualSettings
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import JevContinuationEvidence
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevDoneRegistry
from vidbyte.prompts.catalog import Prompts


class JevFreshContinuation(JevDoneContinuation):
    """Continue failed done checks through an agent with a clean context window."""

    def __init__(self, run_state: JevRunState, continual: JevContinualSettings, response: JevResponse, fresh_agent_factory: Callable[[], BaseAgent]) -> None:
        # Reuses the done-check state, cap, response writer, and faithful-scope budget policy while creating each fresh agent per attempt.
        super().__init__(run_state, continual, response)
        self.fresh_agent_factory = fresh_agent_factory
        self._fresh_output: str | None = None
        self._pending_evidence: JevContinuationEvidence | None = None

    async def should_continue(self, final_answer: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> bool:
        """Run the clean-context agent only when a done check failed and the continuation limit allows it."""
        self._fresh_output = None
        self._pending_evidence = None
        if not await super().should_continue(final_answer, responses, calls):
            return False
        prompt = self.message()
        if not prompt:
            return False
        try:
            fresh_agent = self.fresh_agent_factory()
            fresh_agent.history.clear()
            reply = await fresh_agent.arun(AgentInput(prompt=prompt))
        except VidbyteSdkError:
            # @intent fresh-agent-failure-leaves-current-answer
            # Fresh continuation is advisory; a model failure leaves the already produced answer in place.
            return False
        self._fresh_output = reply.content.strip() or None
        if self._fresh_output is None:
            return False
        raw_metadata = getattr(reply, "metadata", None)
        metadata = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        raw_responses = metadata.get("iteration_outputs")
        if isinstance(raw_responses, (tuple, list)) and all(isinstance(item, str) for item in raw_responses):
            evidence_responses = tuple(raw_responses)
        else:
            evidence_responses = (reply.content,)
        if not evidence_responses or evidence_responses[-1] != reply.content:
            evidence_responses = (*evidence_responses, reply.content)
        raw_calls = metadata.get("tool_calls")
        evidence_calls = tuple(item for item in raw_calls if isinstance(item, ToolCallContext)) if isinstance(raw_calls, (tuple, list)) else ()
        self._pending_evidence = JevContinuationEvidence(
            source="fresh",
            responses=evidence_responses,
            tool_calls=evidence_calls,
        )
        return True

    def continue_(self, messages: list[dict[str, Any]]) -> JevContinuationEvidence | None:
        """Append the fresh agent's response and return its raw evidence segment."""
        if self._fresh_output is None or self._pending_evidence is None:
            self._fresh_output = None
            self._pending_evidence = None
            return None
        self.response.continued()
        messages.append({"role": "user", "content": self._fresh_output})
        evidence = self._pending_evidence
        self._fresh_output = None
        self._pending_evidence = None
        return evidence

    # @intent fresh-attempt-starts-from-validated-source-context
    # The fresh agent must see the original request, current run state, and latest handoff while starting with no main-agent history.
    # If any required source is unavailable, do not launch with a partial or stale prompt that could invent the continuation scope.
    def message(self) -> str:
        """Build the fresh agent's clean-context input from the original request, state, and latest handoff."""
        handoff = self.run_state.handoff_writer.rendered
        if not self.run_state.rendered or not handoff:
            return ""
        return Prompts().get(Prompt.JEV_FRESH_CONTINUATION_PROMPT).format(
            request=self.run_state.request,
            run_state=self.run_state.rendered,
            handoff=handoff,
            gate_assessment=self._render_gate_assessment(),
        )

    def _render_gate_assessment(self) -> str:
        # Rebuilds the complete gate section from this attempt's latest check results.
        """Render every enabled gate's stable guidance and its latest failed question text."""
        results = {result.check: result for result in self.run_state.latest_results}
        sections = []
        for check in self.run_state.checks:
            result = results.get(check)
            if result is None or not result.available:
                status = "Status: not evaluated."
            elif result.passed:
                status = "Status: passed; no questions failed."
            elif result.failed_questions:
                questions = "\n".join(f"- {item.question}" for item in result.failed_questions)
                status = f"Questions that failed:\n{questions}"
            else:
                status = "Status: gate failed on deterministic evidence; no Jev question failed."
            title = check.value.replace("_", " ").title()
            sections.append(f"## {title}\n\n{JevDoneRegistry.description(check)}\n\n{status}")
        content = "\n\n".join(sections)
        return f"<completion_gate_assessment>\n{content}\n</completion_gate_assessment>"


__all__ = ["JevFreshContinuation"]
