"""Context Protocol Header

Description:
    Exposes agent-runtime context-window algorithm implementations.
Purpose:
    Keeps algorithm-specific runtime orchestration outside AgentRuntime.
Architecture:
    - ReflexionRuntimeAlgorithm: Executes Reflexion retry/reflection loops.
    - MultiProviderAgenticGraderRuntimeAlgorithm: Executes Multi-Provider Agentic Grader loops.
Relations:
    Used by vidbyte.agents.context_algorithms.
"""

from __future__ import annotations

from vidbyte.agents.algorithms.reflexion import ReflexionRuntimeAlgorithm
from vidbyte.agents.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderRuntimeAlgorithm

__all__ = [
    "ReflexionRuntimeAlgorithm",
    "MultiProviderAgenticGraderRuntimeAlgorithm",
]

