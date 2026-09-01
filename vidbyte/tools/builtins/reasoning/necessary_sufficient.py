"""FILE: vidbyte/tools/builtins/reasoning/necessary_sufficient.py

PURPOSE: Records one necessary sufficient reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the necessary_sufficient tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen NecessarySufficientContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import (
    NECESSARY_SUFFICIENT_REQUIRED_FIELDS,
    NECESSARY_SUFFICIENT_VERDICT_VALUES,
)
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
                "Analyze the relationship between a condition and a target: is the condition necessary for the "
                "target, sufficient for it, both, or neither? State the direction of each check and the "
                "implications that follow. Use this whenever a claim asserts that one thing 'requires' or "
                "'guarantees' another — the two directions are routinely conflated, and the conflation survives "
                "until someone checks both. The required fields make each part of the strategy explicit so the "
                "conclusion can be examined against its stated basis."
            ),
            parameters=(
                ToolParameter(
                    name="condition",
                    type="string",
                    description=(
                        "The condition whose relationship to target is under analysis — e.g. 'valid login'. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion. Keeping it explicit prevents the analysis from relying on an "
                        "unstated assumption and gives later iterations a stable basis for comparison. State only the "
                        "information relevant to this field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="target",
                    type="string",
                    description=(
                        "The target state the condition may enable or require — e.g. 'session granted'. This field is "
                        "part of the strategy's explicit contract, so its contribution can be reviewed separately from "
                        "the final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison. State only the "
                        "information relevant to this field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="necessity_direction",
                    type="string",
                    description=(
                        "Whether target implies condition — can target hold without condition? Name a concrete "
                        "counter-scenario if it can; state the general argument if it cannot. 'Probably yes' is not a "
                        "direction; a direction is a claim with a reason. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="sufficiency_direction",
                    type="string",
                    description=(
                        "Whether condition implies target — does condition alone guarantee target, or can condition "
                        "hold while target fails? The failure scenario, when it exists, is the whole analysis. This "
                        "field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'necessary_only', 'sufficient_only', 'both', 'neither'. 'both' means the condition and "
                        "target are equivalent. 'neither' means the claimed relationship fails in both directions. This "
                        "field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="implications",
                    type="string",
                    description=(
                        "What the verdict means for decisions downstream — what must be checked, what can be relied on, "
                        "and what cannot. An analysis that commits to a verdict but names no implication has not "
                        "finished its job. This field is part of the strategy's explicit contract, so its contribution "
                        "can be reviewed separately from the final conclusion. Keeping it explicit prevents the "
                        "analysis from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison."
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad verdict enum.
        error = ReasoningToolInput.missing_required(
            args, NECESSARY_SUFFICIENT_REQUIRED_FIELDS
        )
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"),
            NECESSARY_SUFFICIENT_VERDICT_VALUES,
            "verdict",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the NecessarySufficientContextItem from validated call arguments.
        from vidbyte.context.primitives import NecessarySufficientContextItem

        return cast(
            ContextItem,
            NecessarySufficientContextItem(
                primitive_id=primitive_id,
                condition=ReasoningToolInput.text(args, "condition"),
                target=ReasoningToolInput.text(args, "target"),
                necessity_direction=ReasoningToolInput.text(
                    args, "necessity_direction"
                ),
                sufficiency_direction=ReasoningToolInput.text(
                    args, "sufficiency_direction"
                ),
                verdict=ReasoningToolInput.text(args, "verdict"),
                implications=ReasoningToolInput.text(args, "implications"),
                title=ReasoningToolInput.text(args, "title", "Condition Analysis")
                or "Condition Analysis",
            ),
        )
