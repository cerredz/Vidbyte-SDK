"""Context Protocol Header

Description:
    Defines ContinualTraceAgent, a dedicated BaseAgent that fills a trace schema.
Purpose:
    Performs one continual trace update pass over a read-only snapshot of a main
    agent run, filling a typed trace schema through the updateTrace tool. Mirrors the
    HandoffAgent pattern so trace updates use normal SDK agent and tool primitives.
Architecture:
    - ContinualTraceAgent: BaseAgent subclass exposing a single updateTrace tool.
Relations:
    Subclasses vidbyte.agents.base.BaseAgent, used by
    vidbyte.middleware.continual_trace.ContinualTraceMiddleware.
Similar Files:
    - vidbyte/agents/handoff.py: The handoff agent this mirrors.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.continual_trace import UpdateTraceTool


class ContinualTraceAgent(BaseAgent):
    """Dedicated BaseAgent that fills a trace schema from a main run snapshot."""

    def __init__(self, schema: TraceSchema | type | Mapping[str, Any], *, name: str = "continual-trace", trace_so_far: Mapping[str, Any] | None = None, max_trace_iterations: int = 3, **kwargs: Any) -> None:
        # Build the single updateTrace tool, load the trace prompt, and never trace itself.
        self.schema: TraceSchema = TraceSchema.coerce(schema)
        kwargs.pop("tools", None)
        kwargs.pop("system_prompt", None)
        kwargs.pop("output_schema", None)
        kwargs.pop("handoff", None)
        kwargs.pop("trace_option", None)
        kwargs.pop("max_iterations", None)
        self._tool = UpdateTraceTool(self.schema, trace_so_far)
        super().__init__(name=name, system_prompt=Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT), tools=[self._tool], max_iterations=max_trace_iterations, **kwargs)
        self.last_error: str | None = None

    @classmethod
    def from_source_agent(cls, source_agent: BaseAgent, schema: TraceSchema | type | Mapping[str, Any], *, trace_so_far: Mapping[str, Any] | None = None, max_trace_iterations: int = 3) -> "ContinualTraceAgent":
        """Build a trace agent that reuses a source agent's runner and provider configuration."""
        return cls(
            schema,
            trace_so_far=trace_so_far,
            max_trace_iterations=max_trace_iterations,
            provider=source_agent.runner_config.provider,
            model_name=source_agent.runner_config.model_name,
            api_key=source_agent.runner_config.api_key,
            temperature=source_agent.runner_config.temperature,
        )

    @classmethod
    async def run_update(cls, source_agent: BaseAgent, schema: TraceSchema | type | Mapping[str, Any], *, context_window: str, trace_so_far: Mapping[str, Any] | None = None, max_trace_iterations: int = 3, runtime_metadata: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], str | None]:
        """Run one fail-open trace update and return the accumulated artifact and any error."""
        agent = cls.from_source_agent(source_agent, schema, trace_so_far=trace_so_far, max_trace_iterations=max_trace_iterations)
        artifact = await agent.update(context_window=context_window, runtime_metadata=runtime_metadata)
        return artifact, agent.last_error

    async def update(self, *, context_window: str, runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Run the bounded internal loop and return the latest accepted trace artifact."""
        try:
            await self.arun(self._render_prompt(context_window, runtime_metadata))
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return self._tool.current_trace()
        self.last_error = self._tool.last_error
        return self._tool.current_trace()

    def _render_prompt(self, context_window: str, runtime_metadata: Mapping[str, Any] | None) -> str:
        # Build the trace-agent user prompt from the main context and current trace state.
        return "\n\n".join(
            (
                "<main_context_window>\n" + context_window + "\n</main_context_window>",
                "<trace_schema>\n" + f"Name: {self.schema.name}\n" + f"Description: {self.schema.description or 'No description provided.'}\n" + self.schema.describe_fields() + "\n</trace_schema>",
                "<trace_so_far>\n" + json.dumps(self._tool.current_trace(), indent=2, sort_keys=True, default=str) + "\n</trace_so_far>",
                "<runtime_metadata>\n" + json.dumps(dict(runtime_metadata or {}), indent=2, sort_keys=True, default=str) + "\n</runtime_metadata>",
            )
        )


__all__ = [
    "ContinualTraceAgent",
]
