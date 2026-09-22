"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Executes fixed Jev preflight policies before the inherited generative agent loop.
ROLE IN CODEBASE: JevRuntime owns security classification, action selection, and response metadata.
ARCHITECTURE NOTE: BaseAgent continues to own runners, tools, tracing, usage, and session wiring.
COMMON MODIFICATION PATTERNS: Resolve named settings here and translate typed decisions into fixed runtime actions.
KNOWN EDGE CASES: BLOCK and PAUSE fail closed on unavailable classification; REPORT records unknown flags and continues.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py and tests/test_jev_agent.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.jev.presets import (
    SECURITY_FLAGS,
    SECURITY_QUESTIONS,
    SecurityAction,
    SecurityPreset,
)
from vidbyte.agents.jev.response import JevResponse, JevSecurityResult
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.constants.jev import JEV_NOUL_FALSE, JEV_NOUL_TRUE
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevDecisionRequest
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.tracing import SpanContext


class JevRuntime(AgentRuntime):
    """Run configured security preflight before entering the inherited linear loop."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and refuses generic BaseAgent runtime selection.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        self.jev_settings = jev_settings
        super().__init__(**kwargs)

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
        """Classify configured security input before the ordinary generative loop."""
        if not self.jev_settings.preflight:
            return await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )

        preset = self.jev_settings.preflight[0]
        response = await self._security_preflight(message)
        security = response.results["security"]
        must_stop = security.any_sensitive is True or (
            not security.available and preset.on_detected in (SecurityAction.BLOCK, SecurityAction.PAUSE)
        )
        if must_stop and preset.on_detected is not SecurityAction.REPORT:
            reason = "sensitive_data_blocked" if preset.on_detected is SecurityAction.BLOCK else "sensitive_data_review_required"
            output = self._security_message(security, preset)
            return AgentResult(
                output=output,
                strategy_name="jev_security_preflight",
                metadata={"jev_response": response, "stop_reason": reason},
            )

        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata={**dict(result.metadata), "jev_response": response},
            structured=result.structured,
        )

    async def _security_preflight(self, message: str) -> JevResponse:
        # Sends only the current request text to TypeSafe and stores category flags, never the text itself.
        response = JevResponse()
        try:
            request = JevDecisionRequest(
                state=(
                    "Classify whether the supplied request contains each sensitive-data category. "
                    "Treat each question independently. Distinguish actual or plausibly real data from "
                    "topic mentions and obvious placeholders.\n\nSUPPLIED REQUEST:\n" + message
                ),
                questions=SECURITY_QUESTIONS,
            )
            decision = await DecisionModelRunner(self.jev_settings.decision).arun(request)
            response.usage = JevUsage.from_usage_payload(decision.usage or {})
            flags: dict[str, bool | None] = {}
            for flag, question in zip(SECURITY_FLAGS, SECURITY_QUESTIONS, strict=True):
                answer = decision.answers.get(question.name)
                if answer is None:
                    flags[flag] = None
                    continue
                true_probability = answer.probabilities.get(JEV_NOUL_TRUE)
                false_probability = answer.probabilities.get(JEV_NOUL_FALSE)
                flags[flag] = (
                    None
                    if true_probability is None or false_probability is None
                    else true_probability >= false_probability
                )
            available = all(value is not None for value in flags.values())
            response.results["security"] = JevSecurityResult(
                available=available,
                flags=flags,
                any_sensitive=_any_sensitive(flags),
            )
        except VidbyteSdkError:
            response.results["security"] = JevSecurityResult(
                available=False,
                flags={flag: None for flag in SECURITY_FLAGS},
                any_sensitive=None,
            )
        return response

    @staticmethod
    def _security_message(result: JevSecurityResult, preset: SecurityPreset) -> str:
        # Names detected categories without echoing potentially sensitive input values.
        categories = tuple(flag.replace("_", " ") for flag, detected in result.flags.items() if detected is True)
        if categories:
            category_text = ", ".join(categories)
            if preset.on_detected is SecurityAction.BLOCK:
                return f"This request appears to contain sensitive data in these categories: {category_text}. The request was blocked before the agent started."
            return f"This request appears to contain sensitive data in these categories: {category_text}. Review is required before the agent can continue."
        if preset.on_detected is SecurityAction.BLOCK:
            return "The request could not be checked for sensitive data, so it was blocked before the agent started."
        return "The request could not be checked for sensitive data. Review it before starting the agent."


def _any_sensitive(flags: Mapping[str, bool | None]) -> bool | None:
    # Preserves a known positive while returning unknown when no positive is known and checks are incomplete.
    values = tuple(flags.values())
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


__all__ = ["JevRuntime"]
