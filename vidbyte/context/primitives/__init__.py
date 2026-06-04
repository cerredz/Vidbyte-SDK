"""Context Protocol Header

Description:
    Public package of structured context primitives for context management.
Purpose:
    Gives developers standardized, immutable units of context that can be
    collected by a ContextManager and converted into existing SDK context objects.
Architecture:
    - base: ContextItem structural protocol and shared rendering helpers.
    - documents: Text/File/GitDiff/Document/Environment/Memory primitives.
    - tasks: Task/Progress/Plan primitives.
    - records: Artifact/Response/ToolCall primitives for existing context records.
    - checkpoints: ReflexionContextItem and TrajectoryCheckpointContextItem for context algorithms.
    - All concrete types support primitive_id and primitive_frozen for registry management.
Relations:
    Used by vidbyte.context.manager and re-exported by vidbyte.context and
    vidbyte.lib.dataclasses for compatibility.
"""

from __future__ import annotations

from vidbyte.context.primitives.base import ContextItem
from vidbyte.context.primitives.checkpoints import ReflexionContextItem, TrajectoryCheckpointContextItem
from vidbyte.context.primitives.documents import (
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    TextContextItem,
)
from vidbyte.context.primitives.records import (
    ArtifactContextItem,
    ResponseContextItem,
    ToolCallContextItem,
)
from vidbyte.context.primitives.tasks import (
    PlanContextItem,
    ProgressContextItem,
    TaskContextItem,
)

__all__ = [
    "ArtifactContextItem",
    "ContextItem",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "PlanContextItem",
    "ProgressContextItem",
    "ReflexionContextItem",
    "ResponseContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "TrajectoryCheckpointContextItem",
]
