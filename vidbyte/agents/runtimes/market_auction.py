"""Context Protocol Header

Description:
    Implements the Market Auction non-linear agent execution runtime.
Purpose:
    The runtime generates specialist roles, collects parallel bids (confidence + approach),
    selects the highest-confidence winner, and executes the task under the winning role's
    system prompt — task assignment is dynamic, not fixed.
Architecture:
    - MarketAuctionAgentRuntime: Orchestrates role generation, bidding, winner selection, execution.
Relations:
    Located in vidbyte/agents/runtimes/market_auction.py. Registered in RuntimeRegistry.
    Instantiated by BaseAgent._runtime() when runtime_type is MARKET_AUCTION.
Similar Files:
    - vidbyte/agents/runtimes/beam_search.py: Beam Search non-linear runtime.
    - vidbyte/agents/runtimes/gossip.py: Gossip non-linear runtime.
"""

from __future__ import annotations

import asyncio
import json
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


class MarketAuctionAgentRuntime:
    """Generates specialist roles, collects bids, selects winner, and executes under the winning role."""

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
        num_agents: int = 3,
        roles: tuple[str, ...] | None = None,
        max_approach_chars: int = 500,
        auctioneer_system_prompt: str = "",
        bidder_system_prompt_template: str = "",
        executor_system_prompt_template: str = "",
        **kwargs: Any,
    ) -> None:
        # Store agent config and market auction parameters; middleware is intentionally ignored.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self._tracer: TracerBase = tracer or NullTracer()
        self.run_id = run_id
        self.num_agents = num_agents
        self.roles = roles
        self.max_approach_chars = max_approach_chars
        self.auctioneer_system_prompt = auctioneer_system_prompt
        self.bidder_system_prompt_template = bidder_system_prompt_template
        self.executor_system_prompt_template = executor_system_prompt_template

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
        # Build the initial context window for the auction process.
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
        # Run auction: generate roles, collect bids, select winner, execute.
        started_at = time.monotonic()
        roles = await self._resolve_roles(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        bids = await self._collect_bids(
            message,
            roles,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )
        winning_role, winning_bid = self._select_winner(bids, roles)
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
        return self._with_metadata(result, roles=roles, bids=bids, winning_role=winning_role, winning_bid=winning_bid, started_at=started_at)

    async def _resolve_roles(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> list[str]:
        # Use predefined roles or generate them dynamically from the task.
        if self.roles is not None:
            return list(self.roles)
        return await self._generate_roles(
            message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
        )

    async def _generate_roles(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> list[str]:
        # Call the auctioneer to produce specialist role names for the task.
        try:
            raw = await invoke_runner(runner, message, system=self.auctioneer_system_prompt)
            roles_text = runner_output_text(raw)
            roles = self._parse_roles(roles_text)
        except Exception:
            roles = []
        if not roles:
            roles = [f"Expert {i + 1}" for i in range(self.num_agents)]
        while len(roles) < self.num_agents:
            roles.append(f"General Expert {len(roles) + 1}")
        return roles

    async def _collect_bids(
        self,
        message: str,
        roles: list[str],
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> list[dict[str, Any]]:
        # Collect bids from all roles in parallel.
        tasks = [
            self._run_bid(message, role, runner=runner, context=context, provider=provider,
                          invoke_runner=invoke_runner, runner_output_text=runner_output_text)
            for role in roles
        ]
        return list(await asyncio.gather(*tasks))

    async def _run_bid(
        self,
        message: str,
        role: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> dict[str, Any]:
        # Call the LLM as a specific role bidder and parse the structured bid response.
        bidder_system = self.bidder_system_prompt_template.format(role=role)
        try:
            raw = await invoke_runner(runner, message, system=bidder_system)
            bid = self._parse_bid(runner_output_text(raw))
        except Exception:
            bid = {"can_handle": False, "confidence": 0, "approach": ""}
        approach = str(bid.get("approach", ""))[:self.max_approach_chars]
        return {**bid, "approach": approach}

    async def _execute_winner(
        self,
        message: str,
        role: str,
        bid: dict[str, Any],
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
    ) -> StrategyResult:
        # Run the winning role as a full agent trial with the executor system prompt.
        from vidbyte.agents.runtime import AgentRuntime
        approach = str(bid.get("approach", "Best effort.")) or "Best effort."
        executor_system = self.executor_system_prompt_template.format(role=role, approach=approach)
        executor_context = replace(
            context,
            system_prompt=executor_system,
            metadata={**dict(context.metadata), "market_auction_role": role},
        )
        inner = AgentRuntime(
            agent_name=self.agent_name,
            system_prompt=executor_system,
            tools=self.tools,
            permission_policy=self.permission_policy,
            config=self.config,
            tracer=self._tracer,
            run_id=self.run_id,
        )
        return await inner._arun_once(
            message,
            runner=runner,
            context=executor_context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            metadata={**(metadata or {}), "market_auction_role": role},
            options=dict(options or {}),
            trace_context=trace_context,
        )

    def _select_winner(self, bids: list[dict[str, Any]], roles: list[str]) -> tuple[str, dict[str, Any]]:
        # Select the highest-confidence bidder; fall back to the first role if all bids are zero.
        if not bids:
            return roles[0] if roles else "Expert 1", {"can_handle": True, "confidence": 0, "approach": "", "_fallback": True}
        best_index = max(range(len(bids)), key=lambda i: int(bids[i].get("confidence", 0)))
        return roles[best_index], bids[best_index]

    def _with_metadata(
        self,
        result: StrategyResult,
        *,
        roles: list[str],
        bids: list[dict[str, Any]],
        winning_role: str,
        winning_bid: dict[str, Any],
        started_at: float,
    ) -> StrategyResult:
        # Attach Market Auction trace metadata to the execution result.
        meta = dict(result.metadata)
        meta["market_auction"] = {
            "role_count": len(roles),
            "winning_role": winning_role,
            "winning_confidence": int(winning_bid.get("confidence", 0)),
            "fallback_used": bool(winning_bid.get("_fallback", False)),
            "elapsed_seconds": max(0.0, time.monotonic() - started_at),
            "bids": tuple(
                {"role": role, "can_handle": bool(bid.get("can_handle", False)), "confidence": int(bid.get("confidence", 0))}
                for role, bid in zip(roles, bids)
            ),
        }
        return StrategyResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=meta)

    @staticmethod
    def _parse_roles(text: str) -> list[str]:
        # Extract role name strings from a JSON array in the auctioneer output.
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end])
                if isinstance(parsed, list):
                    return [str(r) for r in parsed if r]
            except (json.JSONDecodeError, ValueError):
                pass
        return [line.strip().lstrip("-•").strip() for line in text.splitlines() if line.strip()][:5]

    @staticmethod
    def _parse_bid(text: str) -> dict[str, Any]:
        # Parse a structured bid from the bidder response; return a zero-confidence fallback on failure.
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except (json.JSONDecodeError, ValueError):
                pass
        return {"can_handle": False, "confidence": 0, "approach": ""}


__all__ = ["MarketAuctionAgentRuntime"]
