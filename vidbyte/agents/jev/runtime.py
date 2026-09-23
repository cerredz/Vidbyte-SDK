"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent, including the optional documentation lookup before the linear loop.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: With documentation on, JevDocumentation decides whether the request needs outside documentation and finds links; JevRuntime appends them to this run's context system prompt only, so settings, the agent, and later runs keep the original prompt.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: Without documentation, running performs no Jev call and needs no TypeSafe credential. A lookup that finds no links leaves the context unchanged. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-documentation.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_documentation.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.documentation import JevDocumentation
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext

DOCUMENTATION_METADATA_KEY = "jev_documentation"


class JevRuntime(AgentRuntime):
    """Linear runtime that can add documentation links for the request before running."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, documentation: JevDocumentation | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        if documentation is not None and not isinstance(documentation, JevDocumentation):
            raise ConfigurationError("JevRuntime.documentation must be a JevDocumentation or None.", details={"received_documentation": type(documentation).__name__})
        self.jev_settings = jev_settings
        self.documentation = documentation
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
        """Add documentation links for this request when enabled, then run the inherited loop."""
        documentation = self.documentation
        if documentation is None:
            return await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        found = await documentation.lookup(message)
        section = found.prompt_section()
        if section is not None:
            # @intent documentation-reaches-only-this-run
            # Only this run's context changes; JevAgentSettings, the agent, and later runs keep their prompts.
            current = context.system_prompt or self.system_prompt
            context = replace(context, system_prompt=f"{current.rstrip()}\n\n{section}")
        result = await super().arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        return replace(result, metadata={**dict(result.metadata), DOCUMENTATION_METADATA_KEY: found})


__all__ = ["DOCUMENTATION_METADATA_KEY", "JevRuntime"]
