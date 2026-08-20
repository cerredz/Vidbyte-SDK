"""Context Protocol Header

Description:
    Implements InstantiateTool — a model-callable builtin for recording a
    rule-to-case instantiation into the active ContextManager.
Purpose:
    Lets the model force the general rule, the case, the applicability
    conditions, the condition-by-condition check, the derived conclusion, and
    the scope check into a checkable shape — a general rule applied without
    verifying its conditions is a rule applied to a case it may not govern.
Architecture:
    - InstantiateTool: BaseTool that constructs an InstantiateContextItem from
      model-provided arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("general_rule", "case", "applicability_conditions", "conditions_met", "derived_conclusion", "scope_check")


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
                "Apply a general rule to a concrete case: state the rule, the case, the "
                "conditions under which the rule governs, the per-condition check, the "
                "derived conclusion, and the scope check. Use this whenever the model "
                "concludes 'the rule says X, so for this case X' — instantiation is the "
                "step where rules silently stop applying and conclusions keep going."
            ),
            parameters=(
                ToolParameter(
                    name="general_rule",
                    type="string",
                    description=(
                        "The general rule being applied, stated with its conditions "
                        "visible — 'if P and Q, then R'. A rule whose conditions cannot "
                        "be listed cannot be instantiated."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="case",
                    type="string",
                    description=(
                        "The concrete case the rule is applied to, named precisely enough "
                        "that each condition can be checked against it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="applicability_conditions",
                    type="array",
                    description=(
                        "The conditions the case must satisfy for the rule to govern, "
                        "each its own string. Every condition the rule actually requires "
                        "must be listed — omitting one is how rules get stretched. May "
                        "be passed as a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conditions_met",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'condition' and 'satisfied': "
                        "the per-condition verdict for this case. Each applicable "
                        "condition gets a verdict; a condition without a verdict is a "
                        "condition unexamined. May also be passed as a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="derived_conclusion",
                    type="string",
                    description=(
                        "What follows for the case once the conditions are verified — "
                        "including the honest conclusion that some conditions fail and "
                        "the rule does not apply."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope_check",
                    type="string",
                    description=(
                        "Whether the case is genuinely inside the rule's domain — the "
                        "boundary sanity check that catches rules applied to cases they "
                        "never governed, conditions notwithstanding."
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
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty conditions, or empty conditions_met.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("applicability_conditions")):
            return "Field 'applicability_conditions' requires at least one entry."
        if not ReasoningToolInput.object_list(args.get("conditions_met")):
            return "Field 'conditions_met' requires at least one entry."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the InstantiateContextItem from validated call arguments.
        from vidbyte.context.primitives import InstantiateContextItem
        return InstantiateContextItem(
            primitive_id=primitive_id,
            general_rule=ReasoningToolInput.text(args, "general_rule"),
            case=ReasoningToolInput.text(args, "case"),
            applicability_conditions=ReasoningToolInput.string_list(args.get("applicability_conditions")),
            conditions_met=ReasoningToolInput.object_list(args.get("conditions_met")),
            derived_conclusion=ReasoningToolInput.text(args, "derived_conclusion"),
            scope_check=ReasoningToolInput.text(args, "scope_check"),
            title=ReasoningToolInput.text(args, "title", "Instantiation") or "Instantiation",
        )