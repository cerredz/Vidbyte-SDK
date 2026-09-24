"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent, including the optional prompt-alignment and tool-alignment passes before the linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: With self_align on, JevAgentAlignment returns the prompt for this run and JevRuntime swaps it into the run's context and this run-local runtime only; settings and the agent keep the original prompt. With tool_align set, JevAgentAlignment returns catalog tools for this run, which JevRuntime adds to this run-local runtime's tools and context, then releases when the run ends.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: Without self_align or tool_align, running performs no Jev call and needs no TypeSafe credential. Attached tools' MCP sessions are released in a finally block, so a failing run still closes them. The added-tools footer is skipped when the run returns structured output. A caller-supplied context system prompt skips alignment. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-agent-alignment.md, docs/design/jev-tool-alignment.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_alignment.py, tests/test_jev_tool_alignment.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.alignment import (
    JevAgentAlignment,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevToolAlignmentResult,
    JevToolAlignmentStatus,
    JevToolAttachment,
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
TOOL_ALIGNMENT_METADATA_KEY = "jev_tool_alignment"
# Prompt-alignment outcomes whose fit gate was actually answered, so tool alignment need not ask it again.
_SCOPE_ANSWERED = frozenset({JevAlignmentStatus.ALIGNED, JevAlignmentStatus.NO_GAPS, JevAlignmentStatus.EDITS_REJECTED})


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
        """Align the system prompt and the tools for this request when enabled, then run the inherited loop."""
        alignment = self.alignment
        if alignment is None:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        extra: dict[str, Any] = {}
        prompt_result: JevAlignmentResult | None = None
        if self.jev_settings.self_align:
            prompt_result, context = await self._align(alignment, message, context)
            extra[ALIGNMENT_METADATA_KEY] = prompt_result
        attachment: JevToolAttachment | None = None
        run_options = options
        if self.jev_settings.tool_align is not None:
            attachment = await self._align_tools(alignment, message, prompt_result)
            extra[TOOL_ALIGNMENT_METADATA_KEY] = attachment.result
            context, run_options = self._with_attached_tools(attachment, context, options)
        try:
            result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=run_options, trace_context=trace_context)
        finally:
            # @intent attached-sessions-close-with-the-run
            # Attached MCP sessions belong to this run only; closing them here, even when the loop raises, keeps a
            # later run from reusing a tool it was never judged for.
            if attachment is not None:
                await alignment.release_tools(attachment)
        return replace(result, output=self._announced(result, attachment), metadata={**dict(result.metadata), **extra})

    async def _align_tools(self, alignment: JevAgentAlignment, message: str, prompt_result: JevAlignmentResult | None) -> JevToolAttachment:
        # Runs tool alignment unless prompt alignment already found the request out of scope, reusing its gate answer.
        if prompt_result is not None and prompt_result.status is JevAlignmentStatus.OUT_OF_SCOPE:
            return JevToolAttachment(JevToolAlignmentResult(JevToolAlignmentStatus.OUT_OF_SCOPE, detail="Prompt alignment found the request out of scope, so no tools were added."))
        scope_checked = prompt_result is not None and prompt_result.status in _SCOPE_ANSWERED
        return await alignment.align_tools(message, self.system_prompt, self.user_tools, scope_checked=scope_checked)

    def _with_attached_tools(self, attachment: JevToolAttachment, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        # Adds attached tools to this run-local runtime and context; the agent and its settings keep their tool list.
        # @intent attach-only-to-this-run
        # Only this runtime instance and this run's context change, mirroring how prompt alignment swaps the prompt.
        if not attachment.tools:
            return context, options
        self.user_tools = self.user_tools.extend(attachment.tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        run_options = dict(options or {})
        # A caller-computed schema list would hide the attached tools, so the loop rebuilds schemas from self.tools.
        run_options.pop("tools", None)
        return replace(context, tools=self.tools.specs()), run_options

    def _announced(self, result: AgentResult, attachment: JevToolAttachment | None) -> str:
        # Appends the code-written list of added tools, so users see exactly what was attached; never for structured output.
        tool_settings = self.jev_settings.tool_align
        if attachment is None or tool_settings is None or not tool_settings.announce or result.structured is not None:
            return result.output
        summary = attachment.result.summary()
        if not summary:
            return result.output
        return f"{result.output.rstrip()}\n\n{summary}" if result.output.strip() else summary

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


__all__ = ["ALIGNMENT_METADATA_KEY", "TOOL_ALIGNMENT_METADATA_KEY", "JevRuntime"]
