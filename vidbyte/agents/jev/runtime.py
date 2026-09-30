"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs preflight, optional prompt and tool alignment, run-state checks, and the tool selector before the inherited linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate, alignment helper, JevRunState, JevContinuation, and JevResponse writer at construction and passes them in. The runtime answers AgentRuntime's finish-attempt hook by asking the JevContinuation whether to continue.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring while applying named policies internally.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With no done check enabled there is no JevRunState, so every finish attempt stands. A chosen specialist runs through its own agent, so this agent's alignment, selector, and done checks do not apply. Alignment sessions close even when the main run fails. A plain BaseAgent(runtime="jev") has no JevRuntimeSettings, gate, or response writer and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, and scripts/test-jev-tool-selector.py.
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
from vidbyte.agents.jev.continuation import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAlignmentSettings, JevRuntimeSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools

_SCOPE_ANSWERED = frozenset({JevAlignmentStatus.ALIGNED, JevAlignmentStatus.NO_GAPS, JevAlignmentStatus.EDITS_REJECTED})


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(
        self,
        *,
        runtime_settings: JevRuntimeSettings | None = None,
        preflight: JevPreflightGate | None = None,
        run_state: JevRunState | None = None,
        continuation: JevContinuation | None = None,
        response: JevResponse | None = None,
        alignment: JevAgentAlignment | None = None,
        alignment_settings: JevAlignmentSettings | None = None,
        **kwargs: Any,
    ) -> None:
        # Retains the validated runtime settings, the gate, the done checks, the continuation, and the response writer JevAgent built, and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without them; refusing here names JevAgent instead of failing later on a None field.
        if (
            not isinstance(runtime_settings, JevRuntimeSettings)
            or not isinstance(preflight, JevPreflightGate)
            or not isinstance(response, JevResponse)
            or not isinstance(alignment_settings, JevAlignmentSettings)
            or (alignment is not None and not isinstance(alignment, JevAgentAlignment))
            or (alignment is None and (alignment_settings.system_prompt or alignment_settings.tool_settings))
        ):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={
                    "received_runtime_settings": type(runtime_settings).__name__,
                    "received_preflight": type(preflight).__name__,
                    "received_response": type(response).__name__,
                    "received_alignment": type(alignment).__name__,
                },
            )
        self.runtime_settings = runtime_settings
        self.preflight = preflight
        self.run_state = run_state
        self.continuation = continuation
        self.response = response
        self.alignment = alignment
        self.alignment_settings = alignment_settings
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
        """Run the preflight gate, then apply enabled run-local preflights before entering the inherited agent loop."""
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        if not await self.preflight.pass_(message):
            return self.response.stopped()
        if self.preflight.specialist is not None:
            return self.response.delegated(await self.preflight.specialist.agent.arun(message))

        alignment = self.alignment
        prompt_result: JevAlignmentResult | None = None
        attachment: JevToolAttachment | None = None
        try:
            if alignment is not None and self.alignment_settings.system_prompt:
                prompt_result, context = await self._align(alignment, message, context)
                self.response.alignment(prompt_result)
            if alignment is not None and self.alignment_settings.tool_settings:
                attachment = await self._align_tools(alignment, message, prompt_result)
                self.response.tool_alignment(attachment.result)
                context, options = self._with_attached_tools(attachment, context, options)

            if self.run_state is not None:
                await self.run_state.begin(message)
            selector_metadata: dict[str, Any] | None = None
            if JevPreflightPreset.TOOL_SELECTOR in self.runtime_settings.preflight:
                candidate_tool_count = len(self.user_tools)
                selector = JevPreflightTools(self.runtime_settings.decision, self.runtime_settings.tool_selector_threshold)
                self.user_tools = await selector.run(message, self.user_tools)
                self.tools = with_internal_agent_tools(self.user_tools)
                context = replace(context, tools=self.tools.specs())
                run_options = dict(options or {})
                run_options.pop("tools", None)
                options = run_options
                selector_metadata = {
                    "available": selector.available,
                    "candidate_tool_count": candidate_tool_count,
                    "selected_tool_count": len(self.user_tools),
                }
                if selector.usage is not None:
                    selector_metadata["usage"] = {
                        "input_tokens": selector.usage.input_tokens,
                        "output_tokens": selector.usage.output_tokens,
                    }

            result = await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )
            if attachment is not None and attachment.result.summary():
                result = replace(result, output=self._announced(result, attachment))
            if selector_metadata is not None:
                result = replace(result, metadata={**dict(result.metadata), "jev_tool_selector": selector_metadata})
            return self.response.finished(result)
        finally:
            if attachment is not None and alignment is not None:
                await alignment.release_tools(attachment)

    async def _align_tools(self, alignment: JevAgentAlignment, message: str, prompt_result: JevAlignmentResult | None) -> JevToolAttachment:
        if prompt_result is not None and prompt_result.status is JevAlignmentStatus.OUT_OF_SCOPE:
            return JevToolAttachment(JevToolAlignmentResult(JevToolAlignmentStatus.OUT_OF_SCOPE, detail="Prompt alignment found the request out of scope, so no tools were added."))
        scope_checked = prompt_result is not None and prompt_result.status in _SCOPE_ANSWERED
        return await alignment.align_tools(message, self.system_prompt, self.user_tools, scope_checked=scope_checked)

    def _with_attached_tools(self, attachment: JevToolAttachment, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        if not attachment.tools:
            return context, options
        self.user_tools = self.user_tools.extend(attachment.tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        run_options = dict(options or {})
        run_options.pop("tools", None)
        return replace(context, tools=self.tools.specs()), run_options

    def _announced(self, result: AgentResult, attachment: JevToolAttachment) -> str:
        if not self.alignment_settings.tool_settings or not self.alignment_settings.tool_options.announce or result.structured is not None:
            return result.output
        summary = attachment.result.summary()
        return f"{result.output.rstrip()}\n\n{summary}" if summary and result.output.strip() else summary or result.output

    async def _align(self, alignment: JevAgentAlignment, message: str, context: BaseAgentContext) -> tuple[JevAlignmentResult, BaseAgentContext]:
        original = self.system_prompt
        current = context.system_prompt or ""
        prefix = original if current.startswith(original) else original.strip()
        if not current.startswith(prefix):
            return JevAlignmentResult(JevAlignmentStatus.SKIPPED, original, detail="The run context carries a caller-supplied system prompt."), context
        tools = tuple(f"{spec.name}: {spec.description}" for spec in self.user_tools.specs())
        aligned = await alignment.align(message, original, tools=tools)
        if aligned.system_prompt == original:
            return aligned, context
        self.system_prompt = aligned.system_prompt
        return aligned, replace(context, system_prompt=aligned.system_prompt.strip() + current[len(prefix):])

    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        """Ask the continuation whether this finish attempt continues the loop, and let it shape what the main agent reads next."""
        # @intent continuation-logic-lives-in-the-continuation
        # The owner asked the runtime to only ask "should we continue?" and then "continue", so every reason to
        # continue and every message it sends lives in a JevContinuation subclass, never in this runtime.
        if self.continuation is None or not await self.continuation.should_continue(result.output, state.iteration_outputs, state.call_contexts):
            return False
        self.continuation.continue_(messages)
        return True


__all__ = ["JevRuntime"]
