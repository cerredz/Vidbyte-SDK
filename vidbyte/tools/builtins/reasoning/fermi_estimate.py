"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/fermi_estimate.py
PURPOSE: Implements the model-callable fermi-estimate reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

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
                "Use this tool when an unknown quantity must be estimated without a direct "
                "measurement. It decomposes the quantity into simpler factors and combines "
                "their estimates through explicit arithmetic. A sanity band and anchor-risk "
                "note expose the assumptions most likely to create an order-of-magnitude error. "
                "The resulting record should make the calculation reproducible and identify "
                "which input would most improve the estimate."
            ),
            parameters=(
                ToolParameter(
                    name="quantity",
                    type="string",
                    description=(
                        "Name the unknown quantity being estimated. State it precisely enough that "
                        "the model can identify the relevant units and boundary. A clear quantity "
                        "keeps the decomposition focused on the question that needs an answer. "
                        "Provide it as a plain string and include units when they are meaningful."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="decomposition",
                    type="array",
                    description=(
                        "Break the quantity into factors that are individually easier to estimate "
                        "than the whole. State one factor per entry with its rough value and unit. "
                        "This decomposition lets the model inspect and revise assumptions instead "
                        "of guessing the final answer directly. Provide a JSON array of strings or "
                        "a JSON-encoded string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="arithmetic",
                    type="string",
                    description=(
                        "Show how the decomposed factors combine to produce the estimate. Include "
                        "the relevant multiplication, division, or addition so another reader can "
                        "re-derive the result. Explicit arithmetic exposes unit mistakes and "
                        "unexamined assumptions in the calculation. Provide the calculation as a "
                        "plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="estimate",
                    type="string",
                    description=(
                        "State the resulting point estimate for the quantity. Include the units "
                        "that correspond to the original question. This is the central numerical "
                        "output produced by the decomposition and arithmetic. Provide it as a plain "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="sanity_band",
                    type="string",
                    description=(
                        "Give an order-of-magnitude range in which the true value should fall. "
                        "Use the range as an independent check on the point estimate, even when "
                        "the arithmetic is internally consistent. A broad sanity band helps the "
                        "model detect a factor that is wrong by ten times or more. Provide the band "
                        "as a plain string with units or clear endpoints."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="anchor_risk",
                    type="string",
                    description=(
                        "State whether an earlier number likely pulled the estimate toward it. Use "
                        "'none' when no meaningful anchor is present, 'anchored_low' when the "
                        "estimate may be biased downward, or 'anchored_high' when it may be biased "
                        "upward. This judgment helps the model distinguish an independently derived "
                        "estimate from a conversational starting point. Provide one of those enum "
                        "values as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded Fermi estimate. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Fermi Estimate'."
                    ),
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "The reasoning record could not be stored because its context values were invalid.",
                metadata={"error": "invalid_reasoning_context"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if decomposition, a required field, or the enum is invalid.
        if not ReasoningToolInput.string_list(args.get("decomposition")):
            return "Missing or empty required field: 'decomposition'."
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        anchor_risk = ReasoningToolInput.text(args, "anchor_risk")
        return ReasoningToolInput.enum_error(
            anchor_risk, _ANCHOR_RISK_VALUES, "anchor_risk"
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the FermiEstimateContextItem from validated call arguments.
        from vidbyte.context.primitives import FermiEstimateContextItem

        return cast(
            ContextItem,
            FermiEstimateContextItem(
                primitive_id=primitive_id,
                quantity=ReasoningToolInput.text(args, "quantity"),
                decomposition=ReasoningToolInput.string_list(args.get("decomposition")),
                arithmetic=ReasoningToolInput.text(args, "arithmetic"),
                estimate=ReasoningToolInput.text(args, "estimate"),
                sanity_band=ReasoningToolInput.text(args, "sanity_band"),
                anchor_risk=ReasoningToolInput.text(args, "anchor_risk"),
                title=ReasoningToolInput.text(args, "title", "Fermi Estimate")
                or "Fermi Estimate",
            ),
        )
