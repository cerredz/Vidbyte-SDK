"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs the JevPreflight gate, then either returns the gate's response or runs the inherited linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate and the JevResponse writer at construction and passes both in, while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: Every preset decision lives in JevPreflight.pass_; this runtime holds no preset checks. It applies only the one generic outcome a gate can produce (a narrower tool catalog), and it forwards metadata, options, and trace context to the inherited loop without reading them.
COMMON MODIFICATION PATTERNS: Add a preset's behavior as a case in JevPreflight.pass_ rather than here; extend JevPreflightRun only when a gate case must change another part of the run.
KNOWN EDGE CASES: With no preflight preset enabled the gate makes no Jev call and needs no TypeSafe credential. A plain BaseAgent(runtime="jev") has no gate and is refused here. A closed gate never reaches the generative runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.preflight import JevPreflight
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevPreflightRun
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools._internal import with_internal_agent_tools
from vidbyte.tools.catalog import Tools


class JevRuntime(AgentRuntime):
    """Linear runtime gated by JevPreflight: a closed gate returns JevResponse's result, an open one runs the loop."""

    def __init__(self, *, preflight: JevPreflight | None = None, response: JevResponse | None = None, **kwargs: Any) -> None:
        # Retains the gate and the response writer JevAgent built, and delegates the loop itself to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without a gate; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(preflight, JevPreflight) or not isinstance(response, JevResponse):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_preflight": type(preflight).__name__, "received_response": type(response).__name__},
            )
        self.preflight = preflight
        self.response = response
        super().__init__(**kwargs)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, **loop: Any) -> AgentResult:
        """Return the gate's response when JevPreflight closes it, or run the linear loop with the tools it chose."""
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        run = JevPreflightRun(message=message, tools=self.user_tools)
        if not await self.preflight.pass_(run):
            return self.response.stopped()
        if run.tools is not self.user_tools:
            context = self._use_tools(run.tools, context)
        return self.response.finished(await super().arun(message, handle=handle, context=context, **loop))

    def _use_tools(self, tools: Tools, context: BaseAgentContext) -> BaseAgentContext:
        # Swaps in the gate's catalog for both execution lookup and the schemas the model sees.
        # @intent hidden-tools-are-uncallable
        # Pruning only the schemas would still let a model call a hidden tool by name, so the runtime's
        # own catalogs are replaced too.
        self.user_tools = tools
        self.tools = with_internal_agent_tools(tools)
        return replace(context, tools=self.tools.specs())


__all__ = ["JevRuntime"]
