"""Context Protocol Header

Description:
    Dispatches attached context-window algorithms for AgentRuntime.
Purpose:
    Keeps AgentRuntime focused on the generic model/tool loop while providing a
    clean detection and adapter surface for runtime context-window algorithms;
    privacy-sensitive algorithms can suppress content-bearing structural traces.
Architecture:
    - AgentRuntimeContextAlgorithms: Detects configured algorithms and returns
      per-algorithm runtime implementations, including the return-level
      PairwiseTournamentRuntimeAlgorithm.
Relations:
    Used by vidbyte.agents.runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.agents.algorithms import MultiProviderAgenticGraderRuntimeAlgorithm, PairwiseTournamentRuntimeAlgorithm, ReflexionRuntimeAlgorithm
from vidbyte.context.runtime import InnerContextWindowAlgorithm
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult

if TYPE_CHECKING:
    from vidbyte.agents.runtimes import LinearAgentRuntime as AgentRuntime


class AgentRuntimeContextAlgorithms:
    """Adapter surface for context-window algorithms attached to an agent."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    def detect_algorithm(self) -> str | None:
        # Return the configured runtime algorithm name, if any.
        if self.runtime.algorithm.reflexion is not None:
            return "reflexion"
        if self.runtime.algorithm.multi_provider_agentic_grader is not None:
            return "multi_provider_agentic_grader"
        if self.runtime.algorithm.pairwise_tournament is not None:
            return "pairwise_tournament"
        if self.runtime.algorithm.trajectory_checkpoints is not None:
            return "trajectory_checkpoints"
        if self.runtime.algorithm.problem_space_search is not None:
            return "problem_space_search"
        if self.runtime.algorithm.error_correction is not None:
            return "error_correction"
        return None

    def is_algorithm(self, name: str) -> bool:
        # Return whether the configured runtime algorithm matches name.
        return self.detect_algorithm() == name

    def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | PairwiseTournamentRuntimeAlgorithm | None:
        # Return the configured runtime algorithm implementation.
        if self.runtime.algorithm.reflexion is not None:
            return ReflexionRuntimeAlgorithm(self.runtime, self.runtime.algorithm.reflexion)
        if self.runtime.algorithm.multi_provider_agentic_grader is not None:
            return MultiProviderAgenticGraderRuntimeAlgorithm(self.runtime, self.runtime.algorithm.multi_provider_agentic_grader)
        if self.runtime.algorithm.pairwise_tournament is not None:
            return PairwiseTournamentRuntimeAlgorithm(self.runtime, self.runtime.algorithm.pairwise_tournament)
        return None

    def inner_loop_algorithm(self) -> InnerContextWindowAlgorithm | None:
        # Return the configured inner-loop context-window algorithm, if any.
        if self.runtime.algorithm.trajectory_checkpoints is not None:
            return self.runtime.algorithm.trajectory_checkpoints
        if self.runtime.algorithm.problem_space_search is not None:
            return self.runtime.algorithm.problem_space_search
        if self.runtime.algorithm.error_correction is not None:
            return self.runtime.algorithm.error_correction
        return None

    def has_inner_loop_algorithm(self) -> bool:
        # Return whether the active algorithm updates context inside _arun_once.
        return self.inner_loop_algorithm() is not None

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult | None:
        """Run the configured algorithm, or return None when no algorithm exists."""
        algorithm = self.return_algorithm()
        if algorithm is None:
            return None
        algorithm_name = self.detect_algorithm() or "unknown"
        content_private = algorithm_name == "pairwise_tournament"
        span_attributes = {"algorithm": algorithm_name} if content_private else {"algorithm": algorithm_name, "message": message}
        span = self._start_algorithm_span(trace_context, **span_attributes)
        try:
            result = await algorithm.arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=span or trace_context,
            )
            self._end_algorithm_span(span, output="completed" if content_private else result.output)
            return result
        except BaseException as exc:
            if content_private:
                self._end_algorithm_span(span, output="failed")
            else:
                self._end_algorithm_span(span, error=exc)
            raise

    def _start_algorithm_span(self, parent: SpanContext | None, **attributes: Any) -> SpanContext | None:
        # Opens an algorithm span only when semantic tracing is active.
        if not _is_semantic_tracer(self.runtime._tracer):
            return None
        return self.runtime._tracer.start_span("algorithm." + str(attributes.get("algorithm", "unknown")), parent=parent, **attributes)

    def _end_algorithm_span(self, span: SpanContext | None, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes an algorithm span only when one was opened.
        if span is not None:
            self.runtime._tracer.end_span(span, output=output, error=error)


def _is_semantic_tracer(tracer: object) -> bool:
    # Detects TraceController-like tracers without importing vidbyte.trace during agent initialization.
    return all(hasattr(tracer, attr) for attr in ("inner", "profile", "translator"))


__all__ = [
    "AgentRuntimeContextAlgorithms",
]


