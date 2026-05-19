from __future__ import annotations

from vidbyte.strategies.agent_loops import PlanAndExecuteStrategy, SelfRefinementStrategy
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

    def chain_of_thought(self) -> ChainOfThoughtStrategy:
        return ChainOfThoughtStrategy()

    def step_back(self) -> StepBackStrategy:
        return StepBackStrategy()

    def chain_of_draft(self, *, max_words_per_step: int = 5) -> ChainOfDraftStrategy:
        return ChainOfDraftStrategy(max_words_per_step=max_words_per_step)

    def skeleton_of_thought(
        self,
        *,
        max_points: int = 8,
        max_workers: int = 4,
    ) -> SkeletonOfThoughtStrategy:
        return SkeletonOfThoughtStrategy(max_points=max_points, max_workers=max_workers)

    def self_consistency(self, *, samples: int = 5) -> SelfConsistencyStrategy:
        return SelfConsistencyStrategy(samples=samples)

    def budget_forcing(self, *, max_rounds: int = 3) -> BudgetForcingStrategy:
        return BudgetForcingStrategy(max_rounds=max_rounds)

    def answer_convergence(
        self,
        *,
        max_samples: int = 7,
        window: int = 3,
    ) -> AnswerConvergenceStrategy:
        return AnswerConvergenceStrategy(max_samples=max_samples, window=window)

    def plan_and_execute(self) -> PlanAndExecuteStrategy:
        return PlanAndExecuteStrategy()

    def self_refinement(
        self,
        *,
        create_system_prompt: str,
        refine_system_prompt: str,
        iterations: int,
        feedback_system_prompt: str | None = None,
    ) -> SelfRefinementStrategy:
        return SelfRefinementStrategy(
            create_system_prompt=create_system_prompt,
            refine_system_prompt=refine_system_prompt,
            iterations=iterations,
            feedback_system_prompt=feedback_system_prompt,
        )

    def paradigm_router(self) -> ParadigmRouterStrategy:
        return ParadigmRouterStrategy()
