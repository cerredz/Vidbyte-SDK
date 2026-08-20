"""Context Protocol Header

Description:
    Implements ParadoxTool — a model-callable builtin for recording a paradox
    dissection into the active ContextManager.
Purpose:
    Lets the model force the paradox, its premises, the hidden assumption, the
    premise chosen to drop, the resolution, and what the paradox reveals into a
    checkable shape — a paradox is not a mystery, it is a premise audit.
Architecture:
    - ParadoxTool: BaseTool that constructs a ParadoxContextItem from model-
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

_REQUIRED_FIELDS = ("paradox", "premises", "hidden_assumption", "premise_to_drop", "resolution", "what_it_reveals")


class ParadoxTool(BaseTool):
    """Builtin tool that records a paradox dissection into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="paradox",
            description=(
                "Dissect a paradox: state the paradox, enumerate the premises that produce "
                "it, name the hidden assumption, choose exactly one premise to drop, give "
                "the resolution, and say what the paradox reveals. Use this whenever an "
                "argument produces a genuine contradiction — every paradox is a small set "
                "of premises with one impostor, and the dissection finds it."
            ),
            parameters=(
                ToolParameter(
                    name="paradox",
                    type="string",
                    description=(
                        "The paradox, stated as the contradiction it produces — e.g. 'the "
                        "barber shaves all and only those who do not shave themselves'. "
                        "The premises below must generate this exact contradiction."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "The premises the paradox runs on, each a separate string. At "
                        "least two are required — a paradox needs tension between "
                        "premises to be a paradox. Every premise that the contradiction "
                        "actually depends on must be listed; an unlisted premise is a "
                        "hidden assumption wearing a premise's absence. May be passed as "
                        "a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="hidden_assumption",
                    type="string",
                    description=(
                        "The unstated commitment that quietly makes the paradox work — "
                        "the assumption the premises share but never declare. 'None' is "
                        "an answer only when the listed premises genuinely generate the "
                        "contradiction alone."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premise_to_drop",
                    type="string",
                    description=(
                        "The single premise to reject, stated exactly as it appears in "
                        "premises (matching is case-sensitive) — the contradiction "
                        "evaporates only when the right premise goes. Choosing a premise "
                        "that is not listed means the audit has not finished."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="resolution",
                    type="string",
                    description=(
                        "What remains after dropping the premise — the consistent "
                        "situation that replaces the paradox, and why the dropped "
                        "premise was the impostor rather than any other."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="what_it_reveals",
                    type="string",
                    description=(
                        "What the paradox teaches beyond its own resolution — the "
                        "general limit or assumption it exposes about the domain (self-"
                        "reference, totality, unboundedness). A dissection that names no "
                        "lesson has only resolved, not understood."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the paradox primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"paradox:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, undersized premises, or a premise_to_drop not in premises.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        premises = ReasoningToolInput.string_list(args.get("premises"))
        if len(premises) < 2:
            return "Field 'premises' requires at least two premises for a paradox."
        if ReasoningToolInput.text(args, "premise_to_drop") not in premises:
            return "Field 'premise_to_drop' must name one of the stated 'premises'."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the ParadoxContextItem from validated call arguments.
        from vidbyte.context.primitives import ParadoxContextItem
        return ParadoxContextItem(
            primitive_id=primitive_id,
            paradox=ReasoningToolInput.text(args, "paradox"),
            premises=ReasoningToolInput.string_list(args.get("premises")),
            hidden_assumption=ReasoningToolInput.text(args, "hidden_assumption"),
            premise_to_drop=ReasoningToolInput.text(args, "premise_to_drop"),
            resolution=ReasoningToolInput.text(args, "resolution"),
            what_it_reveals=ReasoningToolInput.text(args, "what_it_reveals"),
            title=ReasoningToolInput.text(args, "title", "Paradox Dissection") or "Paradox Dissection",
        )