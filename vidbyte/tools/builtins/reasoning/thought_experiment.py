"""Context Protocol Header

Description:
    Implements ThoughtExperimentTool — a model-callable builtin for recording a
    gedankenexperiment into the active ContextManager.
Purpose:
    Lets the model force the setup, the manipulation, the predicted outcome, the
    insight, and the limits into a checkable shape — a thought experiment is a
    controlled imagination, and its value is only as good as its limits are
    named.
Architecture:
    - ThoughtExperimentTool: BaseTool that constructs a
      ThoughtExperimentContextItem from model-provided arguments and upserts it
      into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager, vidbyte.context.primitives, and the
    shared vidbyte.tools.builtins.reasoning._parsing.ReasoningToolInput helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_REQUIRED_FIELDS = ("setup", "manipulation", "predicted_outcome", "insight", "limits")


class ThoughtExperimentTool(BaseTool):
    """Builtin tool that records a gedankenexperiment into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="thought_experiment",
            description=(
                "Run a controlled thought experiment: describe the imagined world, the "
                "single manipulation, the predicted outcome, the insight it forces, and "
                "the limits of the result. Use this when the model needs to isolate a "
                "principle from a tangled situation — the thought experiment removes "
                "exactly one variable at a time and sees what survives."
            ),
            parameters=(
                ToolParameter(
                    name="setup",
                    type="string",
                    description=(
                        "The imagined situation, fully specified — the actors, the "
                        "objects, the rules of the world. An under-specified setup "
                        "produces outcomes that could be caused by any of several "
                        "differences."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="manipulation",
                    type="string",
                    description=(
                        "The single change that defines the experiment — exactly one "
                        "variable altered against the setup. Two simultaneous changes "
                        "make the outcome attribution impossible."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="predicted_outcome",
                    type="string",
                    description=(
                        "What the setup plus the manipulation is predicted to produce — "
                        "and, where the thought experiment argues against a position, "
                        "what that position would have predicted instead. The contrast "
                        "is the experiment."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="insight",
                    type="string",
                    description=(
                        "The principle the experiment demonstrates — the general lesson "
                        "that travels beyond the imagined world. An experiment that "
                        "yields no insight was a daydream, not an experiment."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="limits",
                    type="string",
                    description=(
                        "Where the thought experiment stops holding — the real-world "
                        "differences that keep the insight from transferring wholesale, "
                        "and what would need checking empirically. Thought experiments "
                        "are instruments; every instrument has a range."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the thought_experiment primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"thought_experiment:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if any required field is missing or empty.
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the ThoughtExperimentContextItem from validated call arguments.
        from vidbyte.context.primitives import ThoughtExperimentContextItem
        return ThoughtExperimentContextItem(
            primitive_id=primitive_id,
            setup=ReasoningToolInput.text(args, "setup"),
            manipulation=ReasoningToolInput.text(args, "manipulation"),
            predicted_outcome=ReasoningToolInput.text(args, "predicted_outcome"),
            insight=ReasoningToolInput.text(args, "insight"),
            limits=ReasoningToolInput.text(args, "limits"),
            title=ReasoningToolInput.text(args, "title", "Thought Experiment") or "Thought Experiment",
        )