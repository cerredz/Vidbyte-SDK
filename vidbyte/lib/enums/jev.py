"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines Jev's closed vocabularies: TypeSafe question types, preflight presets, every opt-in done check and fixed question key (including output-count, input-set, motivating-case, scope-coverage, output-extent, report/action-alignment, assumption-reconciliation, required-actions, cumulative-obligations, discovered-item-coverage, expert-depth, and self-review checks), motivating-case classifications, and dynamic problem-item kinds. Negative coverage is an opt-in done check with a fixed question key. Guaranteed-next-action judgments have separate fixed question keys. Run-brief item statuses, approach outcomes, and refresh statuses describe the mid-run brief `vidbyte/agents/jev/brief/` keeps.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, `vidbyte/agents/jev/gate/` matches on presets, and `vidbyte/agents/jev/done/` builds enabled done-check schemas and questions.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, record layer, and tool layer all read it, and lower layers may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a TypeSafe question type only when documented, and extend validation and answer normalization with it. Add preflight keys with their fixed question dataclasses and preset registration. Add a done check together with its run-state and handoff sections and one fixed question in `vidbyte/lib/jev/done/`; post-run-derived items belong in the handoff.
KNOWN EDGE CASES: `noul` is TypeSafe's spelling for a yes/no question; keep the serialized value exactly as the API expects. A question key's value is the answer name Jev returns, so it must remain unique. TOOL_SELECTOR has no question keys because it asks one question per configured tool at run time.
RELATED DOCS: docs/design/jev-can-simplify-done-criteria.md, docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, skills/jev-continuation/SKILL.md, and https://docs.typesafe.ai/api.md, docs/design/jev-negative-coverage.md, docs/design/jev-mid-run-problem-repair-gate.md, docs/design/jev-guaranteed-next-actions.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, docs/design/jev-discovered-item-coverage.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py, tests/test_jev_done.py.
"""

from __future__ import annotations

from enum import Enum


class JevQuestionType(str, Enum):
    """TypeSafe System One question types."""

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class JevPreflightPreset(str, Enum):
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflightGate (fixed-question presets) or the tool selector acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"
    RUN_STATE_RELATION = "run_state_relation"
    BULK_WORK = "bulk_work"


# Load skills/jev-continuation/SKILL.md before adding a member here: it is the step-by-step checklist for adding
# a continuation done check (run-state and handoff sections, the batched Jev question, and the continuation message).
class JevDoneCheck(str, Enum):
    """The done checks a JevAgent user can enable; each assembles the items and evidence it needs and asks Jev before a run may finish."""

    MULTI_PART = "multi_part"
    CAN_SIMPLIFY = "can_simplify"
    OUTPUT_COUNT = "output_count"
    CLAIMS = "claims"
    INPUT_EXHAUSTION = "input_exhaustion"
    NEGATIVE_COVERAGE = "negative_coverage"
    GUARANTEED_NEXT_ACTIONS = "guaranteed_next_actions"
    TARGET_OUTCOME = "target_outcome"
    MOTIVATING_CASE = "motivating_case"
    SCOPE_COVERAGE = "scope_coverage"
    COMPLETION_EVIDENCE = "completion_evidence"
    INPUT_SET_COVERAGE = "input_set_coverage"

    OUTPUT_EXTENT = "output_extent"
    REPORT_ACTION_ALIGNMENT = "report_action_alignment"
    ASSUMPTIONS_RECONCILED = "assumptions_reconciled"
    PROBLEMS_RESOLVED = "problems_resolved"
    PHASE_PROGRESS = "phase_progress"
    REQUIRED_ACTIONS = "required_actions"
    CUMULATIVE_OBLIGATIONS = "cumulative_obligations"
    DISCOVERED_ITEM_COVERAGE = "discovered_item_coverage"
    FAITHFUL_SCOPE = "faithful_scope"
    EXPERT_DEPTH = "expert_depth"
    SELF_REVIEW = "self_review"
    REQUIRED_SEQUENCE = "required_sequence"


class JevContinuationGate(str, Enum):
    """How JevAgent applies a failed done check before returning to work."""

    SAME_CONTEXT = "same_context"
    FRESH = "fresh"


class JevDoneQuestionKey(str, Enum):
    """The key of every fixed done question, prefixed by the done check that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    MULTI_PART_DELIVERED = "multi_part.delivered"
    CAN_SIMPLIFY_IMPLEMENTATION = "can_simplify.implementation"
    OUTPUT_COUNT_SATISFIED = "output_count.satisfied"
    CLAIMS_SUPPORTED = "claims.supported"
    INPUT_EXHAUSTION_TRAVERSED = "input_exhaustion.traversed"
    NEGATIVE_COVERAGE_SUPPORTED = "negative_coverage.supported"
    GUARANTEED_NEXT_ACTIONS_NECESSARY = "guaranteed_next_actions.necessary"
    GUARANTEED_NEXT_ACTIONS_UNFINISHED = "guaranteed_next_actions.unfinished"
    TARGET_OUTCOME_DEMONSTRATED = "target_outcome.demonstrated"
    MOTIVATING_CASE_RECALL = "motivating_case.recall"
    MOTIVATING_CASE_EXERCISED = "motivating_case.exercised"
    COMPLETION_EVIDENCE_SUPPORTED = "completion_evidence.supported"
    INPUT_SET_COVERAGE_ENGAGED = "input_set_coverage.engaged"

    OUTPUT_EXTENT_SATISFIED = "output_extent.satisfied"
    REPORT_ACTION_ALIGNMENT_MATCHED = "report_action_alignment.matched"
    ASSUMPTIONS_RECONCILED_REVISITED = "assumptions_reconciled.revisited"
    PROBLEMS_RESOLVED_FIXED = "problems_resolved.fixed"
    PHASE_PROGRESS_REACHED = "phase_progress.reached"
    SCOPE_COVERAGE_BREADTH = "scope_coverage.breadth"
    SCOPE_COVERAGE_APPLIED = "scope_coverage.applied"
    REQUIRED_SEQUENCE_WORK_SHOWN = "required_sequence.work_shown"
    REQUIRED_SEQUENCE_USES_PREVIOUS_OUTPUT = "required_sequence.uses_previous_output"
    REQUIRED_ACTIONS_COMPLETED = "required_actions.completed"
    CUMULATIVE_OBLIGATION_FULFILLED = "cumulative_obligations.fulfilled"
    CUMULATIVE_USER_TURN_RECONCILED = "cumulative_obligations.user_turn_reconciled"
    DISCOVERED_ITEM_PROCESSED = "discovered_item_coverage.processed"
    DISCOVERED_ITEM_INVENTORY_COMPLETE = "discovered_item_coverage.inventory_complete"
    FAITHFUL_SCOPE = "faithful_scope"
    EXPERT_DEPTH_HANDLED = "expert_depth.handled"
    SELF_REVIEW_RESOLVED = "self_review.resolved"
    SELF_REVIEW_IN_SCOPE = "self_review.in_scope"


class JevBoundaryKind(str, Enum):
    """Kinds of boundary condition a motivating-case check may describe."""

    EMPTY_OR_MISSING = "empty_or_missing"
    SIZE_OR_LIMIT = "size_or_limit"
    REPEAT_OR_RETRY = "repeat_or_retry"
    FAILURE_PATH = "failure_path"
    CONFLICTING_STATE = "conflicting_state"
    ORDERING_OR_TIMING = "ordering_or_timing"
    ACCESS = "access"
    FORMAT = "format"
    OTHER = "other"


class JevScenarioRole(str, Enum):
    """Whether a scenario was named by the user or inferred by the state writer."""

    MOTIVATING = "motivating"
    REQUESTED = "requested"
    IMPLIED = "implied"


class JevExerciseMode(str, Enum):
    """Which evidence can satisfy a motivating scenario."""

    RUN = "run"
    RUN_OR_INSPECT = "run_or_inspect"
    INSPECT_ONLY = "inspect_only"


class JevScopeBreadth(str, Enum):
    """How much of a group the request asks the change to reach."""

    EVERY_MEMBER = "every_member"
    NAMED_LIST = "named_list"
    ONE_EXAMPLE = "one_example"
    SINGLE_TARGET = "single_target"

    def is_checked(self) -> bool:
        """Return whether the requested breadth covers multiple members."""
        return self in (JevScopeBreadth.EVERY_MEMBER, JevScopeBreadth.NAMED_LIST)


class JevScopeUniverse(str, Enum):
    """Where the members of a scope group are identified."""

    NAMED_IN_REQUEST = "named_in_request"
    FOUND_IN_WORKSPACE = "found_in_workspace"
    OPEN_ENDED = "open_ended"


class JevScopeUnitSource(str, Enum):
    """How one unit was identified in the run handoff."""

    NAMED_IN_REQUEST = "named_in_request"
    FOUND_BY_RUN = "found_by_run"
    MENTIONED_BY_AGENT = "mentioned_by_agent"


class JevCompletionStatus(str, Enum):
    """The whole-task completion status communicated by a JevAgent final answer."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    UNCLEAR = "unclear"


class JevOutputExtentUnit(str, Enum):
    """Text units supported by the OUTPUT_EXTENT request schema."""

    WORDS = "words"
    CHARACTERS = "characters"
    LINES = "lines"
    SECTIONS = "sections"
    PAGES = "pages"


class JevOutputExtentComparator(str, Enum):
    """Directions of explicit numeric bounds for an output extent."""

    MINIMUM = "minimum"
    EXACT = "exact"
    MAXIMUM = "maximum"


class JevProblemCheckItemType(str, Enum):
    """The two dynamic item kinds judged by the problem-resolution check."""

    PROBLEM = "problem"
    REQUEST_COMPLETION = "request_completion"


class JevSkillStatus(str, Enum):
    """Outcome of evaluating one configured skill for the current request."""

    SELECTED = "selected"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"


class JevRunBriefUpdateStatus(str, Enum):
    """Outcome of one scheduled mid-run brief refresh attempt."""

    UPDATED = "updated"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class JevClaimKind(str, Enum):
    """The closed categories of factual assertions the CLAIMS handoff can describe."""

    SOURCE_CONTENT = "source_content"
    ARTIFACT_CHANGE = "artifact_change"
    COMMAND_RESULT = "command_result"
    TEST_RESULT = "test_result"
    RUN_ACTIVITY = "run_activity"
    OTHER_FACT = "other_fact"


class JevPreflightQuestionKey(str, Enum):
    """The key of every fixed preflight question, prefixed by the preset that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    CLARITY_ACTION = "clarity.action"
    CLARITY_OBJECT = "clarity.object"
    CLARITY_DELIVERABLE = "clarity.deliverable"
    CLARITY_TARGET = "clarity.target"
    CLARITY_REFERENCES = "clarity.references"
    CLARITY_SCOPE_PARTS = "clarity.scope_parts"
    CLARITY_SCOPE_SIZE = "clarity.scope_size"
    RUN_STATE_RELATION = "run_state_relation"
    BULK_WORK_MULTIPLE_ITEMS = "bulk_work.multiple_items"
    BULK_WORK_KNOWN_ITEMS = "bulk_work.known_items"
    BULK_WORK_SAME_OPERATION = "bulk_work.same_operation"
    BULK_WORK_SEPARATE_RESULTS = "bulk_work.separate_results"
    BULK_WORK_INDEPENDENT_ITEMS = "bulk_work.independent_items"
    BULK_WORK_SEPARATE_CHANGES = "bulk_work.separate_changes"
    BULK_WORK_ANY_ORDER = "bulk_work.any_order"
    BULK_WORK_SUBSTANTIAL_ITEMS = "bulk_work.substantial_items"
    CLARITY_COMPLETION = "clarity.completion"
    CLARITY_INFORMATION = "clarity.information"
    CLARITY_CONSTRAINTS = "clarity.constraints"
    CLARITY_PRIORITIES = "clarity.priorities"
    CLARITY_CONSISTENCY = "clarity.consistency"
    CLARITY_TIME_CONTEXT = "clarity.time_context"
    CLARITY_SINGLE_READING = "clarity.single_reading"


class JevDynamicComputeOption(str, Enum):
    """A kind of additional agent compute the mid-run checkpoint can select, in tie-break order."""

    FRESH_AGENT = "fresh_agent"
    FORK_AGENT = "fork_agent"
    SUBAGENT = "subagent"
    CLONE = "clone"
    SWARM = "swarm"


class JevComputeQuestionKey(str, Enum):
    """The key of every fixed dynamic-compute evidence question."""

    FRESH_AGENT_ERROR_RATE_RISING = "fresh_agent.error_rate_rising"
    FRESH_AGENT_SAME_FAILURE_PERSISTS = "fresh_agent.same_failure_persists"
    FRESH_AGENT_REPEATED_ACTION_NO_INFORMATION = "fresh_agent.repeated_action_no_information"
    FRESH_AGENT_DRIFT_FROM_USER_GOAL = "fresh_agent.drift_from_user_goal"
    FRESH_AGENT_USER_CONSTRAINT_OMITTED = "fresh_agent.user_constraint_omitted"
    FRESH_AGENT_CLAIM_CONTRADICTS_EVIDENCE = "fresh_agent.claim_contradicts_evidence"
    FRESH_AGENT_DISPROVEN_ASSUMPTION_CONTINUES = "fresh_agent.disproven_assumption_continues"
    FRESH_AGENT_EARLIER_EVIDENCE_IGNORED = "fresh_agent.earlier_evidence_ignored"
    FRESH_AGENT_FIX_INTRODUCES_FAILURE = "fresh_agent.fix_introduces_failure"
    FRESH_AGENT_PLAN_OSCILLATES = "fresh_agent.plan_oscillates"
    FRESH_AGENT_LOST_CONTINUITY = "fresh_agent.lost_continuity"
    FRESH_AGENT_BRIEF_SUPPORTS_RESUME = "fresh_agent.brief_supports_resume"
    FORK_AGENT_DISTINCT_APPROACHES = "fork_agent.distinct_approaches"
    FORK_AGENT_SAME_VERIFIED_STATE = "fork_agent.same_verified_state"
    FORK_AGENT_INDEPENDENT_PATHS = "fork_agent.independent_paths"
    FORK_AGENT_BOUNDED_EXPERIMENTS = "fork_agent.bounded_experiments"
    FORK_AGENT_COMMON_SUCCESS_CONDITION = "fork_agent.common_success_condition"
    FORK_AGENT_NO_CLEAR_WINNER = "fork_agent.no_clear_winner"
    FORK_AGENT_NON_FORECLOSING = "fork_agent.non_foreclosing"
    FORK_AGENT_ISOLATED_SIDE_EFFECTS = "fork_agent.isolated_side_effects"
    FORK_AGENT_PARALLEL_EVIDENCE = "fork_agent.parallel_evidence"
    FORK_AGENT_DIFFERENT_HYPOTHESES = "fork_agent.different_hypotheses"
    FORK_AGENT_SELECTABLE_RESULT = "fork_agent.selectable_result"
    FORK_AGENT_REQUEST_ALIGNED_PATHS = "fork_agent.request_aligned_paths"
    SUBAGENT_BOUNDED_SUBTASK = "subagent.bounded_subtask"
    SUBAGENT_EXPLICIT_DELIVERABLE = "subagent.explicit_deliverable"
    SUBAGENT_PACKAGED_INPUTS = "subagent.packaged_inputs"
    SUBAGENT_OWN_TOOL_INTERACTIONS = "subagent.own_tool_interactions"
    SUBAGENT_NO_MIDTASK_DECISIONS = "subagent.no_midtask_decisions"
    SUBAGENT_SEPARATE_FROM_CENTRAL_PATH = "subagent.separate_from_central_path"
    SUBAGENT_INTEGRATABLE_RESULT = "subagent.integratable_result"
    SUBAGENT_PARALLEL_PROGRESS = "subagent.parallel_progress"
    SUBAGENT_FOCUSED_CONTEXT = "subagent.focused_context"
    SUBAGENT_PARTITIONABLE_ITEMS = "subagent.partitionable_items"
    SUBAGENT_ISOLATED_WRITES = "subagent.isolated_writes"
    SUBAGENT_SUBSTANTIVE_WORK = "subagent.substantive_work"
    CLONE_OUTCOME_VARIES = "clone.outcome_varies"
    CLONE_INCIDENTAL_FAILURE = "clone.incidental_failure"
    CLONE_SETTLED_APPROACH = "clone.settled_approach"
    CLONE_CHECKABLE_RESULT = "clone.checkable_result"
    CLONE_RESTATABLE_WORK = "clone.restatable_work"
    CLONE_ISOLATED_ATTEMPTS = "clone.isolated_attempts"
    CLONE_INDEPENDENT_ATTEMPTS = "clone.independent_attempts"
    CLONE_BOUNDED_REMAINING_UNIT = "clone.bounded_remaining_unit"
    CLONE_NO_PENDING_USER_DECISION = "clone.no_pending_user_decision"
    CLONE_COMPARABLE_OUTPUTS = "clone.comparable_outputs"
    CLONE_AFFORDABLE_ATTEMPT = "clone.affordable_attempt"
    CLONE_GOAL_DEPENDS_ON_STEP = "clone.goal_depends_on_step"
    SWARM_MANY_UNITS = "swarm.many_units"
    SWARM_SUBSTANTIAL_UNITS = "swarm.substantial_units"
    SWARM_ENUMERATED_UNITS = "swarm.enumerated_units"
    SWARM_DISJOINT_SCOPES = "swarm.disjoint_scopes"
    SWARM_INDEPENDENT_UNITS = "swarm.independent_units"
    SWARM_SETTLED_CONVENTIONS = "swarm.settled_conventions"
    SWARM_SEPARATE_BLOCKERS = "swarm.separate_blockers"
    SWARM_UNIT_VERIFICATION = "swarm.unit_verification"
    SWARM_ISOLATED_WRITES = "swarm.isolated_writes"
    SWARM_LONG_HORIZON = "swarm.long_horizon"
    SWARM_CONTEXT_OVERFLOW = "swarm.context_overflow"
    SWARM_COMBINED_RESULT = "swarm.combined_result"


class JevSwarmPlanQuestionKey(str, Enum):
    """The key of every fixed question Jev answers about one assignment of a SWARM plan."""

    SELF_CONTAINED = "swarm_plan.self_contained"
    DISJOINT = "swarm_plan.disjoint"
    IN_SCOPE = "swarm_plan.in_scope"
    CHECKABLE_DELIVERABLE = "swarm_plan.checkable_deliverable"


__all__ = ["JevBoundaryKind", "JevClaimKind", "JevCompletionStatus", "JevComputeQuestionKey", "JevContinuationGate", "JevDoneCheck", "JevDoneQuestionKey", "JevDynamicComputeOption", "JevExerciseMode", "JevOutputExtentComparator", "JevOutputExtentUnit", "JevPreflightPreset", "JevPreflightQuestionKey", "JevProblemCheckItemType", "JevQuestionType", "JevRunBriefUpdateStatus", "JevScenarioRole", "JevScopeBreadth", "JevScopeUnitSource", "JevScopeUniverse", "JevSkillStatus", "JevSwarmPlanQuestionKey"]
