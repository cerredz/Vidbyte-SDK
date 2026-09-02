"""FILE: vidbyte/tools/builtins/reasoning/instantiate.py

PURPOSE: Records one instantiate reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the instantiate tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen InstantiateContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import INSTANTIATE_REQUIRED_FIELDS
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


class InstantiateTool(BaseTool):
    """Builtin tool that records a rule-to-case instantiation into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="instantiate",
            description=(
                "Apply a general rule to a concrete case: state the rule, the case, the conditions under which "
                "the rule governs, the per-condition check, the derived conclusion, and the scope check. Use "
                "this whenever the model concludes 'the rule says X, so for this case X' — instantiation is the "
                "step where rules silently stop applying and conclusions keep going. The required fields make "
                "each part of the strategy explicit so the conclusion can be examined against its stated basis. "
                "The recorded result preserves the analysis for later iterations without independently "
                "verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="general_rule",
                    type="string",
                    description=(
                        "The general rule being applied, stated with its conditions visible — 'if P and Q, then R'. A "
                        "rule whose conditions cannot be listed cannot be instantiated. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="case",
                    type="string",
                    description=(
                        "The concrete case the rule is applied to, named precisely enough that each condition can be "
                        "checked against it. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison. State only the information relevant to this field so the recorded "
                        "reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="applicability_conditions",
                    type="array",
                    description=(
                        "The conditions the case must satisfy for the rule to govern, each its own string. Every "
                        "condition the rule actually requires must be listed — omitting one is how rules get stretched. "
                        "May be passed as a JSON array of strings or a JSON string. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conditions_met",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'condition' and 'satisfied': the per-condition verdict for "
                        "this case. Each applicable condition gets a verdict; a condition without a verdict is a "
                        "condition unexamined. May also be passed as a JSON string. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="derived_conclusion",
                    type="string",
                    description=(
                        "What follows for the case once the conditions are verified — including the honest conclusion "
                        "that some conditions fail and the rule does not apply. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion. "
                        "Keeping it explicit prevents the analysis from relying on an unstated assumption and gives "
                        "later iterations a stable basis for comparison. State only the information relevant to this "
                        "field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope_check",
                    type="string",
                    description=(
                        "Whether the case is genuinely inside the rule's domain — the boundary sanity check that "
                        "catches rules applied to cases they never governed, conditions notwithstanding. This field is "
                        "part of the strategy's explicit contract, so its contribution can be reviewed separately from "
                        "the final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison. State only the "
                        "information relevant to this field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the instantiate primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"instantiate:{self._counter}"
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
        # Returns an error string for a missing field, empty conditions, or empty conditions_met.
        error = ReasoningToolInput.missing_required(args, INSTANTIATE_REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("applicability_conditions")):
            return "Field 'applicability_conditions' requires at least one entry."
        if not ReasoningToolInput.object_list(args.get("conditions_met")):
            return "Field 'conditions_met' requires at least one entry."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the InstantiateContextItem from validated call arguments.
        from vidbyte.context.primitives import InstantiateContextItem

        return cast(
            ContextItem,
            InstantiateContextItem(
                primitive_id=primitive_id,
                general_rule=ReasoningToolInput.text(args, "general_rule"),
                case=ReasoningToolInput.text(args, "case"),
                applicability_conditions=ReasoningToolInput.string_list(
                    args.get("applicability_conditions")
                ),
                conditions_met=ReasoningToolInput.object_list(
                    args.get("conditions_met")
                ),
                derived_conclusion=ReasoningToolInput.text(args, "derived_conclusion"),
                scope_check=ReasoningToolInput.text(args, "scope_check"),
                title=ReasoningToolInput.text(args, "title", "Instantiation")
                or "Instantiation",
            ),
        )
