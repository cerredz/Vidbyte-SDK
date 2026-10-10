"""FILE: vidbyte/agents/jev/compute/swarm.py

PURPOSE: Implements the helpers of the SWARM dynamic-compute option: one fresh copy of the main agent per plan assignment, all run concurrently, and the results text the main agent receives.
ROLE IN CODEBASE: JevSwarmTool calls JevSwarmAgent.attempt once a plan passes its checks, records the outputs, and returns JevSwarmAgent.results as the tool result.
ARCHITECTURE NOTE: A helper is a plain BaseAgent built from the main agent's JevAgentSettings with an empty history, like a CLONE copy, so its usage reaches the run's ledger through BaseAgent.generate_reply. It receives its assignment as the prompt and the request and verified brief as context items.
COMMON MODIFICATION PATTERNS: Keep assignment and results text in vidbyte/prompts/prompts/jev_swarm/; keep plan reading and checks in swarm_plan.py and launch policy in swarm_tool.py.
KNOWN EDGE CASES: A helper that raises VidbyteSdkError or returns an empty reply is marked failed while the others still return. Each reply is recorded in full and clipped only in the text the main agent reads.
RELATED DOCS: docs/design/jev-compute-swarm.md.
TESTS: tests/test_jev_compute_swarm.py.
"""

from __future__ import annotations

import asyncio

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.context.primitives import ContextItem, TextContextItem
from vidbyte.lib.constants.jev import (
    JEV_SWARM_BRIEF_CONTEXT_TITLE,
    JEV_SWARM_OUTPUT_MAX_CHARS,
    JEV_SWARM_REQUEST_CONTEXT_TITLE,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevSwarmAssignment,
    JevSwarmOutput,
    JevSwarmPlan,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts


class JevSwarmAgent(BaseAgent):
    """One helper that carries out a single SWARM assignment as a fresh copy of the main agent."""

    def __init__(self, settings: JevAgentSettings, assignment: JevSwarmAssignment) -> None:
        # @intent helpers-inherit-main-agent-permissions
        # A helper must not gain tools or privileges the caller denied to the main agent, and it never receives launch_swarm.
        super().__init__(
            name=f"{settings.name}-swarm-{assignment.id}",
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
        self.assignment = assignment

    @classmethod
    async def attempt(cls, settings: JevAgentSettings, request: str, brief: JevRunBrief, plan: JevSwarmPlan) -> tuple[JevSwarmOutput, ...]:
        """Run one helper per assignment concurrently and return every output in plan order."""
        context = (
            TextContextItem(title=JEV_SWARM_REQUEST_CONTEXT_TITLE, content=request),
            TextContextItem(title=JEV_SWARM_BRIEF_CONTEXT_TITLE, content=brief.render()),
        )
        outputs = await asyncio.gather(*(cls(settings, assignment)._output(plan.conventions, context) for assignment in plan.assignments))
        return tuple(outputs)

    @staticmethod
    def results(outputs: tuple[JevSwarmOutput, ...]) -> str:
        """Render every helper's output, clipped, as the tool result the main agent reads."""
        sections = "\n\n".join(JevSwarmAgent._section(output) for output in outputs)
        return Prompts().get(Prompt.JEV_SWARM_RESULTS_PROMPT).format(results=sections)

    @staticmethod
    def _section(output: JevSwarmOutput) -> str:
        # Labels each result with its assignment so the main agent can match, check, and repair it.
        if not output.completed:
            return f"# {output.id}: {output.name} (failed)"
        return f"# {output.id}: {output.name} (completed)\n\n{JevComputeStates.clip(output.content, JEV_SWARM_OUTPUT_MAX_CHARS)}"

    async def _output(self, conventions: str, context: tuple[ContextItem, ...]) -> JevSwarmOutput:
        # @intent one-failed-helper-does-not-cancel-the-others
        # Assignments are independent units, so a provider failure in one helper is reported as that unit failing.
        assignment = self.assignment
        prompt = Prompts().get(Prompt.JEV_SWARM_ASSIGNMENT_PROMPT).format(
            name=assignment.name,
            objective=assignment.objective,
            inputs=assignment.inputs,
            deliverable=assignment.deliverable,
            boundaries=assignment.boundaries,
            verification=assignment.verification,
            conventions=conventions,
        )
        try:
            reply = await self.arun(AgentInput(prompt=prompt, context_items=context))
        except VidbyteSdkError:
            content = ""
        else:
            content = reply.content.strip()
        return JevSwarmOutput(id=assignment.id, name=assignment.name, content=content, completed=bool(content))


__all__ = ["JevSwarmAgent"]
