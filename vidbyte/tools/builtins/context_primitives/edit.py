"""Context Protocol Header

Description:
    Implements ContextEditTool for exact-string edits on managed primitives.
Purpose:
    Lets agents surgically correct managed primitives after user feedback without
    rewriting unrelated fields or silently patching ambiguous text.
Architecture:
    - ContextEditTool: BaseTool that unique-matches across string/tuple fields.
Relations:
    Used via ContextWindowFactory and vidbyte.tools.builtins.context_primitives.
    Depends on ContextManager and frozen primitive semantics.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager

_SKIP_FIELDS = frozenset({"kind", "primitive_id", "primitive_frozen", "metadata"})


class ContextEditTool(BaseTool):
    """Builtin tool that performs an exact unique replacement on editable primitive fields."""

    def __init__(self, context_manager: ContextManager) -> None:
        """Store the live manager shared with AgentRuntime."""
        self._manager = context_manager

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for this tool."""
        return ToolSpec(
            name="context_edit",
            description=(
                "context_edit surgically corrects a managed context-window primitive after user "
                "feedback. It replaces exactly one unique occurrence of old_string with new_string "
                "across editable string or string-tuple fields (e.g. content, goal, steps), "
                "preserving placement and other fields. It refuses zero matches, multiple matches, "
                "frozen primitives, and empty old_string. Prefer context_list/context_stats first; "
                "use context_upsert or create tools for full rewrites."
            ),
            parameters=(
                ToolParameter(
                    name="primitive_id",
                    type="string",
                    description=(
                        "primitive_id is the registry key of the managed primitive to edit. "
                        "Use context_stats or context_list if you need to discover available ids."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description=(
                        "old_string is the exact existing substring to replace. It must appear "
                        "exactly once across editable fields — expand it if missing or ambiguous."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    description=(
                        "new_string is the replacement text written in place of the single old_string match."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Patch one unique match in the primitive or return a steering error."""
        primitive_id = str(call.arguments.get("primitive_id", "")).strip()
        old_string = str(call.arguments.get("old_string", ""))
        new_string = str(call.arguments.get("new_string", ""))
        if not primitive_id:
            return ToolResult.error(call.tool_name, "primitive_id is required.")
        if not old_string:
            return ToolResult.error(
                call.tool_name,
                "old_string must be a non-empty exact string that appears once in the primitive.",
            )
        item = self._manager.get_by_id(primitive_id)
        if item is None:
            return ToolResult.error(
                call.tool_name,
                f"Primitive '{primitive_id}' does not exist. Use context_stats or context_list to inspect available ids.",
            )
        if getattr(item, "primitive_frozen", False):
            return ToolResult.error(
                call.tool_name,
                f"Primitive '{primitive_id}' is frozen; it cannot be modified. Create a new primitive with a different id instead.",
            )
        if not dataclasses.is_dataclass(item):
            return ToolResult.error(call.tool_name, f"Primitive '{primitive_id}' is not a dataclass and cannot be edited.")
        try:
            updated = self._apply_unique_replace(item, old_string, new_string)
            self._manager.upsert_preserving_placement(updated)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(
            call.tool_name,
            f"Primitive '{primitive_id}' edited successfully.",
            metadata={"primitive_id": primitive_id},
        )

    def _apply_unique_replace(self, item: object, old_string: str, new_string: str) -> object:
        """Return a replaced dataclass when old_string matches exactly once across editable fields."""
        hits = self._collect_match_hits(item, old_string)
        total = sum(count for _, count, _ in hits)
        primitive_id = getattr(item, "primitive_id", "?")
        if total == 0:
            raise ValueError(
                f"old_string was not found in primitive '{primitive_id}'. "
                "Read the rendered context and pass an exact substring that appears once."
            )
        if total > 1:
            raise ValueError(
                f"old_string appears {total} times in primitive '{primitive_id}'. "
                "Use a longer exact string that appears once."
            )
        field_name, _, payload = hits[0]
        new_value = self._replace_hit_value(payload, old_string, new_string)
        return dataclasses.replace(item, **{field_name: new_value})

    def _collect_match_hits(self, item: object, old_string: str) -> list[tuple[str, int, Any]]:
        """Collect (field_name, match_count, field_value) for editable fields with matches."""
        hits: list[tuple[str, int, Any]] = []
        for field in dataclasses.fields(item):
            if field.name in _SKIP_FIELDS:
                continue
            value = getattr(item, field.name)
            count = self._count_matches(value, old_string)
            if count > 0:
                hits.append((field.name, count, value))
        return hits

    def _count_matches(self, value: Any, old_string: str) -> int:
        """Count exact old_string occurrences in a string or string-tuple field value."""
        if isinstance(value, str):
            return value.count(old_string)
        if isinstance(value, tuple) and all(isinstance(part, str) for part in value):
            return sum(part.count(old_string) for part in value)
        return 0

    def _replace_hit_value(self, value: Any, old_string: str, new_string: str) -> Any:
        """Replace the single old_string occurrence inside a string or string-tuple value."""
        if isinstance(value, str):
            return value.replace(old_string, new_string, 1)
        if isinstance(value, tuple) and all(isinstance(part, str) for part in value):
            parts = list(value)
            for index, part in enumerate(parts):
                if old_string in part:
                    parts[index] = part.replace(old_string, new_string, 1)
                    break
            return tuple(parts)
        raise ValueError("Matched field is not an editable string or string-tuple.")


__all__ = ["ContextEditTool"]
