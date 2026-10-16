"""Agent-readable contract for ``vidbyte/lib/enums/prompts.py``.

FILE:
    vidbyte/lib/enums/prompts.py

PURPOSE:
    Defines the stable typed identifiers for all 139 static prompt assets across 35
    JSON/Markdown-backed families, and the opt-in system-prompt presets an agent can
    attach. This file owns identifiers only; prompt text and family metadata belong
    under ``vidbyte/prompts/prompts/``.

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
    SystemPromptPreset(str, Enum): Presets accepted by ``BaseAgent(system_prompt_presets=)``.
    Each value is a family key whose ``system_prompt`` leaf holds the preset text, so a
    new preset is one member plus one family. Coverage lives in
    ``tests/features/system_prompt_presets/``.

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

    CREATE_SKILLS_CREATE_SKILL = "create_skills.create_skill"
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
    JEV_RUN_STATE_REQUIRED_SEQUENCE_AGENT = "jev_run_state.required_sequence_agent"
    INDEPENDENT_CRITIC_REVIEW_PROMPT = "independent_critic.review_prompt"
    JEV_CLARIFICATION_SYSTEM_PROMPT = "jev_clarification.system_prompt"
    JEV_CLONE_PROMPT = "jev_clone.clone_prompt"
    JEV_CLONE_RESULTS_PROMPT = "jev_clone.results_prompt"
    JEV_CONTINUATION_CONTINUE_PROMPT = "jev_continuation.continue_prompt"
    JEV_BULK_WORK_TOOL_DESCRIPTION = "jev_bulk_work.tool_description"
    JEV_BULK_WORK_TASKS_DESCRIPTION = "jev_bulk_work.tasks_description"
    JEV_BULK_WORK_TASK_PROMPT = "jev_bulk_work.task_prompt"
    JEV_BULK_WORK_WORKER_SYSTEM_PROMPT = "jev_bulk_work.worker_system_prompt"
    JEV_BULK_WORK_SYNTHESIS_PROMPT = "jev_bulk_work.synthesis_prompt"
    JEV_BULK_WORK_REJECTED_PROMPT = "jev_bulk_work.rejected_prompt"
    JEV_BULK_WORK_CLOSED_PROMPT = "jev_bulk_work.closed_prompt"
    JEV_FRESH_CONTINUATION_PROMPT = "jev_fresh_continuation.fresh_prompt"
    JEV_HANDOFF_SYSTEM_PROMPT = "jev_handoff.system_prompt"
    JEV_REVIEW_SYSTEM_PROMPT = "jev_review.system_prompt"
    JEV_RUN_BRIEF_SYSTEM_PROMPT = "jev_run_brief.system_prompt"
    JEV_RUN_BRIEF_UPDATE_PROMPT = "jev_run_brief.update_prompt"
    JEV_RUN_STATE_SYSTEM_PROMPT = "jev_run_state.system_prompt"
    JEV_SWARM_PLAN_PROMPT = "jev_swarm.plan_prompt"
    JEV_SWARM_ASSIGNMENT_PROMPT = "jev_swarm.assignment_prompt"
    JEV_SWARM_RESULTS_PROMPT = "jev_swarm.results_prompt"
    JEV_SWARM_REJECTED_PROMPT = "jev_swarm.rejected_prompt"
    JEV_SWARM_RETRY_PROMPT = "jev_swarm.retry_prompt"
    JEV_SWARM_CLOSED_PROMPT = "jev_swarm.closed_prompt"
    JEV_SWARM_TOOL_DESCRIPTION = "jev_swarm.tool_description"
    JEV_SWARM_CONVENTIONS_DESCRIPTION = "jev_swarm.conventions_description"
    JEV_SWARM_ASSIGNMENTS_DESCRIPTION = "jev_swarm.assignments_description"
    JEV_SWARM_NAME_DESCRIPTION = "jev_swarm.name_description"
    JEV_SWARM_OBJECTIVE_DESCRIPTION = "jev_swarm.objective_description"
    JEV_SWARM_INPUTS_DESCRIPTION = "jev_swarm.inputs_description"
    JEV_SWARM_DELIVERABLE_DESCRIPTION = "jev_swarm.deliverable_description"
    JEV_SWARM_BOUNDARIES_DESCRIPTION = "jev_swarm.boundaries_description"
    JEV_SWARM_VERIFICATION_DESCRIPTION = "jev_swarm.verification_description"
    INFINITE_MEMORY_ROOT_SYSTEM_PROMPT = "infinite_memory.root_system_prompt"
    INFINITE_MEMORY_GENERATOR_SYSTEM_PROMPT = "infinite_memory.generator_system_prompt"
    INFINITE_MEMORY_VERIFIER_SYSTEM_PROMPT = "infinite_memory.verifier_system_prompt"
    INFINITE_MEMORY_TASK_PROMPT = "infinite_memory.task_prompt"
    INFINITE_MEMORY_VERIFIER_TASK_PROMPT = "infinite_memory.verifier_task_prompt"
    INFINITE_MEMORY_RESUME_PROMPT = "infinite_memory.resume_prompt"
    INFINITE_MEMORY_RESULT_CARD = "infinite_memory.result_card"
    INFINITE_MEMORY_REPLAYED_LABEL = "infinite_memory.replayed_label"
    INFINITE_MEMORY_LAUNCH_REJECTED_PROMPT = "infinite_memory.launch_rejected_prompt"
    INFINITE_MEMORY_MEMORY_REJECTED_PROMPT = "infinite_memory.memory_rejected_prompt"
    INFINITE_MEMORY_REMEMBER_SAVED_PROMPT = "infinite_memory.remember_saved_prompt"
    INFINITE_MEMORY_REMEMBER_STAGED_PROMPT = "infinite_memory.remember_staged_prompt"
    INFINITE_MEMORY_NOTE_SAVED_PROMPT = "infinite_memory.note_saved_prompt"
    INFINITE_MEMORY_ENTRY_DROPPED_PROMPT = "infinite_memory.entry_dropped_prompt"
    INFINITE_MEMORY_QUOTA_LINE = "infinite_memory.quota_line"
    INFINITE_MEMORY_MAP_HEADER = "infinite_memory.map_header"
    INFINITE_MEMORY_LAUNCH_TOOL_DESCRIPTION = "infinite_memory.launch_tool_description"
    INFINITE_MEMORY_LAUNCH_TASKS_DESCRIPTION = "infinite_memory.launch_tasks_description"
    INFINITE_MEMORY_LAUNCH_NAME_DESCRIPTION = "infinite_memory.launch_name_description"
    INFINITE_MEMORY_LAUNCH_GOAL_DESCRIPTION = "infinite_memory.launch_goal_description"
    INFINITE_MEMORY_LAUNCH_DONE_CRITERIA_DESCRIPTION = "infinite_memory.launch_done_criteria_description"
    INFINITE_MEMORY_LAUNCH_GENERATOR_PROMPT_DESCRIPTION = "infinite_memory.launch_generator_prompt_description"
    INFINITE_MEMORY_LAUNCH_VERIFIER_PROMPT_DESCRIPTION = "infinite_memory.launch_verifier_prompt_description"
    INFINITE_MEMORY_LAUNCH_CONTEXT_DESCRIPTION = "infinite_memory.launch_context_description"
    INFINITE_MEMORY_LAUNCH_TOOLS_DESCRIPTION = "infinite_memory.launch_tools_description"
    INFINITE_MEMORY_REMEMBER_TOOL_DESCRIPTION = "infinite_memory.remember_tool_description"
    INFINITE_MEMORY_REMEMBER_KIND_DESCRIPTION = "infinite_memory.remember_kind_description"
    INFINITE_MEMORY_REMEMBER_TEXT_DESCRIPTION = "infinite_memory.remember_text_description"
    INFINITE_MEMORY_REMEMBER_TAGS_DESCRIPTION = "infinite_memory.remember_tags_description"
    INFINITE_MEMORY_REMEMBER_REFS_DESCRIPTION = "infinite_memory.remember_refs_description"
    INFINITE_MEMORY_REMEMBER_SUPERSEDES_DESCRIPTION = "infinite_memory.remember_supersedes_description"
    INFINITE_MEMORY_WRITE_NOTE_TOOL_DESCRIPTION = "infinite_memory.write_note_tool_description"
    INFINITE_MEMORY_NOTE_PATH_DESCRIPTION = "infinite_memory.note_path_description"
    INFINITE_MEMORY_WRITE_NOTE_TEXT_DESCRIPTION = "infinite_memory.write_note_text_description"
    INFINITE_MEMORY_WRITE_NOTE_FILE_DESCRIPTION = "infinite_memory.write_note_file_description"
    INFINITE_MEMORY_EDIT_FILE_TOOL_DESCRIPTION = "infinite_memory.edit_file_tool_description"
    INFINITE_MEMORY_EDIT_FILE_OLD_TEXT_DESCRIPTION = "infinite_memory.edit_file_old_text_description"
    INFINITE_MEMORY_EDIT_FILE_NEW_TEXT_DESCRIPTION = "infinite_memory.edit_file_new_text_description"
    INFINITE_MEMORY_DROP_ENTRY_TOOL_DESCRIPTION = "infinite_memory.drop_entry_tool_description"
    INFINITE_MEMORY_DROP_ENTRY_ID_DESCRIPTION = "infinite_memory.drop_entry_id_description"
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
    WORKING_PRINCIPLES_SYSTEM_PROMPT = "working_principles.system_prompt"


class SystemPromptPreset(str, Enum):
    """Opt-in system-prompt fragments an agent can attach; each value names the prompt family that holds its text."""

    WORKING_PRINCIPLES = "working_principles"


__all__ = [
    "Prompt",
    "SystemPromptPreset",
]
