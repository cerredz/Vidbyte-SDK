"""Context Protocol Header

Description:
    Defines configuration classes for Linear, MCTS Search, Actor, and non-linear runtimes.
Purpose:
    Allows developers to cleanly configure runtime settings inside a single
    structured parameter, avoiding main agent constructor clutter.
Architecture:
    - LinearRuntime: Configuration object for linear runs.
    - MctsSearchRuntime: Configuration object for Monte Carlo Tree Search.
    - ActorRuntime: Configuration object for asynchronous multi-agent swarms.
    - BeamSearchRuntime: Configuration object for Beam Search non-linear runtime.
    - DAGDataflowRuntime: Configuration object for DAG Dataflow non-linear runtime.
    - MarketAuctionRuntime: Configuration object for Market Auction non-linear runtime.
    - GossipRuntime: Configuration object for Gossip non-linear runtime.
Relations:
    Located in vidbyte/agents/runtimes/configs.py. Imported by BaseAgent.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: Domain configs.
"""

from __future__ import annotations
from typing import Any, Sequence, TYPE_CHECKING
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.actor import PrebuiltActor


class LinearRuntime:
    """Configurable settings for the Linear execution runtime."""

    def __init__(self) -> None:
        # Initializes a linear runtime configuration.
        self.runtime_type = AgentRuntimeType.LINEAR


class MctsSearchRuntime:
    """Configurable settings for the Branching Search MCTS execution runtime."""

    def __init__(self) -> None:
        # Initializes an MCTS search runtime configuration.
        self.runtime_type = AgentRuntimeType.MCTS_SEARCH


class ActorRuntime:
    """Configurable settings for the Asynchronous Actor Model execution runtime."""

    def __init__(
        self,
        *,
        topology: AgentRuntimeType | str = AgentRuntimeType.ACTOR_MODEL_P2P,
        dynamic_actors: bool = False,
        max_loop: int = 20,
        termination_mode: str = "coordinator",
        worker_model: str | None = None,
        include_actors: Sequence[type[PrebuiltActor]] | None = None,
    ) -> None:
        # Initializes an actor runtime configuration with specific topologies and prebuilt actors.
        from vidbyte.lib.registries.models import ProviderModelRegistry
        self.runtime_type = AgentRuntimeType(topology)
        if max_loop < 1:
            raise ConfigurationError("ActorRuntime max_loop must be at least 1.")
        _valid_termination_modes = ("coordinator", "quiescence")
        if termination_mode not in _valid_termination_modes:
            raise ConfigurationError(
                f"ActorRuntime termination_mode must be one of {_valid_termination_modes}, "
                f"got '{termination_mode}'."
            )
        if worker_model is not None:
            ProviderModelRegistry.validate_model(worker_model)
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model
        self.include_actors = include_actors


_DEFAULT_GOSSIP_ANGLES = (
    "approach from first principles",
    "focus on edge cases and failure modes",
    "consider alternative approaches",
    "evaluate practical implementation details",
)


class BeamSearchRuntime:
    """Configurable settings for the Beam Search non-linear execution runtime."""

    def __init__(
        self,
        *,
        beam_width: int = 3,
        max_scorer_chars: int = 8000,
        scorer_system_prompt: str | None = None,
        scorer_prompt: str | None = None,
    ) -> None:
        # Validates and stores Beam Search runtime parameters.
        from vidbyte.prompts.catalog import Prompts
        self.runtime_type = AgentRuntimeType.BEAM_SEARCH
        if beam_width < 1:
            raise ConfigurationError("BeamSearchRuntime beam_width must be at least 1.")
        if max_scorer_chars < 1:
            raise ConfigurationError("BeamSearchRuntime max_scorer_chars must be at least 1.")
        self.beam_width = beam_width
        self.max_scorer_chars = max_scorer_chars
        _p = Prompts()
        self.scorer_system_prompt = scorer_system_prompt or _p.get(Prompt.BEAM_SEARCH_SCORER_SYSTEM_PROMPT)
        self.scorer_prompt = scorer_prompt or _p.get(Prompt.BEAM_SEARCH_SCORER_PROMPT)


class DAGDataflowRuntime:
    """Configurable settings for the DAG Dataflow non-linear execution runtime."""

    def __init__(
        self,
        *,
        max_parallel: int = 4,
        max_node_output_chars: int = 12000,
        planner_system_prompt: str | None = None,
        node_system_prompt: str | None = None,
        synthesizer_system_prompt: str | None = None,
    ) -> None:
        # Validates and stores DAG Dataflow runtime parameters.
        from vidbyte.prompts.catalog import Prompts
        self.runtime_type = AgentRuntimeType.DAG_DATAFLOW
        if max_parallel < 1:
            raise ConfigurationError("DAGDataflowRuntime max_parallel must be at least 1.")
        if max_node_output_chars < 1:
            raise ConfigurationError("DAGDataflowRuntime max_node_output_chars must be at least 1.")
        self.max_parallel = max_parallel
        self.max_node_output_chars = max_node_output_chars
        _p = Prompts()
        self.planner_system_prompt = planner_system_prompt or _p.get(Prompt.DAG_DATAFLOW_PLANNER_SYSTEM_PROMPT)
        self.node_system_prompt = node_system_prompt or _p.get(Prompt.DAG_DATAFLOW_NODE_SYSTEM_PROMPT)
        self.synthesizer_system_prompt = synthesizer_system_prompt or _p.get(Prompt.DAG_DATAFLOW_SYNTHESIZER_SYSTEM_PROMPT)


class MarketAuctionRuntime:
    """Configurable settings for the Market Auction non-linear execution runtime."""

    def __init__(
        self,
        *,
        num_agents: int = 3,
        roles: Sequence[str] | None = None,
        max_approach_chars: int = 500,
        auctioneer_system_prompt: str | None = None,
        bidder_system_prompt_template: str | None = None,
        executor_system_prompt_template: str | None = None,
    ) -> None:
        # Validates and stores Market Auction runtime parameters.
        from vidbyte.prompts.catalog import Prompts
        self.runtime_type = AgentRuntimeType.MARKET_AUCTION
        if num_agents < 1:
            raise ConfigurationError("MarketAuctionRuntime num_agents must be at least 1.")
        if max_approach_chars < 1:
            raise ConfigurationError("MarketAuctionRuntime max_approach_chars must be at least 1.")
        self.num_agents = num_agents
        self.roles = tuple(roles) if roles is not None else None
        self.max_approach_chars = max_approach_chars
        _p = Prompts()
        self.auctioneer_system_prompt = auctioneer_system_prompt or _p.get(Prompt.MARKET_AUCTION_AUCTIONEER_SYSTEM_PROMPT)
        self.bidder_system_prompt_template = bidder_system_prompt_template or _p.get(Prompt.MARKET_AUCTION_BIDDER_SYSTEM_PROMPT)
        self.executor_system_prompt_template = executor_system_prompt_template or _p.get(Prompt.MARKET_AUCTION_EXECUTOR_SYSTEM_PROMPT)


class GossipRuntime:
    """Configurable settings for the Gossip non-linear execution runtime."""

    def __init__(
        self,
        *,
        num_agents: int = 4,
        gossip_rounds: int = 3,
        max_knowledge_chars: int = 6000,
        angles: Sequence[str] | None = None,
        agent_system_prompt: str | None = None,
        merge_system_prompt: str | None = None,
        synthesizer_system_prompt: str | None = None,
    ) -> None:
        # Validates and stores Gossip runtime parameters.
        from vidbyte.prompts.catalog import Prompts
        self.runtime_type = AgentRuntimeType.GOSSIP
        if num_agents < 2:
            raise ConfigurationError("GossipRuntime num_agents must be at least 2.")
        if gossip_rounds < 1:
            raise ConfigurationError("GossipRuntime gossip_rounds must be at least 1.")
        if max_knowledge_chars < 1:
            raise ConfigurationError("GossipRuntime max_knowledge_chars must be at least 1.")
        self.num_agents = num_agents
        self.gossip_rounds = gossip_rounds
        self.max_knowledge_chars = max_knowledge_chars
        resolved_angles = tuple(angles) if angles is not None else _DEFAULT_GOSSIP_ANGLES
        while len(resolved_angles) < num_agents:
            resolved_angles = (*resolved_angles, f"explore angle {len(resolved_angles) + 1}")
        self.angles = resolved_angles
        _p = Prompts()
        self.agent_system_prompt = agent_system_prompt or _p.get(Prompt.GOSSIP_AGENT_SYSTEM_PROMPT)
        self.merge_system_prompt = merge_system_prompt or _p.get(Prompt.GOSSIP_MERGE_SYSTEM_PROMPT)
        self.synthesizer_system_prompt = synthesizer_system_prompt or _p.get(Prompt.GOSSIP_SYNTHESIZER_SYSTEM_PROMPT)
