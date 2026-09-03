"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/abduce.py
PURPOSE: Implements the model-callable abduce reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Implements AbduceTool — a model-callable builtin for recording an
    inference-to-the-best-explanation pass into the active ContextManager.
Purpose:
    Lets the model force itself to weigh genuine competing hypotheses against
    the evidence, rather than presenting the first plausible story as the
    explanation.
Architecture:
    - AbduceTool: BaseTool that constructs an AbductionContextItem from model-
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

_REQUIRED_FIELDS = ("best", "discriminating_test")
_MIN_HYPOTHESES = 2


class AbduceTool(BaseTool):
    """Builtin tool that records an inference-to-the-best-explanation pass into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="abduce",
            description=(
                "Use this tool when observed evidence permits multiple plausible explanations "
                "and the task requires choosing among them. It compares at least two genuine "
                "hypotheses against the same evidence and records which account explains the "
                "evidence with the fewest unsupported assumptions. The discriminating test "
                "keeps the preferred explanation provisional by naming evidence that could "
                "separate it from competitors. The resulting record should make the choice, "
                "uncertainty, and next verification step inspectable."
            ),
            parameters=(
                ToolParameter(
                    name="evidence",
                    type="array",
                    description=(
                        "List the observed facts that the candidate explanations must account "
                        "for. State each fact separately so the model can compare explanations "
                        "against the same evidence. These facts define the problem that the "
                        "abductive inference is trying to explain. Provide a JSON array of "
                        "strings or a JSON-encoded string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="hypotheses",
                    type="array",
                    description=(
                        "List two to four genuinely competing explanations for the evidence, "
                        "with each entry shaped as an object containing hypothesis, explains, "
                        "simplicity, and assumptions_required. Use those fields to show what "
                        "each candidate explains, how many extra assumptions it needs, and what "
                        "must be true for it to hold. Real competitors let the model choose the "
                        "best explanation instead of endorsing the first plausible story. "
                        "Provide a JSON array of objects or a JSON-encoded string, and include at "
                        "least two valid hypotheses."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="best",
                    type="string",
                    description=(
                        "Identify the hypothesis that best explains the evidence. Refer to it by "
                        "its hypothesis text or by a short label that clearly maps to one entry. "
                        "Choose it by weighing explanatory coverage and simplicity together. "
                        "Provide the selected explanation as a plain string so the comparison "
                        "remains explicit."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="runner_up",
                    type="string",
                    description=(
                        "Name the second-best hypothesis when one remains a serious competitor. "
                        "Add a brief explanation of why it is weaker than the selected best "
                        "hypothesis. Naming the runner-up preserves the comparison that makes "
                        "this an abductive inference rather than a single asserted story. "
                        "This parameter is optional and may be left empty when no runner-up is "
                        "useful."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="discriminating_test",
                    type="string",
                    description=(
                        "Describe the observation, test, or question that would distinguish the "
                        "best explanation from its runner-up. Use this when the current evidence "
                        "still leaves meaningful ambiguity between the candidates. If the evidence "
                        "already discriminates, identify what ruled the runner-up out. Provide the "
                        "test or existing discriminator as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded abductive inference. The "
                        "label helps the model and callers distinguish this note from other "
                        "context items. Use the default label when no more specific name is "
                        "needed. Provide a plain string; it defaults to 'Abductive Inference'."
                    ),
                    required=False,
                    default="Abductive Inference",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the abduction primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"abduce:{self._counter}"
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
        # Returns an error string if evidence, hypotheses (>=2), or a required field is missing.
        if not ReasoningToolInput.string_list(args.get("evidence")):
            return "Missing or empty required field: 'evidence'."
        hypotheses = ReasoningToolInput.object_list(args.get("hypotheses"))
        if len(hypotheses) < _MIN_HYPOTHESES:
            return (
                f"Field 'hypotheses' requires at least {_MIN_HYPOTHESES} genuinely competing "
                f"hypothesis objects; received {len(hypotheses)}."
            )
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the AbductionContextItem from validated call arguments.
        from vidbyte.context.primitives import AbductionContextItem

        return cast(
            ContextItem,
            AbductionContextItem(
                primitive_id=primitive_id,
                evidence=ReasoningToolInput.string_list(args.get("evidence")),
                hypotheses=ReasoningToolInput.object_list(args.get("hypotheses")),
                best=ReasoningToolInput.text(args, "best"),
                runner_up=ReasoningToolInput.text(args, "runner_up") or None,
                discriminating_test=ReasoningToolInput.text(
                    args, "discriminating_test"
                ),
                title=ReasoningToolInput.text(args, "title", "Abductive Inference")
                or "Abductive Inference",
            ),
        )
