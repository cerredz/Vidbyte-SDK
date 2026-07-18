"""Context Protocol Header

Description:
    Exposes the public context management and context-window algorithm interfaces.
Purpose:
    Allows developers to import all context-window configuration models, presets,
    and managers from a single public namespace.
Architecture:
    - Namespace client for ContextWindow, ContextManager, and MultiAgentContext.
    - Problem-solving records for framing, epistemics, decisions, execution, and closure.
Key Functions / Exports:
    - ContextManager: Manages loading, updating, and exporting context items.
    - ContextWindow: Represents the sliding/compacted context window.
    - MultiAgentContext: Builds and renders orchestration context primitives.
    - ContextWindowAlgorithm: Base class for context window compaction/pruning.
    - IndependentCriticAlgorithm: Configures isolated advisory candidate review.
Relation to codebase as a whole:
    Provides public exports for all context primitives and algorithms (including
    general problem-solving challenges as well as IndependentCriticAlgorithm,
    MultiProviderAgenticGraderAlgorithm, and ReflexionAlgorithm) which are
    consumed by callers, agents, and runner engines to manage LLM context
    windows dynamically.
Similar files:
    - vidbyte/__init__.py: Root module exporting overall SDK contracts.
    - vidbyte/context/manager.py: Contains the concrete ContextManager implementation.
    - vidbyte/context/window.py: Contains the concrete ContextWindow implementation.
"""

from __future__ import annotations

from vidbyte.context.algorithms import (
    ContextWindowAlgorithm,
    CriticFailurePolicy,
    ErrorCorrectionAlgorithm,
    IndependentCriticAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    ParallelPanelAlgorithm,
    ProblemSpaceSearchAlgorithm,
    ReflexionAlgorithm,
    ToolResultAdmission,
    TrajectoryCheckpointAlgorithm,
)
from vidbyte.context.compaction import CompactionMode, CompactionStats, ContextCompactionEngine, Summarizer
from vidbyte.context.primitives import (
    AlternativeChallengeContextItem,
    AmbiguityContextItem,
    ArtifactContextItem,
    AssumptionChallengeContextItem,
    BoundaryContextItem,
    CompletionGateContextItem,
    ContextItem,
    DecisionChallengeContextItem,
    DependencyContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    ErrorCorrectionContextItem,
    EvidenceChallengeContextItem,
    FeedbackGapContextItem,
    FileContextItem,
    GitDiffContextItem,
    InterventionRiskContextItem,
    InvariantContextItem,
    MemoryContextItem,
    ModelChallengeContextItem,
    MultiAgentContextSerializer,
    MultiAgentLedgerContextItem,
    MultiAgentLimitsContextItem,
    MultiAgentReportContextItem,
    MultiAgentRequestContextItem,
    MultiAgentTeamContextItem,
    MultiAgentTerminalContextItem,
    ObjectiveConflictContextItem,
    ObjectiveGapContextItem,
    PlanContextItem,
    PerspectiveGapContextItem,
    ProblemFrameContextItem,
    ProblemSpaceSearchContextItem,
    ProcessStallContextItem,
    ProgressContextItem,
    ResponseContextItem,
    RiskEscalationContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
    TradeoffContextItem,
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
    "AlternativeChallengeContextItem",
    "AmbiguityContextItem",
    "ArtifactContextItem",
    "AssumptionChallengeContextItem",
    "BaseContext",
    "BaseAgentContext",
    "BoundaryContextItem",
    "CompletionGateContextItem",
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
    "CriticFailurePolicy",
    "DecisionChallengeContextItem",
    "DependencyContextItem",
    "DocumentContextItem",
    "EngineeringHandoff",
    "EnvironmentContextItem",
    "ErrorCorrectionAlgorithm",
    "ErrorCorrectionContextItem",
    "EvidenceChallengeContextItem",
    "FeedbackGapContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "Handoff",
    "IndependentCriticAlgorithm",
    "InterventionRiskContextItem",
    "InvariantContextItem",
    "MemoryContextItem",
    "MinimalHandoff",
    "ModelChallengeContextItem",
    "MultiAgentContext",
    "MultiAgentContextSerializer",
    "MultiAgentLedgerContextItem",
    "MultiAgentLimitsContextItem",
    "MultiAgentReportContextItem",
    "MultiAgentRequestContextItem",
    "MultiAgentTeamContextItem",
    "MultiAgentTerminalContextItem",
    "ObjectiveConflictContextItem",
    "ObjectiveGapContextItem",
    "ResearchHandoff",
    "MultiProviderAgenticGraderAlgorithm",
    "ParallelPanelAlgorithm",
    "InnerContextWindowAlgorithm",
    "PlanContextItem",
    "PerspectiveGapContextItem",
    "ProblemFrameContextItem",
    "ProblemSpaceSearchAlgorithm",
    "ProblemSpaceSearchContextItem",
    "ProcessStallContextItem",
    "ProgressContextItem",
    "ReflexionAlgorithm",
    "ResponseContextItem",
    "RiskEscalationContextItem",
    "Summarizer",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "TradeoffContextItem",
    "ToolResultAdmission",
    "TrajectoryCheckpointAlgorithm",
    "TrajectoryCheckpointContextItem",
]
