"""FILE: vidbyte/agents/jev/specialists.py

PURPOSE: Implements Jev specialist routing: one fixed Choice question, the probability threshold policy, the fail-open decision path, and isolated specialist execution.
ROLE IN CODEBASE: JevRuntime builds a JevSpecialistRouter when JevAgentSettings.agents is non-empty and hands it the whole run, passing the general loop as a callable.
ARCHITECTURE NOTE: The validated JevSpecialist and JevSpecialistCatalog records live in vidbyte/lib/dataclasses/jev.py, their limits in vidbyte/lib/constants/jev.py, and the question text in vidbyte/prompts/jev/.
COMMON MODIFICATION PATTERNS: Change routing policy here and wording in the Markdown prompt assets; keep JevRuntime limited to the call that delegates to this router.
KNOWN EDGE CASES: A decision failure or oversized routing input falls back to the general agent; a specialist execution failure is surfaced without replaying the task through the general agent.
RELATED DOCS: docs/design/jev-specialist-routing.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from vidbyte.agents.jev.prompts import JevPrompt, JevPrompts
from vidbyte.agents.pricing import UsageTracker
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.jev import (
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
    JevSpecialistCatalog,
)
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.runners.decision import DecisionModelRunner

_JEV_SPECIALIST_QUESTION_NAME = "specialist"
_JEV_SPECIALIST_FALLBACK_NO_MATCH = "no_suitable_agent"
_JEV_SPECIALIST_FALLBACK_WEAK = "below_probability_threshold"
_JEV_SPECIALIST_FALLBACK_DECISION_ERROR = "decision_unavailable"
_JEV_SPECIALIST_FALLBACK_INPUT_LIMIT = "routing_input_too_large"


class JevSpecialistRouter:
    """Selects at most one registered specialist per task and runs it, or runs the general loop."""

    def __init__(self, decision: DecisionModelConfig, catalog: JevSpecialistCatalog, usage_tracker: UsageTracker) -> None:
        # Retains the validated decision config, catalog, and the agent-owned usage tracker for the decision call.
        self._decision = decision
        self._catalog = catalog
        self._usage_tracker = usage_tracker

    async def run(self, message: str, *, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, general: Callable[[], Awaitable[AgentResult]]) -> AgentResult:
        """Route one task: run the selected specialist, or await `general` on no match, a weak match, or an unavailable decision."""
        # @intent route-before-task-model
        # Jev receives only the current prompt and configured descriptions; weak or unavailable decisions use the general loop before task tools execute.
        if self.routing_input_size(message) > JEV_SPECIALIST_MAX_ROUTING_CHARS:
            return await self._run_general(general, reason=_JEV_SPECIALIST_FALLBACK_INPUT_LIMIT)
        try:
            response = await DecisionModelRunner(self._decision).arun(self.decision_request(message))
            self._usage_tracker.record_call(response)
            answer = response.answer(_JEV_SPECIALIST_QUESTION_NAME)
        except Exception as exc:
            return await self._run_general(general, reason=_JEV_SPECIALIST_FALLBACK_DECISION_ERROR, error_type=type(exc).__name__)
        if answer.question_type is not JevQuestionType.CHOICE or answer.choice == JEV_SPECIALIST_NO_MATCH_ID:
            return await self._run_general(general, reason=_JEV_SPECIALIST_FALLBACK_NO_MATCH)
        specialist = self._catalog.get(answer.choice)
        probability = answer.probabilities.get(answer.choice)
        if specialist is None or probability is None:
            return await self._run_general(general, reason=_JEV_SPECIALIST_FALLBACK_DECISION_ERROR)
        if probability < self._catalog.match_threshold:
            return await self._run_general(general, reason=_JEV_SPECIALIST_FALLBACK_WEAK, selected_id=specialist.id, probability=probability)
        return await self._run_specialist(message, specialist, context=context, metadata=metadata, options=options, probability=probability)

    def decision_request(self, message: str) -> JevDecisionRequest:
        """Build the one fixed Choice question from the prompt and the registered descriptions."""
        # @intent fixed-specialist-choice-contract
        # Stable IDs and an explicit no-match option map each response to one validated catalog entry or the general-agent fallback.
        options = tuple(JevOption(specialist.id, specialist.description) for specialist in self._catalog.specialists)
        options = (*options, JevOption(JEV_SPECIALIST_NO_MATCH_ID, JevPrompts.get(JevPrompt.SPECIALIST_NO_MATCH)))
        question = JevQuestion(name=_JEV_SPECIALIST_QUESTION_NAME, question_type=JevQuestionType.CHOICE, instructions=JevPrompts.get(JevPrompt.SPECIALIST_QUESTION), options=options)
        return JevDecisionRequest(state=message, questions=(question,))

    def routing_input_size(self, message: str) -> int:
        """Return the combined prompt, catalog, and fixed question length sent to TypeSafe."""
        fixed_chars = len(JevPrompts.get(JevPrompt.SPECIALIST_QUESTION)) + len(JEV_SPECIALIST_NO_MATCH_ID) + len(JevPrompts.get(JevPrompt.SPECIALIST_NO_MATCH))
        return len(message) + self._catalog.metadata_chars() + fixed_chars

    async def _run_general(self, general: Callable[[], Awaitable[AgentResult]], *, reason: str, error_type: str | None = None, selected_id: str | None = None, probability: float | None = None) -> AgentResult:
        # Runs the unchanged general loop and records only bounded, non-sensitive routing outcome metadata.
        result = await general()
        routing: dict[str, str | float] = {"outcome": "general", "reason": reason}
        if error_type is not None:
            routing["error_type"] = error_type
        if selected_id is not None:
            routing["selected_id"] = selected_id
        if probability is not None:
            routing["selected_probability"] = probability
        return replace(result, metadata={**dict(result.metadata), "jev_specialist_routing": routing})

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
            return AgentResult(
                output=reply.content,
                strategy_name="jev_specialist",
                metadata={
                    "provider": child.runner_config.provider,
                    "model_name": child.runner_config.model_name,
                    "tool_calls": reply.metadata.get("tool_calls", ()),
                    "tool_call_states": reply.metadata.get("tool_call_states", ()),
                    "jev_specialist_routing": {
                        "outcome": "specialist",
                        "selected_id": specialist.id,
                        "selected_probability": probability,
                        "threshold": self._catalog.match_threshold,
                    },
                    "specialist_usage": child.get_usage(),
                },
                structured=reply.structured,
            )
        finally:
            await child.close_mcp_servers()


__all__ = ["JevSpecialistRouter"]
