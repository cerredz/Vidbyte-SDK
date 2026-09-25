"""FILE: vidbyte/agents/jev/preflight/clarification.py

PURPOSE: Implements JevClarificationAgent, the generative agent the preflight gate routes an unclear request to, which writes simple questions for the user to answer before the main agent runs.
ROLE IN CODEBASE: JevPreflight builds one instance when the CLARITY preset is enabled, and its clarity case calls clarify(); JevResponse returns the questions to the user and stops the run.
ARCHITECTURE NOTE: Jev only recognizes which clarity checks failed; writing questions is generation, so it belongs to a generative model (skills/asking-jev-questions/SKILL.md, strategy 16). The agent reuses the JevAgent's generative model, but its prompt is fixed, it has no tools, and it sees only the request and the failed checks.
COMMON MODIFICATION PATTERNS: Change what the agent writes in vidbyte/prompts/prompts/jev_clarification/system_prompt.md; change which checks it is told about in gaps().
KNOWN EDGE CASES: A generative failure or an empty reply returns None, so the gate fails open and the main agent runs. History is cleared before every call, so one user's earlier request never reaches a later clarification.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import json

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_CLARIFICATION_MAX_ITERATIONS,
    JEV_NOUL_YES_THRESHOLD,
    JEV_PREFLIGHT_REQUEST_FIELD,
)
from vidbyte.lib.dataclasses.jev import JevClarification, JevPresetResult
from vidbyte.lib.enums.jev import JevPreflightQuestionKey
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry
from vidbyte.prompts.catalog import Prompts

# The JSON field that lists the failed checks, named in the clarification agent's system prompt.
MISSING_FIELD = "missing"


class JevClarificationAgent(BaseAgent):
    """Generative agent that turns an unclear request into short questions the user can answer."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Reuses the JevAgent's generative model and key; the prompt and the empty tool list are fixed here.
        # @intent clarifier-can-only-ask
        # The owner configured one generative model, so the clarifier calls it, but no caller can give it
        # tools or another prompt: its only job is writing questions, never starting the user's work.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevClarificationAgent requires the JevAgentSettings of the agent it clarifies for.")
        super().__init__(
            name=f"{settings.name}-clarification",
            system_prompt=Prompts().get(Prompt.JEV_CLARIFICATION_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_CLARIFICATION_MAX_ITERATIONS),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

    async def clarify(self, request: str, result: JevPresetResult) -> JevClarification | None:
        """Return questions for the user about the clarity checks `result` failed, or None when none were written."""
        gaps = self.gaps(result)
        message = json.dumps({JEV_PREFLIGHT_REQUEST_FIELD: request, MISSING_FIELD: [JevPreflightRegistry.get(key).gap for key in gaps]})
        self.history.clear()
        try:
            reply = await self.arun(message)
        except VidbyteSdkError:
            # The gate fails open on a clarifier outage, exactly as it does on a Jev outage.
            return None
        questions = reply.content.strip()
        return JevClarification(questions=questions, gaps=gaps, usage=self.get_usage()) if questions else None

    @staticmethod
    def gaps(result: JevPresetResult) -> tuple[JevPreflightQuestionKey, ...]:
        """Return the clarity checks Jev answered no, weakest first, or the single weakest check when none fell below one half."""
        yes = result.yes()
        ranked = sorted(yes, key=yes.__getitem__)
        failed = tuple(key for key in ranked if yes[key] < JEV_NOUL_YES_THRESHOLD)
        return failed or tuple(ranked[:1])


__all__ = ["JevClarificationAgent"]
