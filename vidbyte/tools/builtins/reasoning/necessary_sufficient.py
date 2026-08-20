"""Context Protocol Header

Description:
    Implements NecessarySufficientTool — a model-callable builtin for recording
    a condition-relationship analysis into the active ContextManager.
Purpose:
    Lets the model force the condition, the target, the direction of necessity,
    the direction of sufficiency, a verdict, and the implications into a
    checkable shape — the necessity/sufficiency confusion is the most common
    silent error in causal and conditional claims.
Architecture:
    - NecessarySufficientTool: BaseTool that constructs a
      NecessarySufficientContextItem from model-provided arguments and upserts
      it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("condition", "target", "necessity_direction", "sufficiency_direction", "verdict", "implications")
_VERDICT_VALUES = ("necessary_only", "sufficient_only", "both", "neither")


class NecessarySufficientTool(BaseTool):
    """Builtin tool that records a condition-relationship analysis into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="necessary_sufficient",
            description=(
                "Analyze the relationship between a condition and a target: is the "
                "condition necessary for the target, sufficient for it, both, or neither? "
                "State the direction of each check and the implications that follow. Use "
                "this whenever a claim asserts that one thing 'requires' or 'guarantees' "
                "another — the two directions are routinely conflated, and the conflation "
                "survives until someone checks both."
            ),
            parameters=(
                ToolParameter(
                    name="condition",
                    type="string",
                    description=(
                        "The condition whose relationship to target is under analysis — "
                        "e.g. 'valid login'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="target",
                    type="string",
                    description=(
                        "The target state the condition may enable or require — e.g. "
                        "'session granted'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="necessity_direction",
                    type="string",
                    description=(
                        "Whether target implies condition — can target hold without "
                        "condition? Name a concrete counter-scenario if it can; state the "
                        "general argument if it cannot. 'Probably yes' is not a direction; "
                        "a direction is a claim with a reason."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="sufficiency_direction",
                    type="string",
                    description=(
                        "Whether condition implies target — does condition alone guarantee "
                        "target, or can condition hold while target fails? The failure "
                        "scenario, when it exists, is the whole analysis."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'necessary_only', 'sufficient_only', 'both', 'neither'. "
                        "'both' means the condition and target are equivalent. 'neither' "
                        "means the claimed relationship fails in both directions."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="implications",
                    type="string",
                    description=(
                        "What the verdict means for decisions downstream — what must be "
                        "checked, what can be relied on, and what cannot. An analysis that "
                        "commits to a verdict but names no implication has not finished "
                        "its job."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the necessary_sufficient primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"necessary_sufficient:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad verdict enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"), _VERDICT_VALUES, "verdict"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the NecessarySufficientContextItem from validated call arguments.
        from vidbyte.context.primitives import NecessarySufficientContextItem
        return NecessarySufficientContextItem(
            primitive_id=primitive_id,
            condition=ReasoningToolInput.text(args, "condition"),
            target=ReasoningToolInput.text(args, "target"),
            necessity_direction=ReasoningToolInput.text(args, "necessity_direction"),
            sufficiency_direction=ReasoningToolInput.text(args, "sufficiency_direction"),
            verdict=ReasoningToolInput.text(args, "verdict"),
            implications=ReasoningToolInput.text(args, "implications"),
            title=ReasoningToolInput.text(args, "title", "Condition Analysis") or "Condition Analysis",
        )