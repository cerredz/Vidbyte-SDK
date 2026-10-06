"""FILE: vidbyte/tools/builtins/reasoning/strawman.py

PURPOSE: Records one strawman reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the strawman tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen StrawmanContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import STRAWMAN_REQUIRED_FIELDS
from vidbyte.lib.enums.reasoning_strategies import StrawmanCriticism
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
                "Audit a criticism for strawmanning: state the original argument, the restatement the criticism "
                "actually attacks, the distortion between them, the fair restatement, and whether the criticism "
                "survives. Use this before repeating or acting on a critique of a position — a criticism aimed "
                "at a distorted version of the argument proves nothing about the argument. The required fields "
                "make each part of the strategy explicit so the conclusion can be examined against its stated "
                "basis. The recorded result preserves the analysis for later iterations without independently "
                "verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="original_argument",
                    type="string",
                    description=(
                        "The argument as it was actually made — quoted or paraphrased faithfully, including its "
                        "qualifications. The audit is only as fair as this reconstruction. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="restated_argument",
                    type="string",
                    description=(
                        "The argument the criticism is actually attacking — the version that appears in the critique. "
                        "Often identical to original_argument in the strawmanner's head; the audit exists to make the "
                        "gap visible. This field is part of the strategy's explicit contract, so its contribution can "
                        "be reviewed separately from the final conclusion. Keeping it explicit prevents the analysis "
                        "from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="distortion",
                    type="string",
                    description=(
                        "Every place the restatement diverges from the original — weakened qualifications, shifted "
                        "scope, exaggerated strength, dropped conditions. A divergence too small to matter is still "
                        "worth naming; naming it is what the audit is for. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion. "
                        "Keeping it explicit prevents the analysis from relying on an unstated assumption and gives "
                        "later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fair_restatement",
                    type="string",
                    description=(
                        "The version of the argument that keeps its strength while being precise — the strongest honest "
                        "reconstruction, since a criticism should face the strongest version of the position. This "
                        "field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison. State only "
                        "the information relevant to this field so the recorded reasoning remains focused and "
                        "auditable."
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
                        "The criticism that genuinely applies to fair_restatement, once the distortion is removed — or "
                        "'none' if nothing survives. The audit's product is this honest remainder. This field is part "
                        "of the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad criticism enum.
        error = ReasoningToolInput.missing_required(args, STRAWMAN_REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "criticism_applies"),
            StrawmanCriticism.values(),
            "criticism_applies",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the StrawmanContextItem from validated call arguments.
        from vidbyte.context.primitives import StrawmanContextItem

        return cast(
            ContextItem,
            StrawmanContextItem(
                primitive_id=primitive_id,
                original_argument=ReasoningToolInput.text(args, "original_argument"),
                restated_argument=ReasoningToolInput.text(args, "restated_argument"),
                distortion=ReasoningToolInput.text(args, "distortion"),
                fair_restatement=ReasoningToolInput.text(args, "fair_restatement"),
                criticism_applies=ReasoningToolInput.text(args, "criticism_applies"),
                residual_critique=ReasoningToolInput.text(args, "residual_critique"),
                title=ReasoningToolInput.text(args, "title", "Strawman Audit")
                or "Strawman Audit",
            ),
        )
