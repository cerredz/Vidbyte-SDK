"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs JevPreflight before the inherited linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: All preflight questions, scoring, and fail-open policy live in vidbyte/lib/jev/preflight/; this runtime only short-circuits an unclear request and attaches the JevResponse to the result metadata.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With no preflight preset enabled this runtime performs no Jev call and needs no TypeSafe credential. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here. An unclear request never reaches the generative runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.constants.jev import (
    JEV_PREFLIGHT_STRATEGY_NAME,
    JEV_RESPONSE_METADATA_KEY,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflight
from vidbyte.lib.tracing import SpanContext


class JevRuntime(AgentRuntime):
    """Linear runtime that asks JevPreflight first and stops to ask the user when the request is unclear."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates the loop itself to AgentRuntime.
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
        """Return the clarifying question for an unclear request, or run the linear loop with preflight state attached."""
        # @intent unclear-requests-never-reach-the-model
        # A failing preflight returns its clarifying question without invoking the generative runner, so the
        # user is asked before any tokens are spent; every other outcome runs the inherited loop unchanged.
        presets = cast(tuple[JevPreflightPreset, ...], self.jev_settings.preflight)  # JevAgentSettings normalized every entry.
        response = await JevPreflight.run(message, presets=presets, decision=self.jev_settings.decision)
        if response.needs_clarification:
            return AgentResult(
                output=response.output or "",
                strategy_name=JEV_PREFLIGHT_STRATEGY_NAME,
                metadata={JEV_RESPONSE_METADATA_KEY: response, "stop_reason": "needs_clarification"},
            )
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        response.output = result.output
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata={**dict(result.metadata), JEV_RESPONSE_METADATA_KEY: response},
            structured=result.structured,
        )


__all__ = ["JevRuntime"]
