from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.multi_agent.base import BaseMultiAgentStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult


class EconomicGateStrategy(BaseMultiAgentStrategy):
    """Route to orchestration only when the prompt appears worth the overhead."""

    name = "multi_agent.economic_gate"

    def __init__(self, *, baseline_strategy: BaseStrategy, orchestration_strategy: BaseStrategy, scorer: Callable[[str, StrategyContext | None], float] | None = None, threshold: float = 0.6) -> None:
        super().__init__(max_calls=1)
        if threshold < 0 or threshold > 1:
            raise ValueError("threshold must be between 0 and 1.")
        self.baseline_strategy = baseline_strategy
        self.orchestration_strategy = orchestration_strategy
        self.scorer = scorer or self._default_appropriateness_score
        self.threshold = threshold

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: Any) -> StrategyResult:
        try:
            score = max(0.0, min(1.0, float(self.scorer(prompt, context))))
        except Exception:
            score = 0.0
        selected = self.orchestration_strategy if score >= self.threshold else self.baseline_strategy
        route = "orchestration" if selected is self.orchestration_strategy else "baseline"
        try:
            result = await selected.arun(prompt, runner=runner, context=context, tools=tools, **options)
        except Exception as exc:
            raise StrategyExecutionError(f"Economic gate selected {route}, but execution failed.") from exc
        return StrategyResult(
            output=result.output,
            strategy_name=self.name,
            metadata={"route": route, "score": score, "selected_strategy": result.strategy_name},
        )

    @staticmethod
    def _default_appropriateness_score(prompt: str, context: StrategyContext | None = None) -> float:
        score = 0.0
        lowered = prompt.lower()
        if len(prompt) > 500:
            score += 0.25
        if any(word in lowered for word in ("compare", "evaluate", "verify", "research", "tradeoff")):
            score += 0.25
        if any(word in lowered for word in ("multi-step", "complex", "architecture", "plan", "strategy")):
            score += 0.25
        if context and context.system_prompt:
            score += 0.1
        if context and context.budget and context.budget.max_model_calls and context.budget.max_model_calls <= 2:
            score -= 0.2
        return max(0.0, min(score, 1.0))
