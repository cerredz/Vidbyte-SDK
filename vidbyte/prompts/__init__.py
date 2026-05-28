from __future__ import annotations

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import PromptRecord, Prompts
from vidbyte.prompts.prompts import VMAOPrompts
from vidbyte.prompts.strategies import (
    AgenticRagPrompts,
    AnswerConvergencePrompts,
    BudgetForcingPrompts,
    ChainOfDraftPrompts,
    ChainOfThoughtPrompts,
    ContextEngineeringPrompts,
    ExpertPromptingPrompts,
    MultiAgentReflexionPrompts,
    MultiProviderAgenticGraderPrompts,
    ParadigmRouterPrompts,
    PlanAndExecutePrompts,
    PromptEngineeringPrompts,
    ReflexionPrompts,
    SelfConsistencyPrompts,
    SkeletonOfThoughtPrompts,
    StepBackPrompts,
    TreeOfThoughtsPrompts,
)

_prompts = Prompts()

for _prompt_key, _import_name in _prompts.import_names().items():
    globals()[_import_name] = _prompts.get(_prompt_key)

_direct_prompt_exports = tuple(sorted(_prompts.import_names().values()))

__all__ = [
    "AgenticRagPrompts",
    "AnswerConvergencePrompts",
    "BudgetForcingPrompts",
    "ChainOfDraftPrompts",
    "ChainOfThoughtPrompts",
    "ContextEngineeringPrompts",
    "ExpertPromptingPrompts",
    "MultiAgentReflexionPrompts",
    "MultiProviderAgenticGraderPrompts",
    "ParadigmRouterPrompts",
    "PlanAndExecutePrompts",
    "Prompt",
    "PromptEngineeringPrompts",
    "PromptRecord",
    "Prompts",
    "ReflexionPrompts",
    "SelfConsistencyPrompts",
    "SkeletonOfThoughtPrompts",
    "StepBackPrompts",
    "TreeOfThoughtsPrompts",
    "VMAOPrompts",
] + list(_direct_prompt_exports)
