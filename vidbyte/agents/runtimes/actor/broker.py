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
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.runtimes.actor.actor import AgentActor, PrebuiltActorFactory
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.agents.types import AgentMessage
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, StrategyContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.tracing import TracerBase
from vidbyte.middleware import AgentMiddleware
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext


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
        include_actors: Sequence[type] | None = None,
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
        self.include_actors = include_actors

        # Registry and state tracking
        self._actors: dict[str, AgentActor] = {}
        self._tasks: list[asyncio.Task] = []
        self._message_count = 0
        self._completion_future: asyncio.Future[str] | None = None

        # RunnerHandle and options populated at execution time
        self._handle: RunnerHandle | None = None
        self._options: Mapping[str, Any] | None = None

    async def spawn(self, actor_id: str, system_prompt: str, model_name: str | None = None) -> AgentActor:
        """Instantiates an AgentActor, registers it, and schedules its loop."""
        actor = AgentActor(
            actor_id=actor_id,
            system_prompt=system_prompt,
            broker=self,
            model_name=model_name,
        )
        return await self.spawn_instance(actor)

    async def spawn_instance(self, actor: AgentActor) -> AgentActor:
        """Registers an instantiated AgentActor and schedules its reactive loop."""
        span = self._start_semantic_span("runtime.actor.spawn", actor_id=actor.actor_id, actor_type=actor.__class__.__name__)
        self._actors[actor.actor_id] = actor
        task = asyncio.create_task(actor.start())
        self._tasks.append(task)
        self._end_semantic_span(span, output=actor.actor_id)
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
        span = self._start_semantic_span("runtime.actor.llm", actor_id=actor.actor_id, prompt=prompt)
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

        assert self._handle is not None
        try:
            raw_result = await self._handle.invoke(prompt, context=actor_context, **call_options)
            output = self._handle.extract_text(raw_result)
            self._end_semantic_span(span, output=output)
            return output
        except BaseException as exc:
            self._end_semantic_span(span, error=exc)
            raise

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: Any = None) -> StrategyResult:
        """Launches prebuilt/dynamic networks and runs asynchronous message-passing loops."""
        span = self._start_semantic_span("runtime.actor.run", parent=trace_context, agent_name=self.agent_name, termination_mode=self.termination_mode)
        self._handle = handle
        self._options = options or {}
        self._message_count = 0
        self._completion_future = asyncio.get_running_loop().create_future()

        try:
            # Spawn prebuilt actors based on include_actors list
            actor_classes = self.include_actors
            if actor_classes is None:
                from vidbyte.agents.runtimes.actor.actor import (
                    CoderActor,
                    CriticActor,
                    GeneratorActor,
                    PlannerActor,
                    ReasonerActor,
                    ReviewerActor,
                )
                actor_classes = [
                    PlannerActor,
                    CoderActor,
                    ReviewerActor,
                    GeneratorActor,
                    CriticActor,
                    ReasonerActor,
                ]

            for actor_cls in actor_classes:
                try:
                    actor_inst = actor_cls(broker=self, model_name=self.worker_model)
                    await self.spawn_instance(actor_inst)
                except Exception:
                    pass  # Ignore catalog errors in non-test fallback environments

            # Attach dynamic actor tools if configured
            if self.dynamic_actors:
                from vidbyte.tools.dynamic_actor import DynamicActorTool
                self.tools = self.tools.add(DynamicActorTool(self))

            # Root orchestrator actor
            await self.spawn(self.agent_name, self.system_prompt, model_name=None)

            # Boot message
            await self.send("system", self.agent_name, message)

            # Execution tracking and termination safeguards
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
            self._end_semantic_span(span, output=output_text)
        except BaseException as exc:
            self._end_semantic_span(span, error=exc)
            raise
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

    def _start_semantic_span(self, name: str, parent: Any = None, **attributes: Any) -> Any:
        # Opens actor runtime spans only for semantic controllers.
        if not _is_semantic_tracer(self.tracer):
            return None
        return self.tracer.start_span(name, parent=parent, **attributes)

    def _end_semantic_span(self, span: Any, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes actor runtime spans only when one was opened.
        if span is not None and _is_semantic_tracer(self.tracer):
            self.tracer.end_span(span, output=output, error=error)

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
        span = self._start_semantic_span("runtime.actor.message", sender=sender, recipient=recipient, content=content)

        # Max loop safety gate
        if self._message_count >= self.max_loop:
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(f"Execution terminated. Max loops ({self.max_loop}) reached.")
            self._end_semantic_span(span, output="max_loop")
            return

        if recipient == "system" or recipient == "orchestrator":
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(content)
            self._end_semantic_span(span, output="completion")
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
        self._end_semantic_span(span, output="queued" if target else "missing_recipient")


class BroadcastActorRuntime(BaseActorRuntime):
    """Replicates and broadcasts incoming messages to all registered actor mailboxes."""

    async def send(self, sender: str, recipient: str, content: str, parent_task_id: str | None = None) -> None:
        self._message_count += 1
        span = self._start_semantic_span("runtime.actor.message", sender=sender, recipient=recipient, content=content)

        # Max loop safety gate
        if self._message_count >= self.max_loop:
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(f"Execution terminated. Max loops ({self.max_loop}) reached.")
            self._end_semantic_span(span, output="max_loop")
            return

        if recipient == "system" or recipient == "orchestrator":
            if self._completion_future and not self._completion_future.done():
                self._completion_future.set_result(content)
            self._end_semantic_span(span, output="completion")
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
        self._end_semantic_span(span, output="broadcast")


def _is_semantic_tracer(tracer: object) -> bool:
    # Detects TraceController-like tracers without importing vidbyte.trace during runtime initialization.
    return all(hasattr(tracer, attr) for attr in ("inner", "profile", "translator"))
