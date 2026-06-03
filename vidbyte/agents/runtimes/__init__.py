"""Context Protocol Header

Description:
    Exposes all swappable agent loop execution runtimes.
Purpose:
    Allows BaseAgent to dynamically import and dispatch different runtime loop
    paradigms (linear execution, search trees, actor mailboxes, and non-linear runtimes).
Architecture:
    - LinearAgentRuntime: Sequential perception-action model-tool loop.
    - SearchTreeRuntimeComponent: Branching Monte Carlo Tree Search.
    - PointToPointActorRuntime: Asynchronous point-to-point actor model runtime.
    - BroadcastActorRuntime: Asynchronous broadcast actor model runtime.
    - BeamSearchAgentRuntime: Beam Search non-linear runtime.
    - DAGDataflowAgentRuntime: DAG Dataflow non-linear runtime.
    - MarketAuctionAgentRuntime: Market Auction non-linear runtime.
    - GossipAgentRuntime: Gossip non-linear runtime.
Relations:
    Imported by vidbyte.agents.base and the test harness suite.
Similar Files:
    - vidbyte/agents/base.py: Client class dispatching these runtimes.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
from vidbyte.agents.runtimes.actor.broker import PointToPointActorRuntime, BroadcastActorRuntime
from vidbyte.agents.runtimes.base_nonlinear import BaseNonLinearRuntime
from vidbyte.agents.runtimes.beam_search import BeamSearchAgentRuntime
from vidbyte.agents.runtimes.dag_dataflow import DAGDataflowAgentRuntime
from vidbyte.agents.runtimes.market_auction import MarketAuctionAgentRuntime
from vidbyte.agents.runtimes.gossip import GossipAgentRuntime
from vidbyte.agents.runtimes.configs import LinearRuntime, MctsSearchRuntime, ActorRuntime, BeamSearchRuntime, DAGDataflowRuntime, MarketAuctionRuntime, GossipRuntime
from vidbyte.agents.runtimes.actor.actor import (
    PrebuiltActor,
    PlannerActor,
    ReviewerActor,
    GeneratorActor,
    CriticActor,
    ReasonerActor,
    SummarizationActor,
    DecomposerActor,
    ExplorerActor,
    TradeoffActor,
    HypothesisGeneratorActor,
    RefinerActor,
    SafetyActor,
    FinalAnswerActor,
)

__all__ = [
    "LinearAgentRuntime",
    "SearchTreeRuntimeComponent",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
    "BaseNonLinearRuntime",
    "BeamSearchAgentRuntime",
    "DAGDataflowAgentRuntime",
    "MarketAuctionAgentRuntime",
    "GossipAgentRuntime",
    "LinearRuntime",
    "MctsSearchRuntime",
    "ActorRuntime",
    "BeamSearchRuntime",
    "DAGDataflowRuntime",
    "MarketAuctionRuntime",
    "GossipRuntime",
    "PrebuiltActor",
    "PlannerActor",
    "ReviewerActor",
    "GeneratorActor",
    "CriticActor",
    "ReasonerActor",
    "SummarizationActor",
    "DecomposerActor",
    "ExplorerActor",
    "TradeoffActor",
    "HypothesisGeneratorActor",
    "RefinerActor",
    "SafetyActor",
    "FinalAnswerActor",
]
