from __future__ import annotations

from typing import ClassVar, Iterable

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.reasoning import (
    ChainOfDraftStrategy,
    ChainOfThoughtStrategy,
    SkeletonOfThoughtStrategy,
    StepBackStrategy,
)
from vidbyte.strategies.sampling import SelfConsistencyStrategy
from vidbyte.strategies.types import StrategyResult


class ParadigmRouterStrategy(BaseStrategy):
    name: ClassVar[str] = "paradigm_router"

    def __init__(self, strategies: Iterable[BaseStrategy] | None = None) -> None:
        selected = strategies or (
            ChainOfThoughtStrategy(),
            StepBackStrategy(),
            ChainOfDraftStrategy(),
            SkeletonOfThoughtStrategy(),
            SelfConsistencyStrategy(samples=3),
        )
        self._strategies = {strategy.name: strategy for strategy in selected}

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        use_model_router = bool(options.get("use_model_router", False))
        selected_name = (
            self._route_with_model(prompt, runner=runner)
            if use_model_router
            else self._route_with_heuristics(prompt)
        )
        selected = self._strategies.get(selected_name) or self._strategies["chain_of_thought"]
        result = selected.run(prompt, runner=runner)
        return StrategyResult(
            output=result.output,
            strategy_name=self.name,
            calls=result.calls,
            metadata={
                "selected_strategy": selected.name,
                "selected_metadata": dict(result.metadata),
                "routing_mode": "model" if use_model_router else "heuristic",
            },
        )

    def _route_with_heuristics(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(term in lowered for term in ("outline", "sections", "write a report", "draft")):
            return "skeleton_of_thought"
        if any(term in lowered for term in ("principle", "why", "explain", "concept")):
            return "step_back"
        if any(term in lowered for term in ("short", "concise", "quick", "brief")):
            return "chain_of_draft"
        if any(term in lowered for term in ("math", "calculate", "prove", "logic")):
            return "self_consistency"
        return "chain_of_thought"

    def _route_with_model(self, prompt: str, *, runner: TextModelRunner) -> str:
        options = ", ".join(self._strategies)
        response = runner.run(
            "\n".join(
                [
                    "Select the best reasoning strategy for this task.",
                    f"Available strategies: {options}.",
                    "Return only the exact strategy name.",
                    "",
                    prompt,
                ]
            )
        )
        normalized = response.text.strip().lower()
        for name in self._strategies:
            if name in normalized:
                return name
        return self._route_with_heuristics(prompt)
