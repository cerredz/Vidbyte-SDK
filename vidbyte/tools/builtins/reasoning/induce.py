"""Context Protocol Header

Description:
    Implements InduceTool — a model-callable builtin for recording an inductive
    generalization into the active ContextManager.
Purpose:
    Lets the model force a generalization projected from specific observations
    into a shape that names its own sample-bias risk and falsifying case,
    rather than presenting an inductive leap as settled fact.
Architecture:
    - InduceTool: BaseTool that constructs an InductionContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager, vidbyte.context.primitives, and the
    shared vidbyte.tools.builtins.reasoning._parsing.ReasoningToolInput helper.
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

_REQUIRED_FIELDS = ("pattern", "generalization", "sample_bias_risk", "falsifying_case")


class InduceTool(BaseTool):
    """Builtin tool that records an inductive generalization into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="induce",
            description=(
                "Run an inductive generalization: list the specific observations, name the "
                "pattern they share, and state the general claim projected beyond them. Use "
                "this when reasoning from particular cases to a general rule. Inductive "
                "conclusions are never certain by construction, so a sample-bias risk and a "
                "concrete falsifying case are required alongside the generalization itself."
            ),
            parameters=(
                ToolParameter(
                    name="observations",
                    type="array",
                    description=(
                        "List the specific instances or data points from which the "
                        "generalization is drawn. Keep each entry as one concrete observation "
                        "rather than a summary of many cases. These observations are the "
                        "evidence from which the model will separate a pattern from a broader "
                        "claim. Provide a JSON array of strings or a JSON-encoded string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description=(
                        "Describe the regularity noticed across the observations. State the "
                        "pattern before extending it to future or unseen cases. Keeping this "
                        "description separate helps the model distinguish an observation from "
                        "the inductive leap built on it. Provide the pattern as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="generalization",
                    type="string",
                    description=(
                        "State the general claim projected from the pattern beyond the listed "
                        "observations. Make the scope clear, such as all cases, future cases, "
                        "or a stated population. This is the inductive leap and is not guaranteed "
                        "by the observations alone. Provide the generalization as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="sample_bias_risk",
                    type="string",
                    description=(
                        "Describe how the observation set could be unrepresentative. Consider a "
                        "small or self-selected sample, one time or place, survivorship bias, or "
                        "another systematic source of skew. This risk shows how the generalization "
                        "could fail even when every individual observation is accurate. Provide "
                        "the risk assessment as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="falsifying_case",
                    type="string",
                    description=(
                        "Give a concrete observation that would break the generalization if it "
                        "occurred. Make the case specific enough that a future observation could "
                        "be compared with it. This field gives the model a way to test the claim "
                        "instead of treating the pattern as certain. Provide the falsifying case "
                        "as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="string",
                    description=(
                        "Give a calibrated confidence in the generalization on a scale from 0.0 "
                        "to 1.0, written as a numeric string such as '0.6'. Use the value to show "
                        "how strongly the observations support the broader claim, not how certain "
                        "the wording sounds. Inductive conclusions are provisional, so very high "
                        "values should be unusual. This parameter is optional and may be omitted."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded generalization. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Inductive Generalization'."
                    ),
                    required=False,
                    default="Inductive Generalization",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the induction primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"induce:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if observations or any required scalar field is missing.
        if not ReasoningToolInput.string_list(args.get("observations")):
            return "Missing or empty required field: 'observations'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the InductionContextItem from validated call arguments.
        from vidbyte.context.primitives import InductionContextItem

        return cast(
            ContextItem,
            InductionContextItem(
                primitive_id=primitive_id,
                observations=ReasoningToolInput.string_list(args.get("observations")),
                pattern=ReasoningToolInput.text(args, "pattern"),
                generalization=ReasoningToolInput.text(args, "generalization"),
                sample_bias_risk=ReasoningToolInput.text(args, "sample_bias_risk"),
                falsifying_case=ReasoningToolInput.text(args, "falsifying_case"),
                confidence=ReasoningToolInput.probability(args.get("confidence")),
                title=ReasoningToolInput.text(args, "title", "Inductive Generalization")
                or "Inductive Generalization",
            ),
        )
