"""Context Protocol Header

Description:
    Central registry mapping AgentRuntimeType enum values to their runtime classes.
Purpose:
    Eliminates one-off runtime_classes dicts scattered across the SDK and centralizes
    all runtime-to-class resolution with validation helpers.
Architecture:
    - RuntimeRegistry: Static registry with lazy-import resolution to avoid circular deps.
Key Functions:
    - resolve: Returns the runtime class for a given AgentRuntimeType.
    - validate: Raises ConfigurationError if runtime_type is unrecognized.
    - supported_runtimes: Returns a sorted list of all registered runtime type strings.
Relations:
    Used by vidbyte/agents/base.py._runtime(). Add new runtimes here, not in agent code.
Similar Files:
    - vidbyte/lib/registries/models.py: ProviderModelRegistry for provider-model mappings.
    - vidbyte/lib/registries/actors.py: ActorRegistry for prebuilt actor classes.
"""

from __future__ import annotations

from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


class RuntimeRegistry:
    """Central registry for mapping AgentRuntimeType values to their runtime classes."""

    @classmethod
    def resolve(cls, runtime_type: AgentRuntimeType) -> type:
        # Returns the runtime class for the given AgentRuntimeType; lazy-imports avoid circular deps.
        from vidbyte.agents.runtimes import (
            LinearAgentRuntime,
            SearchTreeRuntimeComponent,
            PointToPointActorRuntime,
            BroadcastActorRuntime,
            BeamSearchAgentRuntime,
            DAGDataflowAgentRuntime,
            MarketAuctionAgentRuntime,
            GossipAgentRuntime,
        )
        _registry: dict[AgentRuntimeType, type] = {
            AgentRuntimeType.LINEAR: LinearAgentRuntime,
            AgentRuntimeType.MCTS_SEARCH: SearchTreeRuntimeComponent,
            AgentRuntimeType.ACTOR_MODEL: PointToPointActorRuntime,
            AgentRuntimeType.ACTOR_MODEL_P2P: PointToPointActorRuntime,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST: BroadcastActorRuntime,
            AgentRuntimeType.BEAM_SEARCH: BeamSearchAgentRuntime,
            AgentRuntimeType.DAG_DATAFLOW: DAGDataflowAgentRuntime,
            AgentRuntimeType.MARKET_AUCTION: MarketAuctionAgentRuntime,
            AgentRuntimeType.GOSSIP: GossipAgentRuntime,
        }
        runtime_cls = _registry.get(runtime_type)
        if runtime_cls is None:
            raise ConfigurationError(
                f"Unknown runtime type '{runtime_type.value}'. "
                f"Supported: {cls.supported_runtimes()}"
            )
        return runtime_cls

    @classmethod
    def validate(cls, runtime_type: AgentRuntimeType) -> None:
        # Raises ConfigurationError if runtime_type is not a recognized AgentRuntimeType.
        cls.resolve(runtime_type)

    @classmethod
    def supported_runtimes(cls) -> list[str]:
        # Returns a sorted list of all supported AgentRuntimeType string values.
        return sorted(rt.value for rt in AgentRuntimeType)


__all__ = ["RuntimeRegistry"]
