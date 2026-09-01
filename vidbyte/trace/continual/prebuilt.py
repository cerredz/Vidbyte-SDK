"""Context Protocol Header

Description:
    Defines the default action-oriented continual trace schema plus six symmetric
    three-axis trace schemas.
Purpose:
    Gives developers ready-made typed schemas for summarizing an agent's goal,
    actions, mistakes, and current status during execution, and — separately —
    schemas that keep goal success, path quality, and answer correctness as three
    equally-decomposed, never-blended axes.
Architecture:
    Pydantic models declaring typed, described fields, converted to module-level
    TraceSchema constants via TraceSchema.from_model. Every symmetric schema below
    groups its fields into exactly three axis-prefixed groups (goal_success_*,
    path_quality_*, answer_correctness_*) with identical field count and shape per
    group within that schema. Every field meant to accumulate history across
    updates is declared as a top-level ARRAY field rather than nested inside an
    OBJECT field, because UpdateTraceTool's object merge is a one-level shallow
    dict.update() (vidbyte/tools/continual_trace.py:154-164) — a list nested inside
    an OBJECT field would be silently overwritten, not appended, on every update
    that touches that field.
Relations:
    Re-exported by vidbyte.trace.continual and vidbyte.trace.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


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

    goal_success_status: str = Field(
        description=(
            "The current read on whether the agent's output satisfies the user's stated goal — "
            "one of 'achieved', 'in_progress', 'failed', or 'partial'. Scored purely on goal "
            "completion, independent of path_quality_status and answer_correctness_status: a "
            "messy path can still reach the goal, and a clean path can still fail to. This is a "
            "scalar field, so each update replaces the previous value outright — always write the "
            "full current status, not a delta."
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

    path_quality_status: str = Field(
        description=(
            "The current read on whether the actions taken so far have been efficient and safe — "
            "one of 'efficient', 'inefficient', 'risky', or 'blocked'. Scored purely on the path: "
            "it does not move just because goal_success_status changed. Replaced in full on every "
            "update. Use 'risky' when at least one action carried meaningful risk even if none has "
            "caused harm yet, and 'blocked' when the agent is currently unable to proceed."
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

    answer_correctness_status: str = Field(
        description=(
            "The current read on whether the specific factual claims in the agent's output are "
            "verifiably true — one of 'verified', 'unverified', 'contradicted', or 'partial'. "
            "Scored purely on claim correctness against available evidence; it does not move just "
            "because the goal was reached or the path was clean. Replaced in full on every update. "
            "Use 'contradicted' as soon as any claim conflicts with a source or another claim, "
            "even if other claims in the same output are fine."
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

    goal_success_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the goal, such as 'matches explicit user "
            "intent' or 'satisfies stated constraints'. Shape per entry: {criterion: string, met: "
            "bool, evidence: string, iteration: int}. Scored purely on criteria the goal itself "
            "implies — never let a path_quality or answer_correctness finding change an entry "
            "here. Append a new entry each time a criterion is newly evaluated or re-evaluated; "
            "do not edit a prior entry, since a criterion whose answer changes gets a new entry "
            "with the current iteration."
        ),
    )
    path_quality_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the actions taken, such as 'no redundant "
            "tool calls' or 'followed the stated plan'. Shape per entry: {criterion: string, met: "
            "bool, evidence: string, iteration: int}. Scored purely on the path — a path criterion "
            "should never fail just because the goal ultimately wasn't reached. Append a new entry "
            "per (re-)evaluation; never edit an existing one in place."
        ),
    )
    answer_correctness_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per criterion evaluated against the answer's claims, such as 'claims are "
            "sourced' or 'no contradictions'. Shape per entry: {criterion: string, met: bool, "
            "evidence: string, iteration: int}. Scored purely on claim correctness — a criterion "
            "here should never be marked met just because the goal was reached through a clean "
            "path. Append a new entry per (re-)evaluation; never edit an existing one in place."
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
            "0-1. How closely the current output matches the user's explicit intent, independent "
            "of goal_constraint_satisfaction and goal_completion_pct. Replaced in full on every "
            "update."
        ),
    )
    goal_constraint_satisfaction: float = Field(
        description=(
            "0-1. The fraction of the goal's stated constraints currently satisfied, independent "
            "of goal_intent_alignment and goal_completion_pct. Replaced in full on every update."
        ),
    )
    goal_completion_pct: float = Field(
        description=(
            "0-1. How much of the goal is done, independent of goal_intent_alignment and "
            "goal_constraint_satisfaction — a partially-aligned output can still be near-complete "
            "on scope. Replaced in full on every update."
        ),
    )
    path_efficiency: float = Field(
        description=(
            "0-1. The absence of redundant or wasted steps in the actions taken so far, "
            "independent of path_safety and path_plan_adherence. Replaced in full on every "
            "update."
        ),
    )
    path_safety: float = Field(
        description=(
            "0-1. The absence of risky or blocked actions, independent of path_efficiency and "
            "path_plan_adherence — an efficient path can still be unsafe. Replaced in full on "
            "every update."
        ),
    )
    path_plan_adherence: float = Field(
        description=(
            "0-1. How closely the actions taken matched the agent's own stated plan, independent "
            "of path_efficiency and path_safety. Replaced in full on every update."
        ),
    )
    correctness_grounding: float = Field(
        description=(
            "0-1. The fraction of claims traceable to a checkable source, independent of "
            "correctness_consistency and correctness_completeness. Replaced in full on every "
            "update."
        ),
    )
    correctness_consistency: float = Field(
        description=(
            "0-1. The absence of internal contradictions among the claims made, independent of "
            "correctness_grounding and correctness_completeness. Replaced in full on every "
            "update."
        ),
    )
    correctness_completeness: float = Field(
        description=(
            "0-1. The absence of gaps the answer should cover but doesn't, independent of "
            "correctness_grounding and correctness_consistency. Replaced in full on every update."
        ),
    )


SymmetricSubScoreTrace = TraceSchema.from_model(
    SymmetricSubScoreTraceModel,
    name="symmetric_subscore_trace",
    description="Goal success, path quality, and answer correctness, each decomposed into three independent 0-1 metrics that are never averaged.",
)


class SymmetricEventLedgerTraceModel(BaseModel):
    """Each axis gets its own append-only event log, all three the same shape, so history accumulates symmetrically across all three instead of one axis being logged in detail while the others are only scored."""

    goal_success_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per meaningful change in goal status. Shape per entry: {iteration: int, "
            "subgoal_id: string, status: string, description: string}. Append a new event "
            "whenever a subgoal's status changes; do not resend an existing subgoal_id to update "
            "it in place — the latest event for a given subgoal_id is what readers should treat "
            "as current."
        ),
    )
    path_quality_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per meaningful action taken. Shape per entry: {iteration: int, step_id: "
            "string, action: string, risk_flag: string}. Append a new event per action; a retried "
            "action gets a new step_id rather than mutating a prior entry."
        ),
    )
    answer_correctness_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One entry per claim checked. Shape per entry: {iteration: int, claim_id: string, "
            "claim_text: string, verified: bool}. Append a new event each time a claim is "
            "(re-)checked; a claim re-verified later produces a new event with the same claim_id "
            "rather than replacing the earlier one — readers should fold the log and take the "
            "latest verified value per claim_id."
        ),
    )


SymmetricEventLedgerTrace = TraceSchema.from_model(
    SymmetricEventLedgerTraceModel,
    name="symmetric_event_ledger_trace",
    description="Goal success, path quality, and answer correctness as three parallel append-only event logs.",
)


class SymmetricTimelineTraceModel(BaseModel):
    """Each axis gets its own time series — one snapshot appended per trace-agent pass — so the trend of that axis over the run, not just its final value, is preserved and stays separate from the other two axes' trends."""

    goal_success_timeline: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One snapshot appended per pass. Shape per entry: {iteration: int, status: string, "
            "confidence: float, note: string}. Append exactly one new entry per update rather "
            "than editing a prior one, so the full sequence of goal-status readings across the "
            "run is preserved."
        ),
    )
    path_quality_timeline: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One snapshot appended per pass. Shape per entry: {iteration: int, efficiency: "
            "float, risky_action_count: int, note: string}. Append exactly one new entry per "
            "update."
        ),
    )
    answer_correctness_timeline: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "One snapshot appended per pass. Shape per entry: {iteration: int, "
            "verified_claim_count: int, contradiction_count: int, note: string}. Append exactly "
            "one new entry per update."
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
            "Append-only. Facts supporting that the goal is being met. Add a new entry only when "
            "a new supporting fact appears; exact duplicates are skipped automatically."
        ),
    )
    goal_success_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only. Facts suggesting the goal is not being met, tracked separately from "
            "goal_success_supporting rather than netted against it — both lists are meant to "
            "grow, and goal_success_verdict is where they get weighed."
        ),
    )
    goal_success_verdict: str = Field(
        description=(
            "'achieved'|'in_progress'|'failed'|'partial'. Replaced in full each pass, weighing "
            "goal_success_supporting against goal_success_contradicting; scored only on goal "
            "completion, independent of path_quality_verdict and answer_correctness_verdict."
        ),
    )

    path_quality_supporting: list[str] = Field(
        default_factory=list,
        description="Append-only. Facts supporting that the path taken is efficient and safe.",
    )
    path_quality_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only. Facts suggesting the path is inefficient or risky, tracked separately "
            "from path_quality_supporting."
        ),
    )
    path_quality_verdict: str = Field(
        description=(
            "'efficient'|'inefficient'|'risky'|'blocked'. Replaced in full each pass, weighing "
            "path_quality_supporting against path_quality_contradicting; scored only on the "
            "path, independent of goal_success_verdict and answer_correctness_verdict."
        ),
    )

    answer_correctness_supporting: list[str] = Field(
        default_factory=list,
        description="Append-only. Facts supporting that current claims are correct.",
    )
    answer_correctness_contradicting: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only. Facts suggesting current claims are wrong or unverified, tracked "
            "separately from answer_correctness_supporting."
        ),
    )
    answer_correctness_verdict: str = Field(
        description=(
            "'verified'|'unverified'|'contradicted'|'partial'. Replaced in full each pass, "
            "weighing answer_correctness_supporting against answer_correctness_contradicting; "
            "scored only on claim correctness, independent of goal_success_verdict and "
            "path_quality_verdict."
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
