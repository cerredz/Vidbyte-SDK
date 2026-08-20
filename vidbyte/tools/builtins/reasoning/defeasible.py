"""Context Protocol Header

Description:
    Implements DefeasibleTool — a model-callable builtin for recording a
    defeasible-reasoning application into the active ContextManager.
Purpose:
    Lets the model force the default rule, the case, the applicability check,
    the defeaters, the final conclusion, and the retraction note into a
    checkable shape — default reasoning is only honest when its defeaters are
    named before its conclusions are trusted.
Architecture:
    - DefeasibleTool: BaseTool that constructs a DefeasibleContextItem from
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

_REQUIRED_FIELDS = ("default_rule", "case", "rule_applies", "defeaters", "final_conclusion", "retraction_note")
_RULE_APPLIES_VALUES = ("yes", "no", "borderline")


class DefeasibleTool(BaseTool):
    """Builtin tool that records a defeasible-reasoning application into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="defeasible",
            description=(
                "Apply a default rule to a case with its defeaters checked: state the rule, "
                "the case, whether the rule applies, the defeaters that could overturn it, "
                "the final conclusion, and the retraction note. Use this whenever the model "
                "reasons 'normally, X implies Y' — the word 'normally' is a defeasible "
                "rule, and the conclusion must survive its defeaters before it is trusted."
            ),
            parameters=(
                ToolParameter(
                    name="default_rule",
                    type="string",
                    description=(
                        "The default inference rule — e.g. 'normally, a package that "
                        "imports X is coupled to X'. Stated as a general rule, not a "
                        "case verdict."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="case",
                    type="string",
                    description=(
                        "The concrete case the rule is being applied to — named precisely "
                        "enough that applicability can be judged."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="rule_applies",
                    type="string",
                    description=(
                        "One of: 'yes', 'no', 'borderline'. 'yes' means the case falls "
                        "under the rule's antecedent. 'no' means the rule never engages. "
                        "'borderline' means the fit is partial and must be argued."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="defeaters",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'defeater' and 'applies': every "
                        "condition that could overturn the rule, and whether each actually "
                        "applies to this case. A list with no defeaters is only complete "
                        "if the common defeaters were considered — say so. May also be "
                        "passed as a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="final_conclusion",
                    type="string",
                    description=(
                        "The conclusion that survives after applying the rule and "
                        "weighing the defeaters — including the case where a defeater "
                        "wins and the default conclusion is overturned."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="retraction_note",
                    type="string",
                    description=(
                        "The condition under which this conclusion would have to be "
                        "retracted — the new information that would flip it. A "
                        "defeasible conclusion that cannot state its retraction "
                        "condition is being treated as indefeasible."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the defeasible primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"defeasible:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field, empty defeaters, or a bad enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        if not ReasoningToolInput.object_list(args.get("defeaters")):
            return "Field 'defeaters' requires at least one entry."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "rule_applies"), _RULE_APPLIES_VALUES, "rule_applies"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the DefeasibleContextItem from validated call arguments.
        from vidbyte.context.primitives import DefeasibleContextItem
        return DefeasibleContextItem(
            primitive_id=primitive_id,
            default_rule=ReasoningToolInput.text(args, "default_rule"),
            case=ReasoningToolInput.text(args, "case"),
            rule_applies=ReasoningToolInput.text(args, "rule_applies"),
            defeaters=ReasoningToolInput.object_list(args.get("defeaters")),
            final_conclusion=ReasoningToolInput.text(args, "final_conclusion"),
            retraction_note=ReasoningToolInput.text(args, "retraction_note"),
            title=ReasoningToolInput.text(args, "title", "Defeasible Reasoning") or "Defeasible Reasoning",
        )