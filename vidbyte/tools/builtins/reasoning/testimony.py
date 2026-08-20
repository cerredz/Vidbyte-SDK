"""Context Protocol Header

Description:
    Implements TestimonyTool — a model-callable builtin for recording a
    testimony-reliability evaluation into the active ContextManager.
Purpose:
    Lets the model force the source, the claim, the reliability factors, the
    corroboration and conflicts, a trust verdict, and the residual uncertainty
    into a checkable shape — testimony is evidence whose value depends entirely
    on the source and the company it keeps.
Architecture:
    - TestimonyTool: BaseTool that constructs a TestimonyContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("source", "claim", "reliability_factors", "trust_verdict", "residual_uncertainty")
_REQUIRED_PRESENT_FIELDS = ("corroboration", "conflicts")
_TRUST_VALUES = ("high", "moderate", "low", "withheld")


class TestimonyTool(BaseTool):
    """Builtin tool that records a testimony-reliability evaluation into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="testimony",
            description=(
                "Evaluate a testimony: name the source, the claim, the reliability factors "
                "with their assessments, the corroboration and conflicts, and commit to a "
                "trust verdict with the residual uncertainty stated. Use this whenever the "
                "model is about to act on information attributed to a person, document, or "
                "system — testimony is the one evidence type whose trust must be argued, "
                "not assumed."
            ),
            parameters=(
                ToolParameter(
                    name="source",
                    type="string",
                    description=(
                        "Who or what testifies — a person, document, system, or channel, "
                        "named precisely. 'Someone said' is not a source."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "What the source asserts, quoted or paraphrased faithfully. The "
                        "evaluation grades this claim from this source — swap either and "
                        "the grade is void."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reliability_factors",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'factor' and 'assessment': the "
                        "relevant factors (expertise, access, incentive, track record, "
                        "freshness) and a substantive assessment of each — not 'good' or "
                        "'bad' but why. May also be passed as a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="corroboration",
                    type="array",
                    description=(
                        "Independent sources or evidence supporting the claim, each named. "
                        "'Independent' is the point — a second source quoting the first "
                        "corroborates nothing. May be passed as a JSON array of strings "
                        "or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conflicts",
                    type="array",
                    description=(
                        "Sources or evidence contradicting the claim, each named. An "
                        "empty list is a real answer, but only if a genuine search was "
                        "made — say what was searched. May be passed as a JSON array of "
                        "strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="trust_verdict",
                    type="string",
                    description=(
                        "One of: 'high', 'moderate', 'low', 'withheld'. 'withheld' means "
                        "the testimony cannot be graded on available information — the "
                        "correct verdict when factors are unknown, not a cop-out."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="residual_uncertainty",
                    type="string",
                    description=(
                        "What remains unknown even at the chosen trust level — the "
                        "failure mode the testimony could still hide. An evaluation that "
                        "names no residual uncertainty has not actually evaluated."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the testimony primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"testimony:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, a missing corroboration/conflicts key, empty factors, or a bad trust enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        for name in _REQUIRED_PRESENT_FIELDS:
            if name not in args:
                return f"Missing or empty required field: '{name}'."
        if not ReasoningToolInput.object_list(args.get("reliability_factors")):
            return "Field 'reliability_factors' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "trust_verdict"), _TRUST_VALUES, "trust_verdict"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the TestimonyContextItem from validated call arguments.
        from vidbyte.context.primitives import TestimonyContextItem
        return TestimonyContextItem(
            primitive_id=primitive_id,
            source=ReasoningToolInput.text(args, "source"),
            claim=ReasoningToolInput.text(args, "claim"),
            reliability_factors=ReasoningToolInput.object_list(args.get("reliability_factors")),
            corroboration=ReasoningToolInput.string_list(args.get("corroboration")),
            conflicts=ReasoningToolInput.string_list(args.get("conflicts")),
            trust_verdict=ReasoningToolInput.text(args, "trust_verdict"),
            residual_uncertainty=ReasoningToolInput.text(args, "residual_uncertainty"),
            title=ReasoningToolInput.text(args, "title", "Testimony Evaluation") or "Testimony Evaluation",
        )