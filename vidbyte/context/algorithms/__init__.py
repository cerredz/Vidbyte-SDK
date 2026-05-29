"""Context Protocol Header

Description:
    Exposes context-window algorithm implementations.
Purpose:
    Keeps runtime context algorithms separate from preset registration and
    public context primitives.
Architecture:
    - Tool-result admission algorithms from tool_results.
    - Reflexion runtime context-window algorithm from reflexion.
    - Multi-provider agentic grader context-window algorithm from multi_provider_agentic_grader.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from vidbyte.context.algorithms.beam_search import BeamSearchAlgorithm
from vidbyte.context.algorithms.dag_dataflow import DAGDataflowAlgorithm
from vidbyte.context.algorithms.gossip import GossipAlgorithm
from vidbyte.context.algorithms.market_auction import MarketAuctionAlgorithm
from vidbyte.context.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderAlgorithm
from vidbyte.context.algorithms.reflexion import ReflexionAlgorithm
from vidbyte.context.algorithms.tool_results import (
    ContextWindowAlgorithm,
    ToolResultAdmission,
)

__all__ = [
    "BeamSearchAlgorithm",
    "ContextWindowAlgorithm",
    "DAGDataflowAlgorithm",
    "GossipAlgorithm",
    "MarketAuctionAlgorithm",
    "MultiProviderAgenticGraderAlgorithm",
    "ReflexionAlgorithm",
    "ToolResultAdmission",
]

