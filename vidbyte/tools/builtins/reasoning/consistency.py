"""FILE: vidbyte/tools/builtins/reasoning/consistency.py

PURPOSE: Records one consistency reasoning result in the ContextManager through a model-callable builtin.
ROLE IN CODEBASE: Provides the consistency tool and its ToolSpec contract for the reasoning-strategy builtin family.
ARCHITECTURE NOTE: Validates model arguments, constructs one frozen ConsistencyContextItem, upserts it through the injected ContextManager, and returns its bounded rendering.
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
    CONSISTENCY_REQUIRED_FIELDS,
    CONSISTENCY_REQUIRED_PRESENT_FIELDS,
    CONSISTENCY_STATUS_VALUES,
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


class ConsistencyTool(BaseTool):
    """Builtin tool that records a belief-set contradiction audit into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="consistency",
            description=(
                "Audit a set of claims for mutual contradiction: state each claim, name the concrete pairs "
                "where both cannot hold, commit to a status, and resolve the conflict. Use this whenever the "
                "model holds several commitments at once — before merging plans, synthesizing positions, or "
                "relying on two rules simultaneously. A belief set that has never been checked for "
                "contradiction is a belief set that is only accidentally consistent. The required fields make "
                "each part of the strategy explicit so the conclusion can be examined against its stated basis."
            ),
            parameters=(
                ToolParameter(
                    name="claims",
                    type="array",
                    description=(
                        "The belief set under audit, each claim stated singly as its own string. At least two claims "
                        "are required — a one-claim set cannot be inconsistent. May be passed as a JSON array of "
                        "strings or a JSON string. This field is part of the strategy's explicit contract, so its "
                        "contribution can be reviewed separately from the final conclusion."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pairwise_conflicts",
                    type="array",
                    description=(
                        "JSON array of objects with keys 'claim_a', 'claim_b', and "
                        "'conflict': the concrete pairs where both claims cannot hold, with "
                        "the contradiction spelled out ('claim_a implies P; claim_b implies "
                        "not-P'). Vague 'these feel incompatible' entries are not "
                        "conflicts — the logical clash must be named. If the set is "
                        "consistent, provide an empty list. May also be passed as a JSON "
                        "string."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="consistency_status",
                    type="string",
                    description=(
                        "One of: 'consistent', 'contradictory', 'unresolved'. 'consistent' "
                        "means no genuine conflict exists. 'contradictory' means at least one "
                        "pair cannot both be true. 'unresolved' means a suspected clash "
                        "exists but cannot yet be proven or disproven."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="resolution",
                    type="string",
                    description=(
                        "Which claim must yield — or what new evidence would decide an 'unresolved' status — and why "
                        "that claim loses. An audit that finds a contradiction and records no resolution is not "
                        "finished. This field is part of the strategy's explicit contract, so its contribution can be "
                        "reviewed separately from the final conclusion. Keeping it explicit prevents the analysis from "
                        "relying on an unstated assumption and gives later iterations a stable basis for comparison."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the consistency primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = f"consistency:{self._counter}"
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
        # Returns an error string for a missing field, an undersized claim set, or a bad enum.
        error = ReasoningToolInput.missing_required(args, CONSISTENCY_REQUIRED_FIELDS)
        if error:
            return error
        for name in CONSISTENCY_REQUIRED_PRESENT_FIELDS:
            if name not in args:
                return f"Missing or empty required field: '{name}'."
        claims = ReasoningToolInput.string_list(args.get("claims"))
        if len(claims) < 2:
            return "Field 'claims' requires at least two claims to audit."
        return ReasoningToolInput.enum_error(
            ReasoningToolInput.text(args, "consistency_status"),
            CONSISTENCY_STATUS_VALUES,
            "consistency_status",
        )

    def _build_item(self, args: dict, primitive_id: str) -> ContextItem:
        # Constructs the ConsistencyContextItem from validated call arguments.
        from vidbyte.context.primitives import ConsistencyContextItem

        return cast(
            ContextItem,
            ConsistencyContextItem(
                primitive_id=primitive_id,
                claims=ReasoningToolInput.string_list(args.get("claims")),
                pairwise_conflicts=ReasoningToolInput.object_list(
                    args.get("pairwise_conflicts")
                ),
                consistency_status=ReasoningToolInput.text(args, "consistency_status"),
                resolution=ReasoningToolInput.text(args, "resolution"),
                title=ReasoningToolInput.text(args, "title", "Consistency Audit")
                or "Consistency Audit",
            ),
        )
