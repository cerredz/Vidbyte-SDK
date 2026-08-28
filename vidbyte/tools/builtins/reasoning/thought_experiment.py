"""FILE: vidbyte/tools/builtins/reasoning/thought_experiment.py

PURPOSE: Records one thought experiment reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the thought_experiment tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen ThoughtExperimentContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
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

_REQUIRED_FIELDS = ("setup", "manipulation", "predicted_outcome", "insight", "limits")


class ThoughtExperimentTool(BaseTool):
    """Builtin tool that records a gedankenexperiment into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="thought_experiment",
            description=(
                "Run a controlled thought experiment: describe the imagined world, the single manipulation, the "
                "predicted outcome, the insight it forces, and the limits of the result. Use this when the "
                "model needs to isolate a principle from a tangled situation — the thought experiment removes "
                "exactly one variable at a time and sees what survives. The required fields make each part of "
                "the strategy explicit so the conclusion can be examined against its stated basis. The recorded "
                "result preserves the analysis for later iterations without independently verifying the model's "
                "judgment."
            ),
            parameters=(
                ToolParameter(
                    name="setup",
                    type="string",
                    description=(
                        "The imagined situation, fully specified — the actors, the objects, the rules of the world. An "
                        "under-specified setup produces outcomes that could be caused by any of several differences. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="manipulation",
                    type="string",
                    description=(
                        "The single change that defines the experiment — exactly one variable altered against the "
                        "setup. Two simultaneous changes make the outcome attribution impossible. This field is part of "
                        "the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="predicted_outcome",
                    type="string",
                    description=(
                        "What the setup plus the manipulation is predicted to produce — and, where the thought "
                        "experiment argues against a position, what that position would have predicted instead. The "
                        "contrast is the experiment. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="insight",
                    type="string",
                    description=(
                        "The principle the experiment demonstrates — the general lesson that travels beyond the "
                        "imagined world. An experiment that yields no insight was a daydream, not an experiment. This "
                        "field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="limits",
                    type="string",
                    description=(
                        "Where the thought experiment stops holding — the real-world differences that keep the insight "
                        "from transferring wholesale, and what would need checking empirically. Thought experiments are "
                        "instruments; every instrument has a range. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the thought_experiment primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"thought_experiment:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if any required field is missing or empty.
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the ThoughtExperimentContextItem from validated call arguments.
        from vidbyte.context.primitives import ThoughtExperimentContextItem

        return cast(
            ContextItem,
            ThoughtExperimentContextItem(
                primitive_id=primitive_id,
                setup=ReasoningToolInput.text(args, "setup"),
                manipulation=ReasoningToolInput.text(args, "manipulation"),
                predicted_outcome=ReasoningToolInput.text(args, "predicted_outcome"),
                insight=ReasoningToolInput.text(args, "insight"),
                limits=ReasoningToolInput.text(args, "limits"),
                title=ReasoningToolInput.text(args, "title", "Thought Experiment")
                or "Thought Experiment",
            ),
        )
