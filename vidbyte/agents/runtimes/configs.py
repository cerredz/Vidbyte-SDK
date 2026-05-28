"""Context Protocol Header

Description:
    Defines configuration classes for Linear, MCTS Search, and Actor runtimes.
Purpose:
    Allows developers to cleanly configure runtime settings inside a single
    structured parameter, avoiding main agent constructor clutter.
Architecture:
    - LinearRuntime: Configuration object for linear runs.
    - MctsSearchRuntime: Configuration object for Monte Carlo Tree Search.
    - ActorRuntime: Configuration object for asynchronous multi-agent swarms.
Relations:
    Located in vidbyte/agents/runtimes/configs.py. Imported by BaseAgent.
Similar Files:
    - vidbyte/lib/dataclasses/agents.py: Domain configs.
"""

from __future__ import annotations
from typing import Any, Sequence, TYPE_CHECKING
from vidbyte.lib.enums import AgentRuntimeType

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
        self.runtime_type = AgentRuntimeType(topology)
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model
        self.include_actors = include_actors
