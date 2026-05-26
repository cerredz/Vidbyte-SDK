"""Context Protocol Header

Description:
    Re-exports public context primitives from vidbyte.context.primitives.
Purpose:
    Preserves compatibility for older `vidbyte.lib.dataclasses.context_items`
    imports while keeping the implementation in the public context package.
Architecture:
    - Compatibility shim only; no primitive implementations live here.
Relations:
    Related to vidbyte.context.primitives.
"""

from __future__ import annotations

from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    ContextPrimitive,
    ContextPrimitivePlacement,
    ContextPrimitiveVisibility,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    IdentityContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.context.updates import ContextPrimitiveUpdate, ContextPrimitiveUpdateAction

__all__ = [
    "ArtifactContextItem",
    "ContextItem",
    "ContextPrimitive",
    "ContextPrimitivePlacement",
    "ContextPrimitiveUpdate",
    "ContextPrimitiveUpdateAction",
    "ContextPrimitiveVisibility",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "IdentityContextItem",
    "MemoryContextItem",
    "PlanContextItem",
    "ProgressContextItem",
    "ResponseContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
]
