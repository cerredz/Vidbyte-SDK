"""Context Protocol Header

Description:
    Implements CounterexampleTool — a model-callable builtin for recording a
    formal disproof into the active ContextManager.
Purpose:
    Lets the model force a general claim, its scope, a constructed violating
    case, and the refined claim that survives into a checkable shape rather
    than asserting "this claim is false" on authority.
Architecture:
    - CounterexampleTool: BaseTool that constructs a CounterexampleContextItem
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

_REQUIRED_FIELDS = ("claim", "intended_scope", "constructed_case", "violated_condition", "generalizes", "refined_claim")


class CounterexampleTool(BaseTool):
    """Builtin tool that records a formal disproof by constructed case into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="counterexample",
            description=(
                "Run a formal disproof: take a general claim, bound its scope, construct a "
                "concrete case inside that scope that violates the claim, name exactly which "
                "condition the case breaks, and state the refined claim that survives. Use "
                "this whenever a universal or general claim is under suspicion — a single "
                "well-constructed case is the cheapest rigorous way to kill a false "
                "generalization. A counterexample that cannot name the violated condition, "
                "or a vague 'there might be a case', is not a counterexample at all."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The general or universal claim under attack, stated so that a single "
                        "case could break it — e.g. 'every file write is atomic'. A claim too "
                        "vague to be violated by any single case cannot be disproven and "
                        "should be sharpened first."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="intended_scope",
                    type="string",
                    description=(
                        "The domain the claim governs — e.g. 'local filesystem writes on "
                        "Linux'. A counterexample outside this scope does not count against "
                        "the claim; stating the scope is what makes the disproof fair."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="constructed_case",
                    type="string",
                    description=(
                        "The concrete, fully-specified case inside intended_scope that "
                        "violates claim — e.g. the exact filesystem operation, inputs, and "
                        "environment. 'There might be a case where...' is not a "
                        "counterexample; the case must be specific enough that a reader "
                        "could reproduce it."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="violated_condition",
                    type="string",
                    description=(
                        "Exactly which part of claim the case breaks — the specific predicate "
                        "that fails. Naming it is what separates a real disproof from a "
                        "case that merely happens to be unusual."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="generalizes",
                    type="string",
                    description=(
                        "Whether the failure is structural (the same pattern would produce "
                        "many such cases, so the claim is deeply false) or an isolated "
                        "exception (a single edge case the claim could sensibly exclude). "
                        "This determines how much weight the counterexample carries."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="refined_claim",
                    type="string",
                    description=(
                        "The corrected claim that survives the case — narrowed scope, added "
                        "condition, or explicit 'claim is false as stated' if nothing "
                        "survives. The disproof is not finished until the replacement claim "
                        "is on the table."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the counterexample primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"counterexample:{self._counter}"
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
        # Constructs the CounterexampleContextItem from validated call arguments.
        from vidbyte.context.primitives import CounterexampleContextItem
        return CounterexampleContextItem(
            primitive_id=primitive_id,
            claim=ReasoningToolInput.text(args, "claim"),
            intended_scope=ReasoningToolInput.text(args, "intended_scope"),
            constructed_case=ReasoningToolInput.text(args, "constructed_case"),
            violated_condition=ReasoningToolInput.text(args, "violated_condition"),
            generalizes=ReasoningToolInput.text(args, "generalizes"),
            refined_claim=ReasoningToolInput.text(args, "refined_claim"),
            title=ReasoningToolInput.text(args, "title", "Counterexample") or "Counterexample",
        )