"""Context Protocol Header

Description:
    Implements BurdenOfProofTool — a model-callable builtin for recording an
    evidence-burden resolution into the active ContextManager.
Purpose:
    Lets the model force the claim, its default presumption, both evidence
    sides, the burden holder, and a verdict into a checkable shape — most
    'unproven' disputes are disputes about who carries the burden, not about
    the evidence.
Architecture:
    - BurdenOfProofTool: BaseTool that constructs a BurdenOfProofContextItem
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

_REQUIRED_FIELDS = ("claim", "default_presumption", "burden_holder", "verdict", "decision")
_REQUIRED_PRESENT_FIELDS = ("supporting_evidence", "opposing_evidence")
_VERDICT_VALUES = ("established", "not_established", "contested")


class BurdenOfProofTool(BaseTool):
    """Builtin tool that records an evidence-burden resolution into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="burden_of_proof",
            description=(
                "Resolve who must prove what: state the claim, the default presumption in "
                "force, the evidence on both sides, the party carrying the burden, and a "
                "verdict. Use this whenever two claims clash and the dispute stalls on "
                "'prove it' — the burden question must be answered before the evidence "
                "question can be."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim whose burden is being assessed — e.g. 'the migration "
                        "will not lose data'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="default_presumption",
                    type="string",
                    description=(
                        "What holds when no evidence is offered — the status quo, the "
                        "documented behavior, the prior. 'No presumption' is a legitimate "
                        "answer only when the context genuinely starts neutral; name it "
                        "explicitly."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="supporting_evidence",
                    type="array",
                    description=(
                        "Every piece of evidence offered for the claim, each its own "
                        "string. An empty list is a real answer — it means the claim "
                        "stands on presumption alone. May be passed as a JSON array of "
                        "strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="opposing_evidence",
                    type="array",
                    description=(
                        "Every piece of evidence offered against the claim, each its own "
                        "string. May be passed as a JSON array of strings or a JSON "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="burden_holder",
                    type="string",
                    description=(
                        "Who must supply the evidence — the party whose claim departs "
                        "from the presumption. A verdict without a named burden holder "
                        "cannot be applied."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="verdict",
                    type="string",
                    description=(
                        "One of: 'established', 'not_established', 'contested'. "
                        "'established' means the burden holder met the standard. "
                        "'not_established' means the evidence falls short, so the "
                        "presumption stands. 'contested' means both sides are genuinely "
                        "balanced and the standard itself is in dispute."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="decision",
                    type="string",
                    description=(
                        "The operative consequence — what action follows from the "
                        "verdict, and what would change it. A burden verdict that leads "
                        "nowhere has not been used."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the burden_of_proof primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"burden_of_proof:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, a missing evidence key, or a bad verdict enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        for name in _REQUIRED_PRESENT_FIELDS:
            if name not in args:
                return f"Missing or empty required field: '{name}'."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "verdict"), _VERDICT_VALUES, "verdict"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the BurdenOfProofContextItem from validated call arguments.
        from vidbyte.context.primitives import BurdenOfProofContextItem
        return BurdenOfProofContextItem(
            primitive_id=primitive_id,
            claim=ReasoningToolInput.text(args, "claim"),
            default_presumption=ReasoningToolInput.text(args, "default_presumption"),
            supporting_evidence=ReasoningToolInput.string_list(args.get("supporting_evidence")),
            opposing_evidence=ReasoningToolInput.string_list(args.get("opposing_evidence")),
            burden_holder=ReasoningToolInput.text(args, "burden_holder"),
            verdict=ReasoningToolInput.text(args, "verdict"),
            decision=ReasoningToolInput.text(args, "decision"),
            title=ReasoningToolInput.text(args, "title", "Burden of Proof") or "Burden of Proof",
        )