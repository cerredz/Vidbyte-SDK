"""Context Protocol Header

Description:
    Executes the Trajectory Checkpoint context-window algorithm for AgentRuntime.
Purpose:
    Injects deterministic progress checkpoints into the direct runtime loop.
Architecture:
    - TrajectoryCheckpointObserver: Builds checkpoints from iteration snapshots.
    - TrajectoryCheckpointRuntimeAlgorithm: Attaches observer to _arun_once.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes public config from context algorithms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms import TrajectoryCheckpoint, TrajectoryCheckpointAlgorithm
from vidbyte.context.templates import RecorderBase
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.tracing import SpanContext

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class TrajectoryCheckpointObserver:
    """Records iteration slots and returns checkpoint text at configured intervals."""

    def __init__(self, *, algorithm: TrajectoryCheckpointAlgorithm, recorder: RecorderBase) -> None:
        # Stores config, recorder, and mutable per-run checkpoint accounting.
        self.algorithm = algorithm
        self.recorder = recorder
        self._seen_iterations: set[int] = set()
        self._checkpoints: list[TrajectoryCheckpoint] = []

    def observe(self, snapshot: AgentIterationSnapshot) -> str | None:
        # Records the iteration and returns checkpoint text only at interval boundaries.
        if snapshot.iteration_count in self._seen_iterations:
            return None
        self._seen_iterations.add(snapshot.iteration_count)
        self.recorder.append("trajectory_checkpoint_iteration", iteration=snapshot.iteration_count)
        if not self.algorithm.should_checkpoint(snapshot.iteration_count, len(self._checkpoints)):
            return None
        checkpoint = self.algorithm.build_checkpoint(snapshot, checkpoint_index=len(self._checkpoints) + 1)
        self._checkpoints.append(checkpoint)
        self.recorder.append(
            "trajectory_checkpoint_injection",
            iteration=snapshot.iteration_count,
            checkpoint_index=checkpoint.checkpoint_index,
        )
        return checkpoint.to_context_text(max_chars=self.algorithm.max_checkpoint_chars, title=self.algorithm.checkpoint_title)

    def metadata(self) -> dict[str, Any]:
        # Returns compact structured metadata for the final AgentResult.
        return {
            "interval": self.algorithm.interval,
            "checkpoint_count": len(self._checkpoints),
            "checkpoints": tuple(self._checkpoint_metadata(checkpoint) for checkpoint in self._checkpoints),
        }

    @staticmethod
    def _checkpoint_metadata(checkpoint: TrajectoryCheckpoint) -> dict[str, Any]:
        # Converts one checkpoint into compact metadata without large rendered text.
        return {
            "iteration": checkpoint.iteration,
            "checkpoint_index": checkpoint.checkpoint_index,
            "score": checkpoint.score,
            "metadata": dict(checkpoint.metadata),
        }


class TrajectoryCheckpointRuntimeAlgorithm:
    """Runtime adapter for the Trajectory Checkpoint context-window algorithm."""

    name = "trajectory_checkpoints"

    def __init__(self, runtime: AgentRuntime, algorithm: TrajectoryCheckpointAlgorithm) -> None:
        # Stores the generic runtime and public algorithm configuration.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Runs the normal direct loop with an observer that can inject checkpoints.
        self.runtime.recorder.append("system_prompt")
        observer = TrajectoryCheckpointObserver(algorithm=self.algorithm, recorder=self.runtime.recorder)
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
            iteration_observer=observer.observe,
        )
        return self._with_trajectory_metadata(result, observer)

    @staticmethod
    def _with_trajectory_metadata(result: AgentResult, observer: TrajectoryCheckpointObserver) -> AgentResult:
        # Merges checkpoint metadata with normal runtime result metadata.
        metadata = dict(result.metadata)
        metadata["trajectory_checkpoints"] = observer.metadata()
        return AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=metadata)


__all__ = [
    "TrajectoryCheckpointObserver",
    "TrajectoryCheckpointRuntimeAlgorithm",
]
