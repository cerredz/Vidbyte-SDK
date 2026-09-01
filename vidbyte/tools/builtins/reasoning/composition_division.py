"""FILE: vidbyte/tools/builtins/reasoning/composition_division.py

PURPOSE: Records one composition division reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the composition_division tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen CompositionDivisionContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    COMPOSITION_DIVISION_REQUIRED_FIELDS,
    COMPOSITION_DIVISION_VALIDITY_VALUES,
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
                "Audit a property transfer between a whole and its parts: state the parts, the whole, the "
                "property, and the aggregation claim, then commit to a verdict and name the deciding "
                "counterexample. Use this whenever the model concludes that a whole has a property because its "
                "parts do (composition) or that a part has a property because the whole does (division) — "
                "distributive properties transfer, collective properties do not, and the boundary between them "
                "is where the fallacies live. The required fields make each part of the strategy explicit so "
                "the conclusion can be examined against its stated basis. The recorded result preserves the "
                "analysis for later iterations without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="parts",
                    type="array",
                    description=(
                        "The constituent parts, each named — e.g. 'each module is independently tested'. May be passed "
                        "as a JSON array of strings or a JSON string. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="whole",
                    type="string",
                    description=(
                        "The aggregate — e.g. 'the full application'. The whole must be the genuine sum of the parts, "
                        "or the audit is about different objects. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="property",
                    type="string",
                    description=(
                        "The property being transferred across levels — e.g. 'tested', 'fast', 'contains a defect'. "
                        "Whether the transfer is valid depends on whether this property is distributive or collective. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="aggregation_claim",
                    type="string",
                    description=(
                        "The exact inference under audit — e.g. 'each module is tested, therefore the application is "
                        "tested'. Quote the claim; the verdict judges this claim and no other. This field is part of "
                        "the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
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
                        "The concrete case that decides the verdict — a collective property held only by the whole, or "
                        "a distributive property borne by each part. For 'unknown', state what evidence would decide "
                        "it. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty parts, or a bad validity enum.
        error = ReasoningToolInput.missing_required(
            args, COMPOSITION_DIVISION_REQUIRED_FIELDS
        )
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("parts")):
            return "Field 'parts' requires at least one part."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "validity"),
            COMPOSITION_DIVISION_VALIDITY_VALUES,
            "validity",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the CompositionDivisionContextItem from validated call arguments.
        from vidbyte.context.primitives import CompositionDivisionContextItem

        return cast(
            ContextItem,
            CompositionDivisionContextItem(
                primitive_id=primitive_id,
                parts=ReasoningToolInput.string_list(args.get("parts")),
                whole=ReasoningToolInput.text(args, "whole"),
                property=ReasoningToolInput.text(args, "property"),
                aggregation_claim=ReasoningToolInput.text(args, "aggregation_claim"),
                validity=ReasoningToolInput.text(args, "validity"),
                counterexample=ReasoningToolInput.text(args, "counterexample"),
                title=ReasoningToolInput.text(args, "title", "Part-Whole Check")
                or "Part-Whole Check",
            ),
        )
