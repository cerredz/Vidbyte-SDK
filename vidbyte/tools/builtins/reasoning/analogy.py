"""Context Protocol Header

Description:
    Implements AnalogyTool — a model-callable builtin for recording an
    analogical transfer into the active ContextManager.
Purpose:
    Lets the model reason from a familiar source domain to an unfamiliar target
    domain while forcing it to name the specific mapped relations and the point
    where the analogy stops holding, instead of trading on vague resemblance.
Architecture:
    - AnalogyTool: BaseTool that constructs an AnalogyContextItem from model-
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

_REQUIRED_FIELDS = (
    "source_domain",
    "target_domain",
    "breaks_down_at",
    "carries_weight",
)
_CARRIES_WEIGHT_VALUES = ("explains_only", "justifies_action")


class AnalogyTool(BaseTool):
    """Builtin tool that records an analogical transfer into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="analogy",
            description=(
                "Reason from a familiar source domain to an unfamiliar target domain by naming "
                "the specific structural correspondences between them. Use this to transfer "
                "understanding, not just to decorate an explanation with a comparison. Every "
                "analogy breaks down somewhere and this tool requires you to say where, and to "
                "declare whether the analogy is only explaining an idea or is actually being "
                "used to justify a decision."
            ),
            parameters=(
                ToolParameter(
                    name="source_domain",
                    type="string",
                    description=(
                        "Name the familiar domain, system, or situation used as the source of "
                        "the analogy. Choose a source whose structure is already understood well "
                        "enough to support a comparison. This gives the model a concrete basis "
                        "for transferring relationships rather than merely repeating a metaphor. "
                        "Provide the source as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="target_domain",
                    type="string",
                    description=(
                        "Name the unfamiliar domain, system, or situation that the analogy is "
                        "intended to illuminate. State the target precisely enough that the model "
                        "can identify which relationships need explanation. Separating the target "
                        "from the source makes the direction of the transfer explicit. Provide the "
                        "target as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="mapped_relations",
                    type="array",
                    description=(
                        "List the specific structural correspondences between the source and "
                        "target domains. State each relation in a form such as 'X in the source "
                        "corresponds to Y in the target' so the mapping can be inspected. These "
                        "relations show whether the analogy transfers structure rather than a "
                        "vague resemblance. Provide a JSON array of strings or a JSON-encoded "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="breaks_down_at",
                    type="string",
                    description=(
                        "Describe where the analogy stops holding between the source and target. "
                        "Identify the divergence that would make the mapped relation unreliable "
                        "if the comparison were extended further. Naming the limit keeps the "
                        "model from treating an explanatory comparison as universal evidence. "
                        "Provide the breakdown point as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="carries_weight",
                    type="string",
                    description=(
                        "State whether the analogy 'explains_only' or 'justifies_action'. Use "
                        "'explains_only' when it is a communication aid and not evidence for a "
                        "decision. Use 'justifies_action' only when the mapped relations support "
                        "the specific action and the stated breakdown does not undermine it. "
                        "Provide one of those two enum values as a plain string, with "
                        "'explains_only' as the safer default."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded analogy. The label helps "
                        "the model and callers distinguish this note from other context items. "
                        "Use the default label when no more specific name is needed. Provide a "
                        "plain string; it defaults to 'Analogical Transfer'."
                    ),
                    required=False,
                    default="Analogical Transfer",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the analogy primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"analogy:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if mapped_relations, a required field, or the enum is invalid.
        if not ReasoningToolInput.string_list(args.get("mapped_relations")):
            return "Missing or empty required field: 'mapped_relations'."
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        carries_weight = ReasoningToolInput.text(args, "carries_weight")
        return ReasoningToolInput.enum_error(
            carries_weight, _CARRIES_WEIGHT_VALUES, "carries_weight"
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the AnalogyContextItem from validated call arguments.
        from vidbyte.context.primitives import AnalogyContextItem

        return cast(
            ContextItem,
            AnalogyContextItem(
                primitive_id=primitive_id,
                source_domain=ReasoningToolInput.text(args, "source_domain"),
                target_domain=ReasoningToolInput.text(args, "target_domain"),
                mapped_relations=ReasoningToolInput.string_list(
                    args.get("mapped_relations")
                ),
                breaks_down_at=ReasoningToolInput.text(args, "breaks_down_at"),
                carries_weight=ReasoningToolInput.text(args, "carries_weight"),
                title=ReasoningToolInput.text(args, "title", "Analogical Transfer")
                or "Analogical Transfer",
            ),
        )
