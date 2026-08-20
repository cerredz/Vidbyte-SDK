"""Context Protocol Header

Description:
    Implements StrawmanTool — a model-callable builtin for recording an
    argument-restatement audit into the active ContextManager.
Purpose:
    Lets the model force the original argument, the restatement under attack,
    the distortion, the fair restatement, the applicability of the criticism,
    and the residual critique into a checkable shape — the strawman is the most
    common argumentative failure because it is invisible to the person
    committing it.
Architecture:
    - StrawmanTool: BaseTool that constructs a StrawmanContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("original_argument", "restated_argument", "distortion", "fair_restatement", "criticism_applies", "residual_critique")
_CRITICISM_VALUES = ("yes", "no", "partially")


class StrawmanTool(BaseTool):
    """Builtin tool that records an argument-restatement audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="strawman",
            description=(
                "Audit a criticism for strawmanning: state the original argument, the "
                "restatement the criticism actually attacks, the distortion between them, "
                "the fair restatement, and whether the criticism survives. Use this before "
                "repeating or acting on a critique of a position — a criticism aimed at a "
                "distorted version of the argument proves nothing about the argument."
            ),
            parameters=(
                ToolParameter(
                    name="original_argument",
                    type="string",
                    description=(
                        "The argument as it was actually made — quoted or paraphrased "
                        "faithfully, including its qualifications. The audit is only as "
                        "fair as this reconstruction."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="restated_argument",
                    type="string",
                    description=(
                        "The argument the criticism is actually attacking — the version "
                        "that appears in the critique. Often identical to "
                        "original_argument in the strawmanner's head; the audit exists to "
                        "make the gap visible."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="distortion",
                    type="string",
                    description=(
                        "Every place the restatement diverges from the original — "
                        "weakened qualifications, shifted scope, exaggerated strength, "
                        "dropped conditions. A divergence too small to matter is still "
                        "worth naming; naming it is what the audit is for."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fair_restatement",
                    type="string",
                    description=(
                        "The version of the argument that keeps its strength while being "
                        "precise — the strongest honest reconstruction, since a criticism "
                        "should face the strongest version of the position."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="criticism_applies",
                    type="string",
                    description=(
                        "One of: 'yes', 'no', 'partially'. 'yes' means the criticism "
                        "still lands on fair_restatement. 'no' means it only hit the "
                        "distortion. 'partially' means some of it survives and the "
                        "surviving part is named in residual_critique."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="residual_critique",
                    type="string",
                    description=(
                        "The criticism that genuinely applies to fair_restatement, once "
                        "the distortion is removed — or 'none' if nothing survives. The "
                        "audit's product is this honest remainder."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the strawman primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"strawman:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad criticism enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "criticism_applies"), _CRITICISM_VALUES, "criticism_applies"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the StrawmanContextItem from validated call arguments.
        from vidbyte.context.primitives import StrawmanContextItem
        return StrawmanContextItem(
            primitive_id=primitive_id,
            original_argument=ReasoningToolInput.text(args, "original_argument"),
            restated_argument=ReasoningToolInput.text(args, "restated_argument"),
            distortion=ReasoningToolInput.text(args, "distortion"),
            fair_restatement=ReasoningToolInput.text(args, "fair_restatement"),
            criticism_applies=ReasoningToolInput.text(args, "criticism_applies"),
            residual_critique=ReasoningToolInput.text(args, "residual_critique"),
            title=ReasoningToolInput.text(args, "title", "Strawman Audit") or "Strawman Audit",
        )