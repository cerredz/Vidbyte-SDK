"""FILE: vidbyte/tools/builtins/reasoning/statistical_syllogism.py

PURPOSE: Records one statistical syllogism reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the statistical_syllogism tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen StatisticalSyllogismContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    "population_claim",
    "frequency",
    "individual",
    "membership",
    "defeater",
    "probable_conclusion",
)


class StatisticalSyllogismTool(BaseTool):
    """Builtin tool that records a frequency-to-individual probability transfer into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="statistical_syllogism",
            description=(
                "Transfer a population frequency onto an individual: state the population claim, the frequency "
                "as a number, the individual, the membership that connects them, the defeater that could break "
                "the transfer, and the probable conclusion. Use this whenever the model concludes about one "
                "thing from a rate — the inference is only as good as the membership and the defeater. The "
                "required fields make each part of the strategy explicit so the conclusion can be examined "
                "against its stated basis. The recorded result preserves the analysis for later iterations "
                "without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="population_claim",
                    type="string",
                    description=(
                        "The rate claim over a population — e.g. '90% of retries succeed within 3 attempts'. The "
                        "frequency must be restated numerically in the frequency field. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="frequency",
                    type="string",
                    description=(
                        "The rate as a number between 0 and 1 — e.g. '0.9'. Must parse as a float; unparsable values "
                        "('most', 'a lot') are rejected. The transfer is only as precise as this number. This field is "
                        "part of the strategy's explicit contract, so its contribution can be reviewed separately from "
                        "the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="individual",
                    type="string",
                    description=(
                        "The single thing the probability is being transferred to — e.g. 'the retry about to be "
                        "issued'. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison. "
                        "State only the information relevant to this field so the recorded reasoning remains focused "
                        "and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="membership",
                    type="string",
                    description=(
                        "Why the individual belongs to the population — the actual connection, not an assumed one. An "
                        "individual that does not belong cannot inherit the population's frequency at all. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion. Keeping it explicit prevents the analysis from relying on an "
                        "unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="defeater",
                    type="string",
                    description=(
                        "What could break the transfer — a property of this individual that removes it from the "
                        "population's distribution, or a population statistic that hides a bimodal split. 'None known' "
                        "is an answer only after considering the obvious candidates. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion. Keeping it explicit prevents the analysis from relying on an unstated assumption "
                        "and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="probable_conclusion",
                    type="string",
                    description=(
                        "The conclusion about the individual, stated with its qualified confidence — including the case "
                        "where the defeater wins and the conclusion must not inherit the frequency. This field is part "
                        "of the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison. State only the "
                        "information relevant to this field so the recorded reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="string",
                    description=(
                        "Optional. A number between 0 and 1 expressing confidence in the "
                        "transfer itself (membership + defeater analysis), not a restatement "
                        "of frequency. Omit if not meaningfully assessable. Must parse as "
                        "a float."
                    ),
                    required=False,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the statistical_syllogism primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"statistical_syllogism:{self._counter}"
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
        # Returns an error string for a missing field or an unparsable frequency/confidence.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if ReasoningToolInput.probability(args.get("frequency")) is None:
            return (
                "Missing or unparsable required field: 'frequency'. Must be a number "
                "from 0.0 to 1.0."
            )
        if (
            args.get("confidence")
            and ReasoningToolInput.probability(args.get("confidence")) is None
        ):
            return (
                "Unparsable field: 'confidence'. Must be a number from 0.0 to 1.0 when "
                "provided."
            )
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the StatisticalSyllogismContextItem from validated call arguments.
        from vidbyte.context.primitives import StatisticalSyllogismContextItem

        return cast(
            ContextItem,
            StatisticalSyllogismContextItem(
                primitive_id=primitive_id,
                population_claim=ReasoningToolInput.text(args, "population_claim"),
                frequency=cast(
                    float, ReasoningToolInput.probability(args.get("frequency"))
                ),
                individual=ReasoningToolInput.text(args, "individual"),
                membership=ReasoningToolInput.text(args, "membership"),
                defeater=ReasoningToolInput.text(args, "defeater"),
                probable_conclusion=ReasoningToolInput.text(
                    args, "probable_conclusion"
                ),
                confidence=ReasoningToolInput.probability(args.get("confidence")),
                title=ReasoningToolInput.text(args, "title", "Statistical Syllogism")
                or "Statistical Syllogism",
            ),
        )
