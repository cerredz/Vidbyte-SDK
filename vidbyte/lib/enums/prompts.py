"""Agent-readable contract for ``vidbyte/lib/enums/prompts.py``.

FILE:
    vidbyte/lib/enums/prompts.py

PURPOSE:
    Defines the stable typed identifiers for all 64 static prompt assets across 22
    JSON/Markdown-backed families. This file owns identifiers only; prompt text and
    family metadata belong under ``vidbyte/prompts/prompts/``.

ROLE IN CODEBASE:
    ``vidbyte/prompts/catalog.py`` converts descriptor keys into these enum values and
    fails import when an asset lacks a matching member. ``vidbyte/prompts/__init__.py``
    uses the resulting catalog to generate direct string exports. Agents, algorithms,
    evaluations, and MCP handlers use these members instead of filesystem paths.

ARCHITECTURE NOTE:
    Enum values are flattened ``family.leaf`` catalog identities. The asset descriptor,
    enum member, README entry, generated direct import, and installed package resource
    form one public contract; additions must update them atomically.

CLASS INVENTORY:
    Prompt(str, Enum): Typed keys accepted by ``Prompts.get()`` and returned by
    ``Prompts.keys()``. Contract coverage lives in ``tests/test_prompts_interface.py``.

COMMON MODIFICATION PATTERNS:
    Add one member for each new descriptor leaf, preserve every published value, update
    the prompt and family counts above, then run the source and installed-package gates.

WHAT NOT TO DO IN THIS FILE:
    1. Do not store prompt text here; assets are owned by ``vidbyte/prompts/prompts/``.
    2. Do not implement loading or validation here; that belongs to
       ``vidbyte/prompts/catalog.py``.
    3. Do not hand-maintain direct imports here; ``vidbyte/prompts/__init__.py`` derives
       them from catalog records.

KNOWN EDGE CASES:
    A descriptor leaf without an exactly matching enum value raises ConfigurationError
    during prompt-package import. Renaming an existing value is a public compatibility
    break even when the Markdown path is unchanged. The asset and family counts in this
    header are maintained manually and must be reconciled after additions or removals.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/README.md
        Catalog conventions, public usage, family descriptions, and canonical links.
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/failure-pattern-repair-prompts.md
        Requirements and rollout for the five failure-pattern-repair prompt keys.

TESTS:
    ``tests/test_prompts_interface.py`` protects enum/asset synchronization and dynamic
    exports; the package stage verifies installed resource loading. This repository does
    not publish a per-file coverage percentage for enum declarations.
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
    FAILURE_PATTERN_REPAIR_RULEBOOK_FEEDBACK_LOOP = "failure_pattern_repair.rulebook_feedback_loop"
    FAILURE_PATTERN_REPAIR_DEPENDENCY_SHAPE_TRIAGE = "failure_pattern_repair.dependency_shape_triage"
    FAILURE_PATTERN_REPAIR_STAGE_GATE_CONTROLLER = "failure_pattern_repair.stage_gate_controller"
    FAILURE_PATTERN_REPAIR_EVALUATOR_RED_TEAM = "failure_pattern_repair.evaluator_red_team"
    FAILURE_PATTERN_REPAIR_SELECTIVE_REGENERATION_LOOP = "failure_pattern_repair.selective_regeneration_loop"
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
