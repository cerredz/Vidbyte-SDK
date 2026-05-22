from __future__ import annotations

# Class-based prompt system (PR10): BasePrompt, PromptKey, PromptVersion, RenderedPrompt
from vidbyte.prompts.base import BasePrompt, PromptError, PromptNotFoundError, PromptRenderError
from vidbyte.prompts.types import PromptKey, PromptVersion, RenderedPrompt

# Central registries (merged PR10 + PR15)
from vidbyte.prompts.registry import PromptLike, PromptRegistry, prompt_registry

# Strategy prompts
from vidbyte.prompts.prompts import VMAOPrompts

# JSON-backed strategy prompts (PR12)
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

# JSON-backed library registry (PR12)
from vidbyte.lib.prompts import PromptRegistry as LibPromptRegistry, PrompRegistry

__all__ = [
    "AgenticRagPrompts",
    "AnswerConvergencePrompts",
    "BasePrompt",
    "BudgetForcingPrompts",
    "ChainOfDraftPrompts",
    "ChainOfThoughtPrompts",
    "ContextEngineeringPrompts",
    "ExpertPromptingPrompts",
    "LibPromptRegistry",
    "MultiAgentReflexionPrompts",
    "ParadigmRouterPrompts",
    "PlanAndExecutePrompts",
    "PrompRegistry",
    "PromptError",
    "PromptKey",
    "PromptLike",
    "PromptNotFoundError",
    "PromptRegistry",
    "PromptRenderError",
    "PromptVersion",
    "RenderedPrompt",
    "SelfConsistencyPrompts",
    "SkeletonOfThoughtPrompts",
    "StepBackPrompts",
    "TreeOfThoughtsPrompts",
    "VMAOPrompts",
    "prompt_registry",
]
