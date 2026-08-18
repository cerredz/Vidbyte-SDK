"""Context Protocol Header

Description:
    Implements FermiEstimateTool — a model-callable builtin for recording a
    decomposed order-of-magnitude estimate into the active ContextManager.
Purpose:
    Lets the model estimate an unknown quantity by factoring it into easier
    sub-estimates instead of guessing the answer directly, and forces a sanity
    band and anchor-risk note so a 10x-off guess gets caught.
Architecture:
    - FermiEstimateTool: BaseTool that constructs a FermiEstimateContextItem
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

_REQUIRED_FIELDS = ("quantity", "arithmetic", "estimate", "sanity_band", "anchor_risk")
_ANCHOR_RISK_VALUES = ("none", "anchored_low", "anchored_high")


class FermiEstimateTool(BaseTool):
    """Builtin tool that records a decomposed Fermi estimate into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="fermi_estimate",
            description=(
                "Estimate an unknown quantity by decomposing it into sub-estimates that are "
                "individually easier to guess than the whole, then combining them with explicit "
                "arithmetic. Use this whenever a number is needed and no direct measurement "
                "exists — the core move is to never guess the answer directly, only its "
                "factored inputs. A sanity band and an anchor-risk note are required so an "
                "order-of-magnitude error can be caught."
            ),
            parameters=(
                ToolParameter(
                    name="quantity",
                    type="string",
                    description="The unknown quantity being estimated, stated precisely with units (e.g. 'number of piano tuners in Chicago', 'requests per second at peak load').",
                    required=True,
                ),
                ToolParameter(
                    name="decomposition",
                    type="array",
                    description=(
                        "The quantity factored into sub-estimates that are individually easier "
                        "to guess than the whole (e.g. population, households per piano, tunings "
                        "per year, tuner capacity). Each entry is one factor with its rough value "
                        "and unit. This is the core Fermi move — guess the inputs, never the "
                        "answer directly. May be a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="arithmetic",
                    type="string",
                    description="How the decomposed factors combine (multiply, divide, sum) to produce the estimate, shown explicitly enough to be checked and re-derived.",
                    required=True,
                ),
                ToolParameter(
                    name="estimate",
                    type="string",
                    description="The resulting point estimate for quantity, with units.",
                    required=True,
                ),
                ToolParameter(
                    name="sanity_band",
                    type="string",
                    description="An order-of-magnitude range the true value should fall within (e.g. '3,000 to 30,000'), used to catch an estimate that is off by 10x or more even if the arithmetic looks clean.",
                    required=True,
                ),
                ToolParameter(
                    name="anchor_risk",
                    type="string",
                    description=(
                        "One of: 'none', 'anchored_low', 'anchored_high'. Names whether a number "
                        "seen earlier in this conversation or task likely pulled the estimate "
                        "toward it rather than the estimate being derived independently from the "
                        "decomposition."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Fermi Estimate'.",
                    required=False,
                    default="Fermi Estimate",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the Fermi-estimate primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"fermi_estimate:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if decomposition, a required field, or the enum is invalid.
        if not ReasoningToolInput.string_list(args.get("decomposition")):
            return "Missing or empty required field: 'decomposition'."
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        anchor_risk = ReasoningToolInput.text(args, "anchor_risk")
        return ReasoningToolInput.enum_error(anchor_risk, _ANCHOR_RISK_VALUES, "anchor_risk")

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the FermiEstimateContextItem from validated call arguments.
        from vidbyte.context.primitives import FermiEstimateContextItem
        return FermiEstimateContextItem(
            primitive_id=primitive_id,
            quantity=ReasoningToolInput.text(args, "quantity"),
            decomposition=ReasoningToolInput.string_list(args.get("decomposition")),
            arithmetic=ReasoningToolInput.text(args, "arithmetic"),
            estimate=ReasoningToolInput.text(args, "estimate"),
            sanity_band=ReasoningToolInput.text(args, "sanity_band"),
            anchor_risk=ReasoningToolInput.text(args, "anchor_risk"),
            title=ReasoningToolInput.text(args, "title", "Fermi Estimate") or "Fermi Estimate",
        )
