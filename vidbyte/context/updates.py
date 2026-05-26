"""Context Protocol Header

Description:
    Defines typed updates for synchronizing context primitives.
Purpose:
    Lets tools and future context-window algorithms request primitive upserts
    and removals without directly mutating agent runtime state.
Architecture:
    - ContextPrimitiveUpdateAction: Supported update operations.
    - ContextPrimitiveUpdate: Immutable primitive update payload.
Relations:
    Consumed by ContextManager and ToolResult.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.context.primitives import ContextItem, context_primitive_id


class ContextPrimitiveUpdateAction(str, Enum):
    """Supported primitive store update operations."""

    UPSERT = "upsert"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class ContextPrimitiveUpdate:
    """Immutable update request for the runtime primitive store."""

    action: ContextPrimitiveUpdateAction | str
    item: ContextItem | None = None
    item_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def upsert(
        cls,
        item: ContextItem,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ContextPrimitiveUpdate":
        """Build an upsert update for a context primitive."""
        return cls(
            action=ContextPrimitiveUpdateAction.UPSERT,
            item=item,
            item_id=context_primitive_id(item),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def remove(
        cls,
        item_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ContextPrimitiveUpdate":
        """Build a removal update for a primitive ID."""
        if not item_id.strip():
            raise ValueError("ContextPrimitiveUpdate.remove() requires a non-empty item_id")
        return cls(
            action=ContextPrimitiveUpdateAction.REMOVE,
            item_id=item_id,
            metadata=dict(metadata or {}),
        )


__all__ = [
    "ContextPrimitiveUpdate",
    "ContextPrimitiveUpdateAction",
]
