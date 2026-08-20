"""Context Protocol Header

Description:
    Implements CircularityTool — a model-callable builtin for recording a
    circular-reasoning audit into the active ContextManager.
Purpose:
    Lets the model force the argument, its premises and conclusion, the
    dependency map, the circle finding, and the fix into a checkable shape —
    circular arguments are valid, sound-looking, and empty.
Architecture:
    - CircularityTool: BaseTool that constructs a CircularityContextItem from
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

_REQUIRED_FIELDS = ("argument", "premises", "conclusion", "dependency_map", "circle_found", "fix", "verdict")
_VERDICT_VALUES = ("circular", "not_circular", "partially")


class CircularityTool(BaseTool):
    """Builtin tool that records a circular-reasoning audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="circularity",
            description=(
                "Audit an argument for circularity: state the premises and conclusion, map "
                "which premises depend on which claims, trace whether the dependency chain "
                "returns to its start, and name the fix. Use this whenever an argument "
                "feels 'too smooth' — circular reasoning is formally valid, which is "
                "precisely why it survives surface checks."
            ),
            parameters=(
                ToolParameter(
                    name="argument",
                    type="string",
                    description=(
                        "The argument under audit, quoted as a whole — the audit judges "
                        "this exact argument, not a paraphrase of it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "The premises as stated, each its own string. May be passed as a "
                        "JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "The conclusion the premises are claimed to establish. For a "
                        "circle, the conclusion must be findable among the premises or "
                        "their implicit dependencies."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="dependency_map",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'premise' and 'depends_on': what "
                        "each premise relies on, including implicit commitments that are "
                        "never stated. An unstated dependence is where the circle hides. "
                        "May also be passed as a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="circle_found",
                    type="string",
                    description=(
                        "The actual dependency loop, spelled out step by step — 'premise 1 "
                        "assumes P, P assumes premise 3, premise 3 assumes the "
                        "conclusion'. If no loop exists, say what was traced to confirm "
                        "its absence."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fix",
                    type="string",
                    description=(
                        "What would break the circle — an independent source for the "
                        "conclusion, a dropped premise, or an external assumption stated "
                        "and defended. An audit that finds a circle and proposes no fix "
                        "has diagnosed but not finished."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'circular', 'not_circular', 'partially'. 'circular' "
                        "means the conclusion (or an equivalent of it) appears as a "
                        "premise. 'partially' means some, but not all, of the support "
                        "loops back."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the circularity primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"circularity:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty premises, empty dependency map, or a bad enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.string_list(args.get("premises")):
            return "Field 'premises' requires at least one premise."
        if not ReasoningToolInput.object_list(args.get("dependency_map")):
            return "Field 'dependency_map' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"), _VERDICT_VALUES, "verdict"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the CircularityContextItem from validated call arguments.
        from vidbyte.context.primitives import CircularityContextItem
        return CircularityContextItem(
            primitive_id=primitive_id,
            argument=ReasoningToolInput.text(args, "argument"),
            premises=ReasoningToolInput.string_list(args.get("premises")),
            conclusion=ReasoningToolInput.text(args, "conclusion"),
            dependency_map=ReasoningToolInput.object_list(args.get("dependency_map")),
            circle_found=ReasoningToolInput.text(args, "circle_found"),
            fix=ReasoningToolInput.text(args, "fix"),
            verdict=ReasoningToolInput.text(args, "verdict"),
            title=ReasoningToolInput.text(args, "title", "Circularity Audit") or "Circularity Audit",
        )