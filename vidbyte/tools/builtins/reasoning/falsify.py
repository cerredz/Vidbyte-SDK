"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/falsify.py
PURPOSE: Implements the model-callable falsify reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Implements FalsifyTool — a model-callable builtin for recording a
    Popperian falsification test into the active ContextManager.
Purpose:
    Lets the model subject a claim to a test designed to fail if the claim is
    false, and forces the boldest at-risk prediction to be named so the claim
    cannot be one that forbids nothing.
Architecture:
    - FalsifyTool: BaseTool that constructs a FalsifyContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager, vidbyte.context.primitives, and the
    shared vidbyte.tools.builtins.reasoning._parsing.ReasoningToolInput helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_REQUIRED_FIELDS = ("claim", "test_design", "riskiest_prediction", "status")
_STATUS_VALUES = ("falsified", "survived", "untested")


class FalsifyTool(BaseTool):
    """Builtin tool that records a claim against its designed falsification test into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="falsify",
            description=(
                "Use this tool when a claim needs a genuine opportunity to fail before it is "
                "treated as established. It records a refuting test and the bold prediction the "
                "claim rules out. The test status distinguishes a designed challenge from one "
                "that has actually produced evidence. The resulting record should make the "
                "claim's exposure to disconfirmation and the next evidentiary step inspectable."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "State the claim being subjected to a falsification test. Make it precise "
                        "enough that some possible observation could contradict it. A claim that "
                        "cannot fail any observation should be narrowed before this tool is used. "
                        "Provide the claim as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="test_design",
                    type="string",
                    description=(
                        "Describe the specific test, observation, or experiment that could refute the "
                        "claim. Design it so that a false claim would produce a failure, rather than "
                        "only looking for confirming evidence. This makes the test informative about "
                        "the claim's limits. Provide the design as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="riskiest_prediction",
                    type="string",
                    description=(
                        "Name the boldest and most specific consequence that the claim forbids. "
                        "Choose the prediction most likely to be wrong if the claim is false. Its "
                        "survival provides stronger support than a prediction that almost any claim "
                        "could accommodate. Provide the prediction as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description=(
                        "Record the current result as 'falsified', 'survived', or 'untested'. Use "
                        "'falsified' only when the test was run and the claim failed, and use "
                        "'survived' only when the test was run and the claim held. Use 'untested' "
                        "when the design exists but the observation has not been made. Provide one "
                        "of those enum values as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded falsification test. The "
                        "label helps the model and callers distinguish this note from other "
                        "context items. Use the default label when no more specific name is "
                        "needed. Provide a plain string; it defaults to 'Falsification Test'."
                    ),
                    required=False,
                    default="Falsification Test",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the falsification primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"falsify:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "The reasoning record could not be stored because its context values were invalid.",
                metadata={"error": "invalid_reasoning_context"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing required field or an invalid status enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        status = ReasoningToolInput.text(args, "status")
        return ReasoningToolInput.enum_error(status, _STATUS_VALUES, "status")

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the FalsifyContextItem from validated call arguments.
        from vidbyte.context.primitives import FalsifyContextItem

        return cast(
            ContextItem,
            FalsifyContextItem(
                primitive_id=primitive_id,
                claim=ReasoningToolInput.text(args, "claim"),
                test_design=ReasoningToolInput.text(args, "test_design"),
                riskiest_prediction=ReasoningToolInput.text(
                    args, "riskiest_prediction"
                ),
                status=ReasoningToolInput.text(args, "status"),
                title=ReasoningToolInput.text(args, "title", "Falsification Test")
                or "Falsification Test",
            ),
        )
