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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.agents.algorithms import MultiProviderAgenticGraderRuntimeAlgorithm, ReflexionRuntimeAlgorithm
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

    def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | None:
        # Return the configured runtime algorithm implementation.
        if self.runtime.algorithm.reflexion is not None:
            return ReflexionRuntimeAlgorithm(self.runtime, self.runtime.algorithm.reflexion)
        if self.runtime.algorithm.multi_provider_agentic_grader is not None:
            return MultiProviderAgenticGraderRuntimeAlgorithm(self.runtime, self.runtime.algorithm.multi_provider_agentic_grader)
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
        return await algorithm.arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )


__all__ = [
    "AgentRuntimeContextAlgorithms",
]


