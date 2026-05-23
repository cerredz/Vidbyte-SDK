from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict
from typing import Any, Sequence

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.multi_agent.base import BaseMultiAgentStrategy
from vidbyte.strategies.multi_agent.types import CandidateFailure, CandidateResult, EvaluationDecision
from vidbyte.strategies.types import StrategyContext, StrategyResult


class MultiAgentConsensusStrategy(BaseMultiAgentStrategy):
    """Run several strategies and ask an evaluator to select the best output."""

    name = "multi_agent.consensus"

    def __init__(self, *, strategies: Sequence[BaseStrategy], evaluator_agent: BaseAgent | None = None, evaluator_strategy: BaseStrategy | None = None, require_json_decision: bool = False, max_calls: int = 20) -> None:
        super().__init__(max_calls=max_calls)
        if not strategies:
            raise ValueError("At least one strategy is required.")
        self.strategies = tuple(strategies)
        self.evaluator_agent = evaluator_agent
        self.evaluator_strategy = evaluator_strategy
        self.require_json_decision = require_json_decision

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: Any) -> StrategyResult:
        self._reset_calls()
        tasks = [
            self._run_candidate(index, strategy, prompt, runner, context, tools, options)
            for index, strategy in enumerate(self.strategies, start=1)
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        candidates: list[CandidateResult] = []
        failures: list[CandidateFailure] = []
        for index, raw in enumerate(raw_results, start=1):
            strategy_name = self._strategy_name(self.strategies[index - 1])
            if isinstance(raw, Exception):
                failures.append(
                    CandidateFailure(
                        index=index,
                        strategy_name=strategy_name,
                        error_type=type(raw).__name__,
                        message=self._safe_error(raw),
                    )
                )
            else:
                candidates.append(raw)
        if not candidates:
            raise StrategyExecutionError(
                "All candidate strategies failed.",
                details={"failures": [asdict(failure) for failure in failures]},
            )
        evaluator_prompt = self._render_evaluator_prompt(prompt, candidates, failures, context)
        evaluator_output = await self._evaluate(evaluator_prompt, runner, context, tools)
        decision = self._parse_decision(evaluator_output, candidates)
        return StrategyResult(
            output=decision.final_output,
            strategy_name=self.name,
            metadata={
                "selected_index": decision.selected_index,
                "grades": dict(decision.grades),
                "rationale": decision.rationale,
                "candidates": [asdict(candidate) for candidate in candidates],
                "failures": [asdict(failure) for failure in failures],
                "evaluator_output": evaluator_output,
            },
        )

    async def _run_candidate(self, index: int, strategy: BaseStrategy, prompt: str, runner: object | None, context: StrategyContext | None, tools: Sequence[object], options: dict[str, Any]) -> CandidateResult:
        self._count_call()
        isolated_context = StrategyContext(
            system_prompt=context.system_prompt if context else None,
            agent_name=context.agent_name if context else None,
            role=context.role if context else None,
            history=tuple(context.history) if context else (),
            file_paths=tuple(context.file_paths) if context else (),
            strategy_metadata={**dict(context.strategy_metadata if context else {}), "candidate_index": index},
            tool_calls=tuple(context.tool_calls) if context else (),
            responses=tuple(context.responses) if context else (),
            budget=context.budget if context else None,
            artifacts=tuple(context.artifacts) if context else (),
            memory=context.memory if context else None,
            permissions=context.permissions if context else None,
            metadata={**dict(context.metadata if context else {}), "candidate_index": index},
        )
        result = await strategy.arun(
            prompt,
            runner=runner,
            context=isolated_context,
            tools=tools,
            **options,
        )
        return CandidateResult(
            index=index,
            strategy_name=result.strategy_name or self._strategy_name(strategy),
            output=result.output,
            metadata=dict(result.metadata),
        )

    async def _evaluate(self, evaluator_prompt: str, runner: object | None, context: StrategyContext | None, tools: Sequence[object]) -> str:
        self._count_call()
        if self.evaluator_agent is not None:
            reply = await self.evaluator_agent.generate_reply(
                evaluator_prompt,
                context=context,
                history=tuple(context.history) if context else (),
                recipient="consensus",
            )
            return reply.content
        if self.evaluator_strategy is not None:
            result = await self.evaluator_strategy.arun(
                evaluator_prompt,
                runner=runner,
                context=context,
                tools=tools,
            )
            return result.output
        if runner is None:
            return json.dumps(
                {
                    "selected_index": 1,
                    "final_output": "",
                    "grades": {},
                    "rationale": "No evaluator agent, evaluator strategy, or runner was supplied.",
                }
            )
        return await self._call_runner(runner, evaluator_prompt)

    def _parse_decision(self, evaluator_output: str, candidates: Sequence[CandidateResult]) -> EvaluationDecision:
        try:
            parsed = json.loads(evaluator_output)
        except json.JSONDecodeError as exc:
            if self.require_json_decision:
                raise StrategyExecutionError("Evaluator did not return valid JSON.") from exc
            return EvaluationDecision(
                selected_index=candidates[0].index,
                final_output=evaluator_output or candidates[0].output,
                rationale="Evaluator output was not JSON; returned raw evaluator output.",
            )
        selected_index = int(parsed.get("selected_index", candidates[0].index))
        selected = next((candidate for candidate in candidates if candidate.index == selected_index), candidates[0])
        final_output = str(parsed.get("final_output") or selected.output)
        return EvaluationDecision(
            selected_index=selected.index,
            final_output=final_output,
            grades=parsed.get("grades", {}),
            rationale=str(parsed.get("rationale", "")),
        )

    def _render_evaluator_prompt(self, original_prompt: str, candidates: Sequence[CandidateResult], failures: Sequence[CandidateFailure], context: StrategyContext | None) -> str:
        system = context.build_context() if context else ""
        candidate_text = "\n\n".join(
            f"Candidate {candidate.index} ({candidate.strategy_name}):\n{candidate.output}"
            for candidate in candidates
        )
        failure_text = "\n".join(
            f"Candidate {failure.index} ({failure.strategy_name}) failed: {failure.error_type}: {failure.message}"
            for failure in failures
        ) or "None"
        return (
            "You are an expert evaluator and consensus router.\n"
            "Judge the candidates against the original task and system context. "
            "Return strict JSON with selected_index, final_output, grades, and rationale.\n\n"
            f"System context:\n{system}\n\n"
            f"Original task:\n{original_prompt}\n\n"
            f"Candidate answers:\n{candidate_text}\n\n"
            f"Failed candidates:\n{failure_text}\n"
        )

    def _strategy_name(self, strategy: BaseStrategy) -> str:
        return getattr(strategy, "strategy_name", strategy.__class__.__name__)

    @classmethod
    async def _call_runner(cls, runner: object, prompt: str) -> str:
        method = getattr(runner, "arun", None)
        if callable(method):
            response = method(prompt)
            if inspect.isawaitable(response):
                response = await response
            return cls._response_text(response)
        method = getattr(runner, "run", None)
        if callable(method):
            response = method(prompt)
            if inspect.isawaitable(response):
                response = await response
            return cls._response_text(response)
        if callable(runner):
            response = runner(prompt)
            if inspect.isawaitable(response):
                response = await response
            return cls._response_text(response)
        raise StrategyExecutionError("Runner does not expose arun(), run(), or callable execution.")

    @staticmethod
    def _response_text(response: object) -> str:
        if isinstance(response, str):
            return response
        for attr in ("output", "text", "content"):
            value = getattr(response, attr, None)
            if isinstance(value, str):
                return value
        return str(response)
