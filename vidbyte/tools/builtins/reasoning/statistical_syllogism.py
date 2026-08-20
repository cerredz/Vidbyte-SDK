"""Context Protocol Header

Description:
    Implements StatisticalSyllogismTool — a model-callable builtin for recording
    a frequency-to-individual probability transfer into the active
    ContextManager.
Purpose:
    Lets the model force the population claim, the frequency, the individual,
    the membership, the defeater, and the probable conclusion into a checkable
    shape — the statistical syllogism is the workhorse inference of everyday
    probability, and its defeater is what keeps it honest.
Architecture:
    - StatisticalSyllogismTool: BaseTool that constructs a
      StatisticalSyllogismContextItem from model-provided arguments and upserts
      it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("population_claim", "frequency", "individual", "membership", "defeater", "probable_conclusion")


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
                "Transfer a population frequency onto an individual: state the population "
                "claim, the frequency as a number, the individual, the membership that "
                "connects them, the defeater that could break the transfer, and the "
                "probable conclusion. Use this whenever the model concludes about one "
                "thing from a rate — the inference is only as good as the membership and "
                "the defeater."
            ),
            parameters=(
                ToolParameter(
                    name="population_claim",
                    type="string",
                    description=(
                        "The rate claim over a population — e.g. '90% of retries succeed "
                        "within 3 attempts'. The frequency must be restated numerically "
                        "in the frequency field."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="frequency",
                    type="string",
                    description=(
                        "The rate as a number between 0 and 1 — e.g. '0.9'. Must parse "
                        "as a float; unparsable values ('most', 'a lot') are rejected. "
                        "The transfer is only as precise as this number."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="individual",
                    type="string",
                    description=(
                        "The single thing the probability is being transferred to — e.g. "
                        "'the retry about to be issued'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="membership",
                    type="string",
                    description=(
                        "Why the individual belongs to the population — the actual "
                        "connection, not an assumed one. An individual that does not "
                        "belong cannot inherit the population's frequency at all."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="defeater",
                    type="string",
                    description=(
                        "What could break the transfer — a property of this individual "
                        "that removes it from the population's distribution, or a "
                        "population statistic that hides a bimodal split. 'None known' is "
                        "an answer only after considering the obvious candidates."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="probable_conclusion",
                    type="string",
                    description=(
                        "The conclusion about the individual, stated with its qualified "
                        "confidence — including the case where the defeater wins and "
                        "the conclusion must not inherit the frequency."
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
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

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
        if args.get("confidence") and ReasoningToolInput.probability(args.get("confidence")) is None:
            return (
                "Unparsable field: 'confidence'. Must be a number from 0.0 to 1.0 when "
                "provided."
            )
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the StatisticalSyllogismContextItem from validated call arguments.
        from vidbyte.context.primitives import StatisticalSyllogismContextItem
        return StatisticalSyllogismContextItem(
            primitive_id=primitive_id,
            population_claim=ReasoningToolInput.text(args, "population_claim"),
            frequency=ReasoningToolInput.probability(args.get("frequency")),
            individual=ReasoningToolInput.text(args, "individual"),
            membership=ReasoningToolInput.text(args, "membership"),
            defeater=ReasoningToolInput.text(args, "defeater"),
            probable_conclusion=ReasoningToolInput.text(args, "probable_conclusion"),
            confidence=ReasoningToolInput.probability(args.get("confidence")),
            title=ReasoningToolInput.text(args, "title", "Statistical Syllogism") or "Statistical Syllogism",
        )