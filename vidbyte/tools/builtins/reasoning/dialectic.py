"""Context Protocol Header

Description:
    Implements DialecticTool — a model-callable builtin for recording a
    thesis-antithesis-synthesis resolution into the active ContextManager.
Purpose:
    Lets the model force the thesis, the strongest antithesis, the synthesis,
    what each side preserved and discarded, and the synthesis's stability into
    a checkable shape — a dialectic that cannot name its antithesis is a
    monologue with pretensions.
Architecture:
    - DialecticTool: BaseTool that constructs a DialecticContextItem from model-
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

_REQUIRED_FIELDS = ("thesis", "antithesis", "synthesis", "preserved_insight", "discarded_insight", "synthesis_stability")


class DialecticTool(BaseTool):
    """Builtin tool that records a thesis-antithesis-synthesis resolution into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="dialectic",
            description=(
                "Resolve a contradiction through synthesis: state the thesis, the strongest "
                "possible antithesis, the synthesis that holds both, what each side "
                "preserved and discarded, and how stable the synthesis is. Use this when "
                "two positions clash and the resolution must do more than pick a winner — "
                "the synthesis must genuinely hold the tension, not paper over it."
            ),
            parameters=(
                ToolParameter(
                    name="thesis",
                    type="string",
                    description=(
                        "The starting position, stated at its strongest — not the weakest "
                        "version that would be easy to beat. A strawman thesis produces a "
                        "fake synthesis."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="antithesis",
                    type="string",
                    description=(
                        "The strongest opposing position — the contradiction the thesis "
                        "must answer. Must differ from thesis (case-insensitive): a "
                        "dialectic between identical positions is not a contradiction. A "
                        "soft or friendly antithesis produces a cheap synthesis."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="synthesis",
                    type="string",
                    description=(
                        "The position that resolves the contradiction by holding what is "
                        "true in both — stated concretely enough that it can be judged "
                        "against both sides. A synthesis that simply repeats one side has "
                        "not synthesized."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="preserved_insight",
                    type="string",
                    description=(
                        "What the synthesis keeps from each side — the truths that "
                        "survive. Name both sides' contributions explicitly, or the "
                        "synthesis is unbalanced."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="discarded_insight",
                    type="string",
                    description=(
                        "What each side gives up in the synthesis — and why it is safe to "
                        "give up. A synthesis that discards nothing has not resolved "
                        "anything."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="synthesis_stability",
                    type="string",
                    description=(
                        "How durable the synthesis is — what new pressure would reopen "
                        "the contradiction, and whether the synthesis absorbs or "
                        "fractures under it."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the dialectic primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"dialectic:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or an antithesis that equals the thesis.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        thesis = ReasoningToolInput.text(args, "thesis")
        antithesis = ReasoningToolInput.text(args, "antithesis")
        if antithesis.lower() == thesis.lower():
            return (
                "Field 'antithesis' must differ from 'thesis' — a dialectic between "
                "identical positions is not a contradiction."
            )
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the DialecticContextItem from validated call arguments.
        from vidbyte.context.primitives import DialecticContextItem
        return DialecticContextItem(
            primitive_id=primitive_id,
            thesis=ReasoningToolInput.text(args, "thesis"),
            antithesis=ReasoningToolInput.text(args, "antithesis"),
            synthesis=ReasoningToolInput.text(args, "synthesis"),
            preserved_insight=ReasoningToolInput.text(args, "preserved_insight"),
            discarded_insight=ReasoningToolInput.text(args, "discarded_insight"),
            synthesis_stability=ReasoningToolInput.text(args, "synthesis_stability"),
            title=ReasoningToolInput.text(args, "title", "Dialectic") or "Dialectic",
        )