"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the linear-runtime seam for Jev; it honors the precomputed gate result, applies the optional tool selector, and runs the inherited model loop.
ROLE IN CODEBASE: `RuntimeRegistry` resolves `AgentRuntimeType.JEV` here; `Jev` supplies validated runtime settings, the response writer, and the per-run preflight result.
ARCHITECTURE NOTE: Profile selection happens before BaseAgent runner construction in `Jev`; this class has no profile-routing policy and retains usage, speed, tracing, and normal agent-loop behavior.
FUNCTION INVENTORY: `JevRuntime.__init__` refuses generic BaseAgent construction without Jev-owned runtime inputs; `arun(...)` stops on a closed gate or delegates to `_run_general(...)`; `_run_general(...)` preserves existing tool-selector behavior.
COMMON MODIFICATION PATTERNS: Keep new global Jev policy in a capability class built by `Jev`; update `JevRuntimeSettings` and the focused runtime tests when its existing loop settings change.
WHAT NOT TO DO IN THIS FILE: 1. Do not select profiles; `vidbyte/agents/jev/specialists.py` owns that decision. 2. Do not re-run preflight; `Jev.generate_reply()` runs it before profile selection.
KNOWN EDGE CASES: A closed preflight result returns the structured clarification without a generative model call; an unavailable tool selector keeps the selected profile's full tool catalog.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `skills/jev-agent/SKILL.md`, and `field-guide/vidbyte-sdk/runtime-boundaries.md`.
TESTS: `tests/test_jev_agent.py`, `tests/test_jev_preflight.py`, and `tests/test_jev_tool_selector.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevRuntimeSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for Jev's already prepared runs."""

    def __init__(self, *, runtime_settings: JevRuntimeSettings | None = None, response: JevResponse | None = None, preflight_passed: bool | None = None, **kwargs: Any) -> None:
        # Refuses direct BaseAgent runtime selection because only Jev can prepare the gate result and profile configuration.
        if not isinstance(runtime_settings, JevRuntimeSettings) or not isinstance(response, JevResponse) or not isinstance(preflight_passed, bool):
            raise ConfigurationError("The 'jev' runtime is only available through Jev; construct Jev(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').")
        self.runtime_settings = runtime_settings
        self.response = response
        self.preflight_passed = preflight_passed
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Returns a clarification for a closed gate; otherwise uses the standard selected-profile loop.
        if not self.preflight_passed:
            return self.response.stopped()
        result = await self._run_general(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        return self.response.finished(result)

    async def _run_general(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Applies tool selection only after Jev has loaded the chosen profile into BaseAgent.
        if JevPreflightPreset.TOOL_SELECTOR not in self.runtime_settings.preflight:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        return await self._run_with_tool_selection(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

    async def _run_with_tool_selection(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Keeps the selector's existing fail-open catalog behavior and run metadata.
        candidate_tool_count = len(self.user_tools)
        selector = JevPreflightTools(self.runtime_settings.decision, self.runtime_settings.tool_selector_threshold)
        self.user_tools = await selector.run(message, self.user_tools)
        selected_tool_count = len(self.user_tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        selected_context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        result = await super().arun(message, handle=handle, context=selected_context, metadata=metadata, options=run_options, trace_context=trace_context)
        selector_metadata: dict[str, Any] = {
            "available": selector.available,
            "candidate_tool_count": candidate_tool_count,
            "selected_tool_count": selected_tool_count,
        }
        if selector.usage is not None:
            selector_metadata["usage"] = {"input_tokens": selector.usage.input_tokens, "output_tokens": selector.usage.output_tokens}
        return replace(result, metadata={**dict(result.metadata), "jev_tool_selector": selector_metadata})


__all__ = ["JevRuntime"]
