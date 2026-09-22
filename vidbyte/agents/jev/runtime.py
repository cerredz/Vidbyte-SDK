"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Executes JevAgent's fixed preflight policies before its inherited generative agent loop.
ROLE IN CODEBASE: JevAgent selects this runtime; it owns preset request assembly, scoring, clarification short-circuiting, and response metadata.
ARCHITECTURE NOTE: All enabled preset questions share one Jev request, while BaseAgent continues to own generative runners, tools, tracing, and usage.
COMMON MODIFICATION PATTERNS: Resolve new named presets here and translate their typed results into fixed runtime actions.
KNOWN EDGE CASES: Disabled and unavailable preflights continue normally; unclear requests must not invoke the generative runner.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_agent.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.jev.presets import (
    JevPreflightDefinition,
    JevPreflightPreset,
    JevPreflightRegistry,
)
from vidbyte.agents.jev.response import JevPresetResult, JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext

_PREFLIGHT_CONTEXT = (
    "You are evaluating whether a user request is clear enough for an autonomous agent to begin substantive work without first asking a clarifying question. "
    "Only count missing or ambiguous information when it could materially change what the agent should do or produce; minor details that can be safely inferred should not reduce clarity. "
    "Treat a dimension that is irrelevant to the request as satisfied. "
    "Evaluate every question independently using only the request below."
)


class JevRuntime(AgentRuntime):
    """Run configured Jev preflights before entering the inherited linear loop."""

    def __init__(self, *, jev_settings: JevAgentSettings, **kwargs: Any) -> None:
        self.jev_settings = jev_settings
        super().__init__(**kwargs)

    async def preflight(self, message: str) -> JevResponse:
        """Evaluate all enabled presets in one Jev request and return run-local state."""
        response = JevResponse(input=message)
        definitions = tuple(
            JevPreflightRegistry.resolve(
                preset if isinstance(preset, JevPreflightPreset) else JevPreflightPreset(preset)
            )
            for preset in self.jev_settings.preflight
        )
        if not definitions:
            return response

        try:
            request = JevDecisionRequest(
                state=f"{_PREFLIGHT_CONTEXT}\n\nUSER REQUEST:\n{message}",
                questions=tuple(question for definition in definitions for question in definition.questions),
            )
            runner = DecisionModelRunner(self.jev_settings.decision)
            decision = await runner.arun(request)
            response.usage = JevUsage.from_usage_payload(decision.usage or {})
            self._record_results(response, definitions, decision.answers)
        except VidbyteSdkError:
            # Preflight is advisory: missing credentials and provider failures must not disable the agent.
            response.results.update(
                {
                    definition.preset.value: JevPresetResult(score=None, available=False)
                    for definition in definitions
                }
            )
        return response

    @staticmethod
    def _record_results(
        response: JevResponse,
        definitions: tuple[JevPreflightDefinition, ...],
        answers: Mapping[str, JevAnswer],
    ) -> None:
        # Scores each preset independently while retaining normalized answer evidence for calibration.
        lowest_failing: tuple[float, str] | None = None
        for definition in definitions:
            preset_answers: dict[str, JevAnswer] = {}
            true_probabilities: list[float] = []
            for question in definition.questions:
                answer = answers.get(question.name)
                if answer is None:
                    raise ConfigurationError(f"No Jev answer for question {question.name!r}.")
                probability = answer.probabilities.get(JEV_NOUL_TRUE)
                if probability is None:
                    raise ConfigurationError(f"Jev answer for {question.name!r} has no true probability.")
                preset_answers[question.name] = answer
                true_probabilities.append(probability)
            score = sum(true_probabilities) / len(true_probabilities)
            response.results[definition.preset.value] = JevPresetResult(score=score, answers=preset_answers)
            if score < definition.threshold:
                response.needs_clarification = True
                preset_lowest = min(
                    (answer.probabilities[JEV_NOUL_TRUE], question_name)
                    for question_name, answer in preset_answers.items()
                )
                if lowest_failing is None or preset_lowest < lowest_failing:
                    lowest_failing = preset_lowest

        if response.needs_clarification and lowest_failing is not None:
            for definition in definitions:
                clarification = definition.clarifications.get(lowest_failing[1])
                if clarification is not None:
                    response.output = clarification
                    return
            response.output = "Could you clarify the intended goal and result before I begin?"

    async def arun(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        """Short-circuit unclear requests or attach preflight state to the normal result."""
        response = await self.preflight(message)
        if response.needs_clarification:
            return AgentResult(
                output=response.output or "Could you clarify your request before I begin?",
                strategy_name="jev_preflight",
                metadata={"jev_response": response, "stop_reason": "needs_clarification"},
            )

        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )
        response.output = result.output
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata={**dict(result.metadata), "jev_response": response},
            structured=result.structured,
        )


__all__ = ["JevRuntime"]
