"""Context Protocol Header

Description:
    Exposes the public context management and context-window algorithm interfaces.
Purpose:
    Allows developers to import all context-window configuration models, presets,
    and managers from a single public namespace.
Architecture:
    - Namespace client for ContextWindow, ContextManager, and MultiAgentContext.
Key Functions / Exports:
    - ContextManager: Manages loading, updating, and exporting context items.
    - ContextWindow: Represents the sliding/compacted context window.
    - MultiAgentContext: Builds and renders orchestration context primitives.
    - ContextWindowAlgorithm: Base class for context window compaction/pruning.
Relation to codebase as a whole:
    Provides public exports for all context primitives and algorithms (including PlanContextItem, MultiProviderAgenticGraderAlgorithm, ReflexionAlgorithm, etc.) which are consumed by agents and runner engines to manage LLM context windows dynamically.
Similar files:
    - vidbyte/__init__.py: Root module exporting overall SDK contracts.
    - vidbyte/context/manager.py: Contains the concrete ContextManager implementation.
    - vidbyte/context/window.py: Contains the concrete ContextWindow implementation.
"""

from __future__ import annotations

from vidbyte.context.algorithms import ContextWindowAlgorithm, DebateStageSettings, ErrorCorrectionAlgorithm, MultiProviderAgenticGraderAlgorithm, ProblemSpaceSearchAlgorithm, ProsecutorDefenderJudgeAlgorithm, ProsecutorDefenderJudgeFailurePolicy, ReflexionAlgorithm, ToolResultAdmission, TrajectoryCheckpointAlgorithm
from vidbyte.context.compaction import CompactionMode, CompactionStats, ContextCompactionEngine, Summarizer
from vidbyte.context.primitives import (
    ArtifactContextItem,
    ContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    ErrorCorrectionContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    MultiAgentContextSerializer,
    MultiAgentLedgerContextItem,
    MultiAgentLimitsContextItem,
    MultiAgentReportContextItem,
    MultiAgentRequestContextItem,
    MultiAgentTeamContextItem,
    MultiAgentTerminalContextItem,
    PlanContextItem,
    ProblemSpaceSearchContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
    TrajectoryCheckpointContextItem,
)
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm
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
from vidbyte.context.multi_agent import MultiAgentContext
from vidbyte.context.presets import ContextWindowPresets
from vidbyte.context.window import ContextWindow

__all__ = [
    "ArtifactContextItem",
    "BaseContext",
    "BaseAgentContext",
    "ContextArtifact",
    "ContextBudget",
    "CompactionMode",
    "CompactionStats",
    "ContextCompactionEngine",
    "ContextItem",
    "ContextManager",
    "ContextPermissions",
    "ContextResponse",
    "ContextToolCall",
    "ContextWindow",
    "ContextWindowAlgorithm",
    "ContextWindowPlacement",
    "ContextWindowPresets",
    "ContextWindowRunContext",
    "DebateStageSettings",
    "DocumentContextItem",
    "EngineeringHandoff",
    "EnvironmentContextItem",
    "ErrorCorrectionAlgorithm",
    "ErrorCorrectionContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "Handoff",
    "MemoryContextItem",
    "MinimalHandoff",
    "MultiAgentContext",
    "MultiAgentContextSerializer",
    "MultiAgentLedgerContextItem",
    "MultiAgentLimitsContextItem",
    "MultiAgentReportContextItem",
    "MultiAgentRequestContextItem",
    "MultiAgentTeamContextItem",
    "MultiAgentTerminalContextItem",
    "ResearchHandoff",
    "MultiProviderAgenticGraderAlgorithm",
    "InnerContextWindowAlgorithm",
    "PlanContextItem",
    "ProblemSpaceSearchAlgorithm",
    "ProsecutorDefenderJudgeAlgorithm",
    "ProsecutorDefenderJudgeFailurePolicy",
    "ProblemSpaceSearchContextItem",
    "ProgressContextItem",
    "ReflexionAlgorithm",
    "ResponseContextItem",
    "Summarizer",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "ToolResultAdmission",
    "TrajectoryCheckpointAlgorithm",
    "TrajectoryCheckpointContextItem",
]
