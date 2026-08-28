"""Context Protocol Header

Description:
    Defines the central Prompt enum keys for Vidbyte SDK prompt assets. This file acts as a
    single source of truth for prompt identifiers.

Purpose:
    Enables static typing, autocomplete, and validation for the 59 static prompt templates
    across 21 JSON/Markdown-backed families, including multi-agent manager, isolated critic
    review, and prosecutor/defender/judge debate phases.

Architecture and Key Functions:
    - Prompt (Enum): Inherits from `str` and `Enum`. It maps high-level, semantic prompt
    identifiers (constants) to their corresponding catalog-relative string paths,
    including the six prosecutor/defender/judge role prompts.
      Keys are used programmatically, while values map to assets under `vidbyte/prompts/prompts/`.

Relation to the codebase as a whole:
    Provides identifiers that are referenced across agents, context window management algorithms,
    and evaluations to fetch compiled prompt assets from the global prompt catalog.
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

    AGENTIC_ENGINEERING_ERROR_MESSAGES = "agentic_engineering.error_messages"
    AGENTIC_ENGINEERING_FEATURE_TEST_PACKS = "agentic_engineering.feature_test_packs"
    AGENTIC_ENGINEERING_FILE_HEADERS = "agentic_engineering.file_headers"
    AGENTIC_ENGINEERING_FOLDER_README = "agentic_engineering.folder_readme"
    AGENTIC_ENGINEERING_FUNCTION_DESIGN = "agentic_engineering.function_design"
    AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING = "agentic_engineering.intent_based_commenting"
    AGENTIC_ENGINEERING_SYSTEM_PROMPT = "agentic_engineering.system_prompt"
    AGENTIC_LOOP_CONTEXT_PROMPT = "agentic_loop.context_prompt"
    HANDOFF_SYSTEM_PROMPT = "handoff.system_prompt"
    INDEPENDENT_CRITIC_REVIEWER_SYSTEM_PROMPT = "independent_critic.reviewer_system_prompt"
    INDEPENDENT_CRITIC_REVIEW_PROMPT = "independent_critic.review_prompt"
    CONTINUAL_TRACE_SYSTEM_PROMPT = "continual_trace.system_prompt"
    CONTEXT_ENGINEERING_GUIDELINE_PROMPT = "context_engineering.guideline_prompt"
    EXPERT_PROMPTING_EXPERT_PROMPT = "expert_prompting.expert_prompt"
    GOALS_GOAL_PROMPT = "goals.goal_prompt"
    MIMIC_BEHAVIOR_MIMIC_PROMPT = "mimic_behavior.mimic_prompt"
    REFLEXION_AGENT_SYSTEM_PROMPT = "reflexion.agent_system_prompt"
    REFLEXION_REFLECT_SYSTEM_PROMPT = "reflexion.reflect_system_prompt"
    REFLEXION_REFLECT_PROMPT = "reflexion.reflect_prompt"
    PROMPT_ENGINEERING_MASTER_PROMPT = "prompt_engineering.master_prompt"
    EVALS_LLM_JUDGE = "evals.llm_judge"
    EVALS_RUBRIC = "evals.rubric"
    MULTI_PROVIDER_AGENTIC_GRADER_AGENT_SYSTEM_PROMPT = "multi_provider_agentic_grader.agent_system_prompt"
    MULTI_PROVIDER_AGENTIC_GRADER_GRADER_SYSTEM_PROMPT = "multi_provider_agentic_grader.grader_system_prompt"
    MULTI_PROVIDER_AGENTIC_GRADER_GRADER_PROMPT = "multi_provider_agentic_grader.grader_prompt"
    MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_SYSTEM_PROMPT = "multi_provider_aggregator.synthesis_system_prompt"
    MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_PROMPT = "multi_provider_aggregator.synthesis_prompt"
    MULTI_AGENT_ORCHESTRATOR_PLANNING_PROMPT = "multi_agent_orchestrator.planning_prompt"
    MULTI_AGENT_ORCHESTRATOR_PROGRESS_PROMPT = "multi_agent_orchestrator.progress_prompt"
    MULTI_AGENT_ORCHESTRATOR_REPLANNING_PROMPT = "multi_agent_orchestrator.replanning_prompt"
    MULTI_AGENT_ORCHESTRATOR_FINAL_PROMPT = "multi_agent_orchestrator.final_prompt"
    TEMPLATES_INTENT_BASED = "templates.intent_based"
    TEMPLATES_PERSONA = "templates.persona"
    TEMPLATES_SPECIFICATION = "templates.specification"
    TEMPLATES_MASTER = "templates.master"
    ACTOR_RUNTIME_PLANNER = "actor_runtime.planner"
    ACTOR_RUNTIME_CODER = "actor_runtime.coder"
    ACTOR_RUNTIME_REVIEWER = "actor_runtime.reviewer"
    ACTOR_RUNTIME_GENERATOR = "actor_runtime.generator"
    ACTOR_RUNTIME_CRITIC = "actor_runtime.critic"
    ACTOR_RUNTIME_REASONER = "actor_runtime.reasoner"
    ACTOR_RUNTIME_SUMMARIZATION = "actor_runtime.summarization"
    ACTOR_RUNTIME_DECOMPOSER = "actor_runtime.decomposer"
    ACTOR_RUNTIME_EXPLORER = "actor_runtime.explorer"
    ACTOR_RUNTIME_TRADEOFF = "actor_runtime.tradeoff"
    ACTOR_RUNTIME_HYPOTHESIS_GENERATOR = "actor_runtime.hypothesis_generator"
    ACTOR_RUNTIME_REFINER = "actor_runtime.refiner"
    ACTOR_RUNTIME_FORMATTER = "actor_runtime.formatter"
    ACTOR_RUNTIME_SAFETY = "actor_runtime.safety"
    ACTOR_RUNTIME_FINAL_ANSWER = "actor_runtime.final_answer"
    TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER = "trajectory_checkpoints.agentic_summarizer"
    PROBLEM_SPACE_SEARCH_EXPLORER = "problem_space_search.explorer"
    ERROR_CORRECTION_AUDITOR = "error_correction.auditor"
    PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_SYSTEM_PROMPT = "prosecutor_defender_judge.prosecutor_system_prompt"
    PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_PROMPT = "prosecutor_defender_judge.prosecutor_prompt"
    PROSECUTOR_DEFENDER_JUDGE_DEFENDER_SYSTEM_PROMPT = "prosecutor_defender_judge.defender_system_prompt"
    PROSECUTOR_DEFENDER_JUDGE_DEFENDER_PROMPT = "prosecutor_defender_judge.defender_prompt"
    PROSECUTOR_DEFENDER_JUDGE_JUDGE_SYSTEM_PROMPT = "prosecutor_defender_judge.judge_system_prompt"
    PROSECUTOR_DEFENDER_JUDGE_JUDGE_PROMPT = "prosecutor_defender_judge.judge_prompt"

__all__ = [
    "Prompt",
]
