"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Runs Jev's combined preflight decision, applies the optional tool selector, and delegates generation to the ordinary linear AgentRuntime loop.
ROLE IN CODEBASE: RuntimeRegistry resolves AgentRuntimeType.JEV here; JevAgent supplies validated settings, its preflight gate, and its response writer.
ARCHITECTURE NOTE: Profile choice is one question inside JevPreflightGate. The selected value is observable metadata only; this runtime remains the configured linear generative agent.
FUNCTION INVENTORY: JevRuntime.__init__ rejects direct construction without JevAgent-owned inputs; arun gates the run and applies optional tool filtering before the inherited loop.
COMMON MODIFICATION PATTERNS: Add fixed decision questions to JevPreflightGate; preserve normal AgentRuntime behavior for generation and keep tool filtering run-local.
WHAT NOT TO DO IN THIS FILE: 1. Do not build profile questions; JevPreflightGate owns them. 2. Do not execute profile entries; specialists.py contains metadata only.
KNOWN EDGE CASES: A failed preflight decision follows its established fail-open policy; a closed clarity gate returns the clarification without a generation call.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/jev-agent/SKILL.md
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and tests/test_jev_tool_selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


class JevRuntime(AgentRuntime):
    """Linear runtime seam for one Jev preflight and the normal generative loop."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, runtime_settings: JevRuntimeSettings | None = None, preflight: JevPreflightGate | None = None, response: JevResponse | None = None, **kwargs: Any) -> None:
        if not isinstance(jev_settings, JevAgentSettings) or not isinstance(runtime_settings, JevRuntimeSettings) or not isinstance(preflight, JevPreflightGate) or not isinstance(response, JevResponse):
            raise ConfigurationError("The 'jev' runtime is only available through JevAgent(JevAgentSettings(...), JevRuntimeSettings(...)).")
        self.jev_settings = jev_settings
        self.runtime_settings = runtime_settings
        self.preflight = preflight
        self.response = response
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        self.response.start(message)
        if not await self.preflight.pass_(message):
            return self.response.stopped()
        if JevPreflightPreset.TOOL_SELECTOR not in self.runtime_settings.preflight:
            return self.response.finished(await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context))
        return await self._run_with_tool_selector(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

    async def _run_with_tool_selector(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        candidate_count = len(self.user_tools)
        selector = JevPreflightTools(self.runtime_settings.decision, self.runtime_settings.tool_selector_threshold)
        self.user_tools = await selector.run(message, self.user_tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        selected_context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        result = await super().arun(message, handle=handle, context=selected_context, metadata=metadata, options=run_options, trace_context=trace_context)
        selector_metadata: dict[str, Any] = {"available": selector.available, "candidate_tool_count": candidate_count, "selected_tool_count": len(self.user_tools)}
        if selector.usage is not None:
            selector_metadata["usage"] = {"input_tokens": selector.usage.input_tokens, "output_tokens": selector.usage.output_tokens}
        return self.response.finished(replace(result, metadata={**dict(result.metadata), "jev_tool_selector": selector_metadata}))


__all__ = ["JevRuntime"]
