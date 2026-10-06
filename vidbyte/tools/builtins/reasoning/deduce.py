"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/deduce.py
PURPOSE: Implements the model-callable deduce reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

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
                "Use this tool when a conclusion should follow necessarily from explicit "
                "premises. It records the premises, the logical rule connecting them, and the "
                "derived conclusion as one checkable chain. A soundness caveat identifies the "
                "premise whose uncertainty most threatens the otherwise valid inference. The "
                "resulting record should separate logical validity from confidence that the "
                "premises are true."
            ),
            parameters=(
                ToolParameter(
                    name="premises",
                    type="array",
                    description=(
                        "The premises are the specific claims from which the deduction begins. "
                        "State each premise separately and in the order used by the inference. "
                        "Use plain strings that describe assumptions, observations, or rules, "
                        "not a summary of the conclusion. Provide a JSON array of strings or a "
                        "JSON-encoded string; at least one premise is required."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="inference_rule",
                    type="string",
                    description=(
                        "Name the logical rule that connects the premises to the conclusion. "
                        "Use a standard rule such as modus ponens, modus tollens, transitivity, "
                        "or universal instantiation when one applies. The rule should describe "
                        "the relationship actually used, rather than a vague label for the "
                        "reasoning. Provide it as a plain string so the inference can be checked."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "State the claim that follows from the premises under the named rule. "
                        "Phrase it as one clear declarative sentence so the model can compare it "
                        "with the premises. The conclusion should express what the inference "
                        "supports, not add an unsupported premise. Provide it as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="soundness_caveat",
                    type="string",
                    description=(
                        "Describe the weakest or least certain premise in the deduction. Explain "
                        "why that premise might be false even if the logical step is valid. This "
                        "separates validity of the inference from soundness of the overall claim. "
                        "Provide the caveat as a plain string, and state explicitly when no premise "
                        "is doubtful."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded deduction. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Deductive Chain'."
                    ),
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "The reasoning record could not be stored because its context values were invalid.",
                metadata={"error": "invalid_reasoning_context"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if premises or any required scalar field is missing.
        if not ReasoningToolInput.string_list(args.get("premises")):
            return "Missing or empty required field: 'premises'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the DeductionContextItem from validated call arguments.
        from vidbyte.context.primitives import DeductionContextItem

        return cast(
            ContextItem,
            DeductionContextItem(
                primitive_id=primitive_id,
                premises=ReasoningToolInput.string_list(args.get("premises")),
                inference_rule=ReasoningToolInput.text(args, "inference_rule"),
                conclusion=ReasoningToolInput.text(args, "conclusion"),
                soundness_caveat=ReasoningToolInput.text(args, "soundness_caveat"),
                title=ReasoningToolInput.text(args, "title", "Deductive Chain")
                or "Deductive Chain",
            ),
        )
