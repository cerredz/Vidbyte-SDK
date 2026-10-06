"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/causal_chain.py
PURPOSE: Implements the model-callable causal-chain reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Implements CausalChainTool — a model-callable builtin for recording a
    causal claim into the active ContextManager.
Purpose:
    Lets the model anchor a cause-effect claim to an explicit mechanism and its
    confounders, so correlation is not silently upgraded to causation.
Architecture:
    - CausalChainTool: BaseTool that constructs a CausalChainContextItem from
      model-provided arguments and upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("cause", "mechanism", "effect", "intervention_test")


class CausalChainTool(BaseTool):
    """Builtin tool that records a causal claim and its mechanism into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="causal_chain",
            description=(
                "Use this tool when a causal claim must be supported by more than observed "
                "association. It records the stepwise mechanism connecting a proposed cause to "
                "its effect. Confounders and an intervention test force the account to address "
                "plausible noncausal explanations. The resulting record should make the causal "
                "path, its vulnerabilities, and the evidence needed to test it inspectable."
            ),
            parameters=(
                ToolParameter(
                    name="cause",
                    type="string",
                    description=(
                        "Name the factor proposed to produce the effect. State it as a specific "
                        "variable, action, event, or condition that could in principle be changed. "
                        "A precise cause gives the model something concrete to connect to the "
                        "mechanism and intervention test. Provide the proposed cause as a plain "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="mechanism",
                    type="string",
                    description=(
                        "Describe the step-by-step pathway connecting the cause to the effect. "
                        "Explain what happens and in what order to make the causal claim plausible. "
                        "The mechanism helps the model distinguish a process from a mere observed "
                        "correlation. Provide the pathway as a plain string, and say when no "
                        "mechanism is known."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="effect",
                    type="string",
                    description=(
                        "Name the outcome claimed to result from the cause. State it precisely "
                        "enough that it could be measured or observed. A concrete effect lets the "
                        "model compare the proposed mechanism with an intervention result. Provide "
                        "the outcome as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="confounders",
                    type="array",
                    description=(
                        "List other variables or pathways that could produce the same relationship "
                        "between cause and effect. Consider common causes, reverse causation, "
                        "selection effects, or other explanations that weaken the causal claim. "
                        "Naming confounders helps the model separate causation from coincidence. "
                        "Provide a JSON array of strings or a JSON-encoded string, and state "
                        "explicitly when no plausible confounder is known."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="intervention_test",
                    type="string",
                    description=(
                        "Describe the experiment, natural experiment, or perturbation that would "
                        "test the causal claim. State what would be changed and what outcome would "
                        "be expected if the mechanism were real. Include how the result would differ "
                        "if the relationship were only correlation. Provide the test design as a "
                        "plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded causal claim. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Causal Chain'."
                    ),
                    required=False,
                    default="Causal Chain",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the causal-chain primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"causal_chain:{self._counter}"
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
        # Returns an error string if confounders or any required scalar field is missing.
        if not ReasoningToolInput.string_list(args.get("confounders")):
            return "Missing or empty required field: 'confounders'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the CausalChainContextItem from validated call arguments.
        from vidbyte.context.primitives import CausalChainContextItem

        return cast(
            ContextItem,
            CausalChainContextItem(
                primitive_id=primitive_id,
                cause=ReasoningToolInput.text(args, "cause"),
                mechanism=ReasoningToolInput.text(args, "mechanism"),
                effect=ReasoningToolInput.text(args, "effect"),
                confounders=ReasoningToolInput.string_list(args.get("confounders")),
                intervention_test=ReasoningToolInput.text(args, "intervention_test"),
                title=ReasoningToolInput.text(args, "title", "Causal Chain")
                or "Causal Chain",
            ),
        )
