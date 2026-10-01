"""FILE: vidbyte/agents/jev/gate/refinement.py

PURPOSE: Implements JevRefinementAgent, the generative agent the preflight gate routes a clear request to when the REFINE preset is enabled; it returns an improved prompt, written from the request and Jev's answer to every clarity check, that the main agent reads instead of the user's message.
ROLE IN CODEBASE: JevPreflightGate builds one instance when REFINE is enabled, and its passing-clarity case calls refine(); the gate exposes the result as `prompt`, which JevRuntime hands to the specialist, the tool selector, and the main loop, and JevResponse records it as `JevAgent.response.refinement`.
ARCHITECTURE NOTE: Jev only recognizes how clear each part of the request is; rewriting is generation, so it belongs to a generative model, and what it may change lives in its system prompt (vidbyte/prompts/prompts/jev_refinement/system_prompt.md). The agent reuses the JevAgent's generative model and key, but its prompt, limits, schema, and tools are fixed here. It owns one ContextManager (`window`) that the runtime renders on every iteration, and its four deep chain-of-thought tools write their notes into that same window. It is not a JevPreflight (vidbyte/agents/jev/preflight.py), whose contract returns a tool catalog.
COMMON MODIFICATION PATTERNS: Change what the agent may improve in the system prompt; change the reply shape in JevRefinementPayload; change which reasoning tools it has in reasoning_tools(); change how each check is shown to it in signal().
KNOWN EDGE CASES: A generative failure, a reply that never matches the schema, or a blank prompt returns None, so the gate keeps the user's message (fail open). History and the window's notes are cleared before every call, so one request's notes never reach a later refinement.
RELATED DOCS: docs/design/jev-preflight-refine.md, docs/design/jev-preflight-clarity.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.constants.jev import (
    JEV_NOUL_YES_THRESHOLD,
    JEV_REFINEMENT_CLEAR_THRESHOLD,
    JEV_REFINEMENT_MAX_ITERATIONS,
    JEV_REFINEMENT_MAX_TOKENS,
)
from vidbyte.lib.dataclasses.agents import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.jev import (
    JevPresetResult,
    JevRefinement,
    JevRefinementPayload,
)
from vidbyte.lib.enums.jev import JevPreflightQuestionKey
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev import JevPreflightRegistry
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.cot_events import (
    AssumptionCheckTool,
    BacktrackTool,
    DecisionTool,
    UncertaintyTool,
)

# The title and source of the context item that reports every clarity check, named in the system prompt.
SIGNAL_TITLE = "Clarity of the request"
SIGNAL_SOURCE = "jev_preflight"
# The label each check carries, by Jev's P(yes); the system prompt names all three.
MISSING_LABEL = "likely missing"
UNCERTAIN_LABEL = "uncertain"
CLEAR_LABEL = "clear"


class JevRefinementAgent(BaseAgent):
    """Generative agent that rewrites a clear request into a clearer prompt without changing what it asks for."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Reuses the JevAgent's generative model and key; the prompt, limits, schema, tools, and window are fixed here.
        # @intent refiner-can-only-rewrite
        # The owner configured one generative model, so the refiner calls it, but no caller can give it other
        # tools or another prompt: its only job is rewriting the request, never starting the user's work.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("JevRefinementAgent requires the JevAgentSettings of the agent it refines for.")
        window = ContextManager()
        super().__init__(
            name=f"{settings.name}-refinement",
            system_prompt=Prompts().get(Prompt.JEV_REFINEMENT_SYSTEM_PROMPT),
            tools=self.reasoning_tools(window),
            context_manager=window,
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_REFINEMENT_MAX_ITERATIONS, max_tokens=JEV_REFINEMENT_MAX_TOKENS),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=JevRefinementPayload,
        )
        self.window = window

    async def refine(self, request: str, result: JevPresetResult) -> JevRefinement | None:
        """Return the improved prompt for a request the clarity preset passed, or None when the agent produced none."""
        self.reset()
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=self.context(result)))
        except VidbyteSdkError:
            # The gate fails open on a refiner outage or a reply that never matched the schema, exactly as it does on a Jev outage.
            return None
        return self.accept(reply, request)

    def reset(self) -> None:
        """Forget the previous call: its conversation and every note its reasoning tools wrote into the window."""
        self.history.clear()
        self.window.clear_registry()

    def accept(self, reply: AgentMessage, request: str) -> JevRefinement | None:
        """Turn the agent's reply into a refinement record, or None when it holds no usable prompt."""
        payload = reply.structured
        if not isinstance(payload, JevRefinementPayload) or not payload.prompt.strip():
            return None
        return JevRefinement.from_payload(payload, request, usage=self.get_usage())

    @staticmethod
    def reasoning_tools(window: ContextManager) -> tuple[BaseTool, ...]:
        """Return the four deep chain-of-thought tools, each writing its notes into the agent's own window."""
        # @intent reasoning-notes-share-the-rendered-window
        # The runtime renders the agent's context_manager on every iteration, so binding the tools to that
        # same manager is what lets the agent read its own assumption, decision, and backtrack notes next step.
        return (AssumptionCheckTool(window), DecisionTool(window), UncertaintyTool(window), BacktrackTool(window))

    @staticmethod
    def context(result: JevPresetResult) -> ContextManager:
        """Build the per-call context: one text item reporting every clarity check, weakest first."""
        yes = result.yes()
        lines = "\n".join(JevRefinementAgent.signal(key, yes[key]) for key in sorted(yes, key=yes.__getitem__))
        return ContextManager([TextContextItem(title=SIGNAL_TITLE, content=lines, source=SIGNAL_SOURCE)])

    @staticmethod
    def signal(key: JevPreflightQuestionKey, yes: float) -> str:
        """Render one check as its label, Jev's P(yes), its question, and, unless it is clear, the gap it may leave."""
        question = JevPreflightRegistry.get(key)
        if yes >= JEV_REFINEMENT_CLEAR_THRESHOLD:
            return f"- {CLEAR_LABEL} ({yes:.0%}): {question.instructions.question}"
        label = MISSING_LABEL if yes < JEV_NOUL_YES_THRESHOLD else UNCERTAIN_LABEL
        return f"- {label} ({yes:.0%}): {question.instructions.question} If not: {question.gap}"


__all__ = ["JevRefinementAgent"]
