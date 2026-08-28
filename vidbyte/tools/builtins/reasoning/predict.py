"""FILE: vidbyte/tools/builtins/reasoning/predict.py

PURPOSE: Records one predict reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the predict tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen PredictContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    "theory",
    "initial_conditions",
    "derived_prediction",
    "observed_outcome",
    "match",
    "revision",
)
_MATCH_VALUES = ("yes", "no", "partial")


class PredictTool(BaseTool):
    """Builtin tool that records a hypothesis-derived prediction and its outcome into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="predict",
            description=(
                "Derive a prediction from a theory and check it against the observed outcome: state the theory, "
                "the initial conditions, the prediction that follows, the outcome actually observed, the match, "
                "and the revision the comparison forces. Use this whenever a theory or model is being relied on "
                "— the prediction step is where theories become testable and the comparison step is where they "
                "become trustworthy. The required fields make each part of the strategy explicit so the "
                "conclusion can be examined against its stated basis. The recorded result preserves the "
                "analysis for later iterations without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="theory",
                    type="string",
                    description=(
                        "The theory or model the prediction is derived from — stated precisely enough that the "
                        "derivation below can be checked. A theory too vague to derive anything from cannot be tested. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="initial_conditions",
                    type="array",
                    description=(
                        "The concrete conditions under which the prediction is made — the input state the theory needs. "
                        "Conditions must be specific enough that the outcome can be compared against the prediction. "
                        "May be passed as a JSON array of strings or a JSON string. This field is part of the "
                        "strategy's explicit contract, so its contribution can be reviewed separately from the final "
                        "conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="derived_prediction",
                    type="string",
                    description=(
                        "What the theory implies will happen under the initial conditions — stated concretely enough to "
                        "be confirmed or refuted. 'Something will improve' is not a prediction; 'the error rate will "
                        "fall below 1%' is. This field is part of the strategy's explicit contract, so its contribution "
                        "can be reviewed separately from the final conclusion. Keeping it explicit prevents the "
                        "analysis from relying on an unstated assumption and gives later iterations a stable basis for "
                        "comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="observed_outcome",
                    type="string",
                    description=(
                        "What actually happened — the observation, with its source and measurement noted. An outcome "
                        "observed without stating how it was observed is an assertion, not an outcome. This field is "
                        "part of the strategy's explicit contract, so its contribution can be reviewed separately from "
                        "the final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="match",
                    type="string",
                    description=(
                        "One of: 'yes', 'no', 'partial'. 'yes' means the outcome "
                        "confirms the prediction. 'no' means it refutes it. 'partial' "
                        "means it lands in between — and the partial match is analyzed, "
                        "not waved through."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="revision",
                    type="string",
                    description=(
                        "What the comparison does to the theory — confirmed, refined, narrowed, or abandoned, with the "
                        "specific adjustment named. A prediction check that revises nothing has learned nothing. This "
                        "field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the predict primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"predict:{self._counter}"
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
        # Returns an error string for a missing field, empty conditions, or a bad match enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("initial_conditions")):
            return "Field 'initial_conditions' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "match"), _MATCH_VALUES, "match"
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the PredictContextItem from validated call arguments.
        from vidbyte.context.primitives import PredictContextItem

        return cast(
            ContextItem,
            PredictContextItem(
                primitive_id=primitive_id,
                theory=ReasoningToolInput.text(args, "theory"),
                initial_conditions=ReasoningToolInput.string_list(
                    args.get("initial_conditions")
                ),
                derived_prediction=ReasoningToolInput.text(args, "derived_prediction"),
                observed_outcome=ReasoningToolInput.text(args, "observed_outcome"),
                match=ReasoningToolInput.text(args, "match"),
                revision=ReasoningToolInput.text(args, "revision"),
                title=ReasoningToolInput.text(
                    args, "title", "Deductive-Nomological Prediction"
                )
                or "Deductive-Nomological Prediction",
            ),
        )
