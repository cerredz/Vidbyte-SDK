"""FILE: vidbyte/tools/builtins/reasoning/paradox.py

PURPOSE: Records one paradox reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the paradox tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen ParadoxContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
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
    "paradox",
    "premises",
    "hidden_assumption",
    "premise_to_drop",
    "resolution",
    "what_it_reveals",
)


class ParadoxTool(BaseTool):
    """Builtin tool that records a paradox dissection into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="paradox",
            description=(
                "Dissect a paradox: state the paradox, enumerate the premises that produce it, name the hidden "
                "assumption, choose exactly one premise to drop, give the resolution, and say what the paradox "
                "reveals. Use this whenever an argument produces a genuine contradiction — every paradox is a "
                "small set of premises with one impostor, and the dissection finds it. The required fields make "
                "each part of the strategy explicit so the conclusion can be examined against its stated basis. "
                "The recorded result preserves the analysis for later iterations without independently "
                "verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="paradox",
                    type="string",
                    description=(
                        "The paradox, stated as the contradiction it produces — e.g. 'the barber shaves all and only "
                        "those who do not shave themselves'. The premises below must generate this exact contradiction. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "The premises the paradox runs on, each a separate string. At "
                        "least two are required — a paradox needs tension between "
                        "premises to be a paradox. Every premise that the contradiction "
                        "actually depends on must be listed; an unlisted premise is a "
                        "hidden assumption wearing a premise's absence. May be passed as "
                        "a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="hidden_assumption",
                    type="string",
                    description=(
                        "The unstated commitment that quietly makes the paradox work — the assumption the premises "
                        "share but never declare. 'None' is an answer only when the listed premises genuinely generate "
                        "the contradiction alone. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premise_to_drop",
                    type="string",
                    description=(
                        "The single premise to reject, stated exactly as it appears in premises (matching is "
                        "case-sensitive) — the contradiction evaporates only when the right premise goes. Choosing a "
                        "premise that is not listed means the audit has not finished. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="resolution",
                    type="string",
                    description=(
                        "What remains after dropping the premise — the consistent situation that replaces the paradox, "
                        "and why the dropped premise was the impostor rather than any other. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison. State only the information relevant "
                        "to this field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_it_reveals",
                    type="string",
                    description=(
                        "What the paradox teaches beyond its own resolution — the general limit or assumption it "
                        "exposes about the domain (self-reference, totality, unboundedness). A dissection that names no "
                        "lesson has only resolved, not understood. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the paradox primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"paradox:{self._counter}"
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
        # Returns an error string for a missing field, undersized premises, or a premise_to_drop not in premises.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        premises = ReasoningToolInput.string_list(args.get("premises"))
        if len(premises) < 2:
            return "Field 'premises' requires at least two premises for a paradox."
        if ReasoningToolInput.text(args, "premise_to_drop") not in premises:
            return "Field 'premise_to_drop' must name one of the stated 'premises'."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the ParadoxContextItem from validated call arguments.
        from vidbyte.context.primitives import ParadoxContextItem

        return cast(
            ContextItem,
            ParadoxContextItem(
                primitive_id=primitive_id,
                paradox=ReasoningToolInput.text(args, "paradox"),
                premises=ReasoningToolInput.string_list(args.get("premises")),
                hidden_assumption=ReasoningToolInput.text(args, "hidden_assumption"),
                premise_to_drop=ReasoningToolInput.text(args, "premise_to_drop"),
                resolution=ReasoningToolInput.text(args, "resolution"),
                what_it_reveals=ReasoningToolInput.text(args, "what_it_reveals"),
                title=ReasoningToolInput.text(args, "title", "Paradox Dissection")
                or "Paradox Dissection",
            ),
        )
