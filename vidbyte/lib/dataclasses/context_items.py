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
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)

__all__ = [
    "ArtifactContextItem",
    "ContextItem",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "ProgressContextItem",
    "ResponseContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
]
