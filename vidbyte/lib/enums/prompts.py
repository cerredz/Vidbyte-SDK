"""Context Protocol Header

Description:
    Defines the central Prompt enum keys for Vidbyte SDK prompt assets. This file acts as a
    single source of truth for prompt identifiers.

Purpose:
    Enables static typing, autocomplete, and validation for static prompt templates loaded
    from external JSON and Markdown files.

Architecture and Key Functions:
    - Prompt (Enum): Inherits from `str` and `Enum`. It maps high-level, semantic prompt
      identifiers (constants) to their corresponding catalog-relative string paths.
      Keys are used programmatically, while values map to assets under `vidbyte/prompts/prompts/`.

Relation to the codebase as a whole:
    Provides identifiers that are referenced across agents, context window management algorithms,
    prompt strategies, and evaluations to fetch compiled prompt assets from the global prompt catalog.
    Used heavily by `vidbyte.prompts.catalog.Prompts` to load and cache text templates, and by
    MCP server handlers to list or resolve prompts.

Similar Files:
    - `vidbyte/lib/enums/model_provider.py`: Defines supported model providers.
    - `vidbyte/lib/enums/model_modality.py`: Defines modalities.
"""

from __future__ import annotations

from enum import Enum


class Prompt(str, Enum):
    """Prompt keys for Vidbyte SDK prompt assets."""


    AGENTIC_LOOP_CONTEXT_PROMPT = "agentic_loop.context_prompt"
    AGENTIC_RAG_RETRIEVE_PROMPT = "agentic_rag.retrieve_prompt"
    AGENTIC_RAG_ANSWER_PROMPT = "agentic_rag.answer_prompt"
    ANSWER_CONVERGENCE_ATTEMPT_PROMPT = "answer_convergence.attempt_prompt"
    BUDGET_FORCING_INITIAL_PROMPT = "budget_forcing.initial_prompt"
    BUDGET_FORCING_CONTINUE_PROMPT = "budget_forcing.continue_prompt"
    CHAIN_OF_DRAFT_DRAFT_PROMPT = "chain_of_draft.draft_prompt"
    CHAIN_OF_THOUGHT_REASON_PROMPT = "chain_of_thought.reason_prompt"
    CONTEXT_ENGINEERING_GUIDELINE_PROMPT = "context_engineering.guideline_prompt"
    EXPERT_PROMPTING_EXPERT_PROMPT = "expert_prompting.expert_prompt"
    GOALS_GOAL_PROMPT = "goals.goal_prompt"
    MIMIC_BEHAVIOR_MIMIC_PROMPT = "mimic_behavior.mimic_prompt"
    MULTI_AGENT_REFLEXION_DRAFT_PROMPT = "multi_agent_reflexion.draft_prompt"
    MULTI_AGENT_REFLEXION_CRITIC_PROMPT = "multi_agent_reflexion.critic_prompt"
    MULTI_AGENT_REFLEXION_FINAL_PROMPT = "multi_agent_reflexion.final_prompt"
    REFLEXION_AGENT_SYSTEM_PROMPT = "reflexion.agent_system_prompt"
    REFLEXION_REFLECT_SYSTEM_PROMPT = "reflexion.reflect_system_prompt"
    REFLEXION_REFLECT_PROMPT = "reflexion.reflect_prompt"
    PARADIGM_ROUTER_ROUTE_PROMPT = "paradigm_router.route_prompt"
    PLAN_AND_EXECUTE_PLAN_PROMPT = "plan_and_execute.plan_prompt"
    PROMPT_ENGINEERING_MASTER_PROMPT = "prompt_engineering.master_prompt"
    PLAN_AND_EXECUTE_EXECUTE_PROMPT = "plan_and_execute.execute_prompt"
    PLAN_AND_EXECUTE_FINAL_PROMPT = "plan_and_execute.final_prompt"
    SELF_CONSISTENCY_SAMPLE_PROMPT = "self_consistency.sample_prompt"
    SKELETON_OF_THOUGHT_SKELETON_PROMPT = "skeleton_of_thought.skeleton_prompt"
    SKELETON_OF_THOUGHT_EXPAND_PROMPT = "skeleton_of_thought.expand_prompt"
    STEP_BACK_PRINCIPLE_PROMPT = "step_back.principle_prompt"
    STEP_BACK_ANSWER_PROMPT = "step_back.answer_prompt"
    TREE_OF_THOUGHTS_BRANCH_PROMPT = "tree_of_thoughts.branch_prompt"
    TREE_OF_THOUGHTS_EVALUATE_PROMPT = "tree_of_thoughts.evaluate_prompt"
    TREE_OF_THOUGHTS_FINAL_PROMPT = "tree_of_thoughts.final_prompt"
    VMAO_PLANNER = "vmao.planner"
    VMAO_PLANNER_REPAIR = "vmao.planner_repair"
    VMAO_SYNTHESIZER = "vmao.synthesizer"
    VMAO_VERIFIER = "vmao.verifier"
    VMAO_GAP_PLANNER = "vmao.gap_planner"
    EVALS_LLM_JUDGE = "evals.llm_judge"
    EVALS_RUBRIC = "evals.rubric"
    MULTI_PROVIDER_AGENTIC_GRADER_AGENT_SYSTEM_PROMPT = "multi_provider_agentic_grader.agent_system_prompt"
    MULTI_PROVIDER_AGENTIC_GRADER_GRADER_SYSTEM_PROMPT = "multi_provider_agentic_grader.grader_system_prompt"
    MULTI_PROVIDER_AGENTIC_GRADER_GRADER_PROMPT = "multi_provider_agentic_grader.grader_prompt"


__all__ = [
    "Prompt",
]
