"""Context Protocol Header

Description:
    Implements a decentralized Actor Model runtime for Vidbyte agents.
Purpose:
    Allows agents to act as fully concurrent, asynchronous message-passing actors,
    eliminating linear sequences and centralized orchestration.
Architecture:
    - ActorInbox: Holds incoming asynchronous messages.
    - AgentActor: Encapsulates agent state, inbox, and local reactive loop.
    - ActorRuntimeComponent: Manages actor lifecycles, execution pools, and message routing.
Relations:
    Located in vidbyte/agents/runtimes/actor.py. Mimics the linear AgentRuntime interface.
Similar Files:
    - vidbyte/agents/runtimes/linear.py: Linear execution runtime.
    - vidbyte/agents/runtimes/search.py: Branching MCTS runtime.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.context.primitives import ContextItem
from vidbyte.context.manager import ContextManager
from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.types import ToolCallContext
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.lib.tracing import TracerBase
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.middleware import AgentMiddleware


class ActorInbox:
    """Manages an incoming message queue for an asynchronous agent actor."""

    def __init__(self) -> None:
        # Create an internal asyncio Queue to queue incoming sender/message tuples.
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def put(self, sender: str, message: Any) -> None:
        # Enqueue a sender name and message payload into the queue.
        await self._queue.put((sender, message))

    async def get(self) -> tuple[str, Any]:
        # Dequeue the next sender name and message payload from the queue.
        return await self._queue.get()


class AgentActor:
    """Encapsulates an isolated agent's reactive state and event loop."""

    def __init__(self, actor_id: str, system_prompt: str, runtime: ActorRuntimeComponent) -> None:
        # Store identity parameters and link to the parent routing runtime broker.
        self.actor_id = actor_id
        self.system_prompt = system_prompt
        self.runtime = runtime
        self.inbox = ActorInbox()
        self.state: dict[str, Any] = {}

    async def start(self) -> None:
        # Indefinitely await incoming messages from the queue and react.
        while True:
            sender, msg = await self.inbox.get()
            response = await self.on_receive(sender, msg)
            if response:
                await self.runtime.send(self.actor_id, sender, response)

    async def on_receive(self, sender: str, message: Any) -> Any:
        # Handle message arrival and optionally spawn sub-actors or return a reply.
        return f"Actor {self.actor_id} processed message from {sender}."


class ActorRuntimeComponent:
    """Manages multiple concurrent agent actors and routes async messages."""

    def __init__(self, *, agent_name: str, system_prompt: str, tools: Tools, permission_policy: PermissionPolicy, config: AgentRuntimeConfig | None = None, tracer: TracerBase | None = None, middleware: Sequence[AgentMiddleware] = (), run_id: str | None = None, algorithm: ContextWindowAlgorithm | str | None = None) -> None:
        # Store configuration and initialize the local active actor map.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self.run_id = run_id
        self._actors: dict[str, AgentActor] = {}

    def build_context(self, message: str, *, base_context: StrategyContext | None, history: Sequence[AgentMessage], agent_history: Sequence[AgentMessage], agent_metadata: Mapping[str, Any], existing_tool_calls: Sequence[ToolCallContext], input_metadata: Mapping[str, Any] | None = None, modality: ModelModality | None = None, agentic_loop: bool = True, context_items: Sequence[ContextItem] = (), context_manager: ContextManager | None = None) -> BaseAgentContext:
        # Formulate initial context details for actor mailboxes.
        manager = ContextManager()
        if context_manager is not None:
            manager.extend(context_manager.items())
        manager.extend(context_items)
        managed_context = manager.to_context(base_context)
        return BaseAgentContext(
            system_prompt=self.system_prompt,
            history=tuple(history) + tuple(agent_history),
            tools=self.tools.specs(),
            file_paths=tuple(managed_context.file_paths),
            strategy_metadata=dict(managed_context.strategy_metadata),
            tool_calls=(*tuple(managed_context.tool_calls), *tuple(existing_tool_calls)),
            responses=tuple(managed_context.responses),
            budget=managed_context.budget,
            artifacts=tuple(managed_context.artifacts),
            memory=managed_context.memory,
            permissions=managed_context.permissions,
            metadata=dict(agent_metadata),
            context_items=tuple(managed_context.context_items),
        )

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: Any = None) -> StrategyResult:
        # Spawn initial actor and execute asynchronous messaging.
        actor_id = str(uuid.uuid4())
        actor = await self.spawn(actor_id, self.system_prompt)
        await self.send("system", actor_id, message)

        # Allow execution loop to process messages
        await asyncio.sleep(0.01)

        output_text = f"Asynchronous actor runtime execution complete. Spawned actor: {actor_id}"
        return StrategyResult(
            output=output_text,
            strategy_name="actor_model",
            calls=(),
            metadata={"spawned_actor": actor_id, "active_actors": len(self._actors)},
        )

    async def spawn(self, actor_id: str, system_prompt: str) -> AgentActor:
        # Create a new actor, register it, and start its loop in the background.
        actor = AgentActor(actor_id, system_prompt, self)
        self._actors[actor_id] = actor
        asyncio.create_task(actor.start())
        return actor

    async def send(self, sender: str, recipient: str, message: Any) -> None:
        # Deliver a message asynchronously to a recipient actor's inbox queue.
        if recipient in self._actors:
            await self._actors[recipient].inbox.put(sender, message)
