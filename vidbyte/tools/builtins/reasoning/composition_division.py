"""Context Protocol Header

Description:
    Implements CompositionDivisionTool — a model-callable builtin for recording
    a part-to-whole property-transfer audit into the active ContextManager.
Purpose:
    Lets the model force the parts, the whole, the property, the aggregation
    claim, a verdict, and a deciding counterexample into a checkable shape —
    composition and division fallacies transfer properties across levels
    without license.
Architecture:
    - CompositionDivisionTool: BaseTool that constructs a
      CompositionDivisionContextItem from model-provided arguments and upserts
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

_REQUIRED_FIELDS = ("parts", "whole", "property", "aggregation_claim", "validity", "counterexample")
_VALIDITY_VALUES = ("valid", "fallacy_of_composition", "fallacy_of_division", "unknown")


class CompositionDivisionTool(BaseTool):
    """Builtin tool that records a part-to-whole property-transfer audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="composition_division",
            description=(
                "Audit a property transfer between a whole and its parts: state the parts, "
                "the whole, the property, and the aggregation claim, then commit to a "
                "verdict and name the deciding counterexample. Use this whenever the model "
                "concludes that a whole has a property because its parts do (composition) "
                "or that a part has a property because the whole does (division) — "
                "distributive properties transfer, collective properties do not, and the "
                "boundary between them is where the fallacies live."
            ),
            parameters=(
                ToolParameter(
                    name="parts",
                    type="array",
                    description=(
                        "The constituent parts, each named — e.g. 'each module is "
                        "independently tested'. May be passed as a JSON array of strings "
                        "or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="whole",
                    type="string",
                    description=(
                        "The aggregate — e.g. 'the full application'. The whole must be "
                        "the genuine sum of the parts, or the audit is about different "
                        "objects."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="property",
                    type="string",
                    description=(
                        "The property being transferred across levels — e.g. 'tested', "
                        "'fast', 'contains a defect'. Whether the transfer is valid "
                        "depends on whether this property is distributive or collective."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="aggregation_claim",
                    type="string",
                    description=(
                        "The exact inference under audit — e.g. 'each module is tested, "
                        "therefore the application is tested'. Quote the claim; the "
                        "verdict judges this claim and no other."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="validity",
                    type="string",
                    description=(
                        "One of: 'valid', 'fallacy_of_composition', 'fallacy_of_division', "
                        "'unknown'. 'valid' means the property transfers lawfully. "
                        "'fallacy_of_composition' means the whole was credited with a "
                        "property that only the parts have. 'fallacy_of_division' means a "
                        "part was credited with a property that only the whole has."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="counterexample",
                    type="string",
                    description=(
                        "The concrete case that decides the verdict — a collective "
                        "property held only by the whole, or a distributive property "
                        "borne by each part. For 'unknown', state what evidence would "
                        "decide it."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the composition_division primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"composition_division:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty parts, or a bad validity enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("parts")):
            return "Field 'parts' requires at least one part."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "validity"), _VALIDITY_VALUES, "validity"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the CompositionDivisionContextItem from validated call arguments.
        from vidbyte.context.primitives import CompositionDivisionContextItem
        return CompositionDivisionContextItem(
            primitive_id=primitive_id,
            parts=ReasoningToolInput.string_list(args.get("parts")),
            whole=ReasoningToolInput.text(args, "whole"),
            property=ReasoningToolInput.text(args, "property"),
            aggregation_claim=ReasoningToolInput.text(args, "aggregation_claim"),
            validity=ReasoningToolInput.text(args, "validity"),
            counterexample=ReasoningToolInput.text(args, "counterexample"),
            title=ReasoningToolInput.text(args, "title", "Part-Whole Check") or "Part-Whole Check",
        )