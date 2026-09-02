"""FILE: vidbyte/tools/builtins/reasoning/partition.py

PURPOSE: Records one partition reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the partition tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen PartitionContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import PARTITION_REQUIRED_FIELDS
from vidbyte.lib.enums.reasoning_strategies import PartitionVerdict
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


class PartitionTool(BaseTool):
    """Builtin tool that records a classification-coverage audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="partition",
            description=(
                "Audit a set of categories against a set of items: state the items, the categories, the rule "
                "that assigns each item to a category, then report coverage and overlap and commit to a "
                "verdict. Use this before relying on a classification to be complete — taxonomies with gaps "
                "silently drop items, and taxonomies with overlaps force double assignment. The required fields "
                "make each part of the strategy explicit so the conclusion can be examined against its stated "
                "basis. The recorded result preserves the analysis for later iterations without independently "
                "verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="items",
                    type="array",
                    description=(
                        "The items that must be classifiable — every one of them, not the convenient ones. An item that "
                        "fits nowhere is a gap the audit must find. May be passed as a JSON array of strings or a JSON "
                        "string. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="categories",
                    type="array",
                    description=(
                        "The candidate categories. A category with no membership rule is a label, not a category. May "
                        "be passed as a JSON array of strings or a JSON string. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="membership_rules",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'category' and 'rule': the decision rule for each category, "
                        "precise enough that any item's membership is decidable — not 'roughly this kind of thing'. May "
                        "also be passed as a JSON string. This field is part of the strategy's explicit contract, so "
                        "its contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="coverage",
                    type="string",
                    description=(
                        "Whether every item lands in at least one category, naming any items that fit nowhere. Empty "
                        "coverage gaps are the audit's primary finding. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="overlap",
                    type="string",
                    description=(
                        "Whether any item could satisfy two categories, naming the offending categories and rules. "
                        "Overlap means the partition is not a partition — membership is ambiguous. This field is part "
                        "of the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'exhaustive_disjoint', 'gaps', 'overlaps'. "
                        "'exhaustive_disjoint' means every item fits exactly one category. "
                        "'gaps' means some item fits none. 'overlaps' means some item fits "
                        "more than one."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the partition primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"partition:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty rules, or a bad verdict enum.
        error = ReasoningToolInput.missing_required(args, PARTITION_REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.object_list(args.get("membership_rules")):
            return "Field 'membership_rules' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"),
            PartitionVerdict.values(),
            "verdict",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the PartitionContextItem from validated call arguments.
        from vidbyte.context.primitives import PartitionContextItem

        return cast(
            ContextItem,
            PartitionContextItem(
                primitive_id=primitive_id,
                items=ReasoningToolInput.string_list(args.get("items")),
                categories=ReasoningToolInput.string_list(args.get("categories")),
                membership_rules=ReasoningToolInput.object_list(
                    args.get("membership_rules")
                ),
                coverage=ReasoningToolInput.text(args, "coverage"),
                overlap=ReasoningToolInput.text(args, "overlap"),
                verdict=ReasoningToolInput.text(args, "verdict"),
                title=ReasoningToolInput.text(args, "title", "Partition Check")
                or "Partition Check",
            ),
        )
