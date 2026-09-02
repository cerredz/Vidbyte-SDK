"""Context Protocol Header

Description:
    Implements the public agentic Trajectory Checkpoint context-window algorithm.
Purpose:
    Generates model-based agentic checkpoints through ContextManager primitives to synthesize runtime history.
Architecture:
    - TrajectoryCheckpointAlgorithm: Frozen config and inner-loop lifecycle implementation.
      Invokes the model runner asynchronously to generate summaries.
Key Functions:
    - after_tool_calls: Coordinates the checkpoint injection cadence.
    - build_item: Invokes the model runner, parses the JSON result, and constructs the ContextItem.
Relations:
    Used by ContextWindow presets and AgentRuntime inner-loop lifecycle dispatch.
Similar Files:
    - `vidbyte/context/algorithms/reflexion.py`
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives import TrajectoryCheckpointContextItem
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts.catalog import Prompts

_MAX_CHECKPOINT_CHARS_LIMIT = 100_000
_MAX_FIELD_CHARS_LIMIT = 25_000
_STATE_KEY = "_trajectory_checkpoints_state"


@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm(InnerContextWindowAlgorithm):
    """Inner-loop trajectory checkpoint algorithm config."""

    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
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

    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
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
            item = await self.build_item(ctx, snapshot, checkpoint_index=len(checkpoints) + 1)
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

    async def build_item(self, ctx: ContextWindowRunContext, snapshot: AgentIterationSnapshot, checkpoint_index: int) -> TrajectoryCheckpointContextItem:
        # Calls the summarizer model to build the checkpoint from current history.
        try:
            system_prompt = Prompts().get(Prompt.TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER)
            history_str = self._format_history(ctx.messages)
            user_message = f"Main Agent System Prompt:\n{ctx.system_prompt or ''}\n\nMain Agent Conversation History:\n{history_str}"
            if not ctx.runner or not ctx.invoke_runner or not ctx.runner_output_text:
                raise ValueError("Context lacks runner or invoke_runner callable.")
            combined_prompt = f"{system_prompt}\n\n{user_message}"
            response = await ctx.invoke_runner(ctx.runner, combined_prompt, **dict(ctx.options or {}))
            response_text = ctx.runner_output_text(response)
            parsed = self._parse_json_response(response_text)
            score = parsed.get("score")
            if score is not None:
                try:
                    score = round(float(score), 2)
                except (ValueError, TypeError):
                    score = None
            return TrajectoryCheckpointContextItem(
                primitive_id=f"trajectory_checkpoint:{checkpoint_index}",
                iteration=snapshot.iteration_count,
                checkpoint_index=checkpoint_index,
                reasoning_summary=parsed.get("reasoning_summary", ""),
                trajectory=parsed.get("trajectory", ""),
                output=parsed.get("output", ""),
                score=score,
                feedback=parsed.get("feedback", ""),
                title=self.checkpoint_title,
                max_chars=self.max_checkpoint_chars,
                metadata={
                    "iteration": snapshot.iteration_count,
                    "checkpoint_index": checkpoint_index,
                    "tool_call_count": len(snapshot.tool_calls),
                    "tokens_used": snapshot.tokens_used,
                    "agentic": True,
                    **dict(self.metadata),
                },
            )
        except Exception as exc:
            ctx.record("trajectory_checkpoint_failure", error=str(exc))
            raise exc

    def _format_history(self, messages: Sequence[dict[str, Any]] | None) -> str:
        # Stringifies the main agent's conversation history messages.
        if not messages:
            return "No history."
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content")
            if role == "tool":
                if not self.include_tool_outputs:
                    text = "[Tool output omitted]"
                else:
                    text = _truncate(str(content or ""), self.max_field_chars)
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "tool_result":
                            if not self.include_tool_outputs:
                                parts.append("[Tool output omitted]")
                            else:
                                raw_val = str(part.get("content") or part.get("output") or "")
                                parts.append(_truncate(raw_val, self.max_field_chars))
                        else:
                            parts.append(part.get("text", ""))
                    else:
                        parts.append(str(part))
                text = " ".join(parts)
            else:
                text = str(content or "")
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                text += f" [Tool Calls: {tool_calls}]"
            name = msg.get("name")
            name_suffix = f" ({name})" if name else ""
            lines.append(f"{role.capitalize()}{name_suffix}: {text}")
        return "\n".join(lines)

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        # Robustly extracts and parses a JSON object from a model response.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
        return json.loads(cleaned)

    def _state(self, ctx: ContextWindowRunContext) -> dict[str, Any]:
        # Returns the mutable per-run trajectory checkpoint state.
        return ctx.state.setdefault(_STATE_KEY, {"seen_iterations": set(), "checkpoints": []})

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
