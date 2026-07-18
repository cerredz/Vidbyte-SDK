"""Context Protocol Header

Description:
    Exposes agent-runtime context-window algorithm implementations.
Purpose:
    Keeps algorithm-specific runtime orchestration outside AgentRuntime.
Architecture:
    - IndependentCriticRuntimeAlgorithm: Executes an isolated advisory review.
    - ReflexionRuntimeAlgorithm: Executes Reflexion retry/reflection loops.
    - MultiProviderAgenticGraderRuntimeAlgorithm: Executes Multi-Provider Agentic Grader loops.
    - ProsecutorDefenderJudgeRuntimeAlgorithm: Executes isolated sequential debate review.
Relations:
    Used by vidbyte.agents.context_algorithms.
"""

from __future__ import annotations

from vidbyte.agents.algorithms.independent_critic import IndependentCriticRuntimeAlgorithm
from vidbyte.agents.algorithms.reflexion import ReflexionRuntimeAlgorithm
from vidbyte.agents.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderRuntimeAlgorithm
from vidbyte.agents.algorithms.prosecutor_defender_judge import ProsecutorDefenderJudgeRuntimeAlgorithm

__all__ = [
    "IndependentCriticRuntimeAlgorithm",
    "ReflexionRuntimeAlgorithm",
    "MultiProviderAgenticGraderRuntimeAlgorithm",
    "ProsecutorDefenderJudgeRuntimeAlgorithm",
]

