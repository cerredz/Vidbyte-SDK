"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs the JevPreflightGate, then returns the gate's response, hands the run to the specialist the gate chose, or writes the run state, applies the tool selector, and runs the inherited linear loop, whose finish attempts the enabled done checks may send back to work.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate, the JevRunState, the JevContinuation, and the JevResponse writer at construction and passes them in, and the runtime keeps run-local tool selection ahead of the inherited agent loop and answers AgentRuntime's finish-attempt hook by asking the JevContinuation whether to continue.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring while applying named policies internally.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With no done check enabled there is no JevRunState, so no run state is written and every finish attempt stands. A gate with no fixed-question preset and no specialist performs no Jev call, and a closed gate never reaches the generative runner. A chosen specialist runs through its own agent, so neither this agent's tool selector nor its done checks apply to it. A disabled selector performs no Jev call; an unavailable selector keeps the original tool catalog. A plain BaseAgent(runtime="jev") has no JevRuntimeSettings, gate, or response writer and is refused here.
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
)
from vidbyte.agents.jev.continuation import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevRuntimeSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAlignmentInput, JevToolSelectorResponse
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


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
        **kwargs: Any,
    ) -> None:
        # Retains the validated runtime settings, the gate, the done checks, the continuation, and the response writer JevAgent built, and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without them; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(runtime_settings, JevRuntimeSettings) or not isinstance(preflight, JevPreflightGate) or not isinstance(response, JevResponse):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={
                    "received_runtime_settings": type(runtime_settings).__name__,
                    "received_preflight": type(preflight).__name__,
                    "received_response": type(response).__name__,
                },
            )
        self.runtime_settings = runtime_settings
        self.preflight = preflight
        self.run_state = run_state
        self.continuation = continuation
        self.response = response
        if alignment is not None and not isinstance(alignment, JevAgentAlignment):
            raise ConfigurationError(
                "JevRuntime.alignment must be a JevAgentAlignment or None.",
                details={"received_alignment": type(alignment).__name__},
            )
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
        """Run the preflight gate, then apply enabled run-local preflights before entering the inherited agent loop."""
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        if not await self.preflight.pass_(message):
            return self.response.stopped()
        if self.preflight.specialist is not None:
            return self.response.delegated(await self.preflight.specialist.agent.arun(message))
        if self.run_state is not None:
            await self.run_state.begin(message)
        alignment_result = None
        if self.alignment is not None:
            alignment_result, context = await self._align(message, context)
            self.response.alignment(alignment_result, aligned_prompt=alignment_result.system_prompt)

        selector_response = None
        run_options = dict(options or {})
        if JevPreflightPreset.TOOL_SELECTOR in self.runtime_settings.preflight:
            candidate_tool_count = len(self.user_tools)
            selector = JevPreflightTools(
                self.runtime_settings.decision,
                self.runtime_settings.tool_selector_threshold,
            )
            self.user_tools = await selector.run(message, self.user_tools)
            self.tools = with_internal_agent_tools(self.user_tools)
            context = replace(context, tools=self.tools.specs())
            run_options.pop("tools", None)
            selector_response = JevToolSelectorResponse(
                available=selector.available,
                candidate_tool_count=candidate_tool_count,
                selected_tool_count=len(self.user_tools),
                usage=selector.usage,
            )
            self.response.tool_selector(selector_response)

        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=run_options,
            trace_context=trace_context,
        )
        result_metadata = dict(result.metadata)
        if selector_response is not None:
            selector_metadata: dict[str, Any] = {
                "available": selector_response.available,
                "candidate_tool_count": selector_response.candidate_tool_count,
                "selected_tool_count": selector_response.selected_tool_count,
            }
            if selector_response.usage is not None:
                selector_metadata["usage"] = {
                    "input_tokens": selector_response.usage.input_tokens,
                    "output_tokens": selector_response.usage.output_tokens,
                }
            result_metadata["jev_tool_selector"] = selector_metadata
        result = replace(result, metadata=result_metadata)
        return self.response.finished(result)

    # @intent alignment-changes-only-this-run
    # Prompt edits belong to the current invocation; carrying them into settings or later requests would make a local adaptation persistent.
    async def _align(self, message: str, context: BaseAgentContext) -> tuple[JevAlignmentResult, BaseAgentContext]:
        """Align the agent's prompt for this run without changing the agent's configured prompt."""
        original = self.system_prompt
        current = context.system_prompt or ""
        prefix = original if current.startswith(original) else original.strip()
        if not current.startswith(prefix):
            return JevAlignmentResult(
                JevAlignmentStatus.SKIPPED,
                original,
                detail="The run context carries a caller-supplied system prompt.",
            ), context
        request = JevAlignmentInput(user_prompt=message, system_prompt=original, tools=tuple(self.user_tools))
        result = await self.alignment.run(request)
        if result.system_prompt == original:
            return result, context
        return result, replace(context, system_prompt=result.system_prompt.strip() + current[len(prefix):])

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
