"""Context Protocol Header

Description:
    Implements RegressTool — a model-callable builtin for recording a
    justification-chain analysis into the active ContextManager.
Purpose:
    Lets the model force the claim, the full chain of justification, where the
    chain terminates, the regress style, and an adequacy judgment into a
    checkable shape — every 'why' chain ends somewhere, and where it ends
    decides whether the chain grounds the claim.
Architecture:
    - RegressTool: BaseTool that constructs a RegressContextItem from model-
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

_REQUIRED_FIELDS = ("claim", "justification_chain", "terminates_at", "style", "adequacy")
_STYLE_VALUES = ("foundational", "circular", "infinite")


class RegressTool(BaseTool):
    """Builtin tool that records a justification-chain analysis into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="regress",
            description=(
                "Trace a claim's chain of justification to its end: list every step of the "
                "chain, name where it terminates, classify the regress style, and judge "
                "whether that ending grounds the claim. Use this whenever the model is "
                "asked 'why' until the answer runs out — the chain must end somewhere, and "
                "the honest question is whether the ending is a foundation, a loop, or a "
                "void."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim whose justification is being traced — the root of the "
                        "'why' chain."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="justification_chain",
                    type="array",
                    description=(
                        "The ordered chain of justifications, one link per entry — each "
                        "'why' answered in sequence, including the steps that reveal "
                        "weakness: 'the claim holds because P; P holds because Q; Q holds "
                        "because...'. A chain edited to hide its weak steps is the reason "
                        "this tool exists. May be passed as a JSON array of strings or a "
                        "JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="terminates_at",
                    type="string",
                    description=(
                        "Exactly where the chain stops: the axiom, definition, assumption, "
                        "or empty answer that ends the regress. If the chain genuinely "
                        "never terminates, say so plainly."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="style",
                    type="string",
                    description=(
                        "One of: 'foundational', 'circular', 'infinite'. 'foundational' "
                        "means the chain ends at a base that is not itself supported "
                        "further (axiom, brute fact, accepted definition). 'circular' "
                        "means the chain returns to the original claim. 'infinite' means "
                        "each answer raises a new question without end."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="adequacy",
                    type="string",
                    description=(
                        "Whether the termination is strong enough to ground the claim in "
                        "this context — a foundational stop may be contested, a circular "
                        "stop is empty, an infinite stop is ungrounded. Name the standard "
                        "the context requires and judge against it."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the regress primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"regress:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad style enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "style"), _STYLE_VALUES, "style"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the RegressContextItem from validated call arguments.
        from vidbyte.context.primitives import RegressContextItem
        return RegressContextItem(
            primitive_id=primitive_id,
            claim=ReasoningToolInput.text(args, "claim"),
            justification_chain=ReasoningToolInput.string_list(args.get("justification_chain")),
            terminates_at=ReasoningToolInput.text(args, "terminates_at"),
            style=ReasoningToolInput.text(args, "style"),
            adequacy=ReasoningToolInput.text(args, "adequacy"),
            title=ReasoningToolInput.text(args, "title", "Justification Regress") or "Justification Regress",
        )