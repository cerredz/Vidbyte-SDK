"""FILE: vidbyte/tools/builtins/reasoning/transitivity.py

PURPOSE: Records one transitivity reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the transitivity tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen TransitivityContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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

_REQUIRED_FIELDS = ("pairwise_links", "derived_chain", "cycle_detected", "consistency")
_CONSISTENCY_VALUES = ("consistent", "cyclic", "intransitive")


class TransitivityTool(BaseTool):
    """Builtin tool that records a transitive-chain audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="transitivity",
            description=(
                "Audit a relation for transitive chaining: state the entities and the relation, list the "
                "checked pairwise links, derive the implied chain, check for cycles, and commit to a verdict. "
                "Use this when the model is about to conclude A relates to C from A relates to B and B relates "
                "to C — some relations (preference, similarity, dependency) are famously not transitive, and "
                "chains built on them are false chains. The required fields make each part of the strategy "
                "explicit so the conclusion can be examined against its stated basis. The recorded result "
                "preserves the analysis for later iterations without independently verifying the model's "
                "judgment."
            ),
            parameters=(
                ToolParameter(
                    name="entities",
                    type="array",
                    description=(
                        "The items under audit — e.g. 'A', 'B', 'C'. May be passed as a JSON array of strings or a JSON "
                        "string. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="relation",
                    type="string",
                    description=(
                        "The relation being chained — e.g. 'equals', 'prefers', 'depends on'. Whether the chain is "
                        "valid depends entirely on whether this relation is transitive; name it precisely. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion. Keeping it explicit prevents the analysis from relying on an "
                        "unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pairwise_links",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'from', 'to', and 'holds': the checked direct links and "
                        "whether each was verified true. Links assumed without checking must be marked 'holds': false "
                        "or omitted — an unchecked link is not a link. May also be passed as a JSON string. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="derived_chain",
                    type="array",
                    description=(
                        "The transitive conclusions forced by the links — each chain stated as its own string, e.g. 'A "
                        "equals C via B'. If the relation is found non-transitive, state the chain that would have "
                        "followed but does not. May be passed as a JSON array of strings or a JSON string. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="cycle_detected",
                    type="string",
                    description=(
                        "Whether the links form a loop (A→B, B→C, C→A) and, if so, what the loop implies for the chain. "
                        "A cycle in a strict-order relation is a contradiction; in an equivalence relation it is "
                        "expected. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="consistency",
                    type="string",
                    description=(
                        "One of: 'consistent', 'cyclic', 'intransitive'. 'consistent' means "
                        "the chain holds under the relation. 'cyclic' means the links form "
                        "a loop that undermines ordering. 'intransitive' means the relation "
                        "does not chain the way the argument assumed."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the transitivity primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"transitivity:{self._counter}"
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
        # Returns an error string for a missing field, empty links, or a bad consistency enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.object_list(args.get("pairwise_links")):
            return "Field 'pairwise_links' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "consistency"),
            _CONSISTENCY_VALUES,
            "consistency",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the TransitivityContextItem from validated call arguments.
        from vidbyte.context.primitives import TransitivityContextItem

        return cast(
            ContextItem,
            TransitivityContextItem(
                primitive_id=primitive_id,
                entities=ReasoningToolInput.string_list(args.get("entities")),
                relation=ReasoningToolInput.text(args, "relation"),
                pairwise_links=ReasoningToolInput.object_list(
                    args.get("pairwise_links")
                ),
                derived_chain=ReasoningToolInput.string_list(args.get("derived_chain")),
                cycle_detected=ReasoningToolInput.text(args, "cycle_detected"),
                consistency=ReasoningToolInput.text(args, "consistency"),
                title=ReasoningToolInput.text(args, "title", "Transitive Chain")
                or "Transitive Chain",
            ),
        )
