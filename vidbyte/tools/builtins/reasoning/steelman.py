"""Context Protocol Header

Description:
    Implements SteelmanTool — a model-callable builtin for recording a
    position tested against its strongest opposition into the active
    ContextManager.
Purpose:
    Lets the model pressure-test a current claim, plan, or decision against
    the best case against it, and requires a concrete revision whenever the
    position does not survive unchanged.
Architecture:
    - SteelmanTool: BaseTool that constructs a SteelmanContextItem from model-
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

_REQUIRED_FIELDS = ("my_position", "strongest_opposition", "survives")
_SURVIVES_VALUES = ("yes", "no", "weakened")


class SteelmanTool(BaseTool):
    """Builtin tool that records a position tested against its strongest opposition into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="steelman",
            description=(
                "Pressure-test a current position by constructing the strongest possible case "
                "against it — as carefully as the position itself was built — then decide "
                "whether the position survives. Use this before committing to a plan, decision, "
                "or claim that could be wrong. If the position does not survive unchanged, a "
                "concrete revision is required; a steelman that never changes anything is not "
                "being taken seriously."
            ),
            parameters=(
                ToolParameter(
                    name="my_position",
                    type="string",
                    description="The claim, plan, or decision currently being held, stated as a clear, falsifiable position rather than a vague leaning.",
                    required=True,
                ),
                ToolParameter(
                    name="strongest_opposition",
                    type="string",
                    description=(
                        "The best case against my_position, constructed as carefully and "
                        "charitably as you would construct my_position itself — not the easiest "
                        "objection to dismiss, but the one a smart, well-informed opponent would "
                        "actually raise. A weak opposing argument defeats the purpose of this "
                        "tool."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="survives",
                    type="string",
                    description=(
                        "One of: 'yes', 'no', 'weakened'. 'yes' means my_position stands "
                        "unchanged against strongest_opposition. 'no' means strongest_opposition "
                        "defeats my_position outright. 'weakened' means my_position still holds "
                        "but in a narrower or more qualified form than originally stated."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="revision",
                    type="string",
                    description=(
                        "How my_position should change in light of strongest_opposition. "
                        "Required whenever survives is 'no' or 'weakened' — leave empty only "
                        "when survives is 'yes'."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Steelman'.",
                    required=False,
                    default="Steelman",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the steelman primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"steelman:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, a bad enum, or a missing conditional revision.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        survives = ReasoningToolInput.text(args, "survives")
        enum_error = ReasoningToolInput.enum_error(survives, _SURVIVES_VALUES, "survives")
        if enum_error:
            return enum_error
        if survives != "yes" and not ReasoningToolInput.text(args, "revision"):
            return "Field 'revision' is required when 'survives' is 'no' or 'weakened'."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the SteelmanContextItem from validated call arguments.
        from vidbyte.context.primitives import SteelmanContextItem
        return SteelmanContextItem(
            primitive_id=primitive_id,
            my_position=ReasoningToolInput.text(args, "my_position"),
            strongest_opposition=ReasoningToolInput.text(args, "strongest_opposition"),
            survives=ReasoningToolInput.text(args, "survives"),
            revision=ReasoningToolInput.text(args, "revision"),
            title=ReasoningToolInput.text(args, "title", "Steelman") or "Steelman",
        )
