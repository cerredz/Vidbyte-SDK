"""Context Protocol Header

Description:
    Defines the built-in agent wrapper for continual trace artifact updates.
Purpose:
    Composes BaseAgent with an updateTrace tool so trace updates use normal SDK
    agent and tool primitives instead of custom one-off model calls.
Architecture:
    - ContinualTraceAgent: Thin wrapper over BaseAgent for trace update loops.
Relations:
    Used by AgentRuntime through ContinualTraceController.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
from vidbyte.trace.options import TraceSchema
from vidbyte.trace.tools import UpdateTraceTool


class ContinualTraceAgent:
    """Thin wrapper over BaseAgent for continual trace updates."""

    def __init__(self, *, runner: object, schema: TraceSchema, max_iterations: int = 3, provider: str | None = None) -> None:
        # Stores the runner and schema used to create one internal BaseAgent per update.
        self.runner = runner
        self.schema = schema
        self.max_iterations = max_iterations
        self.provider = provider
        self.last_error: str | None = None

    async def update(self, *, context_window: str, trace_so_far: Mapping[str, Any], runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        # Runs a bounded internal agent loop and returns the latest accepted trace artifact.
        from vidbyte.agents.base import BaseAgent

        tool = UpdateTraceTool(self.schema, trace_so_far)
        agent = BaseAgent(
            name="continual-trace-agent",
            system_prompt=Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT),
            runner=self.runner,
            tools=[tool],
            max_iterations=self.max_iterations,
        )
        try:
            await agent.arun(self._render_prompt(context_window, tool.current_trace(), runtime_metadata), provider=self.provider)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return tool.current_trace()
        self.last_error = tool.last_error
        return tool.current_trace()

    def _render_prompt(self, context_window: str, trace_so_far: Mapping[str, Any], runtime_metadata: Mapping[str, Any] | None) -> str:
        # Builds the trace-agent user prompt from the main context and trace state.
        return "\n\n".join(
            (
                "<main_context_window>\n" + context_window + "\n</main_context_window>",
                "<trace_schema>\n"
                + f"Name: {self.schema.name}\n"
                + f"Description: {self.schema.description or 'No description provided.'}\n"
                + self.schema.describe_fields()
                + "\n</trace_schema>",
                "<trace_so_far>\n" + json.dumps(dict(trace_so_far), indent=2, sort_keys=True) + "\n</trace_so_far>",
                "<runtime_metadata>\n" + json.dumps(dict(runtime_metadata or {}), indent=2, sort_keys=True, default=str) + "\n</runtime_metadata>",
            )
        )


__all__ = [
    "ContinualTraceAgent",
]
