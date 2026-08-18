"""Context Protocol Header

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

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.reasoning._parsing import ReasoningToolInput
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

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
                "Run an abductive inference (inference to the best explanation): list the "
                "evidence that needs explaining, score at least two genuinely competing "
                "hypotheses against it, and pick the best. Use this when choosing among "
                "possible explanations for observed facts — a debugging root cause, a "
                "diagnosis, a why-did-this-happen question. A single hypothesis is not "
                "abduction; it requires real competitors."
            ),
            parameters=(
                ToolParameter(
                    name="evidence",
                    type="array",
                    description=(
                        "The observed facts that need explaining. List each fact separately. "
                        "May be passed as a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="hypotheses",
                    type="array",
                    description=(
                        "Candidate explanations for the evidence, 2 to 4 of them, each as an "
                        "object: {hypothesis, explains, simplicity, assumptions_required}. "
                        "'hypothesis' is the candidate explanation in one sentence; 'explains' "
                        "states which listed evidence it accounts for and how well; 'simplicity' "
                        "is a short note on how many extra assumptions it needs relative to the "
                        "others; 'assumptions_required' lists what has to be true for it to hold. "
                        "Provide genuine competitors, not one idea plus strawmen — fewer than 2 "
                        "valid hypotheses is rejected. May be a JSON array of objects or a JSON "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="best",
                    type="string",
                    description=(
                        "Which hypothesis (by its 'hypothesis' text or a short label) best "
                        "explains the evidence, chosen for explanatory power and simplicity "
                        "together — not just whichever came to mind first."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="runner_up",
                    type="string",
                    description=(
                        "The second-best hypothesis, if any, and in one clause why it lost to "
                        "'best'. Naming the runner-up is what keeps this an inference among "
                        "competitors rather than a single story dressed up as reasoning. "
                        "Optional."
                    ),
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="discriminating_test",
                    type="string",
                    description=(
                        "An observation, test, or question that would distinguish 'best' from "
                        "the runner-up if the current evidence is ambiguous between them. If the "
                        "evidence already fully discriminates, say what already ruled the "
                        "runner-up out."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Abductive Inference'.",
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
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

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

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the AbductionContextItem from validated call arguments.
        from vidbyte.context.primitives import AbductionContextItem
        return AbductionContextItem(
            primitive_id=primitive_id,
            evidence=ReasoningToolInput.string_list(args.get("evidence")),
            hypotheses=ReasoningToolInput.object_list(args.get("hypotheses")),
            best=ReasoningToolInput.text(args, "best"),
            runner_up=ReasoningToolInput.text(args, "runner_up") or None,
            discriminating_test=ReasoningToolInput.text(args, "discriminating_test"),
            title=ReasoningToolInput.text(args, "title", "Abductive Inference") or "Abductive Inference",
        )
