"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent, delegating specialist routing and applying enabled preflight policies.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; it hands configured specialist catalogs to JevSpecialistRouter and keeps run-local tool selection ahead of the inherited agent loop.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring; each capability's logic lives in its own class and this runtime only calls it.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: An empty specialist catalog and a disabled selector perform no Jev call; an unavailable selector keeps the original tool catalog. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-tool-selector.md, docs/design/jev-specialist-routing.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_tool_selector.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.presets import JevPreflightPreset
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.jev.specialists import JevSpecialistRouter
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

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
        """Route to a registered specialist when configured, otherwise run the general loop with enabled preflights."""
        if self.jev_settings.agents:
            router = JevSpecialistRouter(self.jev_settings.decision, self.jev_settings.specialists, self.usage_tracker)
            return await router.run(message, context=context, metadata=metadata, options=options, general=lambda: self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context))
        return await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

    async def _run_general(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> AgentResult:
        # Applies enabled run-local preflights before entering the inherited agent loop.
        if JevPreflightPreset.TOOL_SELECTOR not in self.jev_settings.preflight:
            return await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )

        candidate_tool_count = len(self.user_tools)
        selector = JevPreflightTools(
            self.jev_settings.decision,
            self.jev_settings.tool_selector_threshold,
        )
        self.user_tools = await selector.run(message, self.user_tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=run_options,
            trace_context=trace_context,
        )
        selector_metadata: dict[str, Any] = {
            "available": selector.available,
            "candidate_tool_count": candidate_tool_count,
            "selected_tool_count": len(self.user_tools),
        }
        if selector.usage is not None:
            selector_metadata["usage"] = {
                "input_tokens": selector.usage.input_tokens,
                "output_tokens": selector.usage.output_tokens,
            }
        return replace(
            result,
            metadata={
                **dict(result.metadata),
                "jev_tool_selector": selector_metadata,
            },
        )


__all__ = ["JevRuntime"]
