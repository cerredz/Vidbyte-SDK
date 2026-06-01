"""Context Protocol Header

Description:
    Implements the Beam Search non-linear agent execution runtime.
Purpose:
    Runs beam_width parallel agent trials, scores each output with an LLM scorer call,
    and returns the highest-scored result — the runtime state is a set of k live
    StrategyResult objects, not one.
Architecture:
    - BeamSearchAgentRuntime: Orchestrates parallel trials and scorer calls.
Relations:
    Located in vidbyte/agents/runtimes/beam_search.py. Registered in RuntimeRegistry.
    Instantiated by BaseAgent._runtime() when runtime_type is BEAM_SEARCH.
Similar Files:
    - vidbyte/agents/runtimes/search.py: MCTS non-linear runtime.
    - vidbyte/agents/runtimes/gossip.py: Gossip non-linear runtime.
"""

from __future__ import annotations

import asyncio
import re
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


class BeamSearchAgentRuntime:
    """Runs beam_width parallel agent trials, scores each, and returns the highest-scored result."""

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
        beam_width: int = 3,
        max_scorer_chars: int = 8000,
        scorer_system_prompt: str = "",
        scorer_prompt: str = "",
        **kwargs: Any,
    ) -> None:
        # Store agent config and beam search parameters; middleware is intentionally ignored.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self._tracer: TracerBase = tracer or NullTracer()
        self.run_id = run_id
        self.beam_width = beam_width
        self.max_scorer_chars = max_scorer_chars
        self.scorer_system_prompt = scorer_system_prompt
        self.scorer_prompt = scorer_prompt

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
        # Build the initial context window for the beam search trials.
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
        # Run beam_width parallel trials, score each, and return the highest-scored result.
        started_at = time.monotonic()
        candidates = await self._run_trials(
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
        scores = await self._score_all(
            candidates,
            task=message,
            runner=runner,
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            metadata=metadata,
            trace_context=trace_context,
        )
        winner, winner_index = self._select_winner(candidates, scores)
        return self._with_metadata(winner, candidates=candidates, scores=scores, winner_index=winner_index, started_at=started_at)

    async def _run_trials(
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
    ) -> list[StrategyResult]:
        # Run beam_width independent agent trials concurrently.
        from vidbyte.agents.runtime import AgentRuntime
        tasks = []
        for i in range(self.beam_width):
            inner = AgentRuntime(
                agent_name=self.agent_name,
                system_prompt=self.system_prompt,
                tools=self.tools,
                permission_policy=self.permission_policy,
                config=self.config,
                tracer=self._tracer,
                run_id=self.run_id,
            )
            tasks.append(
                inner._arun_once(
                    message,
                    runner=runner,
                    context=context,
                    provider=provider,
                    invoke_runner=invoke_runner,
                    runner_output_text=runner_output_text,
                    runner_output_metadata=runner_output_metadata,
                    metadata={**(metadata or {}), "beam_trial_index": i},
                    options=dict(options or {}),
                    trace_context=trace_context,
                )
            )
        return list(await asyncio.gather(*tasks))

    async def _score_all(
        self,
        candidates: list[StrategyResult],
        *,
        task: str,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        metadata: Mapping[str, Any] | None,
        trace_context: Any,
    ) -> list[float]:
        # Score every candidate in parallel with a lightweight LLM scorer call.
        tasks = [
            self._score_one(
                result,
                task=task,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
            )
            for result in candidates
        ]
        return list(await asyncio.gather(*tasks))

    async def _score_one(
        self,
        result: StrategyResult,
        *,
        task: str,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
    ) -> float:
        # Call the LLM scorer for one candidate and extract the numeric score.
        candidate_text = result.output[:self.max_scorer_chars]
        scorer_prompt = self.scorer_prompt.format(task=task, candidate=candidate_text)
        try:
            raw = await invoke_runner(runner, scorer_prompt, system=self.scorer_system_prompt)
            return self._parse_score(runner_output_text(raw))
        except Exception:
            return 0.0

    def _select_winner(self, candidates: list[StrategyResult], scores: list[float]) -> tuple[StrategyResult, int]:
        # Return the candidate with the highest score.
        best = max(range(len(scores)), key=lambda i: scores[i])
        return candidates[best], best

    def _with_metadata(
        self,
        result: StrategyResult,
        *,
        candidates: list[StrategyResult],
        scores: list[float],
        winner_index: int,
        started_at: float,
    ) -> StrategyResult:
        # Attach beam search trace metadata to the winning result.
        meta = dict(result.metadata)
        meta["beam_search"] = {
            "beam_width": self.beam_width,
            "winner_index": winner_index,
            "winner_score": scores[winner_index] if scores else 0.0,
            "elapsed_seconds": max(0.0, time.monotonic() - started_at),
            "candidates": tuple(
                {
                    "trial_index": i,
                    "score": scores[i] if i < len(scores) else 0.0,
                    "output_chars": len(candidates[i].output),
                }
                for i in range(len(candidates))
            ),
        }
        return StrategyResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=meta)

    @staticmethod
    def _parse_score(text: str) -> float:
        # Extract the first integer from scorer output; return 0.0 on parse failure.
        match = re.search(r"\b(\d+)\b", text.strip())
        if match:
            try:
                return float(int(match.group(1)))
            except ValueError:
                pass
        return 0.0


__all__ = ["BeamSearchAgentRuntime"]
