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

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_REQUIRED_FIELDS = ("source_domain", "target_domain", "breaks_down_at", "carries_weight")
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
                    description="The familiar domain, system, or situation being reasoned FROM — the thing you already understand.",
                    required=True,
                ),
                ToolParameter(
                    name="target_domain",
                    type="string",
                    description="The unfamiliar domain, system, or situation being reasoned TO — the thing the analogy is meant to illuminate.",
                    required=True,
                ),
                ToolParameter(
                    name="mapped_relations",
                    type="array",
                    description=(
                        "The specific structural correspondences between source_domain and "
                        "target_domain, each entry stated as 'X in source_domain corresponds to "
                        "Y in target_domain'. An analogy is only as good as its mapped relations "
                        "— vague resemblance ('this is kind of like that') is not enough; name "
                        "what maps to what. May be a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="breaks_down_at",
                    type="string",
                    description=(
                        "Where the analogy stops holding — the point at which source_domain and "
                        "target_domain diverge and the mapping produces a wrong conclusion if "
                        "pushed further. Mandatory: unlimited analogies are how an agent talks "
                        "itself into an unjustified conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="carries_weight",
                    type="string",
                    description=(
                        "One of: 'explains_only' or 'justifies_action'. 'explains_only' means "
                        "the analogy is a communication aid for understanding, not evidence for "
                        "a decision. 'justifies_action' means the analogy is being treated as a "
                        "reason to act, which requires the mapped relations to be structural, "
                        "not superficial. Default to 'explains_only'; choose 'justifies_action' "
                        "only if breaks_down_at does not undermine the specific action being "
                        "justified."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Analogical Transfer'.",
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
        return ReasoningToolInput.enum_error(carries_weight, _CARRIES_WEIGHT_VALUES, "carries_weight")

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the AnalogyContextItem from validated call arguments.
        from vidbyte.context.primitives import AnalogyContextItem
        return AnalogyContextItem(
            primitive_id=primitive_id,
            source_domain=ReasoningToolInput.text(args, "source_domain"),
            target_domain=ReasoningToolInput.text(args, "target_domain"),
            mapped_relations=ReasoningToolInput.string_list(args.get("mapped_relations")),
            breaks_down_at=ReasoningToolInput.text(args, "breaks_down_at"),
            carries_weight=ReasoningToolInput.text(args, "carries_weight"),
            title=ReasoningToolInput.text(args, "title", "Analogical Transfer") or "Analogical Transfer",
        )
