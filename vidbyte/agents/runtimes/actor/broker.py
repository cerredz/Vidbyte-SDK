"""Context Protocol Header

Description:
    Implements Point-to-Point and Broadcast multi-agent brokers.
Purpose:
    Orchestrates actor loops, concurrent task lifecycles, structured message passing,
    and fail-fast termination gates in multi-agent executions.
Architecture:
    - BaseActorRuntime: Abstract parent broker handling initialization, spawning,
      and completion futures.
    - PointToPointActorRuntime: Standard address-based routing.
    - BroadcastActorRuntime: swarm-style replication routing.
Relations:
    Located in vidbyte/agents/runtimes/actor/broker.py. Consumed by BaseAgent.
Similar Files:
    - vidbyte/agents/runtimes/actor/actor.py: Reactive AgentActor classes.
"""

from __future__ import annotations
import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping, Sequence

from vidbyte.agents.runtimes.actor.actor import AgentActor, PrebuiltActorFactory
from vidbyte.agents.runtimes.actor.message import ActorMessage
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


class BaseActorRuntime(ABC):
    """Abstract base broker orchestrating actor lifecycles, execution, and loops."""

    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
        tracer: TracerBase | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        run_id: str | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        dynamic_actors: bool = False,
        max_loop: int = 20,
        termination_mode: str = "coordinator",
        worker_model: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self.tracer = tracer
        self.middleware = middleware
        self.run_id = run_id
        self.algorithm = algorithm
        
        # Swappable actor properties
        self.dynamic_actors = dynamic_actors
        self.max_loop = max_loop
        self.termination_mode = termination_mode
        self.worker_model = worker_model

        # Registry and state tracking
        self._actors: dict[str, AgentActor] = {}
        self._tasks: list[asyncio.Task] = []
        self._message_count = 0
        self._completion_future: asyncio.Future[str] | None = None

        # Core runner references populated at execution time
        self._runner: object | None = None
        self._invoke_runner: Callable[..., Any] | None = None
        self._runner_output_text: Callable[[object], str] | None = None
        self._runner_output_metadata: Callable[[object], Mapping[str, Any]] | None = None
        self._provider: str | None = None
        self._options: Mapping[str, Any] | None = None

    async def spawn(self, actor_id: str, system_prompt: str, model_name: str | None = None) -> AgentActor:
        """Instantiates an AgentActor, registers it, and schedules its loop."""
        actor = AgentActor(
            actor_id=actor_id,
            system_prompt=system_prompt,
            broker=self,
            model_name=model_name,
        )
        self._actors[actor_id] = actor
        task = asyncio.create_task(actor.start())
        self._tasks.append(task)
        return actor

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
    ) -> BaseAgentContext:
        """Formulates context metadata for concurrent actor pipelines."""
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

    async def invoke_actor_completion(self, actor: AgentActor, prompt: str) -> str:
        """Executes LLM completions on behalf of registered actors."""
        actor_context = self.build_context(
            prompt,
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        target_model = actor.model_name or self.worker_model
        call_options = dict(self._options or {})
        if target_model:
            call_options["model_name"] = target_model

        # Invoke runner callback passed at arun
        assert self._invoke_runner is not None
        raw_result = await self._invoke_runner(
            self._runner,
            prompt,
            context=actor_context,
            **call_options
        )
        assert self._runner_output_text is not None
        return self._runner_output_text(raw_result)

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: Any = None,
    ) -> StrategyResult:
        """Launches prebuilt/dynamic networks and runs asynchronous message-passing loops."""
        self._runner = runner
        self._invoke_runner = invoke_runner
        self._runner_output_text = runner_output_text
        self._runner_output_metadata = runner_output_metadata
        self._provider = provider
        self._options = options or {}
        self._message_count = 0
        self._completion_future = asyncio.get_running_loop().create_future()

        # Spawn prebuilt actors automatically
        for role in ["planner", "coder", "reviewer", "generator", "critic", "reasoner"]:
            try:
                prompt = PrebuiltActorFactory.load_persona(role)
                await self.spawn(role, prompt, self.worker_model)
            except Exception:
                pass  # Ignore catalog errors in non-test fallback environments

        # Attach dynamic actor tools if configured
        if self.dynamic_actors:
            from vidbyte.tools.dynamic_actor import DynamicActorTool
            self.tools = self.tools.add(DynamicActorTool(self))

        # Root orchestrator actor
        root_actor = await self.spawn(self.agent_name, self.system_prompt, model_name=None)

        # Boot message
        await self.send("system", self.agent_name, message)

        # Execution tracking and termination safeguards
        try:
            if self.termination_mode == "quiescence":
                # Option B: Quiescence monitor
                while not self._completion_future.done():
                    await asyncio.sleep(0.01)
                    if self._check_quiescence():
                        self._completion_future.set_result("Quiescence reached. Swarm execution completed.")
                        break
            else:
                # Option A: Await root coordinator termination
                await self._completion_future

            output_text = self._completion_future.result()
        finally:
            # Clean up concurrent tasks
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
            self._actors.clear()

        return StrategyResult(
            output=output_text,
            strategy_name=f"actor_model_{self.__class__.__name__}",
            calls=(),
            metadata={"message_count": self._message_count, "active_actors": len(self._actors)},
        )

    def _check_quiescence(self) -> bool:
        """Returns True if all mailboxes are empty and no worker tasks are active."""
        if self._message_count == 0:
            return False
        return all(actor.inbox.empty() for actor in self._actors.values())

    @abstractmethod
    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        """Routes message payload to targets or systems."""


class PointToPointActorRuntime(BaseActorRuntime):
    """Routes messages strictly to a single targeted recipient address inbox."""

    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        self._message_count += 1

        # Max loop safety gate
        if self._message_count >= self.max_loop:
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(f"Execution terminated. Max loops ({self.max_loop}) reached.")
            return

        if recipient == "system" or recipient == "orchestrator":
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(content)
            return

        target = self._actors.get(recipient)
        if target:
            msg = ActorMessage(
                message_id=str(uuid.uuid4()),
                sender=sender,
                recipient=recipient,
                content=content,
                parent_task_id=parent_task_id,
            )
            await target.inbox.put(msg)


class BroadcastActorRuntime(BaseActorRuntime):
    """Replicates and broadcasts incoming messages to all registered actor mailboxes."""

    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        self._message_count += 1

        # Max loop safety gate
        if self._message_count >= self.max_loop:
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(f"Execution terminated. Max loops ({self.max_loop}) reached.")
            return

        if recipient == "system" or recipient == "orchestrator":
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(content)
            return

        # Broadcast to all registered actors (excluding the sender)
        msg_id = str(uuid.uuid4())
        for actor_id, actor in self._actors.items():
            if actor_id != sender:
                msg = ActorMessage(
                    message_id=msg_id,
                    sender=sender,
                    recipient=actor_id,
                    content=content,
                    parent_task_id=parent_task_id,
                )
                await actor.inbox.put(msg)
