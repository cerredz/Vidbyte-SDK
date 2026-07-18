"""Context Protocol Header

Description:
    Dispatches attached context-window algorithms for AgentRuntime.
Purpose:
    Keeps AgentRuntime focused on the generic model/tool loop while providing a
    clean detection and adapter surface for runtime context-window algorithms.
Architecture:
    - AgentRuntimeContextAlgorithms: Detects configured algorithms and returns
      per-algorithm runtime implementations.
Relations:
    Used by vidbyte.agents.runtime.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.agents.algorithms import (
    CritiqueAdjudicateReviseRuntimeAlgorithm,
    IndependentCriticRuntimeAlgorithm,
    MultiProviderAgenticGraderRuntimeAlgorithm,
    ReflexionRuntimeAlgorithm,
)
from vidbyte.context.runtime import InnerContextWindowAlgorithm
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult

if TYPE_CHECKING:
    from vidbyte.agents.runtimes import LinearAgentRuntime as AgentRuntime

_CONTENT_FREE_ALGORITHMS = frozenset({"independent_critic", "critique_adjudicate_revise"})


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
        if self.runtime.algorithm.independent_critic is not None:
            return "independent_critic"
        if self.runtime.algorithm.trajectory_checkpoints is not None:
            return "trajectory_checkpoints"
        if self.runtime.algorithm.problem_space_search is not None:
            return "problem_space_search"
        if self.runtime.algorithm.error_correction is not None:
            return "error_correction"
        if self.runtime.algorithm.critique_adjudicate_revise is not None:
            return "critique_adjudicate_revise"
        return None

    def is_algorithm(self, name: str) -> bool:
        # Return whether the configured runtime algorithm matches name.
        return self.detect_algorithm() == name

    def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | IndependentCriticRuntimeAlgorithm | CritiqueAdjudicateReviseRuntimeAlgorithm | None:
        # Return the configured runtime algorithm implementation.
        if self.runtime.algorithm.reflexion is not None:
            return ReflexionRuntimeAlgorithm(self.runtime, self.runtime.algorithm.reflexion)
        if self.runtime.algorithm.multi_provider_agentic_grader is not None:
            return MultiProviderAgenticGraderRuntimeAlgorithm(self.runtime, self.runtime.algorithm.multi_provider_agentic_grader)
        if self.runtime.algorithm.independent_critic is not None:
            return IndependentCriticRuntimeAlgorithm(self.runtime, self.runtime.algorithm.independent_critic)
        if self.runtime.algorithm.critique_adjudicate_revise is not None:
            return CritiqueAdjudicateReviseRuntimeAlgorithm(self.runtime, self.runtime.algorithm.critique_adjudicate_revise)
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
        span_attributes: dict[str, Any] = {"algorithm": algorithm_name}
        if algorithm_name == "critique_adjudicate_revise":
            span_attributes["task_hash"] = hashlib.sha256(message.encode("utf-8")).hexdigest()
        elif algorithm_name != "independent_critic":
            span_attributes["message"] = message
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
            if algorithm_name == "critique_adjudicate_revise":
                output = "succeeded"
            elif algorithm_name == "independent_critic":
                output = None
            else:
                output = result.output
            self._end_algorithm_span(span, output=output)
            return result
        except BaseException as exc:
            if algorithm_name in _CONTENT_FREE_ALGORITHMS:
                trace_error = _content_free_algorithm_error(exc, algorithm_name)
            else:
                trace_error = exc
            self._end_algorithm_span(span, error=trace_error)
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


def _content_free_algorithm_error(exc: BaseException, algorithm_name: str) -> RuntimeError:
    # Preserve only the exception type in review-algorithm span telemetry.
    label = algorithm_name.replace("_", " ")
    return RuntimeError(f"{label} failed with {type(exc).__name__}.")


__all__ = [
    "AgentRuntimeContextAlgorithms",
]
