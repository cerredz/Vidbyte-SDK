"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Executes JevAgent's preflight definitions before its inherited generative agent loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; it owns preflight request assembly, scoring, clarification short-circuiting, and response metadata.
ARCHITECTURE NOTE: The questions of every selected preset, then the custom questions, are appended into one Jev request over the neutral state {"request": message}; only CLARIFY definitions can short-circuit. BaseAgent continues to own generative runners, tools, tracing, and usage.
COMMON MODIFICATION PATTERNS: Add new preflight policy as JevPreflightDefinition values in presets.py; this runtime evaluates whatever definitions JevPreflight returns.
KNOWN EDGE CASES: Disabled and unavailable preflights continue normally; unclear requests must not invoke the generative runner. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-preflight-custom-questions.md, docs/design/jev-preflight-recurring.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_agent.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.jev.presets import JevPreflightAction, JevPreflightDefinition
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

PREFLIGHT_STATE_FIELD = "request"


class JevRuntime(AgentRuntime):
    """Run configured Jev preflights before entering the inherited linear loop."""

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

    async def preflight(self, message: str) -> JevResponse:
        """Evaluate every preset and custom question in one Jev request and return run-local state."""
        response = JevResponse(input=message)
        definitions = self.jev_settings.preflight.definitions()
        if not definitions:
            return response

        try:
            # @intent shared-state-carries-content-only
            # Every selected preset reads this one state, so it holds the request alone; each
            # preset's framing lives in its own question instructions.
            request = JevDecisionRequest(
                state={PREFLIGHT_STATE_FIELD: message},
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
            if definition.action is JevPreflightAction.CLARIFY and score < definition.threshold:
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
