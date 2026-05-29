"""Context Protocol Header

Description:
    Executes the Beam Search context-window algorithm for AgentRuntime.
Purpose:
    Keeps Beam Search parallel-trial, scoring, and winner-selection orchestration
    out of the generic agent runtime loop.
Architecture:
    - BeamSearchRuntimeAlgorithm: Runs beam_width parallel agent trials, scores
      each output with an LLM scorer call, and returns the highest-scored result.
Relations:
    Used by AgentRuntimeContextAlgorithms. Consumes BeamSearchAlgorithm config
    from vidbyte.context.algorithms.beam_search.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.beam_search import BeamSearchAlgorithm
from vidbyte.lib.tracing import SpanContext
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class BeamSearchRuntimeAlgorithm:
    """Runtime adapter for the Beam Search context-window algorithm."""

    name = "beam_search"

    def __init__(self, runtime: AgentRuntime, algorithm: BeamSearchAlgorithm) -> None:
        """Store the runtime reference and beam search configuration."""
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        """Run beam_width parallel trials, score each, and return the best result."""
        started_at = self.runtime.middleware.clock()
        candidates = await self._run_candidate_trials(
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
        scores = await self._score_all_candidates(
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
        return self._with_beam_metadata(winner, candidates=candidates, scores=scores, winner_index=winner_index, started_at=started_at)

    async def _run_candidate_trials(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[StrategyResult]:
        """Run beam_width independent agent trials in parallel."""
        tasks = [
            self.runtime._arun_once(
                message,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
                metadata=self._trial_metadata(metadata, trial_index=i),
                options=dict(options or {}),
                trace_context=trace_context,
            )
            for i in range(self.algorithm.beam_width)
        ]
        return list(await asyncio.gather(*tasks))

    async def _score_all_candidates(self, candidates: list[StrategyResult], *, task: str, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[float]:
        """Score each candidate output using a parallel LLM scorer call."""
        started_at = self.runtime.middleware.clock()
        tasks = [
            self._score_candidate(
                result,
                task=task,
                runner=runner,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                started_at=started_at,
                metadata=metadata,
                trace_context=trace_context,
            )
            for result in candidates
        ]
        return list(await asyncio.gather(*tasks))

    async def _score_candidate(self, result: StrategyResult, *, task: str, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], started_at: float, metadata: Mapping[str, Any] | None, trace_context: SpanContext | None) -> float:
        """Call the LLM scorer for one candidate and return a numeric score."""
        candidate_text = self.algorithm.truncate_candidate(result.output)
        scorer_prompt = self.algorithm.render_scorer_prompt(task=task, candidate=candidate_text)
        scorer_system = self.algorithm.scorer_system_prompt_text()
        raw_result, _ = await self.runtime._invoke_with_middleware(
            runner,
            scorer_prompt,
            {"system": scorer_system},
            context=context,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=started_at,
            metadata=self._scorer_metadata(metadata),
            trace_context=trace_context,
        )
        if isinstance(raw_result, StrategyResult):
            return 0.0
        return self._parse_score(runner_output_text(raw_result))

    def _select_winner(self, candidates: list[StrategyResult], scores: list[float]) -> tuple[StrategyResult, int]:
        """Return the candidate with the highest score and its index."""
        if not candidates:
            raise RuntimeError("No candidates to select from.")
        best_index = max(range(len(scores)), key=lambda i: scores[i])
        return candidates[best_index], best_index

    def _with_beam_metadata(self, result: StrategyResult, *, candidates: list[StrategyResult], scores: list[float], winner_index: int, started_at: float) -> StrategyResult:
        """Attach Beam Search trace metadata to the winning result."""
        metadata = dict(result.metadata)
        metadata["beam_search"] = {
            "beam_width": self.algorithm.beam_width,
            "winner_index": winner_index,
            "winner_score": scores[winner_index] if scores else 0.0,
            "elapsed_seconds": max(0.0, self.runtime.middleware.clock() - started_at),
            "candidates": tuple(
                {
                    "trial_index": i,
                    "score": scores[i] if i < len(scores) else 0.0,
                    "stop_reason": dict(candidates[i].metadata).get("stop_reason", "unknown"),
                    "output_chars": len(candidates[i].output),
                }
                for i in range(len(candidates))
            ),
        }
        return StrategyResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
        )

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract the first integer from scorer output; return 0.0 on failure."""
        match = re.search(r"\b(\d+)\b", text.strip())
        if match:
            try:
                return float(int(match.group(1)))
            except ValueError:
                pass
        return 0.0

    @staticmethod
    def _trial_metadata(metadata: Mapping[str, Any] | None, *, trial_index: int) -> dict[str, Any]:
        """Build metadata passed into a beam candidate trial."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "beam_search",
            "beam_trial_index": trial_index,
        }

    @staticmethod
    def _scorer_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        """Build metadata passed into a beam scorer call."""
        return {
            **dict(metadata or {}),
            "context_window_algorithm": "beam_search",
            "beam_stage": "scorer",
        }


__all__ = [
    "BeamSearchRuntimeAlgorithm",
]
