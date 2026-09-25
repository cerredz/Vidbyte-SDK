"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent and applies enabled preflight policies.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; it runs the security gate, then run-local tool selection, ahead of the inherited agent loop.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring while applying named policies internally; CONTAIN only narrows state this runtime owns and restores it after the run.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: A disabled preflight performs no Jev call; an unavailable selector keeps the original tool catalog; an unavailable security check stops BLOCK and PAUSE and contains CONTAIN. CONTAIN cannot silence BaseAgent's root trace or session recording, which run outside this runtime. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-tool-selector.md, docs/design/jev-preflight-sensitive-data.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_tool_selector.py, tests/test_jev_sensitive_preflight.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.preflight import JevPreflightSecurity, JevPreflightTools
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.constants.jev import JEV_SECURITY_CONTAIN_PROMPT
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset, JevSecurityAction
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext
from vidbyte.tools._internal import with_internal_agent_tools
from vidbyte.tools.security import PermissionPolicy, ToolPermission

# CONTAIN keeps only tools that cannot change or execute anything; the caller's policy still applies on top.
_CONTAIN_PERMISSIONS = frozenset({ToolPermission.SAFE, ToolPermission.READ})


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
        """Run the security gate, then enabled run-local preflights, before entering the inherited agent loop."""
        if JevPreflightPreset.SECURITY not in self.jev_settings.preflight:
            return await self._arun_with_tool_selection(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

        security = JevPreflightSecurity(self.jev_settings.decision, JevSecurityAction(self.jev_settings.security_action))
        security_result = await security.run(message)
        if security.must_stop(security_result):
            return AgentResult(
                output=security.stop_message(security_result),
                strategy_name="jev_security_preflight",
                metadata={"jev_security": security_result, "stop_reason": security.stop_reason()},
            )
        if security.must_contain(security_result):
            result = await self._arun_contained(message, handle=handle, context=context, metadata=metadata, options=options)
        else:
            result = await self._arun_with_tool_selection(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        return replace(result, metadata={**dict(result.metadata), "jev_security": security_result})

    async def _arun_contained(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
    ) -> AgentResult:
        # Runs the ordinary loop with read-only tools, a no-repeat prompt addendum, and no runtime spans.
        # @intent contain-narrows-then-restores
        # The runtime instance outlives one run, so every narrowed field is restored in finally; otherwise
        # one sensitive request would silently strip tools and tracing from every later run on this agent.
        saved = (self.permission_policy, self.user_tools, self.tools, self._tracer)
        allowed = frozenset(self.permission_policy.allowed & _CONTAIN_PERMISSIONS)
        self.permission_policy = PermissionPolicy(allowed=allowed)
        self.user_tools = self.user_tools.subset(tool.name for tool in self.user_tools if tool.spec().permission in allowed)
        self.tools = with_internal_agent_tools(self.user_tools)
        self._tracer = NullTracer()
        run_options = dict(options or {})
        run_options.pop("tools", None)
        if "system" in run_options:
            run_options["system"] = f"{run_options['system']}\n\n{JEV_SECURITY_CONTAIN_PROMPT}"
        contained_context = replace(
            context,
            system_prompt=f"{context.system_prompt}\n\n{JEV_SECURITY_CONTAIN_PROMPT}",
            tools=self.tools.specs(),
        )
        try:
            return await self._arun_with_tool_selection(message, handle=handle, context=contained_context, metadata=metadata, options=run_options, trace_context=None)
        finally:
            self.permission_policy, self.user_tools, self.tools, self._tracer = saved

    async def _arun_with_tool_selection(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> AgentResult:
        # Applies the TOOL_SELECTOR preflight when enabled, then enters the inherited agent loop.
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
