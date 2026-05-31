"""Context Protocol Header

Description:
    Executes the Adversarial Reflection context-window algorithm.
Purpose:
    Runs scheduled adversarial critique inside the normal direct runtime loop
    and injects critique output as tool-like context for later iterations.
Architecture:
    - AdversarialReflectionRuntimeAlgorithm: Runtime adapter for scheduled critique.
Relations:
    Used by AgentRuntimeContextAlgorithms and AgentRuntime iteration hooks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms import AdversarialReflectionAlgorithm
from vidbyte.lib.dataclasses.agents import AgentRuntimeIterationState, AgentRuntimeIterationUpdate
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.adversarial_agent_tool import AdversarialAgentTool
from vidbyte.tools.types import ToolCall

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class AdversarialReflectionRuntimeAlgorithm:
    """Runtime adapter for scheduled adversarial context injection."""

    name = "adversarial_reflection"

    def __init__(self, runtime: AgentRuntime, algorithm: AdversarialReflectionAlgorithm) -> None:
        # Bind the generic runtime and public algorithm configuration.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Run the normal runtime once with an iteration hook that schedules critique.
        critiques: list[str] = []
        checkpoints: list[dict[str, Any]] = []
        tool = self._resolve_tool(runner=runner, context=context, provider=provider, invoke_runner=invoke_runner, runner_output_text=runner_output_text, metadata=metadata, trace_context=trace_context)

        async def iteration_hook(state: AgentRuntimeIterationState) -> AgentRuntimeIterationUpdate | AgentResult | None:
            # Run the scheduled adversarial tool when cadence and budgets allow it.
            if not self.algorithm.should_run_critique(iteration_count=state.iteration_count, critique_count=len(critiques), terminal=False):
                return None
            trajectory = self.algorithm.format_trajectory(task=message, output=runner_output_text(state.model_response) if state.model_response is not None else "", call_contexts=state.call_contexts, max_chars=self.algorithm.max_critique_chars * 3)
            call = ToolCall(
                tool.name,
                {
                    "task": message,
                    "trajectory": trajectory,
                    "iteration_count": state.iteration_count,
                    "critique_count": len(critiques),
                },
                metadata={"scheduled": True, "context_window_algorithm": self.name},
            )
            processed = await self.runtime.execute_scheduled_tool_call(
                tool,
                call,
                message=message,
                context=state.context,
                provider=provider,
                iteration_count=state.iteration_count,
                model_call_count=state.model_call_count,
                tokens_used=state.tokens_used,
                started_at=self.runtime.middleware.clock(),
                metadata={**dict(metadata or {}), "context_window_algorithm": self.name, "adversarial_stage": "critique"},
                model_response=state.model_response,
                trace_context=trace_context,
            )
            if isinstance(processed, AgentResult):
                return processed
            context_record, result = processed
            critique = self.algorithm.capture_critique(result.output)
            critiques.append(critique)
            checkpoints.append({"iteration_count": state.iteration_count, "status": result.status.value, "critique_chars": len(critique)})
            injected_context = replace(
                state.context,
                tool_calls=(*tuple(state.context.tool_calls), context_record),
                metadata={**dict(state.context.metadata), "context_window_algorithm": self.name, "adversarial_reflection_critique_count": len(critiques)},
            )
            return AgentRuntimeIterationUpdate(context=injected_context, tool_contexts=(context_record,))

        result = await self.runtime._arun_once(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata={**dict(metadata or {}), "context_window_algorithm": self.name},
            options=dict(options or {}),
            trace_context=trace_context,
            iteration_hook=iteration_hook,
        )
        return self._with_adversarial_metadata(result, critiques=critiques, checkpoints=checkpoints)

    def _resolve_tool(self, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AdversarialAgentTool:
        # Return the configured tool or build the default runner-backed critic.
        if self.algorithm.adversarial_tool is not None:
            return self.algorithm.adversarial_tool

        async def critique(arguments: Mapping[str, Any]) -> str:
            # Invoke the existing runner with adversarial prompts through middleware.
            raw_result, _ = await self.runtime._invoke_with_middleware(
                runner,
                self.algorithm.render_adversarial_prompt(
                    task=str(arguments.get("task", "")),
                    trajectory=str(arguments.get("trajectory", "")),
                    iteration_count=int(arguments.get("iteration_count", 0)),
                    critique_count=int(arguments.get("critique_count", 0)),
                ),
                {"system": self.algorithm.adversarial_system_prompt_text()},
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                iteration_count=int(arguments.get("iteration_count", 0)),
                model_call_count=0,
                call_contexts=(),
                tokens_used=None,
                started_at=self.runtime.middleware.clock(),
                metadata={**dict(metadata or {}), "context_window_algorithm": self.name, "adversarial_stage": "critique"},
                trace_context=trace_context,
            )
            if isinstance(raw_result, AgentResult):
                return raw_result.output
            return runner_output_text(raw_result)

        return AdversarialAgentTool(critique=critique, max_output_chars=self.algorithm.max_critique_chars)

    def _with_adversarial_metadata(self, result: AgentResult, *, critiques: list[str], checkpoints: list[dict[str, Any]]) -> AgentResult:
        # Attach structured adversarial reflection trace metadata to the final result.
        metadata = dict(result.metadata)
        metadata["context_window_algorithm"] = self.name
        metadata["adversarial_reflection"] = {
            "interval_iterations": self.algorithm.interval_iterations,
            "max_critiques": self.algorithm.max_critiques,
            "critique_count": len(critiques),
            "critiques": tuple(critiques),
            "checkpoints": tuple(dict(checkpoint) for checkpoint in checkpoints),
        }
        return AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=metadata)


__all__ = [
    "AdversarialReflectionRuntimeAlgorithm",
]

