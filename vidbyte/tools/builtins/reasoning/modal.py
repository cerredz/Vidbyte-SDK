"""Context Protocol Header

Description:
    Implements ModalTool — a model-callable builtin for recording a
    modality analysis into the active ContextManager.
Purpose:
    Lets the model force the modal status (necessary / possible / contingent /
    impossible), the possible-world evidence, the actuality, and the reasoning
    into a checkable shape — claims about what 'must', 'may', or 'cannot'
    happen are routinely smuggled past actuality checks.
Architecture:
    - ModalTool: BaseTool that constructs a ModalContextItem from model-provided
      arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("claim", "modal_status", "possible_world_evidence", "actuality", "reasoning")
_MODAL_VALUES = ("necessary", "possible", "contingent", "impossible")


class ModalTool(BaseTool):
    """Builtin tool that records a modality analysis into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="modal",
            description=(
                "Classify a claim's modality: is it necessary, merely possible, contingent, "
                "or impossible? Supply the evidence that settles the status and separate "
                "actuality from possibility. Use this whenever a claim uses 'must', 'may', "
                "'cannot', 'necessarily', or 'could never' — modal words smuggled into "
                "claims are the difference between a demonstrated fact and a wish."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim whose modality is at issue, quoted with its modal word — "
                        "e.g. 'the retry loop must terminate'. Claims without modal words "
                        "should be graded by their strongest reading."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="modal_status",
                    type="string",
                    description=(
                        "One of: 'necessary', 'possible', 'contingent', 'impossible'. "
                        "'necessary' means the claim holds in every world (true by logic "
                        "or invariant). 'possible' means at least one world makes it true. "
                        "'contingent' means it holds in some worlds and fails in others. "
                        "'impossible' means no world makes it true."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="possible_world_evidence",
                    type="string",
                    description=(
                        "For 'possible': a coherent scenario in which the claim holds, "
                        "specified in enough detail that its coherence is checkable — "
                        "merely asserting 'it could happen' without a describable scenario "
                        "is an empty possibility claim. For 'necessary'/'impossible': the "
                        "general argument that closes off all worlds. For 'contingent': "
                        "one world each way."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="actuality",
                    type="string",
                    description=(
                        "Whether the claim in fact holds here and now — a claim can be "
                        "'possible' and false, 'necessary' and irrelevant, or 'impossible' "
                        "and yet asserted. Never collapse possibility into actuality; "
                        "record both."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reasoning",
                    type="string",
                    description=(
                        "The argument that connects the evidence to the status — why the "
                        "worlds are closed off, or why the counter-world exists. The "
                        "modality is only as strong as this argument."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the modal primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"modal:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad modal enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "modal_status"), _MODAL_VALUES, "modal_status"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the ModalContextItem from validated call arguments.
        from vidbyte.context.primitives import ModalContextItem
        return ModalContextItem(
            primitive_id=primitive_id,
            claim=ReasoningToolInput.text(args, "claim"),
            modal_status=ReasoningToolInput.text(args, "modal_status"),
            possible_world_evidence=ReasoningToolInput.text(args, "possible_world_evidence"),
            actuality=ReasoningToolInput.text(args, "actuality"),
            reasoning=ReasoningToolInput.text(args, "reasoning"),
            title=ReasoningToolInput.text(args, "title", "Modality Analysis") or "Modality Analysis",
        )