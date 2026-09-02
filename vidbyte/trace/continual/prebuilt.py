"""FILE: vidbyte/trace/continual/prebuilt.py

PURPOSE: Defines the default action-oriented continual trace schema (ActionTrace) plus six symmetric three-axis trace schemas that keep goal success, path quality, and answer correctness as three equally-decomposed, never-blended axes, varying only the group-shape used to express that separation.
ROLE IN CODEBASE: Every schema here is a Pydantic model converted to a module-level TraceSchema constant via TraceSchema.from_model, re-exported by vidbyte.trace.continual, vidbyte.trace, and vidbyte.__init__ in that order. SymmetricChecklistTrace, SymmetricEventLedgerTrace, and SymmetricTimelineTrace use TraceField's nested fields/items capability (vidbyte/lib/dataclasses/trace.py) by annotating a list field with `list[SubModel]` instead of `list[dict[str, Any]]` — the nine smaller per-check/per-event/per-snapshot submodels those three schemas need live in the sibling vidbyte/trace/continual/prebuilt_events.py rather than inline here, matching the split documented at field-guide/vidbyte-sdk/tracing-shape-contracts.md. Closed-vocabulary fields (status/verdict) reuse the shared GoalSuccessVerdict/PathQualityVerdict/AnswerCorrectnessVerdict enums from vidbyte/lib/enums/continual_trace.py rather than declaring a schema-local vocabulary.
ARCHITECTURE NOTE: Every symmetric schema groups its fields into exactly three axis-prefixed groups (goal_success_*, path_quality_*, answer_correctness_*) with identical field count and shape per group within that schema. Every field meant to accumulate history across updates is declared as a top-level ARRAY field rather than nested inside an OBJECT field, because UpdateTraceTool's object merge is a one-level shallow dict.update() (vidbyte/tools/continual_trace.py) — a list nested inside an OBJECT field would be silently overwritten, not appended, on every update that touches that field; this holds regardless of whether that OBJECT field's own shape is opaque or, as with the nested submodels here, fully typed. SymmetricFlatTrace, SymmetricSubScoreTrace, and SymmetricEvidenceTrace have no list-of-record fields and so need no helper submodel — only their closed-vocabulary status/verdict fields were upgraded from plain `str` to the shared verdict enums.
COMMON MODIFICATION PATTERNS: Add a new prebuilt schema as a Pydantic model plus a TraceSchema.from_model(...) constant, then export both from vidbyte/trace/continual/__init__.py, vidbyte/trace/__init__.py, and vidbyte/__init__.py in that order, matching ActionTrace's existing position in all three files. Any helper submodel a new schema's list fields need belongs in vidbyte/trace/continual/prebuilt_events.py, imported here by name — do not define a new helper class inline in this file. Add a new closed vocabulary to vidbyte/lib/enums/continual_trace.py rather than a schema-local Literal or hardcoded string list.
KNOWN EDGE CASES: A `str, Enum` field (every status/verdict field below) type-maps to TraceFieldType.STRING with no special-casing (vidbyte/lib/dataclasses/trace.py's `_annotation_to_type` checks `issubclass(target, str)` before Mapping), so the model-facing JSON Schema does not itself enforce the closed set — the field's own description is what communicates the vocabulary to the trace agent.
RELATED DOCS: docs/design/symmetric-continual-trace-schemas.md, field-guide/vidbyte-sdk/tracing-shape-contracts.md, field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: tests/test_symmetric_continual_traces.py, scripts/test-symmetric-continual-traces.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.lib.enums.continual_trace import (
    AnswerCorrectnessVerdict,
    GoalSuccessVerdict,
    PathQualityVerdict,
)
from vidbyte.trace.continual.prebuilt_events import (
    AnswerCorrectnessCheckEntry,
    AnswerCorrectnessEvent,
    AnswerCorrectnessSnapshot,
    GoalSuccessCheckEntry,
    GoalSuccessEvent,
    GoalSuccessSnapshot,
    PathQualityCheckEntry,
    PathQualityEvent,
    PathQualitySnapshot,
)


class ActionTraceModel(BaseModel):
    """Action-oriented continual trace describing goal, work, mistakes, and status."""

    goal: str = Field(
        description=(
            "The original or current high-level goal the main agent is working toward. "
            "Capture the developer's intent as precisely as the context allows, including any "
            "explicit success criteria or constraints. If the goal is refined or narrowed during "
            "the run, record the most current understanding rather than the first phrasing. Keep "
            "this stable across updates unless the context clearly redefines the objective."
        ),
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description=(
            "An ordered list of the important actions, tool calls, decisions, or steps the main "
            "agent has already performed. Each entry should be a short, concrete statement of what "
            "happened and, when useful, why it mattered. Append new meaningful actions rather than "
            "rewriting history so the trace reads as a running log. Omit trivial or repetitive steps "
            "that add no value to a later handoff."
        ),
    )
    mistakes: list[str] = Field(
        default_factory=list,
        description=(
            "Mistakes, failed attempts, incorrect assumptions, dead ends, or recoveries observed so "
            "far. Record what went wrong and, where the context reveals it, the correction that "
            "followed. This field is one of the most valuable parts of a handoff because it stops a "
            "future agent from repeating the same error. Keep prior entries unless the context shows "
            "they were not actually mistakes."
        ),
    )
    current_status: str = Field(
        description=(
            "The latest known state of the task and what still remains unresolved. Summarize how far "
            "the agent has progressed and what the immediate next step appears to be. Note any blocking "
            "conditions, pending tool results, or waiting states that affect progress. This field "
            "should always reflect the most recent context and is expected to change on nearly every "
            "update."
        ),
    )


ActionTrace = TraceSchema.from_model(
    ActionTraceModel,
    name="action_trace",
    description="Tracks the agent goal, work performed, mistakes, and current status.",
)


class SymmetricFlatTraceModel(BaseModel):
    """Three axes — goal success, path quality, answer correctness — each given the identical four-field shape: status, confidence, evidence, rationale. No field can silently absorb another axis's signal."""

    goal_success_status: GoalSuccessVerdict = Field(
        description=(
            "The current read on whether the agent's output satisfies the user's stated goal, drawn "
            "from the shared GoalSuccessVerdict vocabulary. Scored purely on goal completion, "
            "independent of path_quality_status and answer_correctness_status: a messy path can still "
            "reach the goal, and a clean path can still fail to. This is a scalar field, so each "
            "update replaces the previous value outright — always write the full current status, not "
            "a delta."
        ),
    )
    goal_success_confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in goal_success_status, tracked independently of "
            "path_quality_confidence and answer_correctness_confidence — a high-confidence "
            "'failed' is as valid a state as a low-confidence 'achieved'. Replaced in full on "
            "every update; base it on how much of the goal's success criteria could actually be "
            "checked against the current context."
        ),
    )
    goal_success_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts supporting the current "
            "goal_success_status — for example a specific requirement that was met, or a stated "
            "constraint that was violated. New entries are appended across updates and exact "
            "duplicates are automatically skipped, so only add an entry when there is a new fact. "
            "This is what lets a reader audit goal_success_status instead of taking it on faith."
        ),
    )
    goal_success_rationale: str = Field(
        description=(
            "A one- or two-sentence prose justification tying goal_success_evidence to "
            "goal_success_status, written fresh on every update. Replaced in full each pass — do "
            "not append to it. Use it to explain any change in goal_success_status since the last "
            "update, especially reversals."
        ),
    )

    path_quality_status: PathQualityVerdict = Field(
        description=(
            "The current read on whether the actions taken so far have been efficient and safe, drawn "
            "from the shared PathQualityVerdict vocabulary. Scored purely on the path: it does not "
            "move just because goal_success_status changed. Replaced in full on every update. Use "
            "'risky' when at least one action carried meaningful risk even if none has caused harm "
            "yet, and 'blocked' when the agent is currently unable to proceed."
        ),
    )
    path_quality_confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in path_quality_status, tracked independently of "
            "goal_success_confidence and answer_correctness_confidence. Replaced in full each "
            "update. A low value here alongside a high goal_success_confidence is a legitimate "
            "combination — it means the outcome looks good but the process behind it is not well "
            "understood yet."
        ),
    )
    path_quality_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short facts supporting the current path_quality_status — a "
            "specific redundant step, a specific risky tool call, or a specific instance of "
            "following the stated plan well. Appended across updates with exact duplicates "
            "skipped; add a new entry only when a new relevant action occurs."
        ),
    )
    path_quality_rationale: str = Field(
        description=(
            "A one- or two-sentence justification tying path_quality_evidence to "
            "path_quality_status, rewritten fresh on every update and replaced in full each pass. "
            "Call out any change since the last update, such as a new risky action or a recovery "
            "from one."
        ),
    )

    answer_correctness_status: AnswerCorrectnessVerdict = Field(
        description=(
            "The current read on whether the specific factual claims in the agent's output are "
            "verifiably true, drawn from the shared AnswerCorrectnessVerdict vocabulary. Scored purely "
            "on claim correctness against available evidence; it does not move just because the goal "
            "was reached or the path was clean. Replaced in full on every update. Use 'contradicted' "
            "as soon as any claim conflicts with a source or another claim, even if other claims in "
            "the same output are fine."
        ),
    )
    answer_correctness_confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in answer_correctness_status, tracked independently of "
            "goal_success_confidence and path_quality_confidence. Replaced in full each update. "
            "This should reflect how much of the answer's claims could actually be checked, not "
            "how plausible the answer sounds."
        ),
    )
    answer_correctness_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short facts supporting the current answer_correctness_status — a "
            "specific claim that was verified against a source, or a specific contradiction found "
            "between two claims. Appended across updates with exact duplicates skipped."
        ),
    )
    answer_correctness_rationale: str = Field(
        description=(
            "A one- or two-sentence justification tying answer_correctness_evidence to "
            "answer_correctness_status, rewritten fresh on every update and replaced in full each "
            "pass. Call out any newly verified or newly contradicted claim since the last update."
        ),
    )


SymmetricFlatTrace = TraceSchema.from_model(
    SymmetricFlatTraceModel,
    name="symmetric_flat_trace",
    description="Goal success, path quality, and answer correctness as three parallel current-value reads, never blended.",
)


class SymmetricChecklistTraceModel(BaseModel):
    """Each axis is its own append-only checklist of independently-evaluated criteria, so a single axis can gain many entries over a run without any of them being averaged into one pass/fail per axis, let alone across axes."""

    goal_success_checks: list[GoalSuccessCheckEntry] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the goal, such as 'matches explicit user "
            "intent' or 'satisfies stated constraints' — see GoalSuccessCheckEntry "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Scored purely "
            "on criteria the goal itself implies — never let a path_quality or answer_correctness "
            "finding change an entry here. Append a new entry each time a criterion is newly "
            "evaluated or re-evaluated; do not edit a prior entry, since a criterion whose answer "
            "changes gets a new entry with the current iteration and the same criterion_id."
        ),
    )
    path_quality_checks: list[PathQualityCheckEntry] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the actions taken, such as 'no redundant "
            "tool calls' or 'followed the stated plan' — see PathQualityCheckEntry "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Scored purely "
            "on the path — a path criterion should never fail just because the goal ultimately "
            "wasn't reached. Append a new entry per (re-)evaluation; never edit an existing one in "
            "place."
        ),
    )
    answer_correctness_checks: list[AnswerCorrectnessCheckEntry] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the answer's claims, such as 'claims are "
            "sourced' or 'no contradictions' — see AnswerCorrectnessCheckEntry "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Scored purely "
            "on claim correctness — a criterion here should never be marked met just because the "
            "goal was reached through a clean path. Append a new entry per (re-)evaluation; never "
            "edit an existing one in place."
        ),
    )


SymmetricChecklistTrace = TraceSchema.from_model(
    SymmetricChecklistTraceModel,
    name="symmetric_checklist_trace",
    description="Goal success, path quality, and answer correctness as three parallel growing checklists of criteria.",
)


class SymmetricSubScoreTraceModel(BaseModel):
    """Each axis is decomposed into three independent named metrics. The metrics inside one axis are never averaged into a single axis score, and the three axes are never averaged into each other."""

    goal_intent_alignment: float = Field(
        description=(
            "0-1. How closely the current output matches the user's explicit intent, as opposed "
            "to a technically-responsive but off-target answer. Scored independently of "
            "goal_constraint_satisfaction and goal_completion_pct — an output can be perfectly "
            "aligned with intent while still missing a constraint or being incomplete. Replaced "
            "in full on every update rather than averaged with the prior value, so always write "
            "the current best read, not a nudge up or down from the last one."
        ),
    )
    goal_constraint_satisfaction: float = Field(
        description=(
            "0-1. The fraction of the goal's explicitly stated constraints — format, scope, "
            "length, exclusions, and similar hard requirements — currently satisfied. Scored "
            "independently of goal_intent_alignment and goal_completion_pct: an output can "
            "satisfy every constraint while still misreading the user's underlying intent. "
            "Replaced in full on every update; a value below 1.0 should correspond to at least "
            "one identifiable violated constraint, not a vague sense of incompleteness."
        ),
    )
    goal_completion_pct: float = Field(
        description=(
            "0-1. How much of the goal's scope is done, independent of goal_intent_alignment and "
            "goal_constraint_satisfaction — a partially-aligned output can still be near-complete "
            "on scope, and a fully scoped output can still misread intent. Replaced in full on "
            "every update. For a multi-part goal, base this on the fraction of parts addressed, "
            "not a subjective sense of overall progress."
        ),
    )
    path_efficiency: float = Field(
        description=(
            "0-1. The absence of redundant or wasted steps in the actions taken so far — repeated "
            "lookups, abandoned approaches re-tried without new information, or tool calls that "
            "added nothing. Scored independently of path_safety and path_plan_adherence, so a "
            "highly efficient path can still be unsafe or off-plan. Replaced in full on every "
            "update, based on the actions taken up to that point, not a prediction of future "
            "efficiency."
        ),
    )
    path_safety: float = Field(
        description=(
            "0-1. The absence of risky or blocked actions among everything taken so far — actions "
            "with side effects, destructive potential, or that required a safeguard to stop. "
            "Scored independently of path_efficiency and path_plan_adherence — an efficient, "
            "on-plan path can still be unsafe if even one action carried real risk. Replaced in "
            "full on every update; a single risky action should visibly lower this value even if "
            "most of the run was clean."
        ),
    )
    path_plan_adherence: float = Field(
        description=(
            "0-1. How closely the actions actually taken matched the agent's own stated plan or "
            "stated next step, independent of path_efficiency and path_safety — a low-efficiency "
            "path can still faithfully follow the plan, and a fast path can still improvise away "
            "from it. Replaced in full on every update. A value well below 1.0 should correspond "
            "to a concrete deviation, such as skipping a stated step or taking an unannounced "
            "detour."
        ),
    )
    correctness_grounding: float = Field(
        description=(
            "0-1. The fraction of claims in the current output that are traceable to a checkable "
            "source — a document, a tool result, or a verifiable fact — rather than asserted "
            "outright. Scored independently of correctness_consistency and "
            "correctness_completeness: claims can be internally consistent and cover everything "
            "asked while still being entirely unsourced. Replaced in full on every update as new "
            "claims are made or existing ones are checked."
        ),
    )
    correctness_consistency: float = Field(
        description=(
            "0-1. The absence of internal contradictions among the claims made so far — no two "
            "claims asserting incompatible things. Scored independently of correctness_grounding "
            "and correctness_completeness, since a set of claims can be perfectly consistent with "
            "each other while still being ungrounded or incomplete. Replaced in full on every "
            "update; drop it as soon as any contradiction between two claims is detected, even if "
            "each individual claim is otherwise well-sourced."
        ),
    )
    correctness_completeness: float = Field(
        description=(
            "0-1. The absence of gaps the answer should cover but doesn't, given what the goal "
            "and prior claims imply is in scope. Scored independently of correctness_grounding and "
            "correctness_consistency — an answer can be fully grounded and internally consistent "
            "while still leaving an implied sub-question unaddressed. Replaced in full on every "
            "update as more of the answer's expected scope is covered or a new gap is identified."
        ),
    )


SymmetricSubScoreTrace = TraceSchema.from_model(
    SymmetricSubScoreTraceModel,
    name="symmetric_subscore_trace",
    description="Goal success, path quality, and answer correctness, each decomposed into three independent 0-1 metrics that are never averaged.",
)


class SymmetricEventLedgerTraceModel(BaseModel):
    """Each axis gets its own append-only event log, all three the same shape, so history accumulates symmetrically across all three instead of one axis being logged in detail while the others are only scored."""

    goal_success_events: list[GoalSuccessEvent] = Field(
        default_factory=list,
        description=(
            "One entry per meaningful change in a subgoal's status — see GoalSuccessEvent "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Append a new "
            "event whenever a subgoal's status changes; do not resend an existing subgoal_id to "
            "update it in place — the event with the highest iteration for a given subgoal_id is "
            "what readers should treat as current."
        ),
    )
    path_quality_events: list[PathQualityEvent] = Field(
        default_factory=list,
        description=(
            "One entry per meaningful action taken — see PathQualityEvent "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Append a new "
            "event per action; a retried action gets a new step_id rather than mutating a prior "
            "entry."
        ),
    )
    answer_correctness_events: list[AnswerCorrectnessEvent] = Field(
        default_factory=list,
        description=(
            "One entry per claim checked — see AnswerCorrectnessEvent "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-entry shape. Append a new "
            "event each time a claim is (re-)checked; a claim re-verified later produces a new event "
            "with the same claim_id rather than replacing the earlier one — readers should fold the "
            "log and take the highest-iteration event's verified value per claim_id."
        ),
    )


SymmetricEventLedgerTrace = TraceSchema.from_model(
    SymmetricEventLedgerTraceModel,
    name="symmetric_event_ledger_trace",
    description="Goal success, path quality, and answer correctness as three parallel append-only event logs.",
)


class SymmetricTimelineTraceModel(BaseModel):
    """Each axis gets its own time series — one snapshot appended per trace-agent pass — so the trend of that axis over the run, not just its final value, is preserved and stays separate from the other two axes' trends."""

    goal_success_timeline: list[GoalSuccessSnapshot] = Field(
        default_factory=list,
        description=(
            "One snapshot of goal status appended per trace-agent pass, building a trend line "
            "instead of only the latest value — see GoalSuccessSnapshot "
            "(vidbyte/trace/continual/prebuilt_events.py) for the full per-snapshot shape. Append "
            "exactly one new entry per update rather than editing a prior one, so the full sequence "
            "of goal-status readings across the run is preserved and never overwritten. A reversal — "
            "status moving backward from a later iteration to an earlier one — should be visible in "
            "the sequence, not smoothed away."
        ),
    )
    path_quality_timeline: list[PathQualitySnapshot] = Field(
        default_factory=list,
        description=(
            "One snapshot of path quality appended per trace-agent pass, building a trend line of "
            "efficiency and risk over the run rather than only a final value — see "
            "PathQualitySnapshot (vidbyte/trace/continual/prebuilt_events.py) for the full "
            "per-snapshot shape. Append exactly one new entry per update; risky_action_count should "
            "be the cumulative count up to that iteration, not a per-pass delta, so a single entry "
            "is enough to read the running total at that point in the run."
        ),
    )
    answer_correctness_timeline: list[AnswerCorrectnessSnapshot] = Field(
        default_factory=list,
        description=(
            "One snapshot of claim correctness appended per trace-agent pass, building a trend line "
            "of verification progress over the run rather than only a final tally — see "
            "AnswerCorrectnessSnapshot (vidbyte/trace/continual/prebuilt_events.py) for the full "
            "per-snapshot shape. Append exactly one new entry per update; the counts should be "
            "cumulative totals as of that iteration. A contradiction_count that rises partway "
            "through the run and never falls back is a meaningful signal this timeline is meant to "
            "preserve."
        ),
    )


SymmetricTimelineTrace = TraceSchema.from_model(
    SymmetricTimelineTraceModel,
    name="symmetric_timeline_trace",
    description="Goal success, path quality, and answer correctness as three parallel per-pass timelines.",
)


class SymmetricEvidenceTraceModel(BaseModel):
    """Each axis carries its own for/against evidence ledgers plus a verdict — three parallel three-part structures, so the reasoning behind each axis's current state is auditable on its own terms without folding into the other two axes."""

    goal_success_supporting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts supporting that the goal is being met — a "
            "specific requirement satisfied, or a stated sub-goal completed. Add a new entry only "
            "when a new supporting fact appears in the context; exact duplicates are skipped "
            "automatically by the merge logic, so re-stating an already-recorded fact is harmless "
            "but adds nothing. This list, together with goal_success_contradicting, is the "
            "auditable basis for goal_success_verdict."
        ),
    )
    goal_success_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts suggesting the goal is not being met — a "
            "missed requirement, a violated constraint, or an abandoned sub-goal. Tracked "
            "separately from goal_success_supporting rather than netted against it as the run "
            "progresses; both lists are meant to keep growing so a reader can see the full case on "
            "each side. goal_success_verdict is where the two get weighed into one current read."
        ),
    )
    goal_success_verdict: GoalSuccessVerdict = Field(
        description=(
            "The current weighing of goal_success_supporting against goal_success_contradicting "
            "into one read on goal completion, drawn from the shared GoalSuccessVerdict vocabulary. "
            "Scored only on whether the goal was reached, independent of path_quality_verdict and "
            "answer_correctness_verdict — a 'failed' goal can still have an 'efficient' "
            "path_quality_verdict. Replaced in full each pass rather than appended, since only the "
            "latest weighing matters."
        ),
    )

    path_quality_supporting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts supporting that the path taken is "
            "efficient and safe — a well-chosen tool call, or a plan followed precisely. Add a new "
            "entry only when a new supporting fact appears; exact duplicates are skipped "
            "automatically. This list, together with path_quality_contradicting, is the auditable "
            "basis for path_quality_verdict."
        ),
    )
    path_quality_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts suggesting the path is inefficient or "
            "risky — a redundant tool call, a risky action, or an unannounced deviation from the "
            "stated plan. Tracked separately from path_quality_supporting rather than netted "
            "against it; both lists keep growing across the run. path_quality_verdict is where the "
            "two get weighed into one current read."
        ),
    )
    path_quality_verdict: PathQualityVerdict = Field(
        description=(
            "The current weighing of path_quality_supporting against path_quality_contradicting "
            "into one read on the path taken, drawn from the shared PathQualityVerdict vocabulary. "
            "Scored only on the path itself, independent of goal_success_verdict and "
            "answer_correctness_verdict — an 'efficient' path can still accompany a 'contradicted' "
            "answer. Replaced in full each pass rather than appended."
        ),
    )

    answer_correctness_supporting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts supporting that current claims are correct "
            "— a claim confirmed against a source, or two claims found mutually consistent. Add a "
            "new entry only when a new supporting fact appears; exact duplicates are skipped "
            "automatically. This list, together with answer_correctness_contradicting, is the "
            "auditable basis for answer_correctness_verdict."
        ),
    )
    answer_correctness_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only list of short, concrete facts suggesting current claims are wrong or "
            "unverified — a claim that conflicts with a source, or two claims that conflict with "
            "each other. Tracked separately from answer_correctness_supporting rather than netted "
            "against it; both lists keep growing across the run. answer_correctness_verdict is "
            "where the two get weighed into one current read."
        ),
    )
    answer_correctness_verdict: AnswerCorrectnessVerdict = Field(
        description=(
            "The current weighing of answer_correctness_supporting against "
            "answer_correctness_contradicting into one read on claim correctness, drawn from the "
            "shared AnswerCorrectnessVerdict vocabulary. Scored only on the claims themselves, "
            "independent of goal_success_verdict and path_quality_verdict — a 'verified' answer can "
            "still follow a 'risky' path. Replaced in full each pass rather than appended."
        ),
    )


SymmetricEvidenceTrace = TraceSchema.from_model(
    SymmetricEvidenceTraceModel,
    name="symmetric_evidence_trace",
    description="Goal success, path quality, and answer correctness as three parallel evidence-for/against ledgers with a verdict.",
)


__all__ = [
    "ActionTrace",
    "ActionTraceModel",
    "SymmetricChecklistTrace",
    "SymmetricChecklistTraceModel",
    "SymmetricEventLedgerTrace",
    "SymmetricEventLedgerTraceModel",
    "SymmetricEvidenceTrace",
    "SymmetricEvidenceTraceModel",
    "SymmetricFlatTrace",
    "SymmetricFlatTraceModel",
    "SymmetricSubScoreTrace",
    "SymmetricSubScoreTraceModel",
    "SymmetricTimelineTrace",
    "SymmetricTimelineTraceModel",
]
