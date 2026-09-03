"""FILE: vidbyte/tools/builtins/reasoning/socratic.py

PURPOSE: Records one socratic reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the socratic tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen SocraticContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import SOCRATIC_REQUIRED_FIELDS
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
                "Interrogate a claim one question deep: state the claim, the probing question that challenges "
                "it, the assumption the question surfaces, the contradiction found (or none), the revised "
                "claim, and the depth reached. Use this when a claim deserves interrogation but not a full "
                "refutation — the Socratic step trades one assumption for a better one, one layer at a time. "
                "The required fields make each part of the strategy explicit so the conclusion can be examined "
                "against its stated basis. The recorded result preserves the analysis for later iterations "
                "without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim being interrogated, stated exactly as held. The interrogation judges this claim — a "
                        "softened paraphrase escapes the question. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="probing_question",
                    type="string",
                    description=(
                        "The single question that challenges the claim — the question whose answer would reveal whether "
                        "the claim is grounded. A question that cannot be answered in either direction is not probing. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="assumption_surfaced",
                    type="string",
                    description=(
                        "The hidden commitment the question exposes — the premise the claim was quietly relying on. "
                        "Naming it is the entire point of the step. This field is part of the strategy's explicit "
                        "contract, so its contribution can be reviewed separately from the final conclusion. Keeping it "
                        "explicit prevents the analysis from relying on an unstated assumption and gives later "
                        "iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="contradiction_found",
                    type="string",
                    description=(
                        "Whether the surfaced assumption conflicts with anything else the model holds, with the "
                        "conflict spelled out. 'None found' is a legitimate answer only after naming what was checked. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="revised_claim",
                    type="string",
                    description=(
                        "The claim after this step — refined, dropped, or defended with the assumption made explicit. A "
                        "step that surfaces an assumption and returns the claim unchanged has not completed its move. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="depth_reached",
                    type="string",
                    description=(
                        "How deep this step went and what lies beneath it — the next assumption that would surface if "
                        "interrogated again, or the statement that the chain has reached its floor. This field is part "
                        "of the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison. State only the "
                        "information relevant to this field so the recorded reasoning remains focused and auditable."
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "Could not store the reasoning result in the context manager.",
                metadata={"error": "context_upsert_failed"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if any required field is missing or empty.
        return ReasoningToolInput.missing_required(args, SOCRATIC_REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the SocraticContextItem from validated call arguments.
        from vidbyte.context.primitives import SocraticContextItem

        return cast(
            ContextItem,
            SocraticContextItem(
                primitive_id=primitive_id,
                claim=ReasoningToolInput.text(args, "claim"),
                probing_question=ReasoningToolInput.text(args, "probing_question"),
                assumption_surfaced=ReasoningToolInput.text(
                    args, "assumption_surfaced"
                ),
                contradiction_found=ReasoningToolInput.text(
                    args, "contradiction_found"
                ),
                revised_claim=ReasoningToolInput.text(args, "revised_claim"),
                depth_reached=ReasoningToolInput.text(args, "depth_reached"),
                title=ReasoningToolInput.text(args, "title", "Socratic Elenchus")
                or "Socratic Elenchus",
            ),
        )
