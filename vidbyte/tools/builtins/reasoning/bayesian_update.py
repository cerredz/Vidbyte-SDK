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

_REQUIRED_TEXT_FIELDS = ("hypothesis", "evidence", "shift_explanation")
_REQUIRED_PROBABILITY_FIELDS = (
    "prior",
    "likelihood_if_true",
    "likelihood_if_false",
    "posterior",
)


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
                    description=(
                        "Name the specific belief or hypothesis whose probability is being "
                        "updated. State it clearly enough that the evidence can be evaluated as "
                        "supporting or weakening it. A precise hypothesis gives the probability "
                        "values a stable subject across the update. Provide it as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="prior",
                    type="string",
                    description=(
                        "Give the probability assigned to the hypothesis before the new evidence "
                        "is considered. Express it as a numeric string from 0.0 to 1.0, such as "
                        "'0.3'. This is the starting point against which the belief change is "
                        "measured. The value is required and must parse as a probability."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="evidence",
                    type="string",
                    description=(
                        "Describe the new evidence or observation that triggered the update. State "
                        "it precisely enough that its likelihood can be judged under both the "
                        "hypothesis and its negation. This identifies what information should move "
                        "the belief rather than leaving the update unexplained. Provide the "
                        "evidence as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="likelihood_if_true",
                    type="string",
                    description=(
                        "Give the probability of observing the evidence when the hypothesis is "
                        "true. Express it as a numeric string from 0.0 to 1.0. This value shows "
                        "how expected the evidence would be if the hypothesis were correct. It is "
                        "required so the model can compare both sides of the update."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="likelihood_if_false",
                    type="string",
                    description=(
                        "Give the probability of observing the evidence when the hypothesis is "
                        "false. Express it as a numeric string from 0.0 to 1.0. Comparing this "
                        "value with likelihood_if_true shows whether the evidence distinguishes "
                        "the two states. If the values are equal, the evidence should not move the "
                        "prior belief."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="posterior",
                    type="string",
                    description=(
                        "Give the probability assigned to the hypothesis after incorporating the "
                        "evidence. Express it as a numeric string from 0.0 to 1.0. The posterior "
                        "should move from the prior in the direction implied by the two likelihoods. "
                        "A value that does not fit those inputs signals an unexplained belief shift "
                        "and should be revisited."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="shift_explanation",
                    type="string",
                    description=(
                        "Explain in plain language why the posterior moved by the stated amount. "
                        "Connect the prior, evidence, and likelihood comparison to the resulting "
                        "belief. This gives the model an interpretable reason for the numerical "
                        "update rather than just a pair of probabilities. Provide the explanation "
                        "as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded belief update. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Bayesian Update'."
                    ),
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

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the BayesianUpdateContextItem from validated call arguments.
        from vidbyte.context.primitives import BayesianUpdateContextItem

        prior = ReasoningToolInput.probability(args.get("prior"))
        likelihood_if_true = ReasoningToolInput.probability(
            args.get("likelihood_if_true")
        )
        likelihood_if_false = ReasoningToolInput.probability(
            args.get("likelihood_if_false")
        )
        posterior = ReasoningToolInput.probability(args.get("posterior"))
        assert prior is not None
        assert likelihood_if_true is not None
        assert likelihood_if_false is not None
        assert posterior is not None
        return cast(
            ContextItem,
            BayesianUpdateContextItem(
                primitive_id=primitive_id,
                hypothesis=ReasoningToolInput.text(args, "hypothesis"),
                prior=prior,
                evidence=ReasoningToolInput.text(args, "evidence"),
                likelihood_if_true=likelihood_if_true,
                likelihood_if_false=likelihood_if_false,
                posterior=posterior,
                shift_explanation=ReasoningToolInput.text(args, "shift_explanation"),
                title=ReasoningToolInput.text(args, "title", "Bayesian Update")
                or "Bayesian Update",
            ),
        )
