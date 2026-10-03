"""FILE: vidbyte/lib/constants/jev.py

PURPOSE: Declares TypeSafe Jev limits, defaults, wire literals, and preflight/done-check policy values shared by decision records, the provider adapter, and the JevAgent layer. Negative-coverage policy uses the shared threshold and state-field contract. Guaranteed-next-action policy requires a separate necessity and unfinished judgment for each candidate. Required actions adds only procedures the request explicitly names. Cumulative obligations preserve requirements across the supplied chronological user turns. Discovered-item coverage inventories bounded recorded outputs and checks requested per-item processing.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates against these bounds, `vidbyte/providers/typesafe.py` builds requests from the same values, `vidbyte/lib/jev/` reads the preflight policy values, and `vidbyte/agents/jev/` reads the tool-selector and clarification values.
ARCHITECTURE NOTE: Values live in `vidbyte.lib` so both lower-layer modules and the tool layer can import them without a layering inversion.
COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it; local sanity caps stay generous because the API enforces the real (token) limits itself.
KNOWN EDGE CASES: Vendor limits are the 255 Choice options and the 2-10 Score levels; question count, state size, and option-name length are local caps only.
RELATED DOCS: docs/design/jev-can-simplify-done-criteria.md, docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-completion-evidence.md, docs/design/jev-phase-progress.md, docs/design/jev-input-set-coverage.md, docs/design/jev-report-action-alignment.md, docs/design/jev-assumption-reconciliation-done-criteria.md, https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/sdk/python/api/retries.md, docs/design/jev-negative-coverage.md, docs/design/jev-mid-run-problem-repair-gate.md, docs/design/jev-guaranteed-next-actions.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-discovered-item-coverage.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, scripts/test-jev-agent-scaffold.py, and tests/test_jev_done.py.
"""

from __future__ import annotations

# Models and endpoints (https://docs.typesafe.ai/models.md). `jev-latest` and `jev-preview`
# are aliases; the response reports the versioned ID (currently `jev-1.13.0`) that answered.
JEV_DEFAULT_MODEL: str = "jev-latest"
JEV_PREVIEW_MODEL: str = "jev-preview"
JEV_SYSTEMONE_PATH: str = "/systemone"
JEV_MODELS_PATH: str = "/models"

# Documented vendor limits (https://docs.typesafe.ai/api.md#question-types).
JEV_MAX_CHOICE_OPTIONS: int = 255
JEV_MIN_SCORE_LEVELS: int = 2
JEV_MAX_SCORE_LEVELS: int = 10

# Local sanity caps. TypeSafe bounds a request by tokens (64k per request, 32k for the state plus
# the longest question), not by these counts, so each cap sits far above anything that fits.
JEV_MIN_CHOICE_OPTIONS: int = 2
JEV_MAX_OPTION_NAME_CHARS: int = 4_096
JEV_MAX_QUESTIONS: int = 10_000
JEV_MAX_STATE_CHARS: int = 1_000_000
JEV_PROBABILITY_SUM_TOLERANCE: float = 0.01

# Transport defaults. The timeout is deliberately longer than the TypeSafe SDK's 10 seconds so a
# large fan-out request is not cut off; retries mirror the SDK's RetryPolicy defaults
# (max_retries=2, 0.5s initial backoff doubling, statuses 408, 429, and every 5xx including 529).
JEV_DEFAULT_TIMEOUT_SECONDS: float = 60.0
JEV_DEFAULT_RETRY_COUNT: int = 2
JEV_NO_RETRIES: int = 0
JEV_TIMEOUT_FLOOR_SECONDS: float = 0.0
JEV_RETRY_BACKOFF_SECONDS: float = 0.5
JEV_MAX_RESPONSE_BYTES: int = 16_000_000

# HTTP statuses the API documents (https://docs.typesafe.ai/api.md#errors).
JEV_STATUS_REQUEST_TIMEOUT: int = 408
JEV_STATUS_UNAUTHORIZED: int = 401
JEV_STATUS_UNPROCESSABLE: int = 422
JEV_STATUS_RATE_LIMITED: int = 429
JEV_STATUS_OVERLOADED: int = 529
JEV_STATUS_SERVER_ERROR_FLOOR: int = 500
JEV_STATUS_SERVER_ERROR_CEILING: int = 600
JEV_RETRY_STATUS_CODES: tuple[int, ...] = (
    JEV_STATUS_REQUEST_TIMEOUT,
    JEV_STATUS_RATE_LIMITED,
    *range(JEV_STATUS_SERVER_ERROR_FLOOR, JEV_STATUS_SERVER_ERROR_CEILING),
)

# Noul wire literals: the optional criteria keys and the two outcomes a noul answer expands to.
JEV_NOUL_TRUE: str = "true"
JEV_NOUL_FALSE: str = "false"
JEV_NOUL_OPTIONS: tuple[str, ...] = (JEV_NOUL_TRUE, JEV_NOUL_FALSE)
JEV_NOUL_YES_THRESHOLD: float = 0.5

# Preflight policy. The request is the only state field preflight questions read, and a fixed-question
# preset's score is the mean P(yes) of its questions; below the threshold the preset fails.
# 0.75 is a starting point, not a value tuned on a labeled set.
JEV_PREFLIGHT_REQUEST_FIELD: str = "request"
JEV_CLARITY_THRESHOLD: float = 0.75
# One clarity question with P(yes) below this fails the preset on its own, so a mean pulled up by many
# easy yes answers cannot hide one clear no. Also a starting point, not a tuned value.
JEV_CLARITY_VETO_THRESHOLD: float = 0.2
# A run the preflight gate stops reports this strategy name.
JEV_PREFLIGHT_STRATEGY_NAME: str = "jev_preflight"
# JevClarificationAgent limits: its loop and token budget, and the size of the structured reply it must
# return (a few clarifying questions, each with a few recommended answers the user can pick from).
JEV_CLARIFICATION_MAX_ITERATIONS: int = 25
JEV_CLARIFICATION_MAX_TOKENS: int = 100_000
JEV_CLARIFICATION_MAX_QUESTIONS: int = 6
JEV_CLARIFICATION_MIN_RECOMMENDATIONS: int = 2
JEV_CLARIFICATION_MAX_RECOMMENDATIONS: int = 4
# Specialist choice: the question's answer key, and the way-out option that keeps the main JevAgent on the
# run. Every specialist is one more Choice option beside `none`, so the count stops one below the vendor limit.
JEV_SPECIALIST_QUESTION_NAME: str = "specialist"
JEV_SPECIALIST_NONE: str = "none"
JEV_SPECIALIST_MAX_COUNT: int = JEV_MAX_CHOICE_OPTIONS - 1

# Done checks. Every enabled check asks its questions in one request on each finish attempt. A check's
# threshold is used as both the mean threshold and veto, so one clear no is not averaged away.
# Both thresholds are starting points, not values tuned on a labeled set.
JEV_MULTI_PART_THRESHOLD: float = 0.8
JEV_CAN_SIMPLIFY_THRESHOLD: float = 0.8
# Every explicit output-count obligation must independently reach the threshold; starting point, not tuned.
JEV_OUTPUT_COUNT_THRESHOLD: float = 0.8
# Each checkable final-answer claim must reach this P(yes), alone and in the mean, before it is considered supported.
JEV_CLAIMS_THRESHOLD: float = 0.85
# Every explicitly bounded input target must have evidence of the requested level of engagement.
JEV_INPUT_SET_COVERAGE_THRESHOLD: float = 0.8
# A dynamic collection must be supported by trace evidence of its stopping condition, not merely a plausible answer.
JEV_INPUT_EXHAUSTION_THRESHOLD: float = 0.85
# A requested inspection target with a negative or explicitly incomplete report must show matching inspection evidence.
JEV_NEGATIVE_COVERAGE_THRESHOLD: float = 0.85
# Each candidate must independently pass the necessity and unfinished judgments.
JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD: float = 0.9
# Evidence for the requested outcome must reach this P(yes), alone and in the mean; this is a starting point, not tuned.
JEV_TARGET_OUTCOME_THRESHOLD: float = 0.8
# Every motivating scenario must independently reach this P(yes) to pass the gate.
JEV_MOTIVATING_CASE_THRESHOLD: float = 0.8
# A one-time raw-request recall guard may trigger one focused state rebuild above this probability.
JEV_MOTIVATING_CASE_RECALL_THRESHOLD: float = 0.6
# Bound scenarios returned from one request so a broad prompt cannot create an unbounded question batch.
JEV_MOTIVATING_CASE_MAX_SCENARIOS: int = 12
# Each covered member must independently reach this P(yes); missing run evidence is an automatic gap.
JEV_SCOPE_COVERAGE_THRESHOLD: float = 0.8
# A one-time request-only review can widen a narrow label once when Jev recognizes broader wording.
JEV_SCOPE_BREADTH_UPGRADE_THRESHOLD: float = 0.5
# Whether the final answer's whole-task completion status is supported; starting point, not tuned on a labeled set.
JEV_COMPLETION_EVIDENCE_THRESHOLD: float = 0.85

# Explicit requested output extents must meet this threshold and the per-item numeric comparator.
JEV_OUTPUT_EXTENT_THRESHOLD: float = 0.8
# A report/action candidate must reach this P(yes) to count as aligned; this is both the mean threshold and
# veto, and is a starting point rather than a value tuned on a labeled set.
JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD: float = 0.85
# Starting P(yes) threshold and veto for observable reconciliation of consequential assumptions; not calibrated.
JEV_ASSUMPTIONS_RECONCILED_THRESHOLD: float = 0.8
# Every observed problem and the original request must independently reach this P(yes).
JEV_PROBLEMS_RESOLVED_THRESHOLD: float = 0.85
# A requested outcome stage must show progress or an evidenced blocker; this is a starting point, not a tuned value.
JEV_PHASE_PROGRESS_THRESHOLD: float = 0.8
# Each explicitly required action must independently reach this P(yes); starting point, not tuned.
JEV_REQUIRED_ACTIONS_THRESHOLD: float = 0.85
# Every active user obligation independently reaches this P(yes); a single clear no is a veto.
JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD: float = 0.85
# Each discovered source inventory and processed item must independently meet this threshold.
JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD: float = 0.8
# Preserve bounded raw tool outputs for source-inventory questions.
JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS: int = 12_000
JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS: int = 48_000
JEV_FAITHFUL_SCOPE_THRESHOLD: float = 0.8
# The expert-depth check asks one question per detail (a weak point of a requested deliverable), with the
# same rule: the threshold is also the veto. It starts lower than multi-part because depth is graded and a
# false "shallow" costs a whole continuation; 0.7 is a starting point, not a tuned value.
JEV_EXPERT_DEPTH_THRESHOLD: float = 0.7
# Every deliverable in the expert-depth section lists this many details, from the weakest point down.
JEV_EXPERT_DEPTH_MIN_DETAILS: int = 3
JEV_EXPERT_DEPTH_MAX_DETAILS: int = 5
# How many of the weakest incomplete details the continuation names under Focus, so the main agent goes
# deep on a few points at a time instead of shallow on all of them; the next finish attempt re-ranks.
JEV_EXPERT_DEPTH_FOCUS_LIMIT: int = 3
# Both self-review judgments use one threshold; an objection clears when resolved or out of scope.
JEV_SELF_REVIEW_THRESHOLD: float = 0.8
JEV_REQUIRED_SEQUENCE_THRESHOLD: float = 0.75
JEV_REQUIRED_SEQUENCE_MIN_STAGES: int = 2
JEV_REQUIRED_SEQUENCE_MAX_STAGES: int = 12
JEV_STAGE_ID_PREFIX: str = "stage_"
JEV_EVENT_LOG_FIRST_ID: int = 1
JEV_EVENT_LOG_ID_INCREMENT: int = 1
JEV_EVENT_LOG_NEXT_ID: int = 2
JEV_EVENT_LOG_INITIAL_ITERATION: int = 0
JEV_EVENT_LOG_ITERATION_OFFSET: int = 1
# Default of JevContinualSettings.max_continuations: how many times a failed done check may send the main
# agent back to work before its answer is accepted.
JEV_DONE_MAX_CONTINUATIONS: int = 3
JEV_CONTINUATION_BUDGET_INITIAL: int = 0
# Extra main-agent capacity granted for each continuation caused by FAITHFUL_SCOPE.
JEV_FAITHFUL_SCOPE_EXTRA_ITERATIONS: int = 2
JEV_FAITHFUL_SCOPE_EXTRA_TOKENS: int = 16_000
JEV_FAITHFUL_SCOPE_EXTRA_TOOL_CALLS: int = 4
# The state fields the done questions read: the user's request, and one entry per deliverable id holding
# the deliverable, the visible condition that shows it is done, and the evidence JevHandoff compiled for it.
JEV_DONE_REQUEST_FIELD: str = "request"
JEV_DONE_DELIVERABLES_FIELD: str = "deliverables"
JEV_DONE_DELIVERABLE_FIELD: str = "deliverable"
JEV_DONE_COMPLETION_SIGNAL_FIELD: str = "completion_signal"
JEV_DONE_OUTPUT_COUNTS_FIELD: str = "output_counts"
JEV_DONE_OUTPUT_COUNT_OBLIGATION_FIELD: str = "obligation"
JEV_DONE_OUTPUT_COUNT_DESCRIPTION_FIELD: str = "description"
JEV_DONE_OUTPUT_COUNT_TARGET_FIELD: str = "target_count"
JEV_DONE_OUTPUT_COUNT_DISTINCT_FIELD: str = "distinct"
JEV_DONE_OUTPUT_COUNT_UNIT_FIELD: str = "unit"
JEV_DONE_OUTPUT_COUNT_SCOPE_FIELD: str = "scope"
JEV_DONE_OUTPUT_COUNT_DISTINCTNESS_FIELD: str = "distinctness"
JEV_DONE_OUTPUT_COUNT_COMPLETION_FIELD: str = "completion_criteria"
JEV_DONE_OUTPUT_COUNT_ENTRIES_FIELD: str = "entries"
JEV_DONE_OUTPUT_COUNT_OBSERVED_FIELD: str = "observed_count"
JEV_DONE_OUTPUT_COUNT_MET_FIELD: str = "target_met"
JEV_DONE_OUTPUT_COUNT_ENTRY_ID_FIELD: str = "id"
JEV_DONE_OUTPUT_COUNT_ENTRY_VALUE_FIELD: str = "value"
JEV_DONE_OUTPUT_COUNT_ENTRY_KEY_FIELD: str = "distinct_key"
JEV_DONE_OUTPUT_COUNT_ENTRY_EVIDENCE_FIELD: str = "evidence"
JEV_DONE_EVIDENCE_FIELD: str = "evidence"
# The can-simplify check compares the implementation against request constraints.
JEV_DONE_IMPLEMENTATION_FIELD: str = "implementation"
JEV_DONE_PRESERVATION_FIELD: str = "preserve"
JEV_DONE_CLAIMS_FIELD: str = "claims"
JEV_DONE_INPUT_ACTION_FIELD: str = "action"
JEV_DONE_INPUT_ENGAGEMENT_SIGNAL_FIELD: str = "engagement_signal"
JEV_DONE_INPUT_IDENTITY_FIELD: str = "identity"
JEV_DONE_INPUT_SCOPE_FIELD: str = "scope"
JEV_DONE_INPUT_SET_COVERAGE_FIELD: str = "input_set_coverage"
JEV_DONE_INPUT_TARGETS_FIELD: str = "targets"
JEV_DONE_INPUT_TARGET_FIELD: str = "target"
JEV_DONE_INPUT_EXHAUSTION_FIELD: str = "input_exhaustion"
JEV_DONE_NEGATIVE_COVERAGE_FIELD: str = "negative_coverage"
JEV_DONE_INSPECTION_FIELD: str = "inspection"
JEV_DONE_GUARANTEED_NEXT_ACTIONS_FIELD: str = "guaranteed_next_actions"
JEV_DONE_OUTCOME_FIELD: str = "outcome"
JEV_DONE_TRIGGER_FIELD: str = "trigger"
JEV_DONE_ACTION_FIELD: str = "action"
JEV_DONE_TARGET_OUTCOMES_FIELD: str = "target_outcomes"
JEV_DONE_TARGET_OUTCOME_FIELD: str = "target_outcome"
JEV_DONE_TARGET_FIELD: str = "target"
JEV_DONE_TARGET_SCOPE_FIELD: str = "scope"
JEV_DONE_COMPLETION_CRITERION_FIELD: str = "completion_criterion"
JEV_DONE_OBSERVED_PROXY_FIELD: str = "observed_proxy"
JEV_DONE_MOTIVATING_CASES_FIELD: str = "motivating_cases"
JEV_DONE_MOTIVATING_CASE_FIELD: str = "motivating_case"
JEV_DONE_COMPLETION_EVIDENCE_FIELD: str = "completion_evidence"
JEV_DONE_COMPLETION_ITEM_ID: str = "task_completion"
JEV_DONE_COMPLETION_ITEM_INDEX: int = 0
JEV_DONE_COMPLETION_STATUS_FIELD: str = "completion_status"
JEV_DONE_REQUESTED_OUTCOMES_FIELD: str = "requested_outcomes"
JEV_DONE_COMPLETED_WORK_FIELD: str = "completed_work"
JEV_DONE_UNFINISHED_OR_BLOCKED_FIELD: str = "unfinished_or_blocked"

JEV_DONE_OUTPUT_EXTENTS_FIELD: str = "output_extents"
JEV_DONE_OUTPUT_EXTENT_FIELD: str = "output_extent"
JEV_DONE_OUTPUT_EXTENT_TARGET_FIELD: str = "target"
JEV_DONE_OUTPUT_EXTENT_AMOUNT_FIELD: str = "amount"
JEV_DONE_OUTPUT_EXTENT_UNIT_FIELD: str = "unit"
JEV_DONE_OUTPUT_EXTENT_COMPARATOR_FIELD: str = "comparator"
JEV_DONE_OUTPUT_EXTENT_EVIDENCE_FIELD: str = "evidence"
JEV_DONE_OUTPUT_EXTENT_OBSERVED_FIELD: str = "observed"
JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD: str = "report_action_alignment"
JEV_DONE_PLAN_FIELD: str = "plan"
JEV_DONE_EXECUTION_FIELD: str = "execution"
JEV_DONE_FINAL_ACCOUNT_FIELD: str = "final_account"
JEV_DONE_REQUEST_RELEVANCE_FIELD: str = "request_relevance"
JEV_DONE_PROBLEMS_RESOLVED_FIELD: str = "problems_resolved"
JEV_DONE_PROBLEM_ITEMS_FIELD: str = "items"
JEV_DONE_PROBLEM_ID_FIELD: str = "id"
JEV_DONE_PROBLEM_KIND_FIELD: str = "kind"
JEV_DONE_PROBLEM_TITLE_FIELD: str = "title"
JEV_DONE_PROBLEM_DESCRIPTION_FIELD: str = "description"
JEV_DONE_PROBLEM_SCOPE_FIELD: str = "scope"
JEV_DONE_PROBLEM_QUALIFICATIONS_FIELD: str = "qualifications"
JEV_DONE_PROBLEM_REPAIR_FIELD: str = "repair"
JEV_DONE_PROBLEM_VERIFICATION_FIELD: str = "verification"
JEV_DONE_PROBLEM_ASSERTION_FIELD: str = "assertion"
JEV_DONE_PHASE_PROGRESS_FIELD: str = "phase_progress"
JEV_DONE_PHASE_STAGE_FIELD: str = "stage"
JEV_DONE_PHASE_REQUIRED_RESULT_FIELD: str = "required_result"
JEV_DONE_PHASE_REQUEST_SCOPE_FIELD: str = "request_scope"
JEV_DONE_PHASE_OUTPUT_CRITERION_FIELD: str = "output_criterion"
JEV_DONE_REQUIRED_ACTIONS_FIELD: str = "required_actions"
# Cumulative obligations preserve the exact supplied turn history, each request-derived obligation, and per-turn evidence.
JEV_DONE_OBLIGATIONS_FIELD: str = "obligations"
JEV_DONE_USER_TURNS_FIELD: str = "user_turns"
JEV_DONE_USER_TURN_EVIDENCE_FIELD: str = "turn_evidence"
JEV_DONE_OBLIGATION_FIELD: str = "obligation"
JEV_DONE_OBLIGATION_SOURCE_TURN_FIELD: str = "source_turn"
JEV_DONE_OBLIGATION_RELATED_TURNS_FIELD: str = "related_turns"
JEV_DONE_OBLIGATION_STATUS_TURN_FIELD: str = "status_turn"
JEV_DONE_OBLIGATION_COMPLETION_SIGNAL_FIELD: str = "completion_signal"
JEV_DONE_OBLIGATION_ACTIVE_FIELD: str = "active"
JEV_DONE_OBLIGATION_STATUS_REASON_FIELD: str = "status_reason"
JEV_MIN_OBLIGATION_STATUS_REASON_CHARS: int = 1
JEV_MIN_OBLIGATION_TURN_INDEX: int = 0
# Discovered-item handoff and state field names.
JEV_DONE_DISCOVERED_ITEMS_FIELD: str = "discovered_items"
JEV_DONE_DISCOVERED_ITEM_INVENTORY_FIELD: str = "inventory"
JEV_DONE_DISCOVERED_ITEM_SOURCE_FIELD: str = "source_output"
JEV_DONE_DISCOVERED_ITEM_CANDIDATES_FIELD: str = "candidates"
JEV_DONE_DISCOVERED_ITEM_FIELD: str = "item"
JEV_DONE_DISCOVERED_ITEM_ACTION_FIELD: str = "requested_processing"
JEV_DONE_DISCOVERED_ITEM_CRITERIA_FIELD: str = "completion_criteria"
JEV_DONE_DISCOVERED_ITEM_EVIDENCE_FIELD: str = "processing_evidence"
JEV_DONE_DISCOVERED_ITEM_GAP_FIELD: str = "missing"
JEV_DONE_DISCOVERED_ITEM_SOURCE_ID_FIELD: str = "source_id"
JEV_DONE_DISCOVERED_ITEM_IDENTITY_FIELD: str = "identity"
JEV_DONE_CLAIM_FIELD: str = "claim"
JEV_DONE_CLAIM_IDENTITY_FIELD: str = "identity"
JEV_DONE_CLAIM_TITLE_FIELD: str = "title"
JEV_DONE_CLAIM_DESCRIPTION_FIELD: str = "description"
JEV_DONE_CLAIM_INTENT_FIELD: str = "intent"
JEV_DONE_CLAIM_SCOPE_FIELD: str = "scope"
JEV_DONE_CLAIM_QUALIFICATIONS_FIELD: str = "qualifications"
JEV_DONE_CLAIM_KIND_FIELD: str = "kind"
JEV_DONE_CLAIM_OUTPUT_FIELD: str = "output"
JEV_DONE_CLAIM_ASSERTION_FIELD: str = "assertion"
JEV_DONE_CLAIM_ASSERTION_ID_FIELD: str = "id"
JEV_DONE_CLAIM_ASSERTION_STATEMENT_FIELD: str = "statement"
JEV_DONE_CLAIM_COMPLETION_CRITERIA_FIELD: str = "completion_criteria"
JEV_DONE_CLAIM_ASSERTION_SEPARATOR: str = "."
JEV_DONE_SCOPE_COVERAGE_FIELD: str = "scope_coverage"
JEV_DONE_SCOPE_DIMENSIONS_FIELD: str = "dimensions"
JEV_DONE_SCOPE_REQUEST_QUOTE_FIELD: str = "request_quote"
JEV_DONE_SCOPE_REQUESTED_CHANGE_FIELD: str = "requested_change"
JEV_DONE_SCOPE_UNIT_NOUN_FIELD: str = "unit_noun"
JEV_DONE_SCOPE_UNIT_FIELD: str = "unit"
JEV_DONE_SCOPE_MEMBERSHIP_RULE_FIELD: str = "membership_rule"
# The assumption check is post-run-derived and carries one entry per explicit, consequential premise later contradicted.
JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD: str = "assumptions_reconciled"
JEV_DONE_ORIGINAL_ASSUMPTION_FIELD: str = "original_assumption"
JEV_DONE_ORIGINAL_BASIS_FIELD: str = "original_basis"
JEV_DONE_LATER_OBSERVATION_FIELD: str = "later_observation"
JEV_DONE_AFFECTED_WORK_FIELD: str = "affected_work"
JEV_DONE_REVISION_FIELD: str = "revision"
JEV_DONE_HARD_PART_FIELD: str = "hard_part"
JEV_DONE_MISSING_FIELD: str = "missing"
JEV_DONE_WHAT_NOT_TO_DO_FIELD: str = "what_not_to_do"
# The expert-depth entries, one per detail id: the deliverable (JEV_DONE_DELIVERABLE_FIELD), the detail, what
# its shallow version looks like, the visible condition that shows it handled in depth, and the evidence.
JEV_DONE_EXPERT_DETAILS_FIELD: str = "expert_details"
JEV_DONE_DETAIL_FIELD: str = "detail"
JEV_DONE_SHALLOW_VERSION_FIELD: str = "shallow_version"
JEV_DONE_DONE_WHEN_FIELD: str = "done_when"
# Post-run reviewer objections and their request-derived resolution conditions.
JEV_DONE_OBJECTIONS_FIELD: str = "objections"
JEV_DONE_OBJECTION_FIELD: str = "objection"
JEV_DONE_RESOLVED_WHEN_FIELD: str = "resolved_when"
# A deliverable ID is a short lowercase identifier JevRunState writes and JevHandoff must echo exactly.
JEV_DELIVERABLE_ID_PATTERN: str = r"^[a-z][a-z0-9_]{0,63}$"
# Defaults of the JevRunState and JevHandoff limits in JevContinualSettings: each writes one structured reply,
# so their loops stay short; the handoff reads the main agent's whole run, so its token budget is larger.
JEV_RUN_STATE_MAX_ITERATIONS: int = 25
JEV_RUN_STATE_MAX_TOKENS: int = 100_000
JEV_HANDOFF_MAX_ITERATIONS: int = 25
JEV_HANDOFF_MAX_TOKENS: int = 400_000
# Defaults of the JevReviewer limits: like the handoff it reads the main agent's whole run and writes one reply.
JEV_REVIEW_MAX_ITERATIONS: int = 25
JEV_REVIEW_MAX_TOKENS: int = 400_000
# Keep the reviewer question batch bounded and focused on the most serious objections.
JEV_REVIEW_MAX_OBJECTIONS: int = 5

# Tool-selector policy bounds and default: caller settings use probabilities on the closed unit interval.
JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD: float = 0.20
JEV_TOOL_SELECTOR_MAX_THRESHOLD: float = 1.0
JEV_TOOL_SELECTOR_MIN_THRESHOLD: float = 0.0

__all__ = [
    "JEV_CLAIMS_THRESHOLD",
    "JEV_CAN_SIMPLIFY_THRESHOLD",
    "JEV_GUARANTEED_NEXT_ACTIONS_THRESHOLD",
    "JEV_INPUT_EXHAUSTION_THRESHOLD",
    "JEV_INPUT_SET_COVERAGE_THRESHOLD",
    "JEV_ASSUMPTIONS_RECONCILED_THRESHOLD",

    "JEV_OUTPUT_EXTENT_THRESHOLD",
    "JEV_CLARIFICATION_MAX_ITERATIONS",
    "JEV_CLARIFICATION_MAX_QUESTIONS",
    "JEV_CLARIFICATION_MAX_RECOMMENDATIONS",
    "JEV_CLARIFICATION_MAX_TOKENS",
    "JEV_CLARIFICATION_MIN_RECOMMENDATIONS",
    "JEV_CLARITY_THRESHOLD",
    "JEV_CLARITY_VETO_THRESHOLD",
    "JEV_COMPLETION_EVIDENCE_THRESHOLD",
    "JEV_CONTINUATION_BUDGET_INITIAL",
    "JEV_FAITHFUL_SCOPE_EXTRA_ITERATIONS",
    "JEV_FAITHFUL_SCOPE_EXTRA_TOKENS",
    "JEV_FAITHFUL_SCOPE_EXTRA_TOOL_CALLS",
    "JEV_FAITHFUL_SCOPE_THRESHOLD",
    "JEV_DEFAULT_MODEL",
    "JEV_DEFAULT_RETRY_COUNT",
    "JEV_DEFAULT_TIMEOUT_SECONDS",
    "JEV_DONE_ACTION_FIELD",
    "JEV_DONE_REQUIRED_ACTIONS_FIELD",
    "JEV_EVENT_LOG_FIRST_ID",
    "JEV_EVENT_LOG_ID_INCREMENT",
    "JEV_EVENT_LOG_INITIAL_ITERATION",
    "JEV_EVENT_LOG_ITERATION_OFFSET",
    "JEV_EVENT_LOG_NEXT_ID",
    "JEV_DELIVERABLE_ID_PATTERN",
    "JEV_DONE_COMPLETION_SIGNAL_FIELD",
    "JEV_DONE_OUTPUT_COUNTS_FIELD",
    "JEV_DONE_OUTPUT_COUNT_OBLIGATION_FIELD",
    "JEV_DONE_OUTPUT_COUNT_DESCRIPTION_FIELD",
    "JEV_DONE_OUTPUT_COUNT_TARGET_FIELD",
    "JEV_DONE_OUTPUT_COUNT_DISTINCT_FIELD",
    "JEV_DONE_OUTPUT_COUNT_UNIT_FIELD",
    "JEV_DONE_OUTPUT_COUNT_SCOPE_FIELD",
    "JEV_DONE_OUTPUT_COUNT_DISTINCTNESS_FIELD",
    "JEV_DONE_OUTPUT_COUNT_COMPLETION_FIELD",
    "JEV_DONE_OUTPUT_COUNT_ENTRIES_FIELD",
    "JEV_DONE_OUTPUT_COUNT_OBSERVED_FIELD",
    "JEV_DONE_OUTPUT_COUNT_MET_FIELD",
    "JEV_DONE_OUTPUT_COUNT_ENTRY_ID_FIELD",
    "JEV_DONE_OUTPUT_COUNT_ENTRY_VALUE_FIELD",
    "JEV_DONE_OUTPUT_COUNT_ENTRY_KEY_FIELD",
    "JEV_DONE_CLAIM_FIELD",
    "JEV_DONE_CLAIMS_FIELD",
    "JEV_DONE_CLAIM_ASSERTION_FIELD",
    "JEV_DONE_CLAIM_ASSERTION_ID_FIELD",
    "JEV_DONE_CLAIM_ASSERTION_SEPARATOR",
    "JEV_DONE_ASSUMPTIONS_RECONCILED_FIELD",
    "JEV_DONE_ORIGINAL_ASSUMPTION_FIELD",
    "JEV_DONE_ORIGINAL_BASIS_FIELD",
    "JEV_DONE_LATER_OBSERVATION_FIELD",
    "JEV_DONE_AFFECTED_WORK_FIELD",
    "JEV_DONE_REVISION_FIELD",
    "JEV_DONE_CLAIM_ASSERTION_STATEMENT_FIELD",
    "JEV_DONE_CLAIM_COMPLETION_CRITERIA_FIELD",
    "JEV_DONE_CLAIMS_FIELD",
    "JEV_DONE_INPUT_ACTION_FIELD",
    "JEV_DONE_INPUT_ENGAGEMENT_SIGNAL_FIELD",
    "JEV_DONE_INPUT_IDENTITY_FIELD",
    "JEV_DONE_INPUT_SCOPE_FIELD",
    "JEV_DONE_INPUT_SET_COVERAGE_FIELD",
    "JEV_DONE_INPUT_EXHAUSTION_FIELD",
    "JEV_DONE_INPUT_TARGETS_FIELD",
    "JEV_DONE_INPUT_TARGET_FIELD",

    "JEV_DONE_OUTPUT_EXTENTS_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_TARGET_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_AMOUNT_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_UNIT_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_COMPARATOR_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_EVIDENCE_FIELD",
    "JEV_DONE_OUTPUT_EXTENT_OBSERVED_FIELD",
    "JEV_DONE_CLAIM_DESCRIPTION_FIELD",
    "JEV_DONE_CLAIM_FIELD",
    "JEV_DONE_CLAIM_IDENTITY_FIELD",
    "JEV_DONE_CLAIM_INTENT_FIELD",
    "JEV_DONE_CLAIM_KIND_FIELD",
    "JEV_DONE_CLAIM_OUTPUT_FIELD",
    "JEV_DONE_CLAIM_QUALIFICATIONS_FIELD",
    "JEV_DONE_CLAIM_SCOPE_FIELD",
    "JEV_DONE_CLAIM_TITLE_FIELD",
    "JEV_DONE_COMPLETED_WORK_FIELD",
    "JEV_DONE_ACTION_FIELD",
    "JEV_DONE_GUARANTEED_NEXT_ACTIONS_FIELD",
    "JEV_DONE_OUTCOME_FIELD",
    "JEV_DONE_TRIGGER_FIELD",
    "JEV_DONE_COMPLETION_CRITERION_FIELD",
    "JEV_DONE_COMPLETION_EVIDENCE_FIELD",
    "JEV_DONE_COMPLETION_ITEM_ID",
    "JEV_DONE_COMPLETION_ITEM_INDEX",
    "JEV_DONE_COMPLETION_SIGNAL_FIELD",
    "JEV_DONE_COMPLETION_STATUS_FIELD",
    "JEV_DONE_DELIVERABLES_FIELD",
    "JEV_DONE_DELIVERABLE_FIELD",
    "JEV_DONE_DISCOVERED_ITEMS_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_ACTION_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_CANDIDATES_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_CRITERIA_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_EVIDENCE_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_GAP_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_IDENTITY_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_INVENTORY_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_SOURCE_FIELD",
    "JEV_DONE_DISCOVERED_ITEM_SOURCE_ID_FIELD",
    "JEV_DONE_EVIDENCE_FIELD",
    "JEV_DONE_IMPLEMENTATION_FIELD",
    "JEV_DONE_HARD_PART_FIELD",
    "JEV_DONE_MISSING_FIELD",
    "JEV_DONE_WHAT_NOT_TO_DO_FIELD",
    "JEV_DONE_INSPECTION_FIELD",
    "JEV_DONE_DETAIL_FIELD",
    "JEV_DONE_DONE_WHEN_FIELD",
    "JEV_DONE_EXPERT_DETAILS_FIELD",
    "JEV_DONE_MAX_CONTINUATIONS",
    "JEV_DONE_PRESERVATION_FIELD",
    "JEV_DONE_EXECUTION_FIELD",
    "JEV_DONE_FINAL_ACCOUNT_FIELD",
    "JEV_DONE_MOTIVATING_CASES_FIELD",
    "JEV_DONE_MOTIVATING_CASE_FIELD",
    "JEV_DONE_NEGATIVE_COVERAGE_FIELD",
    "JEV_DONE_OBJECTIONS_FIELD",
    "JEV_DONE_OBJECTION_FIELD",
    "JEV_DONE_RESOLVED_WHEN_FIELD",
    "JEV_DONE_OBLIGATIONS_FIELD",
    "JEV_DONE_USER_TURNS_FIELD",
    "JEV_DONE_USER_TURN_EVIDENCE_FIELD",
    "JEV_DONE_OBLIGATION_FIELD",
    "JEV_DONE_OBLIGATION_SOURCE_TURN_FIELD",
    "JEV_DONE_OBLIGATION_RELATED_TURNS_FIELD",
    "JEV_DONE_OBLIGATION_STATUS_TURN_FIELD",
    "JEV_DONE_OBLIGATION_COMPLETION_SIGNAL_FIELD",
    "JEV_DONE_OBLIGATION_ACTIVE_FIELD",
    "JEV_DONE_OBLIGATION_STATUS_REASON_FIELD",
    "JEV_DONE_OBSERVED_PROXY_FIELD",
    "JEV_DONE_PHASE_OUTPUT_CRITERION_FIELD",
    "JEV_DONE_PHASE_PROGRESS_FIELD",
    "JEV_DONE_PHASE_REQUEST_SCOPE_FIELD",
    "JEV_DONE_PHASE_REQUIRED_RESULT_FIELD",
    "JEV_DONE_PHASE_STAGE_FIELD",
    "JEV_DONE_PLAN_FIELD",
    "JEV_DONE_PROBLEMS_RESOLVED_FIELD",
    "JEV_DONE_PROBLEM_ASSERTION_FIELD",
    "JEV_DONE_PROBLEM_DESCRIPTION_FIELD",
    "JEV_DONE_PROBLEM_ID_FIELD",
    "JEV_DONE_PROBLEM_ITEMS_FIELD",
    "JEV_DONE_PROBLEM_KIND_FIELD",
    "JEV_DONE_PROBLEM_QUALIFICATIONS_FIELD",
    "JEV_DONE_PROBLEM_REPAIR_FIELD",
    "JEV_DONE_PROBLEM_SCOPE_FIELD",
    "JEV_DONE_PROBLEM_TITLE_FIELD",
    "JEV_DONE_PROBLEM_VERIFICATION_FIELD",
    "JEV_DONE_REQUESTED_OUTCOMES_FIELD",
    "JEV_DONE_REQUEST_FIELD",
    "JEV_DONE_REQUEST_RELEVANCE_FIELD",
    "JEV_DONE_REPORT_ACTION_ALIGNMENT_FIELD",
    "JEV_DONE_SCOPE_COVERAGE_FIELD",
    "JEV_DONE_SCOPE_DIMENSIONS_FIELD",
    "JEV_DONE_SCOPE_MEMBERSHIP_RULE_FIELD",
    "JEV_DONE_SCOPE_REQUESTED_CHANGE_FIELD",
    "JEV_DONE_SCOPE_REQUEST_QUOTE_FIELD",
    "JEV_DONE_SCOPE_UNIT_FIELD",
    "JEV_DONE_SCOPE_UNIT_NOUN_FIELD",
    "JEV_DONE_TARGET_FIELD",
    "JEV_DONE_TARGET_OUTCOMES_FIELD",
    "JEV_DONE_TARGET_OUTCOME_FIELD",
    "JEV_DONE_TARGET_SCOPE_FIELD",
    "JEV_DONE_UNFINISHED_OR_BLOCKED_FIELD",
    "JEV_DONE_SHALLOW_VERSION_FIELD",
    "JEV_EXPERT_DEPTH_FOCUS_LIMIT",
    "JEV_EXPERT_DEPTH_MAX_DETAILS",
    "JEV_EXPERT_DEPTH_MIN_DETAILS",
    "JEV_EXPERT_DEPTH_THRESHOLD",
    "JEV_HANDOFF_MAX_ITERATIONS",
    "JEV_HANDOFF_MAX_TOKENS",
    "JEV_MAX_CHOICE_OPTIONS",
    "JEV_MAX_OPTION_NAME_CHARS",
    "JEV_MAX_QUESTIONS",
    "JEV_MAX_RESPONSE_BYTES",
    "JEV_MAX_SCORE_LEVELS",
    "JEV_MAX_STATE_CHARS",
    "JEV_MIN_CHOICE_OPTIONS",
    "JEV_MIN_OBLIGATION_STATUS_REASON_CHARS",
    "JEV_MIN_OBLIGATION_TURN_INDEX",
    "JEV_MIN_SCORE_LEVELS",
    "JEV_MODELS_PATH",
    "JEV_MOTIVATING_CASE_MAX_SCENARIOS",
    "JEV_MOTIVATING_CASE_RECALL_THRESHOLD",
    "JEV_MOTIVATING_CASE_THRESHOLD",
    "JEV_MULTI_PART_THRESHOLD",
    "JEV_NEGATIVE_COVERAGE_THRESHOLD",
    "JEV_OUTPUT_COUNT_THRESHOLD",
    "JEV_REQUIRED_ACTIONS_THRESHOLD",
    "JEV_CUMULATIVE_OBLIGATIONS_THRESHOLD",
    "JEV_DISCOVERED_ITEM_COVERAGE_THRESHOLD",
    "JEV_DISCOVERED_ITEM_SOURCE_MAX_CHARS",
    "JEV_DISCOVERED_ITEM_TOTAL_SOURCE_MAX_CHARS",
    "JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD",
    "JEV_NOUL_FALSE",
    "JEV_NOUL_OPTIONS",
    "JEV_NOUL_TRUE",
    "JEV_NOUL_YES_THRESHOLD",
    "JEV_NO_RETRIES",
    "JEV_PHASE_PROGRESS_THRESHOLD",
    "JEV_PREFLIGHT_REQUEST_FIELD",
    "JEV_PREFLIGHT_STRATEGY_NAME",
    "JEV_PREVIEW_MODEL",
    "JEV_PROBABILITY_SUM_TOLERANCE",
    "JEV_PROBLEMS_RESOLVED_THRESHOLD",
    "JEV_RETRY_BACKOFF_SECONDS",
    "JEV_RETRY_STATUS_CODES",
    "JEV_REVIEW_MAX_ITERATIONS",
    "JEV_REVIEW_MAX_OBJECTIONS",
    "JEV_REVIEW_MAX_TOKENS",
    "JEV_REQUIRED_SEQUENCE_MAX_STAGES",
    "JEV_REQUIRED_SEQUENCE_MIN_STAGES",
    "JEV_REQUIRED_SEQUENCE_THRESHOLD",
    "JEV_RUN_STATE_MAX_ITERATIONS",
    "JEV_RUN_STATE_MAX_TOKENS",
    "JEV_SCOPE_BREADTH_UPGRADE_THRESHOLD",
    "JEV_SCOPE_COVERAGE_THRESHOLD",
    "JEV_SELF_REVIEW_THRESHOLD",
    "JEV_SPECIALIST_MAX_COUNT",
    "JEV_SPECIALIST_NONE",
    "JEV_SPECIALIST_QUESTION_NAME",
    "JEV_STATUS_OVERLOADED",
    "JEV_STATUS_RATE_LIMITED",
    "JEV_STATUS_REQUEST_TIMEOUT",
    "JEV_STATUS_SERVER_ERROR_CEILING",
    "JEV_STATUS_SERVER_ERROR_FLOOR",
    "JEV_STATUS_UNAUTHORIZED",
    "JEV_STATUS_UNPROCESSABLE",
    "JEV_STAGE_ID_PREFIX",
    "JEV_SYSTEMONE_PATH",
    "JEV_TARGET_OUTCOME_THRESHOLD",
    "JEV_TIMEOUT_FLOOR_SECONDS",
    "JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD",
    "JEV_TOOL_SELECTOR_MAX_THRESHOLD",
    "JEV_TOOL_SELECTOR_MIN_THRESHOLD",
]
