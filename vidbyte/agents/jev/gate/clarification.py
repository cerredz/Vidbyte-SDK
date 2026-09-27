"""FILE: vidbyte/agents/jev/gate/clarification.py

PURPOSE: Implements JevClarificationAgent, the generative writer the preflight gate uses to return structured questions when the current request is unclear.
ROLE IN CODEBASE: JevPreflightGate builds one instance when the CLARITY preset is enabled, and its clarity case calls clarify(); JevResponse returns the questions to the user and stops the run.
ARCHITECTURE NOTE: Jev only recognizes which clarity checks failed; writing questions is generation, so it belongs to a generative model (skills/asking-jev-questions/SKILL.md, strategy 16). The gate builds this writer from the first configured profile because it runs before profile selection; the prompt is fixed, it has no tools, and its reply is held to JevClarificationPayload.
COMMON MODIFICATION PATTERNS: Change what the agent writes in vidbyte/prompts/prompts/jev_clarification/system_prompt.md; change the reply shape in JevClarificationPayload; change which checks it is told about in gaps().
KNOWN EDGE CASES: A generative failure or a reply that never matches the schema returns None, so the gate fails open and the main agent runs. History is cleared before every call, so one user's earlier request never reaches a later clarification.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.constants.jev import (
    JEV_CLARIFICATION_MAX_ITERATIONS,
    JEV_CLARIFICATION_MAX_TOKENS,
    JEV_NOUL_YES_THRESHOLD,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevClarification,
    JevClarificationPayload,
    JevPresetResult,
)
from vidbyte.lib.enums.jev import JevPreflightQuestionKey
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry
from vidbyte.prompts.catalog import Prompts

# The title and source of the context item that lists the failed checks, named in the system prompt.
MISSING_TITLE = "Missing from the request"
MISSING_SOURCE = "jev_preflight"


class JevClarificationAgent(BaseAgent):
    """Generative agent that turns an unclear request into clarifying questions, each with a few recommended answers."""

    def __init__(self, source_agent: BaseAgent) -> None:
        # Reuses the first profile's generative model and key before profile selection; its own prompt and tools stay fixed.
        # @intent clarifier-can-only-ask
        # The owner configured one generative model, so the clarifier calls it, but no caller can give it
        # tools or another prompt: its only job is writing questions, never starting the user's work.
        super().__init__(
            name=f"{source_agent.name}-clarification",
            system_prompt=Prompts().get(Prompt.JEV_CLARIFICATION_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_CLARIFICATION_MAX_ITERATIONS, max_tokens=JEV_CLARIFICATION_MAX_TOKENS),
            api_key=source_agent.runner_config.api_key,
            provider=source_agent.runner_config.provider,
            model_name=source_agent.runner_config.model_name,
            temperature=source_agent.runner_config.temperature,
            timeout_seconds=source_agent.runner_config.timeout_seconds,
            output_schema=JevClarificationPayload,
        )

    async def clarify(self, request: str, result: JevPresetResult) -> JevClarification | None:
        """Return clarifying questions about the checks `result` failed, or None when the agent produced none."""
        gaps = self.gaps(result)
        self.history.clear()
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=self.context(gaps)))
        except VidbyteSdkError:
            # The gate fails open on a clarifier outage or a reply that never matched the schema, exactly as it does on a Jev outage.
            return None
        if not isinstance(reply.structured, JevClarificationPayload):
            return None
        return JevClarification.from_payload(reply.structured, gaps, usage=self.get_usage())

    @staticmethod
    def context(gaps: tuple[JevPreflightQuestionKey, ...]) -> ContextManager:
        """Build the per-call context: one text item listing what the request is missing, weakest check first."""
        missing = "\n".join(f"- {JevPreflightRegistry.get(key).gap}" for key in gaps)
        return ContextManager([TextContextItem(title=MISSING_TITLE, content=missing, source=MISSING_SOURCE)])

    @staticmethod
    def gaps(result: JevPresetResult) -> tuple[JevPreflightQuestionKey, ...]:
        """Return the clarity checks Jev answered no, weakest first, or the single weakest check when none fell below one half."""
        yes = result.yes()
        ranked = sorted(yes, key=yes.__getitem__)
        failed = tuple(key for key in ranked if yes[key] < JEV_NOUL_YES_THRESHOLD)
        return failed or tuple(ranked[:1])


__all__ = ["JevClarificationAgent"]
