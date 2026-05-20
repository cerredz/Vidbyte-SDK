from __future__ import annotations

from typing import Any

from vidbyte.strategies.agent_loops import PlanAndExecuteStrategy
from vidbyte.strategies.reasoning import (
    ChainOfDraftStrategy,
    ChainOfThoughtStrategy,
    SkeletonOfThoughtStrategy,
    StepBackStrategy,
)
from vidbyte.strategies.routing import ParadigmRouterStrategy
from vidbyte.strategies.sampling import (
    AnswerConvergenceStrategy,
    BudgetForcingStrategy,
    SelfConsistencyStrategy,
)


class StrategyClient:
    """Factory client for prompt/API strategies."""

    def chain_of_thought(self, **runner_options: Any) -> ChainOfThoughtStrategy:
        return ChainOfThoughtStrategy(**runner_options)

    def step_back(self, **runner_options: Any) -> StepBackStrategy:
        return StepBackStrategy(**runner_options)

    def chain_of_draft(self, *, max_words_per_step: int = 5, **runner_options: Any) -> ChainOfDraftStrategy:
        return ChainOfDraftStrategy(max_words_per_step=max_words_per_step, **runner_options)

    def skeleton_of_thought(
        self,
        *,
        max_points: int = 8,
        max_workers: int = 4,
        **runner_options: Any,
    ) -> SkeletonOfThoughtStrategy:
        return SkeletonOfThoughtStrategy(max_points=max_points, max_workers=max_workers, **runner_options)

    def self_consistency(self, *, samples: int = 5, **runner_options: Any) -> SelfConsistencyStrategy:
        return SelfConsistencyStrategy(samples=samples, **runner_options)

    def budget_forcing(self, *, max_rounds: int = 3, **runner_options: Any) -> BudgetForcingStrategy:
        return BudgetForcingStrategy(max_rounds=max_rounds, **runner_options)

    def answer_convergence(
        self,
        *,
        max_samples: int = 7,
        window: int = 3,
        **runner_options: Any,
    ) -> AnswerConvergenceStrategy:
        return AnswerConvergenceStrategy(max_samples=max_samples, window=window, **runner_options)

    def plan_and_execute(self, **runner_options: Any) -> PlanAndExecuteStrategy:
        return PlanAndExecuteStrategy(**runner_options)

    def paradigm_router(self, **runner_options: Any) -> ParadigmRouterStrategy:
        return ParadigmRouterStrategy(**runner_options)
