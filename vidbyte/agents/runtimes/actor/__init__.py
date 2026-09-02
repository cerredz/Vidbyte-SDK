"""Context Protocol Header

Description:
    Initializer for the Actor subpackage, exporting brokers and actors.
Purpose:
    Exposes the redesigned Point-to-Point and Broadcast Actor Runtimes, Prebuilt Actor
    Personas, and ActorMessage schema as public interfaces.
Architecture:
    Package initializer.
Relations:
    Located in vidbyte/agents/runtimes/actor/__init__.py. Consumed by base runtimes.
Similar Files:
    - vidbyte/agents/runtimes/__init__.py: Runtimes subpackage.
"""

from __future__ import annotations
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.agents.runtimes.actor.inbox import ActorInbox
from vidbyte.agents.runtimes.actor.actor import AgentActor, PrebuiltActorFactory
from vidbyte.agents.runtimes.actor.broker import (
    BaseActorRuntime,
    PointToPointActorRuntime,
    BroadcastActorRuntime,
)

__all__ = [
    "ActorMessage",
    "ActorInbox",
    "AgentActor",
    "PrebuiltActorFactory",
    "BaseActorRuntime",
    "PointToPointActorRuntime",
    "BroadcastActorRuntime",
]
