"""FILE: vidbyte/agents/jev/compute/clone.py

PURPOSE: Implements the CLONE dynamic-compute option: identical copies of the main agent attempt the remaining work concurrently from the same verified brief.
ROLE IN CODEBASE: JevComputeController calls JevCloneAgent.attempt once per run when Jev selects CLONE, then hands the replies back to the main loop.
ARCHITECTURE NOTE: A clone is a plain BaseAgent built from the main agent's JevAgentSettings with an empty history, so its usage reaches the run's ledger through BaseAgent.generate_reply.
COMMON MODIFICATION PATTERNS: Keep clone and results text in vidbyte/prompts/prompts/jev_clone/; keep launch policy in the controller.
KNOWN EDGE CASES: A clone that raises VidbyteSdkError or returns an empty reply is dropped; the others still count.
RELATED DOCS: docs/design/jev-compute-clone.md.
TESTS: tests/test_jev_compute_clone.py.
"""

from __future__ import annotations

import asyncio

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import JevRunBrief
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts


class JevCloneAgent(BaseAgent):
    """One copy of the main JevAgent that attempts the remaining work from the verified run brief."""

    def __init__(self, settings: JevAgentSettings, index: int) -> None:
        super().__init__(
            name=f"{settings.name}-clone-{index}",
            system_prompt=settings.system_prompt,
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            tools=settings.tools,
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
        )

    @classmethod
    async def attempt(cls, settings: JevAgentSettings, count: int, request: str, brief: JevRunBrief) -> tuple[str, ...]:
        """Run `count` clones concurrently on the same request and brief and return every non-empty reply."""
        prompt = Prompts().get(Prompt.JEV_CLONE_PROMPT).format(request=request, brief=brief.render())
        replies = await asyncio.gather(*(cls(settings, index)._reply(prompt) for index in range(1, count + 1)))
        return tuple(reply for reply in replies if reply)

    @staticmethod
    def results(outputs: tuple[str, ...]) -> str:
        """Render the clones' replies as the one message the main agent receives."""
        attempts = "\n\n".join(f"# Attempt {number}\n\n{output}" for number, output in enumerate(outputs, start=1))
        return Prompts().get(Prompt.JEV_CLONE_RESULTS_PROMPT).format(attempts=attempts)

    async def _reply(self, prompt: str) -> str:
        # @intent one-failed-clone-does-not-cancel-the-others
        # Clones are independent attempts, so a provider failure in one leaves the rest of the launch intact.
        try:
            reply = await self.arun(AgentInput(prompt=prompt))
        except VidbyteSdkError:
            return ""
        return reply.content.strip()


__all__ = ["JevCloneAgent"]
