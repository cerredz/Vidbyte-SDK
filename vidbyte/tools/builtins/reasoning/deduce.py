"""Context Protocol Header

Description:
    Implements DeduceTool — a model-callable builtin for recording a deductive
    chain into the active ContextManager.
Purpose:
    Lets the model force premises, a named inference rule, and a conclusion into
    a checkable shape rather than asserting a conclusion on its own authority.
Architecture:
    - DeduceTool: BaseTool that constructs a DeductionContextItem from model-
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

_REQUIRED_FIELDS = ("inference_rule", "conclusion", "soundness_caveat")


class DeduceTool(BaseTool):
    """Builtin tool that records a deductive chain — premises, rule, and conclusion — into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="deduce",
            description=(
                "Run a deductive inference: state the premises, name the logical rule that "
                "connects them, and derive the conclusion that necessarily follows. Use this "
                "when a conclusion should be checkable against explicit premises rather than "
                "asserted from authority. Deductive validity guarantees the conclusion only if "
                "every premise is true, so a soundness caveat naming the weakest premise is "
                "required alongside the conclusion."
            ),
            parameters=(
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "Ordered list of premises this deduction starts from, each stated as a "
                        "claim assumed true for the purpose of this inference (not necessarily "
                        "true in the world — that is what soundness_caveat is for). At least one "
                        "premise is required; two or more is typical for a syllogism. May be "
                        "passed as a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="inference_rule",
                    type="string",
                    description=(
                        "Name of the specific logical rule connecting the premises to the "
                        "conclusion, e.g. 'modus ponens', 'modus tollens', 'hypothetical "
                        "syllogism', 'disjunctive syllogism', 'contrapositive', 'transitivity', "
                        "or 'universal instantiation'. Naming the rule is what makes this "
                        "deduction checkable rather than merely asserted."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "The claim that necessarily follows from the premises under the named "
                        "inference_rule, stated as a single declarative sentence."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="soundness_caveat",
                    type="string",
                    description=(
                        "Deductive validity guarantees the conclusion only if every premise is "
                        "true; it says nothing about whether the premises actually are true. Name "
                        "the single weakest or least certain premise and why it might be false. "
                        "If no premise is doubtful, state that explicitly rather than omitting "
                        "this field."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Deductive Chain'.",
                    required=False,
                    default="Deductive Chain",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the deduction primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"deduce:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if premises or any required scalar field is missing.
        if not ReasoningToolInput.string_list(args.get("premises")):
            return "Missing or empty required field: 'premises'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the DeductionContextItem from validated call arguments.
        from vidbyte.context.primitives import DeductionContextItem
        return DeductionContextItem(
            primitive_id=primitive_id,
            premises=ReasoningToolInput.string_list(args.get("premises")),
            inference_rule=ReasoningToolInput.text(args, "inference_rule"),
            conclusion=ReasoningToolInput.text(args, "conclusion"),
            soundness_caveat=ReasoningToolInput.text(args, "soundness_caveat"),
            title=ReasoningToolInput.text(args, "title", "Deductive Chain") or "Deductive Chain",
        )
