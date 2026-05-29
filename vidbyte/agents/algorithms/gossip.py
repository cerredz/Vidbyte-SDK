"""Context Protocol Header

Description:
    Executes the Gossip/Epidemic Knowledge Propagation algorithm for AgentRuntime.
Purpose:
    Keeps agent initialization, pairwise gossip round orchestration, and final
    synthesis out of the generic agent runtime loop.
Architecture:
    - GossipRuntimeAlgorithm: Initializes N agents with partial knowledge, runs
      random pairwise merge rounds, and synthesizes a final answer from converged
      knowledge stores.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes GossipAlgorithm config from
    vidbyte.context.algorithms.gossip.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.gossip import GossipAlgorithm
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class GossipRuntimeAlgorithm:
    """Runtime adapter for the Gossip/Epidemic Knowledge Propagation algorithm."""

    name = "gossip"

    def __init__(self, runtime: AgentRuntime, algorithm: GossipAlgorithm) -> None:
        """Store the runtime reference and gossip configuration."""
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        """Initialize agents, run gossip rounds, then synthesize converged knowledge."""
        started_at = self.runtime.middleware.clock()
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
            metadata=metadata,
            trace_context=trace_context,
        )
        final_output = await self._synthesize(
            message,
            knowledge_stores,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )
        return self._with_gossip_metadata(
            final_output,
            initial_stores=initial_stores,
            final_stores=knowledge_stores,
            started_at=started_at,
        )

    async def _initialize_agents(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[str]:
        """Run N parallel agent trials, each with a distinct analytical angle."""
        tasks = [
            self.runtime._arun_once(
                self.algorithm.build_angle_for_agent(i, message),
                runner=runner,
                context=self._build_agent_context(context, i),
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
                metadata=self._agent_metadata(metadata, agent_index=i),
                options=dict(options or {}),
                trace_context=trace_context,
            )
            for i in range(self.algorithm.num_agents)
        ]
        results: list[StrategyResult] = list(await asyncio.gather(*tasks))
        return [
            self.algorithm.truncate_knowledge(result.output or "(no output)")
            for result in results
        ]

    async def _run_gossip_rounds(self, knowledge_stores: list[str], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[str]:
        """Run gossip_rounds rounds of pairwise knowledge exchange."""
        stores = list(knowledge_stores)
        for round_index in range(self.algorithm.gossip_rounds):
            pairs = self._gossip_pairs(len(stores), round_index)
            merge_tasks = [
                self._merge_pair(
                    stores[i],
                    stores[j],
                    runner=runner,
                    context=context,
                    provider=provider,
                    invoke_runner=invoke_runner,
                    runner_output_text=runner_output_text,
                    metadata=self._round_metadata(metadata, round_index=round_index),
                    trace_context=trace_context,
                )
                for i, j in pairs
            ]
            merged_results = list(await asyncio.gather(*merge_tasks))
            for (i, j), merged in zip(pairs, merged_results):
                stores[i] = merged
                stores[j] = merged
        return stores

    async def _merge_pair(self, knowledge_a: str, knowledge_b: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> str:
        """Merge two knowledge stores into one via a lightweight model call."""
        merge_prompt = self.algorithm.render_merge_prompt(knowledge_a, knowledge_b)
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            merge_prompt,
            {"system": self.algorithm.merge_system_prompt_text()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=metadata or {},
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return knowledge_a
        merged = runner_output_text(raw_result).strip()
        return self.algorithm.truncate_knowledge(merged or knowledge_a)

    async def _synthesize(self, message: str, knowledge_stores: list[str], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> str:
        """Synthesize all converged knowledge stores into a final answer."""
        synthesis_prompt = self.algorithm.render_synthesis_prompt(message, knowledge_stores)
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            synthesis_prompt,
            {"system": self.algorithm.synthesizer_system_prompt_text()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._stage_metadata(metadata, stage="synthesizer"),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return raw_result.output
        return runner_output_text(raw_result)

    def _build_agent_context(self, context: BaseAgentContext, agent_index: int) -> BaseAgentContext:
        """Build a context with the gossip agent system prompt for a specific agent."""
        return replace(
            context,
            system_prompt=self.algorithm.agent_system_prompt_text(),
            metadata={**dict(context.metadata), "gossip_agent_index": agent_index},
        )

    def _with_gossip_metadata(self, output: str, *, initial_stores: list[str], final_stores: list[str], started_at: float) -> StrategyResult:
        """Build the final StrategyResult with Gossip trace metadata."""
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata={
                "stop_reason": "is_done",
                "gossip": {
                    "num_agents": self.algorithm.num_agents,
                    "gossip_rounds": self.algorithm.gossip_rounds,
                    "elapsed_seconds": max(0.0, self.runtime.middleware.clock() - started_at),
                    "initial_knowledge_chars": tuple(len(s) for s in initial_stores),
                    "final_knowledge_chars": tuple(len(s) for s in final_stores),
                },
            },
        )

    @staticmethod
    def _gossip_pairs(n: int, round_index: int) -> list[tuple[int, int]]:
        """Generate agent pairs for a gossip round using a rotation scheme."""
        indices = list(range(n))
        shift = round_index % max(1, n - 1)
        rotated = indices[:1] + indices[1:][shift:] + indices[1:][:shift]
        pairs = []
        for k in range(n // 2):
            pairs.append((rotated[k], rotated[n - 1 - k]))
        return pairs

    @staticmethod
    def _agent_metadata(metadata: Mapping[str, Any] | None, *, agent_index: int) -> dict[str, Any]:
        """Build metadata for a gossip agent initialization trial."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "gossip",
            "gossip_stage": "initialize",
            "gossip_agent_index": agent_index,
        }

    @staticmethod
    def _round_metadata(metadata: Mapping[str, Any] | None, *, round_index: int) -> dict[str, Any]:
        """Build metadata for a gossip merge call."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "gossip",
            "gossip_stage": "merge",
            "gossip_round_index": round_index,
        }

    @staticmethod
    def _stage_metadata(metadata: Mapping[str, Any] | None, *, stage: str) -> dict[str, Any]:
        """Build metadata for gossip non-agentic stage calls."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "gossip",
            "gossip_stage": stage,
        }


__all__ = [
    "GossipRuntimeAlgorithm",
]
