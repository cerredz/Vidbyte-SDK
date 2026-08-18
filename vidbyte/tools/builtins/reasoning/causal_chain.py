"""Context Protocol Header

Description:
    Implements CausalChainTool — a model-callable builtin for recording a
    causal claim into the active ContextManager.
Purpose:
    Lets the model anchor a cause-effect claim to an explicit mechanism and its
    confounders, so correlation is not silently upgraded to causation.
Architecture:
    - CausalChainTool: BaseTool that constructs a CausalChainContextItem from
      model-provided arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("cause", "mechanism", "effect", "intervention_test")


class CausalChainTool(BaseTool):
    """Builtin tool that records a causal claim and its mechanism into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="causal_chain",
            description=(
                "Claim that one thing causes another by stating the step-by-step mechanism "
                "that connects them, not just their correlation. Use this whenever a claim of "
                "the form 'X causes Y' is about to be made or relied on. Confounders and an "
                "intervention test are required so the claim can be distinguished from a "
                "coincidental correlation."
            ),
            parameters=(
                ToolParameter(
                    name="cause",
                    type="string",
                    description="The proposed causal factor — the thing claimed to produce the effect.",
                    required=True,
                ),
                ToolParameter(
                    name="mechanism",
                    type="string",
                    description=(
                        "The step-by-step causal pathway connecting cause to effect: what "
                        "actually happens, in order, that makes cause produce effect. "
                        "Correlation alone is not causation — if you cannot describe a "
                        "mechanism, you have observed a correlation and should say so instead of "
                        "asserting causation."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="effect",
                    type="string",
                    description="The outcome claimed to result from cause, stated so it could in principle be measured or observed.",
                    required=True,
                ),
                ToolParameter(
                    name="confounders",
                    type="array",
                    description=(
                        "Other variables that could produce the same correlation between cause "
                        "and effect without cause actually causing effect — common causes, "
                        "reverse causation, selection effects. If none are plausible, state that "
                        "explicitly as a single entry rather than leaving this empty. May be a "
                        "JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="intervention_test",
                    type="string",
                    description=(
                        "The experiment, natural experiment, or perturbation that would confirm "
                        "the causal claim — what you would change and what you would expect to "
                        "happen if the mechanism is real, versus if it is only correlation."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Causal Chain'.",
                    required=False,
                    default="Causal Chain",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the causal-chain primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"causal_chain:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if confounders or any required scalar field is missing.
        if not ReasoningToolInput.string_list(args.get("confounders")):
            return "Missing or empty required field: 'confounders'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the CausalChainContextItem from validated call arguments.
        from vidbyte.context.primitives import CausalChainContextItem
        return CausalChainContextItem(
            primitive_id=primitive_id,
            cause=ReasoningToolInput.text(args, "cause"),
            mechanism=ReasoningToolInput.text(args, "mechanism"),
            effect=ReasoningToolInput.text(args, "effect"),
            confounders=ReasoningToolInput.string_list(args.get("confounders")),
            intervention_test=ReasoningToolInput.text(args, "intervention_test"),
            title=ReasoningToolInput.text(args, "title", "Causal Chain") or "Causal Chain",
        )
