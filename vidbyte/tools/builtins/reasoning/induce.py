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

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

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
                        "Specific individual instances or data points the generalization is "
                        "drawn from. Each entry should be one concrete observation, not a "
                        "summary of many. May be passed as a JSON array of strings or a JSON "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description=(
                        "The regularity noticed across the observations, described before "
                        "generalizing it — the raw pattern, not yet the claim about all future "
                        "or unseen cases."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="generalization",
                    type="string",
                    description=(
                        "The general claim projected from the pattern beyond the specific "
                        "observations (e.g. 'all X have Y', 'X reliably predicts Y'). This is the "
                        "inductive leap — the part not guaranteed by the observations alone."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="sample_bias_risk",
                    type="string",
                    description=(
                        "How the observation set could be unrepresentative: too small, "
                        "self-selected, drawn from one time/place/source, survivorship bias, or "
                        "any other systematic skew that would make the generalization wrong even "
                        "if every individual observation is accurate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="falsifying_case",
                    type="string",
                    description=(
                        "A concrete observation that, if it occurred, would break this "
                        "generalization. If you cannot describe one, the generalization is not "
                        "yet falsifiable and should be narrowed until it is."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confidence",
                    type="string",
                    description=(
                        "Self-assessed confidence in the generalization, 0.0 to 1.0 (e.g. "
                        "'0.6'). Inductive conclusions are never certain; this should rarely be "
                        "above 0.9. Optional."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Inductive Generalization'.",
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

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the InductionContextItem from validated call arguments.
        from vidbyte.context.primitives import InductionContextItem
        return InductionContextItem(
            primitive_id=primitive_id,
            observations=ReasoningToolInput.string_list(args.get("observations")),
            pattern=ReasoningToolInput.text(args, "pattern"),
            generalization=ReasoningToolInput.text(args, "generalization"),
            sample_bias_risk=ReasoningToolInput.text(args, "sample_bias_risk"),
            falsifying_case=ReasoningToolInput.text(args, "falsifying_case"),
            confidence=ReasoningToolInput.probability(args.get("confidence")),
            title=ReasoningToolInput.text(args, "title", "Inductive Generalization") or "Inductive Generalization",
        )
