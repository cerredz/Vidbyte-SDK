"""Context Protocol Header

Description:
    Implements DifferentialDiagnosisTool — a model-callable builtin for
    recording an elimination-based narrowing pass into the active
    ContextManager.
Purpose:
    Lets the model track a candidate set being narrowed by concrete
    disconfirming evidence, and commit to the single next check that best
    discriminates among what remains, rather than converging on a leading
    guess without ruling anything out.
Architecture:
    - DifferentialDiagnosisTool: BaseTool that constructs a
      DifferentialDiagnosisContextItem from model-provided arguments and
      upserts it into the injected ContextManager.
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

_REQUIRED_FIELDS = ("next_discriminator",)


class DifferentialDiagnosisTool(BaseTool):
    """Builtin tool that records a differential-diagnosis narrowing pass into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="differential_diagnosis",
            description=(
                "Narrow a set of candidate explanations (diagnoses, root causes, culprits) by "
                "elimination: cast the field wide, remove only the candidates a concrete "
                "observation contradicts, and commit to the single next check that best splits "
                "what remains. Use this for debugging, root-cause analysis, or any 'what is "
                "actually going on' question with more than one live possibility."
            ),
            parameters=(
                ToolParameter(
                    name="candidate_set",
                    type="array",
                    description=(
                        "The full initial list of plausible candidates for what's actually "
                        "happening, before elimination begins. Cast this wide — differential "
                        "reasoning depends on not prematurely narrowing the field. May be a JSON "
                        "array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="remaining",
                    type="array",
                    description=(
                        "The candidates from candidate_set still consistent with all evidence "
                        "after removing the ruled_out entries. Must be a subset of candidate_set. "
                        "May be a JSON array of strings or a JSON string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="next_discriminator",
                    type="string",
                    description=(
                        "The single observation, test, or question that would most reduce the "
                        "remaining candidate set — the next thing to check, chosen because it "
                        "discriminates between remaining candidates rather than merely "
                        "confirming the leading one."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="ruled_out",
                    type="array",
                    description=(
                        "Candidates eliminated so far, each as an object {candidate, "
                        "ruled_out_by} where ruled_out_by is the specific observation or test "
                        "result inconsistent with that candidate. A candidate you merely find "
                        "'less likely' is not ruled out — only list ones a concrete piece of "
                        "evidence contradicts. May be a JSON array of objects, a JSON string, or "
                        "omitted if nothing has been ruled out yet."
                    ),
                    required=False,
                    default=(),
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Differential Diagnosis'.",
                    required=False,
                    default="Differential Diagnosis",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the differential-diagnosis primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"differential_diagnosis:{self._counter}"
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if candidate_set, remaining, or next_discriminator is missing.
        if not ReasoningToolInput.string_list(args.get("candidate_set")):
            return "Missing or empty required field: 'candidate_set'."
        if not ReasoningToolInput.string_list(args.get("remaining")):
            return "Missing or empty required field: 'remaining'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the DifferentialDiagnosisContextItem from validated call arguments.
        from vidbyte.context.primitives import DifferentialDiagnosisContextItem
        return DifferentialDiagnosisContextItem(
            primitive_id=primitive_id,
            candidate_set=ReasoningToolInput.string_list(args.get("candidate_set")),
            remaining=ReasoningToolInput.string_list(args.get("remaining")),
            next_discriminator=ReasoningToolInput.text(args, "next_discriminator"),
            ruled_out=ReasoningToolInput.object_list(args.get("ruled_out")),
            title=ReasoningToolInput.text(args, "title", "Differential Diagnosis") or "Differential Diagnosis",
        )
