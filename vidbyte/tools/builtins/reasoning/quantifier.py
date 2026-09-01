"""FILE: vidbyte/tools/builtins/reasoning/quantifier.py

PURPOSE: Records one quantifier reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the quantifier tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen QuantifierContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    QUANTIFIER_KIND_VALUES,
    QUANTIFIER_REQUIRED_FIELDS,
    QUANTIFIER_VERDICT_VALUES,
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


class QuantifierTool(BaseTool):
    """Builtin tool that records a quantified-claim scope analysis into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="quantifier",
            description=(
                "Analyze a quantified claim: name the quantifier actually in force, check one concrete "
                "instance, supply the deciding counterexample (or confirming instance), state the scope "
                "restriction, and commit to a verdict. Use this whenever a claim contains 'all', 'none', "
                "'some', or 'most' and the truth of the claim depends on which one is meant — the single most "
                "common place logical errors hide in prose. The required fields make each part of the strategy "
                "explicit so the conclusion can be examined against its stated basis. The recorded result "
                "preserves the analysis for later iterations without independently verifying the model's "
                "judgment."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The quantified claim under analysis, quoted with its quantifier word visible — e.g. 'all "
                        "retries succeed within 3 attempts'. If the quantifier is implicit, state the claim as it is "
                        "actually used. This field is part of the strategy's explicit contract, so its contribution can "
                        "be reviewed separately from the final conclusion. Keeping it explicit prevents the analysis "
                        "from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="quantifier",
                    type="string",
                    description=(
                        "One of: 'all', 'some', 'none', 'most' — the quantifier the claim actually asserts, not the one "
                        "the speaker intended. A claim phrased as 'all' but only usable as 'most' must be recorded as "
                        "'all' and then graded in the verdict. This field is part of the strategy's explicit contract, "
                        "so its contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="instance_checked",
                    type="string",
                    description=(
                        "The single concrete instance examined against the claim. A quantified claim is tested by "
                        "cases, not by vibes — name the case. This field is part of the strategy's explicit contract, "
                        "so its contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="counterexample",
                    type="string",
                    description=(
                        "For quantifier 'all': a concrete violating instance. For 'none': a "
                        "concrete confirming instance that exists. For 'some' or 'most': a "
                        "non-example showing the claim does not cover everything. If no "
                        "deciding instance exists, state that explicitly rather than leaving "
                        "the field empty — an empty answer is itself the finding."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="scope_restriction",
                    type="string",
                    description=(
                        "How the domain is bounded — e.g. 'over HTTP transport only, not WebSocket'. Unstated "
                        "restrictions are where quantifier errors hide: a claim that is true in one domain and false in "
                        "another is two claims, not one. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'holds', 'fails', 'unverifiable'. 'holds' means the claim "
                        "survives the checked instance and scope. 'fails' means the "
                        "counterexample breaks it. 'unverifiable' means the claim cannot be "
                        "settled from available evidence."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the quantifier primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"quantifier:{self._counter}"
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
        # Returns an error string for a missing field or a bad quantifier/verdict enum.
        error = ReasoningToolInput.missing_required(args, QUANTIFIER_REQUIRED_FIELDS)
        if error:
            return error
        enum_error = ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "quantifier"),
            QUANTIFIER_KIND_VALUES,
            "quantifier",
        )
        if enum_error:
            return enum_error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"),
            QUANTIFIER_VERDICT_VALUES,
            "verdict",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the QuantifierContextItem from validated call arguments.
        from vidbyte.context.primitives import QuantifierContextItem

        return cast(
            ContextItem,
            QuantifierContextItem(
                primitive_id=primitive_id,
                claim=ReasoningToolInput.text(args, "claim"),
                quantifier=ReasoningToolInput.text(args, "quantifier"),
                instance_checked=ReasoningToolInput.text(args, "instance_checked"),
                counterexample=ReasoningToolInput.text(args, "counterexample"),
                scope_restriction=ReasoningToolInput.text(args, "scope_restriction"),
                verdict=ReasoningToolInput.text(args, "verdict"),
                title=ReasoningToolInput.text(args, "title", "Quantifier Analysis")
                or "Quantifier Analysis",
            ),
        )
