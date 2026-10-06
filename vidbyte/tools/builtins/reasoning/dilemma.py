"""FILE: vidbyte/tools/builtins/reasoning/dilemma.py

PURPOSE: Records one dilemma reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the dilemma tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen DilemmaContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import DILEMMA_REQUIRED_FIELDS
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


class DilemmaTool(BaseTool):
    """Builtin tool that records a proof by exhaustive cases into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="dilemma",
            description=(
                "Run a proof by exhaustive cases: enumerate every possible branch, argue from each branch to a "
                "conclusion, and state why no further branch exists. Use this when a conclusion can be shown to "
                "follow no matter which of several mutually exclusive possibilities holds. The exclusion "
                "argument is what makes this a proof — without it, an unlisted third case silently kills the "
                "dilemma. The required fields make each part of the strategy explicit so the conclusion can be "
                "examined against its stated basis."
            ),
            parameters=(
                ToolParameter(
                    name="alternatives",
                    type="array",
                    description=(
                        "The exhaustive set of cases or branches the argument covers, each stated as its own string. At "
                        "least two are required — a dilemma with one branch is a monologue. May be passed as a JSON "
                        "array of strings or a JSON string. This field is part of the strategy's explicit contract, so "
                        "its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="case_reasoning",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'case' and 'leads_to': one entry per alternative, giving the "
                        "argument from that branch to the conclusion. Every alternative must have an entry — a branch "
                        "without reasoning is an unsupported leg of the proof. May also be passed as a JSON string. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "What follows in every branch. If branches land differently, state the split explicitly rather "
                        "than pretending the proof is uniform. This field is part of the strategy's explicit contract, "
                        "so its contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="exhaustiveness",
                    type="string",
                    description=(
                        "Why no further branch exists — the exclusion argument that the alternatives are jointly "
                        "exhaustive. A proof by cases without an exhaustiveness argument proves nothing about the cases "
                        "not listed. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the dilemma primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"dilemma:{self._counter}"
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
        # Returns an error string for a missing field, undersized alternatives, or empty case reasoning.
        error = ReasoningToolInput.missing_required(args, DILEMMA_REQUIRED_FIELDS)
        if error:
            return error
        alternatives = ReasoningToolInput.string_list(args.get("alternatives"))
        if len(alternatives) < 2:
            return "Field 'alternatives' requires at least two branches for a dilemma."
        if not ReasoningToolInput.object_list(args.get("case_reasoning")):
            return "Field 'case_reasoning' requires at least one entry."
        return None

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the DilemmaContextItem from validated call arguments.
        from vidbyte.context.primitives import DilemmaContextItem

        return cast(
            ContextItem,
            DilemmaContextItem(
                primitive_id=primitive_id,
                alternatives=ReasoningToolInput.string_list(args.get("alternatives")),
                case_reasoning=ReasoningToolInput.object_list(
                    args.get("case_reasoning")
                ),
                conclusion=ReasoningToolInput.text(args, "conclusion"),
                exhaustiveness=ReasoningToolInput.text(args, "exhaustiveness"),
                title=ReasoningToolInput.text(args, "title", "Proof by Cases")
                or "Proof by Cases",
            ),
        )
