"""FILE: vidbyte/tools/builtins/reasoning/dialectic.py

PURPOSE: Records one dialectic reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the dialectic tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen DialecticContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    "thesis",
    "antithesis",
    "synthesis",
    "preserved_insight",
    "discarded_insight",
    "synthesis_stability",
)


class DialecticTool(BaseTool):
    """Builtin tool that records a thesis-antithesis-synthesis resolution into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="dialectic",
            description=(
                "Resolve a contradiction through synthesis: state the thesis, the strongest possible "
                "antithesis, the synthesis that holds both, what each side preserved and discarded, and how "
                "stable the synthesis is. Use this when two positions clash and the resolution must do more "
                "than pick a winner — the synthesis must genuinely hold the tension, not paper over it. The "
                "required fields make each part of the strategy explicit so the conclusion can be examined "
                "against its stated basis. The recorded result preserves the analysis for later iterations "
                "without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="thesis",
                    type="string",
                    description=(
                        "The starting position, stated at its strongest — not the weakest version that would be easy to "
                        "beat. A strawman thesis produces a fake synthesis. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion. "
                        "Keeping it explicit prevents the analysis from relying on an unstated assumption and gives "
                        "later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="antithesis",
                    type="string",
                    description=(
                        "The strongest opposing position — the contradiction the thesis must answer. Must differ from "
                        "thesis (case-insensitive): a dialectic between identical positions is not a contradiction. A "
                        "soft or friendly antithesis produces a cheap synthesis. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="synthesis",
                    type="string",
                    description=(
                        "The position that resolves the contradiction by holding what is true in both — stated "
                        "concretely enough that it can be judged against both sides. A synthesis that simply repeats "
                        "one side has not synthesized. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="preserved_insight",
                    type="string",
                    description=(
                        "What the synthesis keeps from each side — the truths that survive. Name both sides' "
                        "contributions explicitly, or the synthesis is unbalanced. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion. "
                        "Keeping it explicit prevents the analysis from relying on an unstated assumption and gives "
                        "later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="discarded_insight",
                    type="string",
                    description=(
                        "What each side gives up in the synthesis — and why it is safe to give up. A synthesis that "
                        "discards nothing has not resolved anything. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="synthesis_stability",
                    type="string",
                    description=(
                        "How durable the synthesis is — what new pressure would reopen the contradiction, and whether "
                        "the synthesis absorbs or fractures under it. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison. State only the information relevant to this field so "
                        "the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the dialectic primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"dialectic:{self._counter}"
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
        # Returns an error string for a missing field or an antithesis that equals the thesis.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        thesis = ReasoningToolInput.text(args, "thesis")
        antithesis = ReasoningToolInput.text(args, "antithesis")
        if antithesis.lower() == thesis.lower():
            return (
                "Field 'antithesis' must differ from 'thesis' — a dialectic between "
                "identical positions is not a contradiction."
            )
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the DialecticContextItem from validated call arguments.
        from vidbyte.context.primitives import DialecticContextItem

        return cast(
            ContextItem,
            DialecticContextItem(
                primitive_id=primitive_id,
                thesis=ReasoningToolInput.text(args, "thesis"),
                antithesis=ReasoningToolInput.text(args, "antithesis"),
                synthesis=ReasoningToolInput.text(args, "synthesis"),
                preserved_insight=ReasoningToolInput.text(args, "preserved_insight"),
                discarded_insight=ReasoningToolInput.text(args, "discarded_insight"),
                synthesis_stability=ReasoningToolInput.text(
                    args, "synthesis_stability"
                ),
                title=ReasoningToolInput.text(args, "title", "Dialectic")
                or "Dialectic",
            ),
        )
