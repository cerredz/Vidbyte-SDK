"""FILE: vidbyte/agents/jev/brief/writer.py

PURPOSE: Implements JevRunBriefWriter, the separate, tool-free agent that reads the previous run brief and the run's newest numbered events and returns the complete updated brief as a structured JevRunBriefPayload.
ROLE IN CODEBASE: JevRunBriefKeeper builds one writer and calls `write` on each refresh attempt; JevRunBriefVerifier then keeps only what the writer's quotes prove.
ARCHITECTURE NOTE: The writer is its own BaseAgent with its own fixed prompt, model, history, and usage, and it never sees or touches the main agent's messages, tools, or context window. It can run a cheaper model than the main agent: JevRunBriefSettings chooses its provider, model, and key, falling back to the main agent's.
COMMON MODIFICATION PATTERNS: Change what the writer is told in vidbyte/prompts/prompts/jev_run_brief/ and what it must return in JevRunBriefPayload; keep verification out of this module.
KNOWN EDGE CASES: History is cleared before every call, so one refresh never sees an earlier one's conversation; the previous brief arrives only as verified JSON in the prompt. A writer outage or a reply that never matches the schema returns None, and the keeper keeps the previous brief.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.brief.events import JevRunBriefEvents
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_EVENT_ID_PREFIX,
    JEV_RUN_BRIEF_NONE,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefPayload,
    JevRunBriefWindow,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts


class JevRunBriefWriter(BaseAgent):
    """Separate, tool-free agent that turns the previous run brief and the run's newest events into the next brief."""

    def __init__(self, settings: JevAgentSettings, brief: JevRunBriefSettings) -> None:
        # Builds the writer from its own prompt and limits, on the brief's model when one is set and otherwise the main agent's.
        # @intent another-provider-brings-its-own-key
        # The main agent's key belongs to the main agent's provider, so a writer on another provider uses its own key
        # or that provider's environment variable, never a key issued for a different vendor.
        own_provider = brief.provider is not None
        super().__init__(
            name=f"{settings.name}-run-brief",
            system_prompt=Prompts().get(Prompt.JEV_RUN_BRIEF_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=brief.max_iterations, max_tokens=brief.max_tokens),
            api_key=brief.api_key if own_provider else (brief.api_key or settings.api_key),
            provider=brief.provider if own_provider else settings.provider,
            model_name=brief.model_name or settings.model_name,
            temperature=brief.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=JevRunBriefPayload,
        )
        self._update_prompt = Prompts().get(Prompt.JEV_RUN_BRIEF_UPDATE_PROMPT)

    async def write(self, request: str, previous: JevRunBrief | None, window: JevRunBriefWindow) -> JevRunBriefPayload | None:
        """Return the complete updated brief the writer wrote for these events, or None when it wrote none."""
        self.history.clear()
        try:
            reply = await self.arun(AgentInput(prompt=self.prompt(request, previous, window)))
        except VidbyteSdkError:
            # A writer outage, or a reply that never matched the schema, keeps the previous brief in place.
            return None
        return reply.structured if isinstance(reply.structured, JevRunBriefPayload) else None

    def prompt(self, request: str, previous: JevRunBrief | None, window: JevRunBriefWindow) -> str:
        """Return the update message: the clipped request, the previous brief or none, and the window of new events."""
        return self._update_prompt.format(
            request=JevRunBriefEvents.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS),
            previous_brief=JEV_RUN_BRIEF_NONE if previous is None else previous.render(),
            first_event=f"{JEV_EVENT_ID_PREFIX}{window.first_event}",
            last_event=f"{JEV_EVENT_ID_PREFIX}{window.last_event}",
            events=window.text,
        )


__all__ = ["JevRunBriefWriter"]
