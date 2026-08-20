"""Context Protocol Header

Description:
    Implements EquivocationTool — a model-callable builtin for recording a
    term-ambiguity audit into the active ContextManager.
Purpose:
    Lets the model force the ambiguous term, its distinct senses, the concrete
    occurrences, the detected drift, and the corrected argument into a
    checkable shape — equivocation is the silent failure mode of every term
    with two meanings.
Architecture:
    - EquivocationTool: BaseTool that constructs an EquivocationContextItem from
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

_REQUIRED_FIELDS = ("term", "senses", "occurrences", "drift", "corrected_argument", "fallacy_present")
_FALLACY_VALUES = ("yes", "no", "uncertain")


class EquivocationTool(BaseTool):
    """Builtin tool that records a term-ambiguity audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="equivocation",
            description=(
                "Audit an argument for a term used in more than one sense: name the term, "
                "enumerate its distinct senses, map each occurrence to the sense in play, "
                "and judge whether the argument's validity depends on the drift between "
                "senses. Use this whenever a key term could plausibly shift meaning between "
                "premise and conclusion — one word, two senses, and a third conclusion "
                "that only follows if the word stayed still."
            ),
            parameters=(
                ToolParameter(
                    name="term",
                    type="string",
                    description=(
                        "The word or phrase under suspicion — e.g. 'fast' or 'the system'. "
                        "The audit is only meaningful for a term that actually appears in "
                        "the argument; a term that never appears cannot equivocate."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="senses",
                    type="array",
                    description=(
                        "The distinct meanings of term that could be in play, each stated "
                        "precisely enough to be told apart — 'fast = quick' vs 'fast = "
                        "fixed in place'. At least two senses are required: with one sense "
                        "there is nothing to equivocate between. May be passed as a JSON "
                        "array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="occurrences",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'context' and 'sense_used': every "
                        "use of the term in the argument, mapped to one of the senses "
                        "listed above. An occurrence mapped to no sense is itself evidence "
                        "of a third, unlisted sense. May also be passed as a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="drift",
                    type="string",
                    description=(
                        "Where the sense changes across the argument — premise uses sense "
                        "1, conclusion requires sense 2 — and what the argument would have "
                        "to give up to hold one sense throughout. If no drift exists, say "
                        "so and stop."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="corrected_argument",
                    type="string",
                    description=(
                        "The argument rewritten so the term keeps a single sense "
                        "throughout, or an explicit statement that no correction is "
                        "possible and the argument fails."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="fallacy_present",
                    type="string",
                    description=(
                        "One of: 'yes', 'no', 'uncertain'. 'yes' means the argument's "
                        "validity depends on the sense drift. 'no' means the term is "
                        "ambiguous but the argument works under either sense. 'uncertain' "
                        "means the occurrence mapping cannot be settled."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the equivocation primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"equivocation:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, undersized senses, empty occurrences, or a bad enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if len(ReasoningToolInput.string_list(args.get("senses"))) < 2:
            return "Field 'senses' requires at least two senses for an equivocation audit."
        if not ReasoningToolInput.object_list(args.get("occurrences")):
            return "Field 'occurrences' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "fallacy_present"), _FALLACY_VALUES, "fallacy_present"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the EquivocationContextItem from validated call arguments.
        from vidbyte.context.primitives import EquivocationContextItem
        return EquivocationContextItem(
            primitive_id=primitive_id,
            term=ReasoningToolInput.text(args, "term"),
            senses=ReasoningToolInput.string_list(args.get("senses")),
            occurrences=ReasoningToolInput.object_list(args.get("occurrences")),
            drift=ReasoningToolInput.text(args, "drift"),
            corrected_argument=ReasoningToolInput.text(args, "corrected_argument"),
            fallacy_present=ReasoningToolInput.text(args, "fallacy_present"),
            title=ReasoningToolInput.text(args, "title", "Equivocation Audit") or "Equivocation Audit",
        )