"""Context Protocol Header

Description:
    Exposes context-window algorithm implementations.
Purpose:
    Keeps runtime context algorithms separate from preset registration and
    public context primitives.
Architecture:
    - Independent critic configuration from independent_critic.
    - Tool-result admission algorithms from tool_results.
    - Reflexion runtime context-window algorithm from reflexion.
    - Multi-provider agentic grader context-window algorithm from multi_provider_agentic_grader.
    - Prosecutor/defender/judge review configuration from prosecutor_defender_judge.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from vidbyte.context.algorithms.error_correction import ErrorCorrectionAlgorithm
from vidbyte.context.algorithms.independent_critic import (
    CriticFailurePolicy,
    IndependentCriticAlgorithm,
)
from vidbyte.context.algorithms.multi_provider_agentic_grader import (
    MultiProviderAgenticGraderAlgorithm,
)
from vidbyte.context.algorithms.problem_space_search import ProblemSpaceSearchAlgorithm
from vidbyte.context.algorithms.prosecutor_defender_judge import (
    DebateStageSettings,
    ProsecutorDefenderJudgeAlgorithm,
    ProsecutorDefenderJudgeFailurePolicy,
)
from vidbyte.context.algorithms.reflexion import ReflexionAlgorithm
from vidbyte.context.algorithms.tool_results import (
    ContextWindowAlgorithm,
    ToolResultAdmission,
)
from vidbyte.context.algorithms.trajectory_checkpoints import (
    TrajectoryCheckpointAlgorithm,
)

__all__ = [
    "CriticFailurePolicy",
    "ContextWindowAlgorithm",
    "ErrorCorrectionAlgorithm",
    "IndependentCriticAlgorithm",
    "MultiProviderAgenticGraderAlgorithm",
    "ProblemSpaceSearchAlgorithm",
    "DebateStageSettings",
    "ProsecutorDefenderJudgeAlgorithm",
    "ProsecutorDefenderJudgeFailurePolicy",
    "ReflexionAlgorithm",
    "TrajectoryCheckpointAlgorithm",
    "ToolResultAdmission",
]
