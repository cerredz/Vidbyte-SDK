"""FILE: vidbyte/tools/builtins/reasoning/modal.py

PURPOSE: Records one modal reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the modal tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen ModalContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
COMMON MODIFICATION PATTERNS: Keep parameters, validation, primitive fields, and rendering synchronized; keep model-facing descriptions general and four to five sentences.
WHAT NOT TO DO: Do not add I/O, LLM calls, or side effects beyond the injected ContextManager upsert, and do not duplicate shared argument parsing.
KNOWN EDGE CASES: Required fields, enum values, list arity, and cross-field relationships are validated before the primitive is constructed.
RELATED DOCS: docs/design/reasoning-strategy-tools-batch-2.md; field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by the SDK source and package CI stages and the reasoning-tool smoke checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vidbyte.context.primitives.base import ContextItem
from vidbyte.lib.constants.reasoning_strategies import (
    MODAL_REQUIRED_FIELDS,
    MODAL_STATUS_VALUES,
)
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


class ModalTool(BaseTool):
    """Builtin tool that records a modality analysis into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="modal",
            description=(
                "Classify a claim's modality: is it necessary, merely possible, contingent, or impossible? "
                "Supply the evidence that settles the status and separate actuality from possibility. Use this "
                "whenever a claim uses 'must', 'may', 'cannot', 'necessarily', or 'could never' — modal words "
                "smuggled into claims are the difference between a demonstrated fact and a wish. The required "
                "fields make each part of the strategy explicit so the conclusion can be examined against its "
                "stated basis."
            ),
            parameters=(
                ToolParameter(
                    name="claim",
                    type="string",
                    description=(
                        "The claim whose modality is at issue, quoted with its modal word — e.g. 'the retry loop must "
                        "terminate'. Claims without modal words should be graded by their strongest reading. This field "
                        "is part of the strategy's explicit contract, so its contribution can be reviewed separately "
                        "from the final conclusion. Keeping it explicit prevents the analysis from relying on an "
                        "unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="modal_status",
                    type="string",
                    description=(
                        "One of: 'necessary', 'possible', 'contingent', 'impossible'. "
                        "'necessary' means the claim holds in every world (true by logic "
                        "or invariant). 'possible' means at least one world makes it true. "
                        "'contingent' means it holds in some worlds and fails in others. "
                        "'impossible' means no world makes it true."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="possible_world_evidence",
                    type="string",
                    description=(
                        "For 'possible': a coherent scenario in which the claim holds, specified in enough detail that "
                        "its coherence is checkable — merely asserting 'it could happen' without a describable scenario "
                        "is an empty possibility claim. For 'necessary'/'impossible': the general argument that closes "
                        "off all worlds. For 'contingent': one world each way. This field is part of the strategy's "
                        "explicit contract, so its contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="actuality",
                    type="string",
                    description=(
                        "Whether the claim in fact holds here and now — a claim can be 'possible' and false, "
                        "'necessary' and irrelevant, or 'impossible' and yet asserted. Never collapse possibility into "
                        "actuality; record both. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion. Keeping it explicit "
                        "prevents the analysis from relying on an unstated assumption and gives later iterations a "
                        "stable basis for comparison."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="reasoning",
                    type="string",
                    description=(
                        "The argument that connects the evidence to the status — why the worlds are closed off, or why "
                        "the counter-world exists. The modality is only as strong as this argument. This field is part "
                        "of the strategy's explicit contract, so its contribution can be reviewed separately from the "
                        "final conclusion. Keeping it explicit prevents the analysis from relying on an unstated "
                        "assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the modal primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"modal:{self._counter}"
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
        # Returns an error string for a missing field or a bad modal enum.
        error = ReasoningToolInput.missing_required(args, MODAL_REQUIRED_FIELDS)
        if error:
            return error
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "modal_status"),
            MODAL_STATUS_VALUES,
            "modal_status",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the ModalContextItem from validated call arguments.
        from vidbyte.context.primitives import ModalContextItem

        return cast(
            ContextItem,
            ModalContextItem(
                primitive_id=primitive_id,
                claim=ReasoningToolInput.text(args, "claim"),
                modal_status=ReasoningToolInput.text(args, "modal_status"),
                possible_world_evidence=ReasoningToolInput.text(
                    args, "possible_world_evidence"
                ),
                actuality=ReasoningToolInput.text(args, "actuality"),
                reasoning=ReasoningToolInput.text(args, "reasoning"),
                title=ReasoningToolInput.text(args, "title", "Modality Analysis")
                or "Modality Analysis",
            ),
        )
