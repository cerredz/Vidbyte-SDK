"""Context Protocol Header

Description:
    Implements the Gossip/Epidemic Knowledge Propagation non-linear agent execution runtime.
Purpose:
    Initializes N agents with partial knowledge (each assigned a distinct analytical angle),
    runs random pairwise knowledge-merge rounds until convergence, then synthesizes a final
    answer — no central coordinator.
Architecture:
    - GossipAgentRuntime: Orchestrates parallel initialization, gossip rounds, and synthesis.
Relations:
    Located in vidbyte/agents/runtimes/gossip.py. Registered in RuntimeRegistry.
    Instantiated by BaseAgent._runtime() when runtime_type is GOSSIP.
Similar Files:
    - vidbyte/agents/runtimes/beam_search.py: Beam Search non-linear runtime.
    - vidbyte/agents/runtimes/market_auction.py: Market Auction non-linear runtime.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, StrategyContext
from vidbyte.lib.dataclasses.strategies import StrategyResult
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.enums import ModelModality
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.middleware import AgentMiddleware


class GossipAgentRuntime:
    """Initializes N agents with partial knowledge, runs gossip rounds, then synthesizes."""

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
        num_agents: int = 4,
        gossip_rounds: int = 3,
        max_knowledge_chars: int = 6000,
        angles: tuple[str, ...] = (),
        agent_system_prompt: str = "",
        merge_system_prompt: str = "",
        synthesizer_system_prompt: str = "",
        **kwargs: Any,
    ) -> None:
        # Store agent config and gossip parameters; middleware is intentionally ignored.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self._tracer: TracerBase = tracer or NullTracer()
        self.run_id = run_id
        self.num_agents = num_agents
        self.gossip_rounds = gossip_rounds
        self.max_knowledge_chars = max_knowledge_chars
        self.angles = angles
        self.agent_system_prompt = agent_system_prompt
        self.merge_system_prompt = merge_system_prompt
        self.synthesizer_system_prompt = synthesizer_system_prompt

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
        # Build the initial context window for the gossip agent trials.
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
        # Initialize agents, run gossip rounds, then synthesize converged knowledge.
        started_at = time.monotonic()
        knowledge_stores = await self._initialize_agents(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )
        initial_stores = list(knowledge_stores)
        knowledge_stores = await self._run_gossip_rounds(
            knowledge_stores,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        final_output = await self._synthesize(
            message,
            knowledge_stores,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        return self._with_metadata(final_output, initial_stores=initial_stores, final_stores=knowledge_stores, started_at=started_at)

    async def _initialize_agents(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None,
        options: Mapping[str, Any] | None,
        trace_context: Any,
    ) -> list[str]:
        # Run N parallel agent trials, each focused on a distinct analytical angle.
        from vidbyte.agents.runtime import AgentRuntime
        tasks = []
        for i in range(self.num_agents):
            angle = self.angles[i] if i < len(self.angles) else f"explore angle {i + 1}"
            angle_task = f"{message}\n\nFocus specifically on: {angle}"
            agent_context = replace(
                context,
                system_prompt=self.agent_system_prompt,
                metadata={**dict(context.metadata), "gossip_agent_index": i},
            )
            inner = AgentRuntime(
                agent_name=self.agent_name,
                system_prompt=self.agent_system_prompt,
                tools=self.tools,
                permission_policy=self.permission_policy,
                config=self.config,
                tracer=self._tracer,
                run_id=self.run_id,
            )
            tasks.append(
                inner._arun_once(
                    angle_task,
                    runner=runner,
                    context=agent_context,
                    provider=provider,
                    invoke_runner=invoke_runner,
                    runner_output_text=runner_output_text,
                    runner_output_metadata=runner_output_metadata,
                    metadata={**(metadata or {}), "gossip_agent_index": i},
                    options=dict(options or {}),
                    trace_context=trace_context,
                )
            )
        results: list[StrategyResult] = list(await asyncio.gather(*tasks))
        return [
            (result.output or "(no output)")[:self.max_knowledge_chars]
            for result in results
        ]

    async def _run_gossip_rounds(
        self,
        knowledge_stores: list[str],
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> list[str]:
        # Run gossip_rounds rounds of pairwise knowledge exchange.
        stores = list(knowledge_stores)
        for round_index in range(self.gossip_rounds):
            pairs = self._gossip_pairs(len(stores), round_index)
            merge_tasks = [
                self._merge_pair(
                    stores[i], stores[j],
                    runner=runner, context=context, provider=provider,
                    invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                )
                for i, j in pairs
            ]
            merged = list(await asyncio.gather(*merge_tasks))
            for (i, j), m in zip(pairs, merged):
                stores[i] = m
                stores[j] = m
        return stores

    async def _merge_pair(
        self,
        knowledge_a: str,
        knowledge_b: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> str:
        # Merge two knowledge stores via a lightweight model call.
        merge_prompt = (
            f"Knowledge report A:\n{knowledge_a}\n\n"
            f"Knowledge report B:\n{knowledge_b}\n\n"
            "Merge these into one comprehensive, non-redundant report:"
        )
        try:
            raw = await invoke_runner(runner, merge_prompt, system=self.merge_system_prompt)
            merged = runner_output_text(raw).strip()
            return (merged or knowledge_a)[:self.max_knowledge_chars]
        except Exception:
            return knowledge_a

    async def _synthesize(
        self,
        message: str,
        knowledge_stores: list[str],
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> str:
        # Combine all converged knowledge stores into a single authoritative answer.
        knowledge_text = "\n\n---\n\n".join(
            f"Knowledge {i + 1}:\n{store}" for i, store in enumerate(knowledge_stores)
        )
        synthesis_prompt = f"Original task:\n{message}\n\nConverged knowledge:\n{knowledge_text}\n\nFinal answer:"
        try:
            raw = await invoke_runner(runner, synthesis_prompt, system=self.synthesizer_system_prompt)
            return runner_output_text(raw)
        except Exception:
            return knowledge_stores[-1] if knowledge_stores else ""

    def _with_metadata(
        self,
        output: str,
        *,
        initial_stores: list[str],
        final_stores: list[str],
        started_at: float,
    ) -> StrategyResult:
        # Build the final StrategyResult with Gossip trace metadata.
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata={
                "stop_reason": "is_done",
                "gossip": {
                    "num_agents": self.num_agents,
                    "gossip_rounds": self.gossip_rounds,
                    "elapsed_seconds": max(0.0, time.monotonic() - started_at),
                    "initial_knowledge_chars": tuple(len(s) for s in initial_stores),
                    "final_knowledge_chars": tuple(len(s) for s in final_stores),
                },
            },
        )

    @staticmethod
    def _gossip_pairs(n: int, round_index: int) -> list[tuple[int, int]]:
        # Generate agent pairs for a gossip round using a rotation scheme.
        indices = list(range(n))
        shift = round_index % max(1, n - 1)
        rotated = indices[:1] + indices[1:][shift:] + indices[1:][:shift]
        return [(rotated[k], rotated[n - 1 - k]) for k in range(n // 2)]


__all__ = ["GossipAgentRuntime"]
