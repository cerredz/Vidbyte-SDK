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

from collections.abc import Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinualSettings
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext


class JevFreshContinuation(JevContinuation):
    """Continue failed done checks through an agent with a clean context window."""

    def __init__(self, run_state: JevRunState, continual: JevContinualSettings, response: JevResponse, fresh_agent: BaseAgent) -> None:
        # Fixes the shared done-check state, continuation limit, response writer, and fresh agent at construction.
        self.run_state = run_state
        self.max_continuations = continual.max_continuations
        self.response = response
        self.fresh_agent = fresh_agent
        self._fresh_output: str | None = None

    async def should_continue(self, final_answer: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> bool:
        """Run the clean-context agent only when a done check failed and the continuation limit allows it."""
        failed = await self.run_state.check(final_answer, responses, calls)
        can_continue = bool(failed) and self.run_state.handoff is not None and self.response.state.continuations < self.max_continuations
        if not can_continue:
            self._fresh_output = None
            return False
        prompt = self.message()
        if not prompt:
            self._fresh_output = None
            return False
        self.fresh_agent.history.clear()
        try:
            reply = await self.fresh_agent.arun(AgentInput(prompt=prompt))
        except VidbyteSdkError:
            # @intent fresh-agent-failure-leaves-current-answer
            # Fresh continuation is advisory; a model failure leaves the already produced answer in place.
            self._fresh_output = None
            return False
        self._fresh_output = reply.content.strip() or None
        return self._fresh_output is not None

    def continue_(self, messages: list[dict[str, Any]]) -> None:
        """Append the fresh agent's completed work to the main loop and record the continuation."""
        if self._fresh_output is None:
            return
        self.response.continued()
        messages.append({"role": "user", "content": self._fresh_output})
        self._fresh_output = None

    def message(self) -> str:
        """Build the fresh agent's clean-context input from the original request, state, and latest handoff."""
        handoff = self.run_state.handoff_writer.rendered
        if not self.run_state.rendered or not handoff:
            return ""
        return Prompts().get(Prompt.JEV_FRESH_CONTINUATION_PROMPT).format(
            request=self.run_state.request,
            run_state=self.run_state.rendered,
            handoff=handoff,
        )


__all__ = ["JevFreshContinuation"]
