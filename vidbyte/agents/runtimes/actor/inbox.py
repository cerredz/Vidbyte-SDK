"""Context Protocol Header

Description:
    Implements a thread-safe asynchronous message queue for individual agent actors.
Purpose:
    Provides decoupled communication in concurrent agent actor systems, serving
    as the primary polling/waiting state for active worker tasks.
Architecture:
    - ActorInbox: Wrapper around asyncio.Queue.
Relations:
    Located in vidbyte/agents/runtimes/actor/inbox.py. Used by AgentActor.
Similar Files:
    - vidbyte/agents/runtimes/actor/message.py: Message schemas.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.message import ActorMessage

class ActorInbox:
    """Manages an incoming message queue for an asynchronous agent actor."""

    def __init__(self) -> None:
        # Create an internal asyncio Queue to queue incoming ActorMessage instances.
        self._queue: asyncio.Queue[ActorMessage] = asyncio.Queue()

    async def put(self, message: ActorMessage) -> None:
        # Enqueue an ActorMessage asynchronously.
        await self._queue.put(message)

    async def get(self) -> ActorMessage:
        # Dequeue the next ActorMessage asynchronously.
        return await self._queue.get()

    def empty(self) -> bool:
        # Returns True if the inbox is empty.
        return self._queue.empty()
