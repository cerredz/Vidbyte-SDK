"""FILE: vidbyte/agents/jev/specialists.py

PURPOSE: Implements Jev specialist routing: one fixed Choice question, the probability threshold policy, the fail-open decision path, and isolated specialist execution.
ROLE IN CODEBASE: JevAgent builds one JevSpecialistRouter from its settings at construction and passes it to JevRuntime, which hands it the run after JevPreflightGate passes, with the general loop as a callable.
ARCHITECTURE NOTE: The validated JevSpecialist, JevSpecialistCatalog, and JevSpecialistRouting records live in vidbyte/lib/dataclasses/jev.py, their limits in vidbyte/lib/constants/jev.py, the fallback reasons in vidbyte/lib/enums/jev.py, and the question text in vidbyte/prompts/jev/. Every routing outcome is reported through JevResponse, so it appears on `JevAgent.response.routing` rather than in result metadata.
COMMON MODIFICATION PATTERNS: Change routing policy here and wording in the Markdown prompt assets (load skills/asking-jev-questions/SKILL.md first); keep JevRuntime limited to the call that delegates to this router.
KNOWN EDGE CASES: An empty catalog makes the router disabled, so JevRuntime runs the general loop with no Jev call; a decision failure or oversized routing input falls back to the general agent; a specialist execution failure is surfaced without replaying the task through the general agent.
RELATED DOCS: docs/design/jev-specialist-routing.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.jev import (
    JEV_PREFLIGHT_REQUEST_FIELD,
    JEV_SPECIALIST_MAX_ROUTING_CHARS,
    JEV_SPECIALIST_NO_MATCH_ID,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevOption,
    JevQuestion,
    JevSpecialist,
    JevSpecialistRouting,
)
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevQuestionType, JevSpecialistFallback
from vidbyte.lib.runners.decision import DecisionModelRunner

_JEV_SPECIALIST_QUESTION_NAME = "specialist"
_JEV_SPECIALIST_STRATEGY_NAME = "jev_specialist"


class JevSpecialistRouter:
    """Selects at most one registered specialist per task and runs it, or runs the general loop, and reports which through JevResponse."""

    def __init__(self, settings: JevAgentSettings, response: JevResponse) -> None:
        # Fixes the decision config and the validated catalog when JevAgent is built; nothing about routing is read at run time.
        self.decision = settings.decision
        self.catalog = settings.specialists
        self.response = response

    @property
    def enabled(self) -> bool:
        """Return True when the owner registered at least one specialist, so a run asks Jev to route."""
        return bool(self.catalog.specialists)

    async def run(self, message: str, *, usage_tracker: UsageTracker, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, general: Callable[[], Awaitable[AgentResult]]) -> AgentResult:
        """Route one task: run the selected specialist, or await `general` on no match, a weak match, or an unavailable decision."""
        # @intent route-before-task-model
        # Jev receives only the current prompt and configured descriptions; weak or unavailable decisions use the general loop before task tools execute.
        if self.routing_input_size(message) > JEV_SPECIALIST_MAX_ROUTING_CHARS:
            return await self._run_general(general, JevSpecialistFallback.INPUT_TOO_LARGE)
        try:
            decision = await DecisionModelRunner(self.decision).arun(self.decision_request(message))
            usage_tracker.record_call(decision)
            answer = decision.answer(_JEV_SPECIALIST_QUESTION_NAME)
        except Exception as exc:
            return await self._run_general(general, JevSpecialistFallback.DECISION_UNAVAILABLE, error_type=type(exc).__name__)
        if answer.question_type is not JevQuestionType.CHOICE or answer.choice == JEV_SPECIALIST_NO_MATCH_ID:
            return await self._run_general(general, JevSpecialistFallback.NO_MATCH)
        specialist = self.catalog.get(answer.choice)
        probability = answer.probabilities.get(answer.choice)
        if specialist is None or probability is None:
            return await self._run_general(general, JevSpecialistFallback.DECISION_UNAVAILABLE)
        if probability < self.catalog.match_threshold:
            return await self._run_general(general, JevSpecialistFallback.WEAK_MATCH, choice=specialist.id, probability=probability)
        return await self._run_specialist(message, specialist, context=context, metadata=metadata, options=options, probability=probability)

    def decision_request(self, message: str) -> JevDecisionRequest:
        """Build the one fixed Choice question from the prompt and the registered descriptions."""
        # @intent fixed-specialist-choice-contract
        # Stable IDs and an explicit no-match option map each response to one validated catalog entry or the general-agent fallback.
        options = tuple(JevOption(specialist.id, specialist.description) for specialist in self.catalog.specialists)
        options = (*options, JevOption(JEV_SPECIALIST_NO_MATCH_ID, JevPrompts.get(JevPrompt.SPECIALIST_NO_MATCH)))
        question = JevQuestion(name=_JEV_SPECIALIST_QUESTION_NAME, question_type=JevQuestionType.CHOICE, instructions=JevPrompts.get(JevPrompt.SPECIALIST_QUESTION), options=options)
        return JevDecisionRequest(state={JEV_PREFLIGHT_REQUEST_FIELD: message}, questions=(question,))

    def routing_input_size(self, message: str) -> int:
        """Return the combined prompt, catalog, and fixed question length sent to TypeSafe."""
        fixed_chars = len(JEV_PREFLIGHT_REQUEST_FIELD) + len(JevPrompts.get(JevPrompt.SPECIALIST_QUESTION)) + len(JEV_SPECIALIST_NO_MATCH_ID) + len(JevPrompts.get(JevPrompt.SPECIALIST_NO_MATCH))
        return len(message) + self.catalog.metadata_chars() + fixed_chars

    async def _run_general(self, general: Callable[[], Awaitable[AgentResult]], fallback: JevSpecialistFallback, *, error_type: str | None = None, choice: str | None = None, probability: float | None = None) -> AgentResult:
        # Records why the general agent handles the task, then runs the unchanged general loop.
        self.response.routed(JevSpecialistRouting(threshold=self.catalog.match_threshold, fallback=fallback, choice=choice, probability=probability, error_type=error_type))
        return await general()

    async def _run_specialist(self, message: str, specialist: JevSpecialist, *, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, probability: float) -> AgentResult:
        # Forks and runs the selected template with the user-visible context, then releases its run resources.
        # @intent isolate-selected-agent-run
        # A fresh fork keeps histories, tools, and MCP resources from one routed task out of later runs.
        child = specialist.agent.fork()
        try:
            child_input = AgentInput(prompt=message, metadata={**dict(metadata or {}), **dict(context.metadata)}, context_items=tuple(context.context_items))
            child_context = BaseContext(
                file_paths=tuple(context.file_paths),
                run_metadata=context.run_metadata,
                tool_calls=tuple(context.tool_calls),
                responses=tuple(context.responses),
                budget=context.budget,
                artifacts=tuple(context.artifacts),
                memory=context.memory,
                permissions=context.permissions,
                metadata=context.metadata,
                context_items=tuple(context.context_items),
            )
            child_history = cast(Sequence[AgentMessage], tuple(context.history))
            reply: AgentMessage = await child.generate_reply(child_input, context=child_context, history=child_history, **dict(options or {}))
            self.response.routed(JevSpecialistRouting(threshold=self.catalog.match_threshold, specialist=specialist.id, choice=specialist.id, probability=probability, usage=child.get_usage()))
            return AgentResult(
                output=reply.content,
                strategy_name=_JEV_SPECIALIST_STRATEGY_NAME,
                metadata={
                    "provider": child.runner_config.provider,
                    "model_name": child.runner_config.model_name,
                    "tool_calls": reply.metadata.get("tool_calls", ()),
                    "tool_call_states": reply.metadata.get("tool_call_states", ()),
                },
                structured=reply.structured,
            )
        finally:
            await child.close_mcp_servers()


__all__ = ["JevSpecialistRouter"]
