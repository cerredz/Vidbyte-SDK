"""Context Protocol Header

Description:
    Per-run controller that schedules continual trace updates for the linear runtime.
Purpose:
    Decides when to invoke ContinualTraceAgent, accumulates the trace artifact, and
    exposes compact metadata, while guaranteeing the trace is never written back into
    the main agent's context window.
Architecture:
    - ContinualTraceController: Stateful per-run scheduler and artifact accumulator.
Relations:
    Created by vidbyte.agents.runtime.AgentRuntime and delegates to
    vidbyte.agents.continual_trace.ContinualTraceAgent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.trace import TraceOption

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.context import BaseAgentContext
    from vidbyte.tools.types import ToolCallContext


class ContinualTraceController:
    """Per-run controller for invoking ContinualTraceAgent at bounded intervals."""

    def __init__(self, *, option: TraceOption | None, runner: object, provider: str) -> None:
        # Initializes trace state and bookkeeping for one main-agent run.
        self.option = option
        self.runner = runner
        self.provider = provider
        self._artifact = option.schema.initial_artifact() if option is not None and option.enabled else {}
        self.update_count = 0
        self.error_count = 0
        self.last_error: str | None = None
        self._last_update_iteration: int | None = None
        self._finalized = False

    @property
    def enabled(self) -> bool:
        # Returns whether this controller should perform trace updates.
        return self.option is not None and self.option.enabled

    async def update_if_due(self, *, force: bool, iteration_count: int, context: "BaseAgentContext", messages: Sequence[Mapping[str, Any]], tool_calls: Sequence["ToolCallContext"], runtime_metadata: Mapping[str, Any]) -> None:
        # Runs a trace update when the configured interval or final update requires it.
        if not self.enabled or self.option is None:
            return
        if not self._should_update(force, iteration_count):
            return
        try:
            from vidbyte.agents.continual_trace import ContinualTraceAgent

            agent = ContinualTraceAgent(
                runner=self.runner,
                schema=self.option.schema,
                max_iterations=self.option.max_trace_iterations,
                provider=self.provider,
            )
            # The updated artifact is stored only on this controller for final metadata; it is
            # deliberately never appended to `messages` or the main agent context window.
            self._artifact = await agent.update(
                context_window=self._render_context_window(context, messages, tool_calls),
                trace_so_far=self._artifact,
                runtime_metadata=runtime_metadata,
            )
            if agent.last_error:
                self._record_error(agent.last_error)
            else:
                self.update_count += 1
                self.last_error = None
        except Exception as exc:
            self._record_error(f"{type(exc).__name__}: {exc}")
        finally:
            self._last_update_iteration = iteration_count
            if force:
                self._finalized = True

    def artifact(self) -> dict[str, Any]:
        # Returns the current trace artifact as a plain dictionary.
        return dict(self._artifact)

    def metadata(self) -> dict[str, Any]:
        # Returns compact trace bookkeeping suitable for AgentResult metadata.
        metadata = {
            "mode": self.option.mode.value if self.option is not None else None,
            "schema": self.option.schema.name if self.option is not None else None,
            "update_count": self.update_count,
            "error_count": self.error_count,
        }
        if self.last_error:
            metadata["last_error"] = self.last_error
        return metadata

    def _should_update(self, force: bool, iteration_count: int) -> bool:
        # Decides whether the current main-agent iteration should trigger a trace update.
        if self.option is None:
            return False
        if force:
            return not self._finalized
        if iteration_count <= 0 or iteration_count % self.option.every_n_iterations != 0:
            return False
        return self._last_update_iteration != iteration_count

    def _record_error(self, error: str) -> None:
        # Records a recoverable trace-agent error without changing the main run.
        self.error_count += 1
        self.last_error = error

    def _render_context_window(self, context: "BaseAgentContext", messages: Sequence[Mapping[str, Any]], tool_calls: Sequence["ToolCallContext"]) -> str:
        # Renders a read-only snapshot of the main agent context plus provider messages and tool summaries.
        sections = [context.build_context()]
        if messages:
            sections.append("Provider messages:\n" + json.dumps(tuple(messages), indent=2, sort_keys=True, default=str))
        if tool_calls:
            sections.append("Main tool calls:\n" + "\n".join(self._tool_call_summary(call) for call in tool_calls))
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _tool_call_summary(call: "ToolCallContext") -> str:
        # Renders one main-agent tool call without exposing trace-agent internal calls.
        status = call.state.value
        output = call.result.output if call.result is not None else None
        return f"- {call.tool_name} ({status}): args={dict(call.arguments)} output={output}"


__all__ = [
    "ContinualTraceController",
]
