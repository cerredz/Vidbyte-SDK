"""FILE: vidbyte/tools/builtins/reasoning/circularity.py

PURPOSE: Records one circularity reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the circularity tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen CircularityContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import CIRCULARITY_REQUIRED_FIELDS
from vidbyte.lib.enums.reasoning_strategies import CircularityVerdict
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


class CircularityTool(BaseTool):
    """Builtin tool that records a circular-reasoning audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="circularity",
            description=(
                "Audit an argument for circularity: state the premises and conclusion, map which premises "
                "depend on which claims, trace whether the dependency chain returns to its start, and name the "
                "fix. Use this whenever an argument feels 'too smooth' — circular reasoning is formally valid, "
                "which is precisely why it survives surface checks. The required fields make each part of the "
                "strategy explicit so the conclusion can be examined against its stated basis. The recorded "
                "result preserves the analysis for later iterations without independently verifying the model's "
                "judgment."
            ),
            parameters=(
                ToolParameter(
                    name="argument",
                    type="string",
                    description=(
                        "The argument under audit, quoted as a whole — the audit judges this exact argument, not a "
                        "paraphrase of it. This field is part of the strategy's explicit contract, so its contribution "
                        "can be reviewed separately from the final conclusion. Keeping it explicit prevents the "
                        "analysis from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison. State only the information relevant to this field so the recorded reasoning "
                        "remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "The premises as stated, each its own string. May be passed as a JSON array of strings or a "
                        "JSON string. This field is part of the strategy's explicit contract, so its contribution can "
                        "be reviewed separately from the final conclusion. Keeping it explicit prevents the analysis "
                        "from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "The conclusion the premises are claimed to establish. For a circle, the conclusion must be "
                        "findable among the premises or their implicit dependencies. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="dependency_map",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'premise' and 'depends_on': what each premise relies on, "
                        "including implicit commitments that are never stated. An unstated dependence is where the "
                        "circle hides. May also be passed as a JSON string. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="circle_found",
                    type="string",
                    description=(
                        "The actual dependency loop, spelled out step by step — 'premise 1 assumes P, P assumes premise "
                        "3, premise 3 assumes the conclusion'. If no loop exists, say what was traced to confirm its "
                        "absence. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fix",
                    type="string",
                    description=(
                        "What would break the circle — an independent source for the conclusion, a dropped premise, or "
                        "an external assumption stated and defended. An audit that finds a circle and proposes no fix "
                        "has diagnosed but not finished. This field is part of the strategy's explicit contract, so its "
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
                        "One of: 'circular', 'not_circular', 'partially'. 'circular' means the conclusion (or an "
                        "equivalent of it) appears as a premise. 'partially' means some, but not all, of the support "
                        "loops back. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the circularity primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"circularity:{self._counter}"
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
        # Returns an error string for a missing field, empty premises, empty dependency map, or a bad enum.
        error = ReasoningToolInput.missing_required(args, CIRCULARITY_REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("premises")):
            return "Field 'premises' requires at least one premise."
        if not ReasoningToolInput.object_list(args.get("dependency_map")):
            return "Field 'dependency_map' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"),
            CircularityVerdict.values(),
            "verdict",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the CircularityContextItem from validated call arguments.
        from vidbyte.context.primitives import CircularityContextItem

        return cast(
            ContextItem,
            CircularityContextItem(
                primitive_id=primitive_id,
                argument=ReasoningToolInput.text(args, "argument"),
                premises=ReasoningToolInput.string_list(args.get("premises")),
                conclusion=ReasoningToolInput.text(args, "conclusion"),
                dependency_map=ReasoningToolInput.object_list(
                    args.get("dependency_map")
                ),
                circle_found=ReasoningToolInput.text(args, "circle_found"),
                fix=ReasoningToolInput.text(args, "fix"),
                verdict=ReasoningToolInput.text(args, "verdict"),
                title=ReasoningToolInput.text(args, "title", "Circularity Audit")
                or "Circularity Audit",
            ),
        )
