"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent, including the optional self-alignment pass before the linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: With self_align on, JevAgentAlignment returns the prompt for this run and JevRuntime swaps it into the run's context and this run-local runtime only; settings and the agent keep the original prompt.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: Without self_align, running performs no Jev call and needs no TypeSafe credential. A caller-supplied context system prompt skips alignment. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-agent-alignment.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_tool_selector.py, tests/test_jev_alignment.py, scripts/test-jev-tool-selector.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.presets import JevPreflightPreset
from vidbyte.agents.jev.alignment import (
    JevAgentAlignment,
    JevAlignmentResult,
    JevAlignmentStatus,
)
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools

ALIGNMENT_METADATA_KEY = "jev_alignment"


class JevRuntime(AgentRuntime):
    """Linear runtime that can align the system prompt with each request before running."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, alignment: JevAgentAlignment | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        if alignment is not None and not isinstance(alignment, JevAgentAlignment):
            raise ConfigurationError("JevRuntime.alignment must be a JevAgentAlignment or None.", details={"received_alignment": type(alignment).__name__})
        self.jev_settings = jev_settings
        self.alignment = alignment
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
        """Apply enabled Jev preflights, align this run's prompt, then enter the inherited loop."""
        selector_metadata: dict[str, Any] | None = None
        if JevPreflightPreset.TOOL_SELECTOR in self.jev_settings.preflight:
            candidate_tool_count = len(self.user_tools)
            selector = JevPreflightTools(self.jev_settings.decision, self.jev_settings.tool_selector_threshold)
            selected_tools = await selector.run(message, self.user_tools)
            self.user_tools = selected_tools
            self.tools = with_internal_agent_tools(selected_tools)
            context = replace(context, tools=self.tools.specs())
            options = {key: value for key, value in (options or {}).items() if key != "tools"}
            selector_metadata = {
                "available": selector.available,
                "candidate_tool_count": candidate_tool_count,
                "selected_tool_count": len(selected_tools),
            }
            if selector.usage is not None:
                selector_metadata["usage"] = {
                    "input_tokens": selector.usage.input_tokens,
                    "output_tokens": selector.usage.output_tokens,
                }

        alignment = self.alignment
        alignment_result: JevAlignmentResult | None = None
        if alignment is not None:
            alignment_result, context = await self._align(alignment, message, context)
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        result_metadata = dict(result.metadata)
        if selector_metadata is not None:
            result_metadata["jev_tool_selector"] = selector_metadata
        if alignment_result is not None:
            result_metadata[ALIGNMENT_METADATA_KEY] = alignment_result
        return replace(result, metadata=result_metadata)

    async def _align(self, alignment: JevAgentAlignment, message: str, context: BaseAgentContext) -> tuple[JevAlignmentResult, BaseAgentContext]:
        # Aligns the prompt at the head of this run's context and swaps in the edited prompt for this run only.
        original = self.system_prompt
        current = context.system_prompt or ""
        prefix = original if current.startswith(original) else original.strip()
        if not current.startswith(prefix):
            # A caller-supplied context prompt is not the agent's prompt, so there is nothing of ours to align.
            return JevAlignmentResult(JevAlignmentStatus.SKIPPED, original, detail="The run context carries a caller-supplied system prompt."), context
        tools = tuple(f"{spec.name}: {spec.description}" for spec in self.user_tools.specs())
        aligned = await alignment.align(message, original, tools=tools)
        if aligned.system_prompt == original:
            return aligned, context
        # @intent align-only-this-runs-prompt
        # Only this run-local runtime and this run's context change; JevAgentSettings, the agent, and the editor keep their prompts.
        self.system_prompt = aligned.system_prompt
        return aligned, replace(context, system_prompt=aligned.system_prompt.strip() + current[len(prefix):])


__all__ = ["ALIGNMENT_METADATA_KEY", "JevRuntime"]
