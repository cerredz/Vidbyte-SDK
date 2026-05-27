"""Context Protocol Header

Description:
    Executes the Reflexion context-window algorithm for AgentRuntime.
Purpose:
    Keeps Reflexion trial, reflection, and retry orchestration out of the
    generic agent runtime loop.
Architecture:
    - ReflexionRuntimeAlgorithm: Runs main trials and reflection-stage calls.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes ReflexionAlgorithm config
    from vidbyte.context.algorithms.reflexion.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms import ReflexionAlgorithm
from vidbyte.lib.tracing import SpanContext
from vidbyte.strategies.types import BaseAgentContext, StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents import AgentRuntime


class ReflexionRuntimeAlgorithm:
    """Runtime adapter for the Reflexion context-window algorithm."""

    name = "reflexion"

    def __init__(self, runtime: AgentRuntime, algorithm: ReflexionAlgorithm) -> None:
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
    ) -> StrategyResult:
        """Run Reflexion attempts, reflecting after failed trials."""
        reflections: list[str] = []
        failed_attempts: list[str] = []
        attempt_summaries: list[dict[str, Any]] = []
        last_result: StrategyResult | None = None

        for trial_index in range(self.algorithm.max_trials):
            result = await self._run_trial(
                message,
                trial_index=trial_index,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
                metadata=metadata,
                options=options,
                reflections=reflections,
                failed_attempts=failed_attempts,
                trace_context=trace_context,
            )
            last_result = result
            failed_attempt = self.algorithm.format_failed_attempt(result)
            attempt_summaries.append(self._attempt_summary(result, trial_index=trial_index))
            if not self.algorithm.should_reflect(result, trial_index=trial_index):
                return self._with_reflexion_metadata(result, reflections=reflections, attempts=attempt_summaries)

            failed_attempts.append(failed_attempt)
            reflected = await self._reflect_after_failure(
                runner,
                task=message,
                failed_attempt=failed_attempt,
                reflections=reflections,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                metadata=metadata,
                trial_index=trial_index,
                trace_context=trace_context,
            )
            if isinstance(reflected, StrategyResult):
                return self._with_reflexion_metadata(reflected, reflections=reflections, attempts=attempt_summaries)
            if reflected:
                reflections.append(reflected)

        assert last_result is not None
        return self._with_reflexion_metadata(last_result, reflections=reflections, attempts=attempt_summaries)

    async def _run_trial(
        self,
        message: str,
        *,
        trial_index: int,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        reflections: Sequence[str],
        failed_attempts: Sequence[str],
        trace_context: SpanContext | None,
    ) -> StrategyResult:
        """Run one main Reflexion trial through the normal runtime loop."""
        trial_context = self.algorithm.context_for_trial(
            context,
            task=message,
            reflections=reflections,
            failed_attempts=failed_attempts,
        )
        return await self.runtime._arun_once(
            message,
            runner=runner,
            context=trial_context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=self._trial_metadata(metadata, trial_index=trial_index),
            options=dict(options or {}),
            trace_context=trace_context,
        )

    async def _reflect_after_failure(
        self,
        runner: object,
        *,
        task: str,
        failed_attempt: str,
        reflections: Sequence[str],
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        metadata: Mapping[str, Any] | None,
        trial_index: int,
        trace_context: SpanContext | None,
    ) -> str | StrategyResult:
        """Run the reflection-stage model call through runtime middleware."""
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            self.algorithm.render_reflection_prompt(
                task=task,
                failed_attempt=failed_attempt,
                reflections=reflections,
            ),
            {"system": self.algorithm.reflection_system_prompt()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=trial_index,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._reflection_metadata(metadata, trial_index=trial_index),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return raw_result
        return self.algorithm.capture_reflection(runner_output_text(raw_result))

    @staticmethod
    def _trial_metadata(
        metadata: Mapping[str, Any] | None,
        *,
        trial_index: int,
    ) -> dict[str, Any]:
        """Build metadata passed into a main Reflexion trial."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "reflexion",
            "reflexion_trial_index": trial_index,
        }

    @staticmethod
    def _reflection_metadata(
        metadata: Mapping[str, Any] | None,
        *,
        trial_index: int,
    ) -> dict[str, Any]:
        """Build metadata passed into a Reflexion reflection-stage call."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "reflexion",
            "reflexion_stage": "reflect",
            "reflexion_trial_index": trial_index,
        }

    @staticmethod
    def _attempt_summary(result: StrategyResult, *, trial_index: int) -> dict[str, Any]:
        """Return compact metadata for one Reflexion trial."""
        return {
            "trial_index": trial_index,
            "stop_reason": ReflexionAlgorithm.stop_reason(result).value,
            "tool_call_count": dict(result.metadata).get("tool_call_count", 0),
        }

    @staticmethod
    def _with_reflexion_metadata(
        result: StrategyResult,
        *,
        reflections: Sequence[str],
        attempts: Sequence[Mapping[str, Any]],
    ) -> StrategyResult:
        """Attach Reflexion trial metadata to a runtime result."""
        metadata = dict(result.metadata)
        metadata["reflexion"] = {
            "trial_count": len(tuple(attempts)),
            "reflection_count": len(tuple(reflections)),
            "reflections": tuple(reflections),
            "attempts": tuple(dict(attempt) for attempt in attempts),
        }
        return StrategyResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
        )


__all__ = [
    "ReflexionRuntimeAlgorithm",
]
