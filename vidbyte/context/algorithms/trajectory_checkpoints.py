"""Context Protocol Header

Description:
    Implements the public Trajectory Checkpoint context-window algorithm config.
Purpose:
    Provides deterministic checkpoint rendering from observable runtime state.
Architecture:
    - TrajectoryCheckpoint: Renderable checkpoint value object.
    - TrajectoryCheckpointAlgorithm: Public immutable algorithm configuration.
Relations:
    Used by ContextWindow presets and TrajectoryCheckpointRuntimeAlgorithm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.errors import ConfigurationError

_MAX_CHECKPOINT_CHARS_LIMIT = 100_000
_MAX_FIELD_CHARS_LIMIT = 25_000
_TRUNCATION_SUFFIX = "\n...[truncated]"


@dataclass(frozen=True, slots=True)
class TrajectoryCheckpoint:
    """Structured runtime checkpoint rendered into the model-visible window."""

    iteration: int
    checkpoint_index: int
    reasoning_summary: str
    trajectory: str
    output: str
    score: float | None
    feedback: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context_text(self, *, max_chars: int, title: str) -> str:
        # Renders the checkpoint with stable required section order and a final size bound.
        score_text = "N/A" if self.score is None else f"{self.score:.2f}"
        text = "\n".join(
            (
                f"## {title}",
                f"Iteration: {self.iteration}",
                f"Checkpoint: {self.checkpoint_index}",
                "",
                "### Reasoning Summary",
                self.reasoning_summary,
                "",
                "### Trajectory",
                self.trajectory,
                "",
                "### Output",
                self.output,
                "",
                "### Score",
                score_text,
                "",
                "### Feedback",
                self.feedback,
            )
        )
        return _truncate(text, max_chars)


@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm:
    """Public immutable config for periodic trajectory checkpoints."""

    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    score_enabled: bool = True
    checkpoint_title: str = "Runtime Checkpoint"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all public config fields so invalid algorithms fail before runtime.
        _validate_positive("interval", self.interval)
        _validate_positive("max_checkpoints", self.max_checkpoints)
        _validate_limit("max_checkpoint_chars", self.max_checkpoint_chars, _MAX_CHECKPOINT_CHARS_LIMIT)
        _validate_limit("max_field_chars", self.max_field_chars, _MAX_FIELD_CHARS_LIMIT)
        _validate_non_empty("checkpoint_title", self.checkpoint_title)
        _validate_metadata_keys(self.metadata)

    def should_checkpoint(self, iteration_count: int, checkpoint_count: int) -> bool:
        # Returns whether this completed iteration should inject a checkpoint.
        if checkpoint_count >= self.max_checkpoints:
            return False
        return iteration_count > 0 and iteration_count % self.interval == 0

    def build_checkpoint(self, snapshot: AgentIterationSnapshot, *, checkpoint_index: int) -> TrajectoryCheckpoint:
        # Builds a bounded checkpoint from observable runtime state only.
        score = self._score(snapshot) if self.score_enabled else None
        return TrajectoryCheckpoint(
            iteration=snapshot.iteration_count,
            checkpoint_index=checkpoint_index,
            reasoning_summary=self._reasoning_summary(snapshot),
            trajectory=self._trajectory(snapshot),
            output=self._output(snapshot),
            score=score,
            feedback=self._feedback(snapshot, score),
            metadata={
                "iteration": snapshot.iteration_count,
                "tool_call_count": len(snapshot.tool_calls),
                "tokens_used": snapshot.tokens_used,
            },
        )

    def _reasoning_summary(self, snapshot: AgentIterationSnapshot) -> str:
        # Summarizes observable progress without exposing hidden chain-of-thought.
        parts = [
            f"Observed iteration {snapshot.iteration_count} for the original task.",
            f"Tool calls recorded so far: {len(snapshot.tool_calls)}.",
        ]
        if snapshot.assistant_output:
            parts.append("The agent produced intermediate assistant output before the checkpoint.")
        if snapshot.tokens_used is not None:
            parts.append(f"Provider-reported tokens used so far: {snapshot.tokens_used}.")
        return _truncate(" ".join(parts), self.max_field_chars)

    def _trajectory(self, snapshot: AgentIterationSnapshot) -> str:
        # Formats recent observable tool states and assistant output into a compact trajectory.
        lines: list[str] = []
        if snapshot.assistant_output:
            lines.append(f"Assistant output: {_truncate(snapshot.assistant_output, self.max_field_chars)}")
        recent_calls = snapshot.tool_calls[-5:]
        for call in recent_calls:
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
        # Computes a deterministic heuristic progress score from observable state.
        if not snapshot.tool_calls:
            return 0.5 if snapshot.assistant_output else 0.0
        total = len(snapshot.tool_calls)
        succeeded = sum(1 for call in snapshot.tool_calls if getattr(getattr(call, "state", None), "value", "") == "succeeded")
        denied_or_failed = sum(1 for call in snapshot.tool_calls if getattr(getattr(call, "state", None), "value", "") in {"denied", "failed"})
        score = max(0.0, min(1.0, (succeeded / total) - (denied_or_failed * 0.2 / total)))
        return round(score, 2)

    def _feedback(self, snapshot: AgentIterationSnapshot, score: float | None) -> str:
        # Produces deterministic next-step guidance from score and tool outcomes.
        if score is not None and score < 0.5:
            return "Re-check the task, address failed or denied tool calls, and choose the next action deliberately."
        if snapshot.assistant_output and not snapshot.tool_calls:
            return "Continue toward a final answer or call a tool if more evidence is needed."
        if snapshot.tool_calls:
            return "Use the observed tool outcomes to decide the next concrete step toward completion."
        return "Continue gathering evidence and avoid losing sight of the original task."


def _validate_positive(field_name: str, value: int) -> None:
    # Raises ConfigurationError if a numeric field is not strictly positive.
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")


def _validate_limit(field_name: str, value: int, limit: int) -> None:
    # Raises ConfigurationError if a character limit is outside the allowed range.
    _validate_positive(field_name, value)
    if value > limit:
        raise ConfigurationError(f"{field_name} exceeds limit of {limit}.")


def _validate_non_empty(field_name: str, value: str) -> None:
    # Raises ConfigurationError if a required string field is empty.
    if not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if metadata contains non-string keys.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


def _truncate(value: str, max_chars: int) -> str:
    # Returns value bounded to max_chars while preserving room for a truncation suffix.
    if len(value) <= max_chars:
        return value
    if max_chars <= len(_TRUNCATION_SUFFIX):
        return value[:max_chars]
    return value[: max_chars - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX


__all__ = [
    "TrajectoryCheckpoint",
    "TrajectoryCheckpointAlgorithm",
]
