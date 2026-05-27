# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Top-level prompt module initializer for the Vidbyte SDK prompts namespace.
# Purpose: Exports prompt catalog accessors, strategy classes, and direct variable prompt strings.
# Architecture & Functions:
#   - Exposes Prompt, Prompts, PromptRecord, VMAOPrompts, and all strategy-specific bundles.
#   - Dynamically loads direct imports from the prompt registry catalog and exports them.
# Codebase Relation:
#   - Main entry point for all prompt assets and strategy bundles used across the SDK.
# Similar Files:
#   - vidbyte/prompts/strategies/__init__.py (strategy-specific initializer)
# ==============================================================================

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
    ParadigmRouterPrompts,
    PlanAndExecutePrompts,
    PromptEngineeringPrompts,
    PromptTemplatesPrompts,
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
    "ParadigmRouterPrompts",
    "PlanAndExecutePrompts",
    "Prompt",
    "PromptEngineeringPrompts",
    "PromptRecord",
    "PromptTemplatesPrompts",
    "Prompts",
    "ReflexionPrompts",
    "SelfConsistencyPrompts",
    "SkeletonOfThoughtPrompts",
    "StepBackPrompts",
    "TreeOfThoughtsPrompts",
    "VMAOPrompts",
] + list(_direct_prompt_exports)

