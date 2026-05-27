# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines strategy-specific prompt bundles for the Vidbyte SDK.
# Purpose: Groups prompts by strategy family to provide clean, unified accessors for agent pipelines.
# Architecture & Functions:
#   - _PromptBundle: Abstract base class that retrieves prompts dynamically from catalog by family key.
#   - PromptTemplatesPrompts: Accessor for the 'templates' prompt family.
# Codebase Relation:
#   - Imported by vidbyte.prompts and used by clients to fetch prompt strategies.
# Similar Files:
#   - vidbyte/prompts/catalog.py (supplies the prompt map)
# ==============================================================================

from __future__ import annotations

from typing import ClassVar

from vidbyte.prompts.catalog import Prompts


class _PromptBundle:
    key: ClassVar[str]

    def export(self) -> dict[str, str]:
        return dict(Prompts().family(self.key))


class ContextEngineeringPrompts(_PromptBundle):
    key = "context_engineering"


class ChainOfThoughtPrompts(_PromptBundle):
    key = "chain_of_thought"


class StepBackPrompts(_PromptBundle):
    key = "step_back"


class ChainOfDraftPrompts(_PromptBundle):
    key = "chain_of_draft"


class SkeletonOfThoughtPrompts(_PromptBundle):
    key = "skeleton_of_thought"


class SelfConsistencyPrompts(_PromptBundle):
    key = "self_consistency"


class BudgetForcingPrompts(_PromptBundle):
    key = "budget_forcing"


class AnswerConvergencePrompts(_PromptBundle):
    key = "answer_convergence"


class PlanAndExecutePrompts(_PromptBundle):
    key = "plan_and_execute"


class ParadigmRouterPrompts(_PromptBundle):
    key = "paradigm_router"


class TreeOfThoughtsPrompts(_PromptBundle):
    key = "tree_of_thoughts"


class MultiAgentReflexionPrompts(_PromptBundle):
    key = "multi_agent_reflexion"


class ReflexionPrompts(_PromptBundle):
    key = "reflexion"


class AgenticRagPrompts(_PromptBundle):
    key = "agentic_rag"


class ExpertPromptingPrompts(_PromptBundle):
    key = "expert_prompting"


class PromptEngineeringPrompts(_PromptBundle):
    key = "prompt_engineering"


class PromptTemplatesPrompts(_PromptBundle):
    """Bundle containing prompt generation templates (intent-based, persona, specification)."""
    key = "templates"


