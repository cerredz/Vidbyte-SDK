from __future__ import annotations

from vidbyte.lib.prompts import PrompRegistry, PromptRegistry
from vidbyte.prompts.strategies import (
    AgenticRagPrompts,
    AnswerConvergencePrompts,
    BudgetForcingPrompts,
    ChainOfDraftPrompts,
    ChainOfThoughtPrompts,
    ContextEngineeringPrompts,
    ExpertPromptingPrompts,
    MultiAgentReflexionPrompts,
    ParadigmRouterPrompts,
    PlanAndExecutePrompts,
    SelfConsistencyPrompts,
    SkeletonOfThoughtPrompts,
    StepBackPrompts,
    TreeOfThoughtsPrompts,
)

__all__ = [
    "AgenticRagPrompts",
    "AnswerConvergencePrompts",
    "BudgetForcingPrompts",
    "ChainOfDraftPrompts",
    "ChainOfThoughtPrompts",
    "ContextEngineeringPrompts",
    "ExpertPromptingPrompts",
    "MultiAgentReflexionPrompts",
    "ParadigmRouterPrompts",
    "PlanAndExecutePrompts",
    "PrompRegistry",
    "PromptRegistry",
    "SelfConsistencyPrompts",
    "SkeletonOfThoughtPrompts",
    "StepBackPrompts",
    "TreeOfThoughtsPrompts",
]
