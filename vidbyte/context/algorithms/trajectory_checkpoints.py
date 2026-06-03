"""Context Protocol Header

Description:
    Implements the public Trajectory Checkpoint context-window algorithm.
Purpose:
    Adds deterministic runtime checkpoints through ContextManager primitives.
Architecture:
    - TrajectoryCheckpointAlgorithm: Frozen config and inner-loop lifecycle implementation.
Relations:
    Used by ContextWindow presets and AgentRuntime inner-loop lifecycle dispatch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives import TrajectoryCheckpointContextItem
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.errors import ConfigurationError

_MAX_CHECKPOINT_CHARS_LIMIT = 100_000
_MAX_FIELD_CHARS_LIMIT = 25_000
_STATE_KEY = "_trajectory_checkpoints_state"


@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm(InnerContextWindowAlgorithm):
    """Deterministic inner-loop trajectory checkpoint algorithm config."""

    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    score_enabled: bool = True
    checkpoint_title: str = "Runtime Checkpoint"
    placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates public config values before runtime execution starts.
        _validate_positive("interval", self.interval)
        _validate_positive("max_checkpoints", self.max_checkpoints)
        _validate_limit("max_checkpoint_chars", self.max_checkpoint_chars, _MAX_CHECKPOINT_CHARS_LIMIT)
        _validate_limit("max_field_chars", self.max_field_chars, _MAX_FIELD_CHARS_LIMIT)
        _validate_non_empty("checkpoint_title", self.checkpoint_title)
        _validate_metadata_keys(self.metadata)
        object.__setattr__(self, "placement", ContextWindowPlacement(self.placement))

    def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Single inner-loop hook: initializes on the first call, then checkpoints per cadence.
        state = self._state(ctx)
        snapshot = ctx.iteration
        if snapshot is None:
            # Run-start initialization: record the system prompt and publish empty metadata.
            ctx.record("system_prompt")
            self._publish_metadata(ctx, state)
            return
        seen = state["seen_iterations"]
        if snapshot.iteration_count in seen:
            return
        seen.add(snapshot.iteration_count)
        ctx.record("trajectory_checkpoint_iteration", iteration=snapshot.iteration_count)
        checkpoints = state["checkpoints"]
        if self.should_checkpoint(snapshot.iteration_count, len(checkpoints)):
            item = self.build_item(snapshot, checkpoint_index=len(checkpoints) + 1)
            self._place_checkpoint(ctx, item)
            checkpoints.append(self._checkpoint_record(item))
            ctx.record("trajectory_checkpoint_injection", iteration=item.iteration, checkpoint_index=item.checkpoint_index)
        self._publish_metadata(ctx, state)

    def _place_checkpoint(self, ctx: ContextWindowRunContext, item: TrajectoryCheckpointContextItem) -> None:
        # Writes the checkpoint through the configured placement using semantic manager methods.
        if self.placement is ContextWindowPlacement.TOP_OF_CONTEXT:
            ctx.place_after_system_prompt(item)
        elif self.placement is ContextWindowPlacement.END_OF_CONTEXT:
            ctx.place_after_tools(item)
        else:
            ctx.context_manager.upsert(item, placement=self.placement)

    def _publish_metadata(self, ctx: ContextWindowRunContext, state: dict[str, Any]) -> None:
        # Publishes compact checkpoint metadata for the final AgentResult.
        ctx.set_metadata(
            "trajectory_checkpoints",
            {
                "interval": self.interval,
                "checkpoint_count": len(state["checkpoints"]),
                "placement": self.placement.value,
                "checkpoints": tuple(state["checkpoints"]),
            },
        )

    def should_checkpoint(self, iteration_count: int, checkpoint_count: int) -> bool:
        # Returns whether this completed iteration should produce a checkpoint.
        if checkpoint_count >= self.max_checkpoints:
            return False
        return iteration_count > 0 and iteration_count % self.interval == 0

    def build_item(self, snapshot: AgentIterationSnapshot, *, checkpoint_index: int) -> TrajectoryCheckpointContextItem:
        # Builds a typed context primitive from observable runtime state.
        score = self._score(snapshot) if self.score_enabled else None
        return TrajectoryCheckpointContextItem(
            primitive_id=f"trajectory_checkpoint:{checkpoint_index}",
            iteration=snapshot.iteration_count,
            checkpoint_index=checkpoint_index,
            reasoning_summary=self._reasoning_summary(snapshot),
            trajectory=self._trajectory(snapshot),
            output=self._output(snapshot),
            score=score,
            feedback=self._feedback(snapshot, score),
            title=self.checkpoint_title,
            max_chars=self.max_checkpoint_chars,
            metadata={
                "iteration": snapshot.iteration_count,
                "checkpoint_index": checkpoint_index,
                "tool_call_count": len(snapshot.tool_calls),
                "tokens_used": snapshot.tokens_used,
                **dict(self.metadata),
            },
        )

    def _state(self, ctx: ContextWindowRunContext) -> dict[str, Any]:
        # Returns the mutable per-run trajectory checkpoint state.
        return ctx.state.setdefault(_STATE_KEY, {"seen_iterations": set(), "checkpoints": []})

    def _reasoning_summary(self, snapshot: AgentIterationSnapshot) -> str:
        # Summarizes observable progress without claiming hidden chain-of-thought.
        parts = [
            f"Observed iteration {snapshot.iteration_count} for the original task.",
            f"Tool calls recorded so far: {len(snapshot.tool_calls)}.",
        ]
        if snapshot.assistant_output:
            parts.append("The agent produced intermediate assistant output before this checkpoint.")
        if snapshot.tokens_used is not None:
            parts.append(f"Provider-reported tokens used so far: {snapshot.tokens_used}.")
        return _truncate(" ".join(parts), self.max_field_chars)

    def _trajectory(self, snapshot: AgentIterationSnapshot) -> str:
        # Formats recent observable assistant and tool states into a compact trajectory.
        lines: list[str] = []
        if snapshot.assistant_output:
            lines.append(f"Assistant output: {_truncate(snapshot.assistant_output, self.max_field_chars)}")
        for call in snapshot.tool_calls[-5:]:
            state = getattr(getattr(call, "state", None), "value", str(getattr(call, "state", "unknown")))
            result = getattr(call, "result", None)
            output = getattr(result, "output", "") if result is not None else ""
            detail = f"; output={_truncate(str(output), 160)}" if self.include_tool_outputs and output else ""
            lines.append(f"Tool {call.tool_name}: {state}{detail}")
        if not lines:
            lines.append("No new observable events.")
        return _truncate("\n".join(lines), self.max_field_chars)

    def _output(self, snapshot: AgentIterationSnapshot) -> str:
        # Selects the latest observable assistant or tool output summary.
        if snapshot.assistant_output:
            return _truncate(snapshot.assistant_output, self.max_field_chars)
        if snapshot.tool_calls:
            latest = snapshot.tool_calls[-1]
            result = getattr(latest, "result", None)
            output = getattr(result, "output", "") if result is not None else ""
            if self.include_tool_outputs and output:
                return _truncate(str(output), self.max_field_chars)
            state = getattr(getattr(latest, "state", None), "value", str(getattr(latest, "state", "unknown")))
            return f"Latest tool call '{latest.tool_name}' finished with state '{state}'."
        return "No output has been observed yet."

    def _score(self, snapshot: AgentIterationSnapshot) -> float:
        # Computes a deterministic heuristic score from observable tool states.
        if not snapshot.tool_calls:
            return 0.5 if snapshot.assistant_output else 0.0
        total = len(snapshot.tool_calls)
        succeeded = sum(1 for call in snapshot.tool_calls if getattr(getattr(call, "state", None), "value", "") == "succeeded")
        denied_or_failed = sum(1 for call in snapshot.tool_calls if getattr(getattr(call, "state", None), "value", "") in {"denied", "failed"})
        score = max(0.0, min(1.0, (succeeded / total) - (denied_or_failed * 0.2 / total)))
        return round(score, 2)

    def _feedback(self, snapshot: AgentIterationSnapshot, score: float | None) -> str:
        # Produces deterministic next-step guidance from observable progress.
        if score is not None and score < 0.5:
            return "Re-check the task, address failed or denied tool calls, and choose the next action deliberately."
        if snapshot.assistant_output and not snapshot.tool_calls:
            return "Continue toward a final answer or call a tool if more evidence is needed."
        if snapshot.tool_calls:
            return "Use the observed tool outcomes to decide the next concrete step toward completion."
        return "Continue gathering evidence and avoid losing sight of the original task."

    @staticmethod
    def _checkpoint_record(item: TrajectoryCheckpointContextItem) -> dict[str, Any]:
        # Converts one checkpoint item into compact final-result metadata.
        return {
            "primitive_id": item.primitive_id,
            "iteration": item.iteration,
            "checkpoint_index": item.checkpoint_index,
            "score": item.score,
            "metadata": dict(item.metadata),
        }


def _validate_positive(field_name: str, value: int) -> None:
    # Raises ConfigurationError if a numeric field is not positive.
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")


def _validate_limit(field_name: str, value: int, limit: int) -> None:
    # Raises ConfigurationError if a character limit is outside bounds.
    _validate_positive(field_name, value)
    if value > limit:
        raise ConfigurationError(f"{field_name} exceeds limit of {limit}.")


def _validate_non_empty(field_name: str, value: str) -> None:
    # Raises ConfigurationError if a public string field is blank.
    if not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if metadata contains non-string keys.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


def _truncate(value: str, max_chars: int) -> str:
    # Returns a string bounded by max_chars including the truncation suffix.
    suffix = "\n...[truncated]"
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)].rstrip() + suffix


__all__ = [
    "TrajectoryCheckpointAlgorithm",
]
