"""FILE: vidbyte/tools/builtins/reasoning/absence_evidence.py

PURPOSE: Records one absence evidence reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the absence_evidence tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen AbsenceEvidenceContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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

_REQUIRED_FIELDS = (
    "hypothesis",
    "expected_evidence_if_true",
    "search_conducted",
    "search_adequacy",
    "significance",
    "conclusion",
)
_SIGNIFICANCE_VALUES = ("evidence_against", "neutral", "evidence_for")


class AbsenceEvidenceTool(BaseTool):
    """Builtin tool that records an absence-of-evidence inference into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="absence_evidence",
            description=(
                "Run an absence-of-evidence analysis: state the hypothesis, what evidence it would produce if "
                "true, what was actually searched, how adequate that search was, and what the absence therefore "
                "means. Use this whenever the model is tempted to conclude 'not found, therefore not real' — "
                "that inference is only licensed when the search would have found the evidence had it existed. "
                "The required fields make each part of the strategy explicit so the conclusion can be examined "
                "against its stated basis. The recorded result preserves the analysis for later iterations "
                "without independently verifying the model's judgment."
            ),
            parameters=(
                ToolParameter(
                    name="hypothesis",
                    type="string",
                    description=(
                        "The claim whose truth is being weighed by absence — e.g. 'this code path is never exercised'. "
                        "This field is part of the strategy's explicit contract, so its contribution can be reviewed "
                        "separately from the final conclusion. Keeping it explicit prevents the analysis from relying "
                        "on an unstated assumption and gives later iterations a stable basis for comparison. State only "
                        "the information relevant to this field so the recorded reasoning remains focused and "
                        "auditable."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="expected_evidence_if_true",
                    type="string",
                    description=(
                        "The observable evidence the hypothesis would produce if it held — specific and named. A "
                        "hypothesis whose evidence would be invisible cannot be supported by absence at all. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion. Keeping it explicit prevents the analysis from relying on an "
                        "unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="search_conducted",
                    type="string",
                    description=(
                        "What was actually searched, how, and how thoroughly — the exact queries, scopes, and depth. "
                        "'We looked' is not a search report. This field is part of the strategy's explicit contract, so "
                        "its contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="search_adequacy",
                    type="string",
                    description=(
                        "Whether the search was adequate to find expected_evidence_if_true — would the evidence have "
                        "surfaced under this search? A search that could not have found the evidence confers zero "
                        "confidence. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="significance",
                    type="string",
                    description=(
                        "One of: 'evidence_against', 'neutral', 'evidence_for'. "
                        "'evidence_against' means the absence, given an adequate search, "
                        "counts against the hypothesis. 'neutral' means the absence is "
                        "uninformative — the search was inadequate or the evidence would "
                        "be invisible. 'evidence_for' means the absence supports the "
                        "hypothesis (it predicts no evidence)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="conclusion",
                    type="string",
                    description=(
                        "What follows for the hypothesis — the operative judgment, including the confidence it deserves "
                        "and what would change it. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison. State only the information relevant to this field so the recorded "
                        "reasoning remains focused and auditable."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the absence_evidence primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"absence_evidence:{self._counter}"
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
        # Returns an error string for a missing field or a bad significance enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "significance"),
            _SIGNIFICANCE_VALUES,
            "significance",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the AbsenceEvidenceContextItem from validated call arguments.
        from vidbyte.context.primitives import AbsenceEvidenceContextItem

        return cast(
            ContextItem,
            AbsenceEvidenceContextItem(
                primitive_id=primitive_id,
                hypothesis=ReasoningToolInput.text(args, "hypothesis"),
                expected_evidence_if_true=ReasoningToolInput.text(
                    args, "expected_evidence_if_true"
                ),
                search_conducted=ReasoningToolInput.text(args, "search_conducted"),
                search_adequacy=ReasoningToolInput.text(args, "search_adequacy"),
                significance=ReasoningToolInput.text(args, "significance"),
                conclusion=ReasoningToolInput.text(args, "conclusion"),
                title=ReasoningToolInput.text(args, "title", "Absence of Evidence")
                or "Absence of Evidence",
            ),
        )
