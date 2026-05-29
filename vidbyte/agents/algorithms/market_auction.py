"""Context Protocol Header

Description:
    Executes the Market Auction context-window algorithm for AgentRuntime.
Purpose:
    Keeps role generation, bid collection, winner selection, and execution
    orchestration out of the generic agent runtime loop.
Architecture:
    - MarketAuctionRuntimeAlgorithm: Generates specialist roles, collects parallel
      bids, selects the highest-confidence winner, and runs the winning agent.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes MarketAuctionAlgorithm config
    from vidbyte.context.algorithms.market_auction.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.market_auction import MarketAuctionAlgorithm
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class MarketAuctionRuntimeAlgorithm:
    """Runtime adapter for the Market Auction context-window algorithm."""

    name = "market_auction"

    def __init__(self, runtime: AgentRuntime, algorithm: MarketAuctionAlgorithm) -> None:
        """Store the runtime reference and market auction configuration."""
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        """Run the auction: generate roles, collect bids, select winner, execute."""
        started_at = self.runtime.middleware.clock()
        roles = await self._resolve_roles(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )
        bids = await self._collect_bids(
            message,
            roles,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )
        winning_role, winning_bid = self.algorithm.select_winner(bids, roles)
        result = await self._execute_winner(
            message,
            winning_role,
            winning_bid,
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
        return self._with_auction_metadata(result, roles=roles, bids=bids, winning_role=winning_role, winning_bid=winning_bid, started_at=started_at)

    async def _resolve_roles(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[str]:
        """Use predefined roles or generate them dynamically from the task."""
        if self.algorithm.roles is not None:
            return list(self.algorithm.roles)
        return await self._generate_roles(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )

    async def _generate_roles(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[str]:
        """Call the auctioneer to generate specialist role names for the task."""
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            message,
            {"system": self.algorithm.auctioneer_system_prompt_text()},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._stage_metadata(metadata, stage="auctioneer"),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return [f"Expert {i + 1}" for i in range(self.algorithm.num_agents)]
        roles_text = runner_output_text(raw_result)
        roles = self.algorithm.parse_roles(roles_text)
        if not roles:
            return [f"Expert {i + 1}" for i in range(self.algorithm.num_agents)]
        while len(roles) < self.algorithm.num_agents:
            roles.append(f"General Expert {len(roles) + 1}")
        return roles

    async def _collect_bids(self, message: str, roles: list[str], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[dict[str, Any]]:
        """Collect bids from all roles in parallel."""
        tasks = [
            self._run_bid(
                message,
                role,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                metadata=metadata,
                trace_context=trace_context,
            )
            for role in roles
        ]
        return list(await asyncio.gather(*tasks))

    async def _run_bid(self, message: str, role: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> dict[str, Any]:
        """Run one bidder call for a given role and return the parsed bid."""
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            message,
            {"system": self.algorithm.bidder_system_prompt_text(role)},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=self.runtime.middleware.clock(),
            metadata=self._stage_metadata(metadata, stage="bidder"),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return {"can_handle": False, "confidence": 0, "approach": ""}
        bid = self.algorithm.parse_bid(runner_output_text(raw_result))
        approach = self.algorithm.truncate_approach(str(bid.get("approach", "")))
        return {**bid, "approach": approach}

    async def _execute_winner(self, message: str, role: str, bid: dict[str, Any], *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> StrategyResult:
        """Run the winning role as a full agent trial with the executor system prompt."""
        executor_context = self._build_executor_context(context, role, bid)
        return await self.runtime._arun_once(
            message,
            runner=runner,
            context=executor_context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata=self._execution_metadata(metadata, role=role),
            options=dict(options or {}),
            trace_context=trace_context,
        )

    def _build_executor_context(self, context: BaseAgentContext, role: str, bid: dict[str, Any]) -> BaseAgentContext:
        """Inject the winning role's executor system prompt into the agent context."""
        approach = str(bid.get("approach", "Best effort.")) or "Best effort."
        executor_system = self.algorithm.executor_system_prompt_text(role=role, approach=approach)
        return replace(
            context,
            system_prompt=executor_system,
            metadata={**dict(context.metadata), "market_auction_role": role},
        )

    def _with_auction_metadata(self, result: StrategyResult, *, roles: list[str], bids: list[dict[str, Any]], winning_role: str, winning_bid: dict[str, Any], started_at: float) -> StrategyResult:
        """Attach Market Auction trace metadata to the execution result."""
        metadata = dict(result.metadata)
        metadata["market_auction"] = {
            "role_count": len(roles),
            "winning_role": winning_role,
            "winning_confidence": int(winning_bid.get("confidence", 0)),
            "fallback_used": bool(winning_bid.get("_fallback", False)),
            "elapsed_seconds": max(0.0, self.runtime.middleware.clock() - started_at),
            "bids": tuple(
                {
                    "role": role,
                    "can_handle": bool(bid.get("can_handle", False)),
                    "confidence": int(bid.get("confidence", 0)),
                }
                for role, bid in zip(roles, bids)
            ),
        }
        return StrategyResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
        )

    @staticmethod
    def _stage_metadata(metadata: Mapping[str, Any] | None, *, stage: str) -> dict[str, Any]:
        """Build metadata for a market auction stage call."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "market_auction",
            "auction_stage": stage,
        }

    @staticmethod
    def _execution_metadata(metadata: Mapping[str, Any] | None, *, role: str) -> dict[str, Any]:
        """Build metadata for the winner's execution trial."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "market_auction",
            "auction_stage": "execution",
            "auction_winning_role": role,
        }


__all__ = [
    "MarketAuctionRuntimeAlgorithm",
]
