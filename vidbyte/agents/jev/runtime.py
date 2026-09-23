"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own reply, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: A fixed Jev specialist choice can select one isolated BaseAgent run before this runtime delegates to the general linear loop.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: An empty specialist catalog performs no Jev decision call and therefore needs no TypeSafe credential. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.jev.specialists import JEV_SPECIALIST_MAX_ROUTING_CHARS, JEV_SPECIALIST_NO_MATCH_ID, JevSpecialist
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext


_JEV_SPECIALIST_QUESTION_NAME = "specialist"
_JEV_SPECIALIST_QUESTION_INSTRUCTIONS = (
    "Which registered specialist best fits this task? Choose exactly one option. "
    "Compare the request with every specialist description and select the single strongest direct fit, "
    "regardless of option order. Choose no_suitable_agent when no specialist clearly covers the request, "
    "when the request falls outside every described scope, or when the best fit is too weak or ambiguous. "
    "Do not invent capabilities that are not stated in a description."
)
_JEV_SPECIALIST_NO_MATCH_DESCRIPTION = "No registered specialist clearly fits this request; use the general agent."
_JEV_SPECIALIST_FALLBACK_NO_MATCH = "no_suitable_agent"
_JEV_SPECIALIST_FALLBACK_WEAK = "below_probability_threshold"
_JEV_SPECIALIST_FALLBACK_DECISION_ERROR = "decision_unavailable"
_JEV_SPECIALIST_FALLBACK_INPUT_LIMIT = "routing_input_too_large"


class JevRuntime(AgentRuntime):
    """Linear runtime that selects an optional specialist once before running the task."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates all current behavior to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        self.jev_settings = jev_settings
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Selects and runs at most one specialist, returning to the regular loop on a weak or unavailable decision.
        # @intent route-before-task-model
        # Jev receives only the current prompt and configured descriptions; weak or unavailable decisions use the general loop before task tools execute.
        if not self.jev_settings.agents:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        if self._routing_input_size(message) > JEV_SPECIALIST_MAX_ROUTING_CHARS:
            return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context, reason=_JEV_SPECIALIST_FALLBACK_INPUT_LIMIT)
        try:
            response = await DecisionModelRunner(self.jev_settings.decision).arun(self._decision_request(message))
            self.usage_tracker.record_call(response)
            answer = response.answer(_JEV_SPECIALIST_QUESTION_NAME)
        except Exception as exc:
            return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context, reason=_JEV_SPECIALIST_FALLBACK_DECISION_ERROR, error_type=type(exc).__name__)
        if answer.question_type is not JevQuestionType.CHOICE or answer.choice == JEV_SPECIALIST_NO_MATCH_ID:
            return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context, reason=_JEV_SPECIALIST_FALLBACK_NO_MATCH)
        specialist = self._specialist_for(answer.choice)
        probability = answer.probabilities.get(answer.choice)
        if specialist is None or probability is None:
            return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context, reason=_JEV_SPECIALIST_FALLBACK_DECISION_ERROR)
        if probability < self.jev_settings.specialist_match_threshold:
            return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context, reason=_JEV_SPECIALIST_FALLBACK_WEAK, selected_id=specialist.id, probability=probability)
        return await self._run_specialist(message, specialist, context=context, metadata=metadata, options=options, probability=probability)

    def _decision_request(self, message: str) -> JevDecisionRequest:
        # Builds one fixed Choice question from the prompt and the registered descriptions.
        # @intent fixed-specialist-choice-contract
        # Stable IDs and an explicit no-match option map each response to one validated catalog entry or the general-agent fallback.
        options = tuple(JevOption(agent.id, agent.description) for agent in self.jev_settings.agents)
        options = (*options, JevOption(JEV_SPECIALIST_NO_MATCH_ID, _JEV_SPECIALIST_NO_MATCH_DESCRIPTION))
        question = JevQuestion(name=_JEV_SPECIALIST_QUESTION_NAME, question_type=JevQuestionType.CHOICE, instructions=_JEV_SPECIALIST_QUESTION_INSTRUCTIONS, options=options)
        return JevDecisionRequest(state=message, questions=(question,))

    def _routing_input_size(self, message: str) -> int:
        # Bounds the combined prompt and catalog before sending a classification request to TypeSafe.
        fixed_chars = len(_JEV_SPECIALIST_QUESTION_INSTRUCTIONS) + len(JEV_SPECIALIST_NO_MATCH_ID) + len(_JEV_SPECIALIST_NO_MATCH_DESCRIPTION)
        catalog_chars = sum(len(agent.id) + len(agent.description) for agent in self.jev_settings.agents)
        return len(message) + catalog_chars + fixed_chars

    def _specialist_for(self, specialist_id: str) -> JevSpecialist | None:
        # Resolves a validated choice ID to its registered immutable template.
        return next((agent for agent in self.jev_settings.agents if agent.id == specialist_id), None)

    async def _run_general(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None, reason: str, error_type: str | None = None, selected_id: str | None = None, probability: float | None = None) -> AgentResult:
        # Runs the unchanged general loop and records only bounded, non-sensitive routing outcome metadata.
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
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
                        "threshold": self.jev_settings.specialist_match_threshold,
                    },
                    "specialist_usage": child.get_usage(),
                },
                structured=reply.structured,
            )
        finally:
            await child.close_mcp_servers()


__all__ = ["JevRuntime"]
