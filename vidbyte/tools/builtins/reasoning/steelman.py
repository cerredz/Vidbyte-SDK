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

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

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
                    description=(
                        "State the claim, plan, or decision currently being held. Make it clear "
                        "enough that a strong opposing case can address the actual position. A "
                        "specific position gives the model something to pressure-test rather than "
                        "a vague leaning to defend. Provide it as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="strongest_opposition",
                    type="string",
                    description=(
                        "Construct the strongest credible case against my_position. Represent the "
                        "opposition as carefully and charitably as a well-informed opponent would "
                        "state it. A serious opposing case reveals weaknesses that an easy objection "
                        "would miss. Provide the opposition as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="survives",
                    type="string",
                    description=(
                        "Record whether the position survives the strongest opposition. Use 'yes' "
                        "when it stands unchanged, 'no' when the opposition defeats it, or "
                        "'weakened' when it remains valid only in a narrower or more qualified form. "
                        "This verdict tells the model whether the pressure test changed the status "
                        "of the original position. Provide one of those enum values as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="revision",
                    type="string",
                    description=(
                        "Describe how my_position should change in light of the opposition. State "
                        "the narrower claim, new condition, or replacement decision that follows "
                        "when the original position is weakened or defeated. A concrete revision "
                        "turns the pressure test into an actionable update. Leave this optional "
                        "field empty only when survives is 'yes'."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded steelman. The label helps "
                        "the model and callers distinguish this note from other context items. Use "
                        "the default label when no more specific name is needed. Provide a plain "
                        "string; it defaults to 'Steelman'."
                    ),
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
        enum_error = ReasoningToolInput.enum_error(
            survives, _SURVIVES_VALUES, "survives"
        )
        if enum_error:
            return enum_error
        if survives != "yes" and not ReasoningToolInput.text(args, "revision"):
            return "Field 'revision' is required when 'survives' is 'no' or 'weakened'."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the SteelmanContextItem from validated call arguments.
        from vidbyte.context.primitives import SteelmanContextItem

        return cast(
            ContextItem,
            SteelmanContextItem(
                primitive_id=primitive_id,
                my_position=ReasoningToolInput.text(args, "my_position"),
                strongest_opposition=ReasoningToolInput.text(
                    args, "strongest_opposition"
                ),
                survives=ReasoningToolInput.text(args, "survives"),
                revision=ReasoningToolInput.text(args, "revision"),
                title=ReasoningToolInput.text(args, "title", "Steelman") or "Steelman",
            ),
        )
