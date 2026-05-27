"""Context Protocol Header

Description:
    Exposes the public context management and context-window algorithm interfaces.
Purpose:
    Allows developers to import all context-window configuration models, presets,
    and managers from a single public namespace.
Architecture:
    - Namespace client for ContextWindow and ContextManager.
Relations:
    Top-level namespace package, re-exported by vidbyte.
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
    StrategyContext,
    VMAOContext,
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
    "EnvironmentContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "MemoryContextItem",
    "MultiProviderAgenticGraderAlgorithm",
    "ProgressContextItem",
    "ReflexionAlgorithm",
    "ResponseContextItem",
    "StrategyContext",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "ToolResultAdmission",
    "VMAOContext",
]
