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

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms import ReflexionAlgorithm
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.tracing import SpanContext

if TYPE_CHECKING:
    from vidbyte.agents import AgentRuntime


class ReflexionRuntimeAlgorithm:
    """Runtime adapter for the Reflexion context-window algorithm."""

    name = "reflexion"

    def __init__(self, runtime: AgentRuntime, algorithm: ReflexionAlgorithm) -> None:
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Run Reflexion attempts, reflecting after failed trials."""
        reflections: list[str] = []
        failed_attempts: list[str] = []
        attempt_summaries: list[dict[str, Any]] = []
        last_result: AgentResult | None = None
        self.runtime.recorder.append("system_prompt")

        for trial_index in range(self.algorithm.max_trials):
            result = await self._run_trial(
                message,
                trial_index=trial_index,
                handle=handle,
                context=context,
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
                handle,
                task=message,
                failed_attempt=failed_attempt,
                reflections=reflections,
                context=context,
                metadata=metadata,
                trial_index=trial_index,
                trace_context=trace_context,
            )
            if isinstance(reflected, AgentResult):
                return self._with_reflexion_metadata(reflected, reflections=reflections, attempts=attempt_summaries)
            if reflected:
                reflections.append(reflected)

        assert last_result is not None
        return self._with_reflexion_metadata(last_result, reflections=reflections, attempts=attempt_summaries)

    async def _run_trial(self, message: str, *, trial_index: int, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, reflections: Sequence[str], failed_attempts: Sequence[str], trace_context: SpanContext | None) -> AgentResult:
        """Run one main Reflexion trial through the normal runtime loop."""
        self.runtime.recorder.append("reflexion_trial", iteration=trial_index)
        trial_context = self.algorithm.context_for_trial(
            context,
            task=message,
            reflections=reflections,
            failed_attempts=failed_attempts,
        )
        return await self.runtime._arun_once(
            message,
            handle=handle,
            context=trial_context,
            metadata=self._trial_metadata(metadata, trial_index=trial_index),
            options=dict(options or {}),
            trace_context=trace_context,
        )

    async def _reflect_after_failure(self, handle: RunnerHandle, *, task: str, failed_attempt: str, reflections: Sequence[str], context: BaseAgentContext, metadata: Mapping[str, Any] | None, trial_index: int, trace_context: SpanContext | None) -> str | AgentResult:
        """Run the reflection-stage model call through runtime middleware."""
        self.runtime.recorder.append("reflexion_reflection", iteration=trial_index)
        raw_result, _, _ = await self.runtime._invoke_with_middleware(
            handle,
            self.algorithm.render_reflection_prompt(
                task=task,
                failed_attempt=failed_attempt,
                reflections=reflections,
            ),
            {"system": self.algorithm.reflection_system_prompt()},
            context=context,
            iteration_count=trial_index,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._reflection_metadata(metadata, trial_index=trial_index),
            trace_context=trace_context,
        )
        if isinstance(raw_result, AgentResult):
            return raw_result
        return self.algorithm.capture_reflection(handle.extract_text(raw_result))

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
    def _attempt_summary(result: AgentResult, *, trial_index: int) -> dict[str, Any]:
        """Return compact metadata for one Reflexion trial."""
        return {
            "trial_index": trial_index,
            "stop_reason": ReflexionAlgorithm.stop_reason(result).value,
            "tool_call_count": dict(result.metadata).get("tool_call_count", 0),
        }

    @staticmethod
    def _with_reflexion_metadata(
        result: AgentResult,
        *,
        reflections: Sequence[str],
        attempts: Sequence[Mapping[str, Any]],
    ) -> AgentResult:
        """Attach Reflexion trial metadata to a runtime result."""
        metadata = dict(result.metadata)
        metadata["reflexion"] = {
            "trial_count": len(tuple(attempts)),
            "reflection_count": len(tuple(reflections)),
            "reflections": tuple(reflections),
            "attempts": tuple(dict(attempt) for attempt in attempts),
        }
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
        )


__all__ = [
    "ReflexionRuntimeAlgorithm",
]


