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
    - multi_agent: Request/team/ledger/report/limits/terminal orchestration primitives.
    - checkpoints: ReflexionContextItem and TrajectoryCheckpointContextItem for context algorithms.
    - cot_events: Deep CoT monitoring event primitives (hypothesis, decision, assumption_check, uncertainty, backtrack).
    - framing/epistemics/decisions/execution/closure: General problem-solving challenges.
    - reasoning_strategies: Deduction/induction/abduction/analogy/causal-chain/
      Bayesian-update/differential-diagnosis/Fermi-estimate/steelman/falsify
      primitives for the named-reasoning-strategy tools.
    - reasoning_traces: Strategy-specific trace primitives for the built-in
      reasoning trace catalog.
    - All concrete types support primitive_id and primitive_frozen for registry management.
Relations:
    Used by vidbyte.context.manager and re-exported by vidbyte.context and
    vidbyte.lib.dataclasses for compatibility.
"""

from __future__ import annotations

from vidbyte.context.primitives.base import ContextItem
from vidbyte.context.primitives.checkpoints import (
    ReflexionContextItem,
    TrajectoryCheckpointContextItem,
)
from vidbyte.context.primitives.closure import (
    CompletionGateContextItem,
    ProcessStallContextItem,
    RiskEscalationContextItem,
)
from vidbyte.context.primitives.cot_events import (
    AssumptionCheckContextItem,
    BacktrackContextItem,
    DecisionContextItem,
    HypothesisContextItem,
    UncertaintyContextItem,
)
from vidbyte.context.primitives.decisions import (
    AlternativeChallengeContextItem,
    DecisionChallengeContextItem,
    TradeoffContextItem,
)
from vidbyte.context.primitives.documents import (
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    TextContextItem,
)
from vidbyte.context.primitives.epistemics import (
    AssumptionChallengeContextItem,
    EvidenceChallengeContextItem,
    ModelChallengeContextItem,
)
from vidbyte.context.primitives.execution import (
    DependencyContextItem,
    FeedbackGapContextItem,
    InterventionRiskContextItem,
    InvariantContextItem,
)
from vidbyte.context.primitives.framing import (
    AmbiguityContextItem,
    BoundaryContextItem,
    ObjectiveConflictContextItem,
    ObjectiveGapContextItem,
    PerspectiveGapContextItem,
    ProblemFrameContextItem,
)
from vidbyte.context.primitives.multi_agent import (
    MultiAgentContextSerializer,
    MultiAgentLedgerContextItem,
    MultiAgentLimitsContextItem,
    MultiAgentReportContextItem,
    MultiAgentRequestContextItem,
    MultiAgentTeamContextItem,
    MultiAgentTerminalContextItem,
)
from vidbyte.context.primitives.reasoning import (
    ErrorCorrectionContextItem,
    ProblemSpaceSearchContextItem,
)
from vidbyte.context.primitives.reasoning_strategies import (
    AbductionContextItem,
    AnalogyContextItem,
    BayesianUpdateContextItem,
    CausalChainContextItem,
    DeductionContextItem,
    DifferentialDiagnosisContextItem,
    FalsifyContextItem,
    FermiEstimateContextItem,
    InductionContextItem,
    SteelmanContextItem,
)
from vidbyte.context.primitives.reasoning_traces import ReasoningTraceContextItem
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
    "AbductionContextItem",
    "AlternativeChallengeContextItem",
    "AmbiguityContextItem",
    "AnalogyContextItem",
    "ArtifactContextItem",
    "AssumptionChallengeContextItem",
    "AssumptionCheckContextItem",
    "BacktrackContextItem",
    "BayesianUpdateContextItem",
    "BoundaryContextItem",
    "CausalChainContextItem",
    "CompletionGateContextItem",
    "ContextItem",
    "DecisionChallengeContextItem",
    "DecisionContextItem",
    "DeductionContextItem",
    "DependencyContextItem",
    "DifferentialDiagnosisContextItem",
    "DocumentContextItem",
    "EnvironmentContextItem",
    "ErrorCorrectionContextItem",
    "EvidenceChallengeContextItem",
    "FalsifyContextItem",
    "FeedbackGapContextItem",
    "FermiEstimateContextItem",
    "FileContextItem",
    "GitDiffContextItem",
    "HypothesisContextItem",
    "InductionContextItem",
    "InterventionRiskContextItem",
    "InvariantContextItem",
    "MemoryContextItem",
    "ModelChallengeContextItem",
    "MultiAgentContextSerializer",
    "MultiAgentLedgerContextItem",
    "MultiAgentLimitsContextItem",
    "MultiAgentReportContextItem",
    "MultiAgentRequestContextItem",
    "MultiAgentTeamContextItem",
    "MultiAgentTerminalContextItem",
    "ObjectiveConflictContextItem",
    "ObjectiveGapContextItem",
    "PerspectiveGapContextItem",
    "PlanContextItem",
    "ProblemFrameContextItem",
    "ProblemSpaceSearchContextItem",
    "ProcessStallContextItem",
    "ProgressContextItem",
    "ReasoningTraceContextItem",
    "ReflexionContextItem",
    "ResponseContextItem",
    "RiskEscalationContextItem",
    "SteelmanContextItem",
    "TaskContextItem",
    "TextContextItem",
    "ToolCallContextItem",
    "TradeoffContextItem",
    "TrajectoryCheckpointContextItem",
    "UncertaintyContextItem",
]
