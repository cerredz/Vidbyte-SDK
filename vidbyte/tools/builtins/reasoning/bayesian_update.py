"""Context Protocol Header

Description:
    Implements BayesianUpdateTool — a model-callable builtin for recording an
    explicit prior-to-posterior belief revision into the active ContextManager.
Purpose:
    Forces silent belief drift into visible numbers: a stated prior, the
    evidence, both conditional likelihoods, and the resulting posterior, so the
    update is auditable rather than a vibe shift in confidence.
Architecture:
    - BayesianUpdateTool: BaseTool that constructs a BayesianUpdateContextItem
      from model-provided arguments and upserts it into the injected
      ContextManager.
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

_REQUIRED_TEXT_FIELDS = ("hypothesis", "evidence", "shift_explanation")
_REQUIRED_PROBABILITY_FIELDS = ("prior", "likelihood_if_true", "likelihood_if_false", "posterior")


class BayesianUpdateTool(BaseTool):
    """Builtin tool that records an explicit prior-to-posterior belief update into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="bayesian_update",
            description=(
                "Revise a belief in light of new evidence by stating the prior probability, "
                "both conditional likelihoods, and the resulting posterior probability as "
                "explicit numbers. Use this whenever new evidence should change how confident "
                "you are in a hypothesis — forcing the numbers makes an unexamined shift in "
                "confidence visible and checkable rather than silent."
            ),
            parameters=(
                ToolParameter(
                    name="hypothesis",
                    type="string",
                    description="The specific belief or hypothesis whose probability is being updated.",
                    required=True,
                ),
                ToolParameter(
                    name="prior",
                    type="string",
                    description=(
                        "Probability assigned to hypothesis BEFORE seeing the new evidence, 0.0 "
                        "to 1.0 (e.g. '0.3'). Required and must parse as a number — this is the "
                        "starting point the update is measured from."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description=(
                        "The new evidence or observation that triggered this update, stated "
                        "precisely enough that its likelihood under the hypothesis and under its "
                        "negation can both be judged."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="likelihood_if_true",
                    type="string",
                    description=(
                        "P(evidence | hypothesis is true) — how likely you would be to observe "
                        "this evidence if the hypothesis were true, 0.0 to 1.0. High values mean "
                        "the evidence is expected under the hypothesis."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="likelihood_if_false",
                    type="string",
                    description=(
                        "P(evidence | hypothesis is false) — how likely you would be to observe "
                        "this evidence if the hypothesis were false, 0.0 to 1.0. The gap between "
                        "this and likelihood_if_true is what does the updating; if they are "
                        "equal, this evidence should not move your belief at all."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="posterior",
                    type="string",
                    description=(
                        "Probability assigned to hypothesis AFTER incorporating the evidence, "
                        "0.0 to 1.0. Should move in the direction implied by likelihood_if_true "
                        "versus likelihood_if_false relative to prior — a posterior that does not "
                        "follow from the stated likelihoods signals unexamined belief drift "
                        "rather than a real update."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="shift_explanation",
                    type="string",
                    description=(
                        "In plain language, why the posterior moved the amount it did (or why it "
                        "barely moved) — connect the arithmetic to the reasoning so the update is "
                        "auditable, not just a pair of numbers."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Bayesian Update'.",
                    required=False,
                    default="Bayesian Update",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the Bayesian-update primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"bayesian_update:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing text field or an unparsable required probability.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_TEXT_FIELDS)
        if error:
            return error
        for field_name in _REQUIRED_PROBABILITY_FIELDS:
            if ReasoningToolInput.probability(args.get(field_name)) is None:
                return (
                    f"Missing or unparsable required field: '{field_name}'. Must be a number "
                    "from 0.0 to 1.0."
                )
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the BayesianUpdateContextItem from validated call arguments.
        from vidbyte.context.primitives import BayesianUpdateContextItem
        return BayesianUpdateContextItem(
            primitive_id=primitive_id,
            hypothesis=ReasoningToolInput.text(args, "hypothesis"),
            prior=ReasoningToolInput.probability(args.get("prior")),
            evidence=ReasoningToolInput.text(args, "evidence"),
            likelihood_if_true=ReasoningToolInput.probability(args.get("likelihood_if_true")),
            likelihood_if_false=ReasoningToolInput.probability(args.get("likelihood_if_false")),
            posterior=ReasoningToolInput.probability(args.get("posterior")),
            shift_explanation=ReasoningToolInput.text(args, "shift_explanation"),
            title=ReasoningToolInput.text(args, "title", "Bayesian Update") or "Bayesian Update",
        )
