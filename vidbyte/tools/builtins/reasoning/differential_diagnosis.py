"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/differential_diagnosis.py
PURPOSE: Implements the model-callable differential-diagnosis reasoning tool and records its structured result in the active context manager.
ROLE IN CODEBASE: The builtins catalog exports this hand-maintained strategy tool alongside the larger reasoning-trace catalog.
ARCHITECTURE NOTE: This module owns its ToolSpec and context-item construction; _parsing.py owns shared input coercion and ContextManager owns placement.
COMMON MODIFICATION PATTERNS: Keep tool and primitive fields synchronized, preserve model-facing semantics, and run focused lint plus canonical CI.
KNOWN EDGE CASES: Model arguments may be JSON-encoded or malformed, and a context write may reject an otherwise parsed record.
RELATED DOCS: vidbyte/tools/README.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

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
                "Use this tool when several candidate explanations remain plausible and must be "
                "narrowed systematically. It starts from a broad candidate set and eliminates "
                "only candidates contradicted by a concrete observation. The next check must be "
                "chosen for how effectively it separates the remaining possibilities. The "
                "resulting record should make every elimination and the priority of the next "
                "diagnostic action inspectable."
            ),
            parameters=(
                ToolParameter(
                    name="candidate_set",
                    type="array",
                    description=(
                        "List the full initial set of plausible candidates before elimination "
                        "begins. Include credible alternatives broadly enough that the model does "
                        "not commit to a leading explanation too early. This set is the reference "
                        "against which later evidence and eliminations are evaluated. Provide a "
                        "JSON array of strings or a JSON-encoded string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="remaining",
                    type="array",
                    description=(
                        "List the candidates from candidate_set that remain consistent with the "
                        "evidence. Remove only candidates contradicted by the recorded ruled-out "
                        "observations or tests, and keep this list as a subset of candidate_set. "
                        "The remaining set tells the model what possibilities still need to be "
                        "distinguished. Provide a JSON array of strings or a JSON-encoded string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="next_discriminator",
                    type="string",
                    description=(
                        "Describe the single observation, test, or question that would most reduce "
                        "the remaining candidate set. Choose it because it distinguishes among "
                        "the live candidates, not merely because it confirms the current leader. "
                        "This gives the model a concrete next step for resolving the differential. "
                        "Provide the discriminator as a plain string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="ruled_out",
                    type="array",
                    description=(
                        "Record candidates eliminated so far as objects with candidate and "
                        "ruled_out_by fields. Explain the specific observation or test result "
                        "that contradicts each eliminated candidate. Do not treat a candidate as "
                        "ruled out merely because it is less likely; concrete disconfirming evidence "
                        "is the purpose of this field. Provide a JSON array of objects or a JSON-"
                        "encoded string, and omit it when nothing has been ruled out."
                    ),
                    required=False,
                    default=(),
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "Choose a human-readable label for the recorded differential. The label "
                        "helps the model and callers distinguish this note from other context "
                        "items. Use the default label when no more specific name is needed. "
                        "Provide a plain string; it defaults to 'Differential Diagnosis'."
                    ),
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
        except ValueError:
            return ToolResult.error(
                call.tool_name,
                "The reasoning record could not be stored because its context values were invalid.",
                metadata={"error": "invalid_reasoning_context"},
            )

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate(self, args: dict) -> str | None:
        # Returns an error string if candidate_set, remaining, or next_discriminator is missing.
        if not ReasoningToolInput.string_list(args.get("candidate_set")):
            return "Missing or empty required field: 'candidate_set'."
        if not ReasoningToolInput.string_list(args.get("remaining")):
            return "Missing or empty required field: 'remaining'."
        return ReasoningToolInput.missing_required(args, _REQUIRED_FIELDS)

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the DifferentialDiagnosisContextItem from validated call arguments.
        from vidbyte.context.primitives import DifferentialDiagnosisContextItem

        return cast(
            ContextItem,
            DifferentialDiagnosisContextItem(
                primitive_id=primitive_id,
                candidate_set=ReasoningToolInput.string_list(args.get("candidate_set")),
                remaining=ReasoningToolInput.string_list(args.get("remaining")),
                next_discriminator=ReasoningToolInput.text(args, "next_discriminator"),
                ruled_out=ReasoningToolInput.object_list(args.get("ruled_out")),
                title=ReasoningToolInput.text(args, "title", "Differential Diagnosis")
                or "Differential Diagnosis",
            ),
        )
