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

from vidbyte.agents.algorithms.beam_search import BeamSearchRuntimeAlgorithm
from vidbyte.agents.algorithms.dag_dataflow import DAGDataflowRuntimeAlgorithm
from vidbyte.agents.algorithms.gossip import GossipRuntimeAlgorithm
from vidbyte.agents.algorithms.market_auction import MarketAuctionRuntimeAlgorithm
from vidbyte.agents.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderRuntimeAlgorithm
from vidbyte.agents.algorithms.reflexion import ReflexionRuntimeAlgorithm

__all__ = [
    "BeamSearchRuntimeAlgorithm",
    "DAGDataflowRuntimeAlgorithm",
    "GossipRuntimeAlgorithm",
    "MarketAuctionRuntimeAlgorithm",
    "MultiProviderAgenticGraderRuntimeAlgorithm",
    "ReflexionRuntimeAlgorithm",
]

