"""Context Protocol Header

Description:
    Implements TrajectoryCheckpointTool — a model-callable builtin for writing
    runtime trajectory checkpoints into the active ContextManager.
Purpose:
    Lets the model persist a self-authored checkpoint at any point during a run,
    unlike TrajectoryCheckpointAlgorithm which fires on a deterministic cadence.
Architecture:
    - TrajectoryCheckpointTool: BaseTool that constructs a TrajectoryCheckpointContextItem
      from model-provided arguments and upserts it into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager and vidbyte.context.primitives.
    Parallel to vidbyte.context.algorithms.trajectory_checkpoints (the algorithm form).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_MAX_SCORE = 1.0
_MIN_SCORE = 0.0


class TrajectoryCheckpointTool(BaseTool):
    """Builtin tool that writes a model-authored trajectory checkpoint into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="trajectory_checkpoint",
            description=(
                "Write a trajectory checkpoint into the context window. "
                "Use this when you want to record your current reasoning, "
                "recent actions, output state, and next steps at a self-chosen moment. "
                "The checkpoint persists across all future turns."
            ),
            parameters=(
                ToolParameter(
                    name="reasoning_summary",
                    type="string",
                    description="Summary of the reasoning and decisions made so far in this run.",
                    required=True,
                ),
                ToolParameter(
                    name="trajectory",
                    type="string",
                    description="Recent sequence of tool calls, actions, and their outcomes.",
                    required=True,
                ),
                ToolParameter(
                    name="output",
                    type="string",
                    description="Current best answer, result, or in-progress state.",
                    required=True,
                ),
                ToolParameter(
                    name="score",
                    type="string",
                    description="Self-assessed quality of the current output, 0.0 to 1.0 (e.g. '0.75'). Optional.",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="feedback",
                    type="string",
                    description="What to focus on or change in the next steps. Optional.",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this checkpoint. Defaults to 'Runtime Checkpoint'.",
                    required=False,
                    default="Runtime Checkpoint",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the checkpoint primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate_required_fields(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = self._next_primitive_id()
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate_required_fields(self, args: dict) -> str | None:
        # Returns an error string if any required string field is missing or empty.
        for field_name in ("reasoning_summary", "trajectory", "output"):
            value = args.get(field_name)
            if not value or not str(value).strip():
                return f"Missing or empty required field: '{field_name}'."
        return None

    def _next_primitive_id(self) -> str:
        # Generates a stable, unique primitive ID based on the instance counter.
        return f"trajectory_checkpoint:{self._counter}"

    def _parse_score(self, raw: str | None) -> float | None:
        # Coerces a string score to a float clamped to [0.0, 1.0], or None on failure.
        if raw is None or str(raw).strip() == "":
            return None
        try:
            value = float(str(raw).strip())
            return max(_MIN_SCORE, min(_MAX_SCORE, value))
        except (ValueError, TypeError):
            return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the TrajectoryCheckpointContextItem from validated call arguments.
        from vidbyte.context.primitives import TrajectoryCheckpointContextItem
        return TrajectoryCheckpointContextItem(
            primitive_id=primitive_id,
            iteration=0,
            checkpoint_index=self._counter,
            reasoning_summary=str(args.get("reasoning_summary", "")).strip(),
            trajectory=str(args.get("trajectory", "")).strip(),
            output=str(args.get("output", "")).strip(),
            score=self._parse_score(args.get("score")),
            feedback=str(args.get("feedback", "")).strip(),
            title=str(args.get("title", "Runtime Checkpoint")).strip() or "Runtime Checkpoint",
        )
