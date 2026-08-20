"""Context Protocol Header

Description:
    Implements SocraticTool — a model-callable builtin for recording a single
    step of Socratic interrogation into the active ContextManager.
Purpose:
    Lets the model force the claim, the probing question, the assumption it
    surfaces, the contradiction found, the revised claim, and the depth reached
    into a checkable shape — one question, one surfaced assumption, one
    revision: the elenchus done one honest step at a time.
Architecture:
    - SocraticTool: BaseTool that constructs a SocraticContextItem from model-
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

_REQUIRED_FIELDS = ("claim", "probing_question", "assumption_surfaced", "contradiction_found", "revised_claim", "depth_reached")


class SocraticTool(BaseTool):
    """Builtin tool that records a single step of Socratic interrogation into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="socratic",
            description=(
                "Interrogate a claim one question deep: state the claim, the probing "
                "question that challenges it, the assumption the question surfaces, the "
                "contradiction found (or none), the revised claim, and the depth reached. "
                "Use this when a claim deserves interrogation but not a full refutation — "
                "the Socratic step trades one assumption for a better one, one layer at a "
                "time."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim being interrogated, stated exactly as held. The "
                        "interrogation judges this claim — a softened paraphrase escapes "
                        "the question."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="probing_question",
                    type="string",
                    description=(
                        "The single question that challenges the claim — the question "
                        "whose answer would reveal whether the claim is grounded. A "
                        "question that cannot be answered in either direction is not "
                        "probing."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="assumption_surfaced",
                    type="string",
                    description=(
                        "The hidden commitment the question exposes — the premise the "
                        "claim was quietly relying on. Naming it is the entire point of "
                        "the step."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="contradiction_found",
                    type="string",
                    description=(
                        "Whether the surfaced assumption conflicts with anything else "
                        "the model holds, with the conflict spelled out. 'None found' is "
                        "a legitimate answer only after naming what was checked."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="revised_claim",
                    type="string",
                    description=(
                        "The claim after this step — refined, dropped, or defended with "
                        "the assumption made explicit. A step that surfaces an assumption "
                        "and returns the claim unchanged has not completed its move."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="depth_reached",
                    type="string",
                    description=(
                        "How deep this step went and what lies beneath it — the next "
                        "assumption that would surface if interrogated again, or the "
                        "statement that the chain has reached its floor."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the socratic primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"socratic:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if any required field is missing or empty.
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the SocraticContextItem from validated call arguments.
        from vidbyte.context.primitives import SocraticContextItem
        return SocraticContextItem(
            primitive_id=primitive_id,
            claim=ReasoningToolInput.text(args, "claim"),
            probing_question=ReasoningToolInput.text(args, "probing_question"),
            assumption_surfaced=ReasoningToolInput.text(args, "assumption_surfaced"),
            contradiction_found=ReasoningToolInput.text(args, "contradiction_found"),
            revised_claim=ReasoningToolInput.text(args, "revised_claim"),
            depth_reached=ReasoningToolInput.text(args, "depth_reached"),
            title=ReasoningToolInput.text(args, "title", "Socratic Elenchus") or "Socratic Elenchus",
        )