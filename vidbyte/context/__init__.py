"""Context Protocol Header

Description:
    Exposes the public context management and context-window algorithm interfaces.
Purpose:
    Allows developers to import all context-window configuration models, presets,
    and managers from a single public namespace.
Architecture:
    - Namespace client for ContextWindow and ContextManager.
Key Functions / Exports:
    - ContextManager: Manages loading, updating, and exporting context items.
    - ContextWindow: Represents the sliding/compacted context window.
    - ContextWindowAlgorithm: Base class for context window compaction/pruning.
Relation to codebase as a whole:
    Provides public exports for all context primitives and algorithms (including PlanContextItem, MultiProviderAgenticGraderAlgorithm, ReflexionAlgorithm, etc.) which are consumed by agents and runner engines to manage LLM context windows dynamically.
Similar files:
    - vidbyte/__init__.py: Root module exporting overall SDK contracts.
    - vidbyte/context/manager.py: Contains the concrete ContextManager implementation.
    - vidbyte/context/window.py: Contains the concrete ContextWindow implementation.
"""

from __future__ import annotations

from vidbyte.context.algorithms import ContextWindowAlgorithm, MultiProviderAgenticGraderAlgorithm, ReflexionAlgorithm, ToolResultAdmission
from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.lib.dataclasses.context import (
    BaseAgentContext,
    BaseContext,
    ContextArtifact,
    ContextBudget,
    ContextPermissions,
    ContextResponse,
    ContextToolCall,
)
from vidbyte.context.handoff import (
    EngineeringHandoff,
    Handoff,
    MinimalHandoff,
    ResearchHandoff,
)
from vidbyte.context.manager import ContextManager
from vidbyte.context.presets import ContextWindowPresets
from vidbyte.context.window import ContextWindow

__all__ = [
    "ArtifactContextItem",
    "BaseContext",
    "BaseAgentContext",
    "ContextArtifact",
    "ContextBudget",
    "ContextItem",
    "ContextManager",
    "ContextPermissions",
    "ContextResponse",
    "ContextToolCall",
    "ContextWindow",
    "ContextWindowAlgorithm",
    "ContextWindowPresets",
    "DocumentContextItem",
    "EngineeringHandoff",
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "Handoff",
    "MemoryContextItem",
    "MinimalHandoff",
    "ResearchHandoff",
    "MultiProviderAgenticGraderAlgorithm",
    "PlanContextItem",
    "ProgressContextItem",
    "ReflexionAlgorithm",
    "ResponseContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "ToolResultAdmission",
]
