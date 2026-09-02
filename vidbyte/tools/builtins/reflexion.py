"""Context Protocol Header

Description:
    Implements ReflexionTool — a model-callable builtin for writing self-critique
    notes into the active ContextManager.
Purpose:
    Lets the model record a self-authored reflexion (critique + correction plan) at
    any point during a run, unlike ReflexionAlgorithm which fires as a return-level
    retry wrapper controlled by the runtime.
Architecture:
    - ReflexionTool: BaseTool that constructs a ReflexionContextItem from model-
      provided arguments and upserts it into the injected ContextManager.
Relations:
    Depends on vidbyte.context.manager and vidbyte.context.primitives.
    Parallel to vidbyte.context.algorithms.reflexion (the algorithm form).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


class ReflexionTool(BaseTool):
    """Builtin tool that writes a model-authored self-critique into the context window."""

    def __init__(self, context_manager: ContextManager) -> None:
        # Stores the live manager and a per-instance counter for stable primitive IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="reflexion",
            description=(
                "Write a self-critique and correction plan into the context window. "
                "Use this when you detect a reasoning error, a repeated mistake, "
                "or a dead-end approach that should be explicitly noted before continuing. "
                "The reflexion note persists across all future turns."
            ),
            parameters=(
                ToolParameter(
                    name="critique",
                    type="string",
                    description="What went wrong or what should be improved in the current approach.",
                    required=True,
                ),
                ToolParameter(
                    name="correction_plan",
                    type="string",
                    description="Concrete steps to correct the approach going forward.",
                    required=True,
                ),
                ToolParameter(
                    name="failed_attempt",
                    type="string",
                    description="Brief description of the approach that failed. Optional.",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Display label for this note. Defaults to 'Reflexion Note'.",
                    required=False,
                    default="Reflexion Note",
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, build the reflexion primitive, and upsert it into the manager."""
        args = dict(call.arguments)

        error = self._validate_required_fields(args)
        if error:
            return ToolResult.error(call.tool_name, error)

        self._counter += 1
        primitive_id = self._next_primitive_id()
        item = self._build_item(args, primitive_id)

        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))

        return ToolResult.success(call.tool_name, item.to_context_text())

    def _validate_required_fields(self, args: dict) -> str | None:
        # Returns an error string if any required string field is missing or empty.
        for field_name in ("critique", "correction_plan"):
            value = args.get(field_name)
            if not value or not str(value).strip():
                return f"Missing or empty required field: '{field_name}'."
        return None

    def _next_primitive_id(self) -> str:
        # Generates a stable, unique primitive ID based on the instance counter.
        return f"reflexion:{self._counter}"

    def _build_item(self, args: dict, primitive_id: str) -> object:
        # Constructs the ReflexionContextItem from validated call arguments.
        from vidbyte.context.primitives import ReflexionContextItem
        raw_failed = args.get("failed_attempt")
        failed_attempt = str(raw_failed).strip() if raw_failed and str(raw_failed).strip() else None
        return ReflexionContextItem(
            primitive_id=primitive_id,
            critique=str(args.get("critique", "")).strip(),
            correction_plan=str(args.get("correction_plan", "")).strip(),
            failed_attempt=failed_attempt,
            title=str(args.get("title", "Reflexion Note")).strip() or "Reflexion Note",
        )
