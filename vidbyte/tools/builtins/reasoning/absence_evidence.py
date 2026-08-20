"""Context Protocol Header

Description:
    Implements AbsenceEvidenceTool — a model-callable builtin for recording an
    absence-of-evidence inference into the active ContextManager.
Purpose:
    Lets the model force the hypothesis, the evidence it would produce, the
    search actually conducted, the search's adequacy, the significance, and a
    conclusion into a checkable shape — 'absence of evidence is evidence of
    absence' is only true when the absence is adequately searched.
Architecture:
    - AbsenceEvidenceTool: BaseTool that constructs an AbsenceEvidenceContextItem
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

_REQUIRED_FIELDS = ("hypothesis", "expected_evidence_if_true", "search_conducted", "search_adequacy", "significance", "conclusion")
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
                "Run an absence-of-evidence analysis: state the hypothesis, what evidence "
                "it would produce if true, what was actually searched, how adequate that "
                "search was, and what the absence therefore means. Use this whenever the "
                "model is tempted to conclude 'not found, therefore not real' — that "
                "inference is only licensed when the search would have found the evidence "
                "had it existed."
            ),
            parameters=(
                ToolParameter(
                    name="hypothesis",
                    type="string",
                    description=(
                        "The claim whose truth is being weighed by absence — e.g. 'this "
                        "code path is never exercised'."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="expected_evidence_if_true",
                    type="string",
                    description=(
                        "The observable evidence the hypothesis would produce if it held — "
                        "specific and named. A hypothesis whose evidence would be invisible "
                        "cannot be supported by absence at all."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="search_conducted",
                    type="string",
                    description=(
                        "What was actually searched, how, and how thoroughly — the exact "
                        "queries, scopes, and depth. 'We looked' is not a search report."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="search_adequacy",
                    type="string",
                    description=(
                        "Whether the search was adequate to find expected_evidence_if_true "
                        "— would the evidence have surfaced under this search? A search "
                        "that could not have found the evidence confers zero confidence."
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
                        "What follows for the hypothesis — the operative judgment, "
                        "including the confidence it deserves and what would change it."
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
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string for a missing field or a bad significance enum.
        error = ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "significance"), _SIGNIFICANCE_VALUES, "significance"
        )

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the AbsenceEvidenceContextItem from validated call arguments.
        from vidbyte.context.primitives import AbsenceEvidenceContextItem
        return AbsenceEvidenceContextItem(
            primitive_id=primitive_id,
            hypothesis=ReasoningToolInput.text(args, "hypothesis"),
            expected_evidence_if_true=ReasoningToolInput.text(args, "expected_evidence_if_true"),
            search_conducted=ReasoningToolInput.text(args, "search_conducted"),
            search_adequacy=ReasoningToolInput.text(args, "search_adequacy"),
            significance=ReasoningToolInput.text(args, "significance"),
            conclusion=ReasoningToolInput.text(args, "conclusion"),
            title=ReasoningToolInput.text(args, "title", "Absence of Evidence") or "Absence of Evidence",
        )