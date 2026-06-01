"""Context Protocol Header

Description:
    Executes the Adversarial Reflection context-window algorithm.
Purpose:
    Runs scheduled adversarial critique inside the normal direct runtime loop
    and injects critique output as tool-like context for later iterations.
Architecture:
    - AdversarialReflectionRuntimeAlgorithm: Runtime adapter for scheduled critique.
    - _DefaultCritiqueCallable: Callable class that runs the runner as the internal critic.
    - _IterationHook: Callable class that schedules and records each critique invocation.
Relations:
    Used by AgentRuntimeContextAlgorithms and AgentRuntime iteration hooks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.agents.hooks.iteration_hooks import AgentRuntimeIterationHook
from vidbyte.context.algorithms import AdversarialReflectionAlgorithm
from vidbyte.lib.dataclasses.agents import AgentRuntimeIterationState, AgentRuntimeIterationUpdate
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.adversarial_agent_tool import AdversarialAgentTool
from vidbyte.tools.types import ToolCall

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class _DefaultCritiqueCallable:
    """Invokes the agent runner with adversarial prompts as the internal default critic."""

    def __init__(
        self,
        *,
        algorithm: AdversarialReflectionAlgorithm,
        runtime: AgentRuntime,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        algorithm_name: str,
        metadata: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> None:
        # Store all dependencies needed to invoke the runner as an adversarial critic.
        self._algorithm = algorithm
        self._runtime = runtime
        self._runner = runner
        self._context = context
        self._provider = provider
        self._invoke_runner = invoke_runner
        self._runner_output_text = runner_output_text
        self._algorithm_name = algorithm_name
        self._metadata = metadata
        self._trace_context = trace_context

    async def __call__(self, arguments: Mapping[str, Any]) -> str:
        # Render the adversarial prompt and invoke the runner through middleware.
        prompt = self._algorithm.render_adversarial_prompt(
            task=str(arguments.get("task", "")),
            trajectory=str(arguments.get("trajectory", "")),
            iteration_count=int(arguments.get("iteration_count", 0)),
            critique_count=int(arguments.get("critique_count", 0)),
        )
        raw_result, _ = await self._runtime._invoke_with_middleware(
            self._runner,
            prompt,
            {"system": self._algorithm.adversarial_system_prompt_text()},
            context=self._context,
            provider=self._provider,
            invoke_runner=self._invoke_runner,
            runner_output_text=self._runner_output_text,
            iteration_count=int(arguments.get("iteration_count", 0)),
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self._runtime.middleware.clock(),
            metadata={**dict(self._metadata or {}), "context_window_algorithm": self._algorithm_name, "adversarial_stage": "critique"},
            trace_context=self._trace_context,
        )
        if isinstance(raw_result, AgentResult):
            return raw_result.output
        return self._runner_output_text(raw_result)


class _IterationHook:
    """Schedules and records each adversarial critique invocation after completed iterations."""

    def __init__(
        self,
        *,
        algorithm: AdversarialReflectionAlgorithm,
        runtime: AgentRuntime,
        message: str,
        tool: AdversarialAgentTool,
        algorithm_name: str,
        provider: str,
        runner_output_text: Callable[[object], str],
        metadata: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> None:
        # Store per-run state alongside configuration for hook invocations.
        self._algorithm = algorithm
        self._runtime = runtime
        self._message = message
        self._tool = tool
        self._algorithm_name = algorithm_name
        self._provider = provider
        self._runner_output_text = runner_output_text
        self._metadata = metadata
        self._trace_context = trace_context
        self.critiques: list[str] = []
        self.checkpoints: list[dict[str, Any]] = []

    async def __call__(
        self, state: AgentRuntimeIterationState
    ) -> AgentRuntimeIterationUpdate | AgentResult | None:
        # Skip this iteration if the scheduling cadence or budget does not allow a critique.
        if not self._algorithm.should_run_critique(
            iteration_count=state.iteration_count,
            critique_count=len(self.critiques),
            terminal=False,
        ):
            return None
        return await self._run_scheduled_critique(state)

    async def _run_scheduled_critique(
        self, state: AgentRuntimeIterationState
    ) -> AgentRuntimeIterationUpdate | AgentResult | None:
        # Build the tool call for this critique and execute it through the scheduled executor.
        call = self._build_critique_call(state)
        processed = await self._runtime.execute_scheduled_tool_call(
            self._tool,
            call,
            message=self._message,
            context=state.context,
            provider=self._provider,
            iteration_count=state.iteration_count,
            model_call_count=state.model_call_count,
            tokens_used=state.tokens_used,
            started_at=self._runtime.middleware.clock(),
            metadata={**dict(self._metadata or {}), "context_window_algorithm": self._algorithm_name, "adversarial_stage": "critique"},
            model_response=state.model_response,
            trace_context=self._trace_context,
        )
        if isinstance(processed, AgentResult):
            return processed
        context_record, result = processed
        return self._record_and_inject_critique(state, context_record=context_record, result=result)

    def _build_critique_call(self, state: AgentRuntimeIterationState) -> ToolCall:
        # Assemble the ToolCall arguments from current runtime state and trajectory.
        model_output = self._runner_output_text(state.model_response) if state.model_response is not None else ""
        trajectory = self._algorithm.format_trajectory(
            task=self._message,
            output=model_output,
            call_contexts=state.call_contexts,
            max_chars=self._algorithm.max_critique_chars * 3,
        )
        return ToolCall(
            self._tool.name,
            {
                "task": self._message,
                "trajectory": trajectory,
                "iteration_count": state.iteration_count,
                "critique_count": len(self.critiques),
            },
            metadata={"scheduled": True, "context_window_algorithm": self._algorithm_name},
        )

    def _record_and_inject_critique(
        self,
        state: AgentRuntimeIterationState,
        *,
        context_record: Any,
        result: Any,
    ) -> AgentRuntimeIterationUpdate:
        # Capture the critique text, record the checkpoint, and return a context update.
        critique = self._algorithm.capture_critique(result.output)
        self.critiques.append(critique)
        self.checkpoints.append({
            "iteration_count": state.iteration_count,
            "status": result.status.value,
            "critique_chars": len(critique),
        })
        injected_context = replace(
            state.context,
            tool_calls=(*tuple(state.context.tool_calls), context_record),
            metadata={
                **dict(state.context.metadata),
                "context_window_algorithm": self._algorithm_name,
                "adversarial_reflection_critique_count": len(self.critiques),
            },
        )
        return AgentRuntimeIterationUpdate(context=injected_context, tool_contexts=(context_record,))


class AdversarialReflectionRuntimeAlgorithm:
    """Runtime adapter for scheduled adversarial context injection."""

    name = "adversarial_reflection"

    def __init__(self, runtime: AgentRuntime, algorithm: AdversarialReflectionAlgorithm) -> None:
        # Bind the generic runtime and public algorithm configuration.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        # Resolve the critique tool and build a per-run hook that records all critiques.
        tool = self._resolve_tool(
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )
        hook = self._build_iteration_hook(
            message=message,
            tool=tool,
            provider=provider,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )

        # Execute the normal runtime loop with the scheduled-critique hook attached.
        result = await self._execute_with_hook(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
            hook=hook,
        )

        # Attach the adversarial critique trace and counts to the final result.
        return self._with_adversarial_metadata(result, hook=hook)

    def _resolve_tool(
        self,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        metadata: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> AdversarialAgentTool:
        # Return the developer-supplied tool or build the internal default critic.
        if self.algorithm.adversarial_tool is not None:
            return self.algorithm.adversarial_tool
        return AdversarialAgentTool(
            critique=_DefaultCritiqueCallable(
                algorithm=self.algorithm,
                runtime=self.runtime,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                algorithm_name=self.name,
                metadata=metadata,
                trace_context=trace_context,
            ),
            max_output_chars=self.algorithm.max_critique_chars,
        )

    def _build_iteration_hook(
        self,
        *,
        message: str,
        tool: AdversarialAgentTool,
        provider: str,
        runner_output_text: Callable[[object], str],
        metadata: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
    ) -> _IterationHook:
        # Construct the stateful hook that will schedule critiques and record their results.
        return _IterationHook(
            algorithm=self.algorithm,
            runtime=self.runtime,
            message=message,
            tool=tool,
            algorithm_name=self.name,
            provider=provider,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )

    async def _execute_with_hook(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: SpanContext | None,
        hook: AgentRuntimeIterationHook,
    ) -> AgentResult:
        # Delegate to the runtime's direct loop with the critique hook registered.
        return await self.runtime._arun_once(
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
            iteration_hook=hook,
        )

    def _with_adversarial_metadata(self, result: AgentResult, *, hook: _IterationHook) -> AgentResult:
        # Attach structured adversarial reflection trace metadata to the final result.
        metadata = dict(result.metadata)
        metadata["context_window_algorithm"] = self.name
        metadata["adversarial_reflection"] = {
            "interval_iterations": self.algorithm.interval_iterations,
            "max_critiques": self.algorithm.max_critiques,
            "critique_count": len(hook.critiques),
            "critiques": tuple(hook.critiques),
            "checkpoints": tuple(dict(c) for c in hook.checkpoints),
        }
        return AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=metadata)


__all__ = [
    "AdversarialReflectionRuntimeAlgorithm",
]
