"""FILE: vidbyte/trace/continual/prebuilt_events.py

PURPOSE: Defines the smaller "helper" Pydantic submodels that back the three symmetric prebuilt continual trace schemas in vidbyte/trace/continual/prebuilt.py whose fields grow over a run — SymmetricChecklistTrace, SymmetricEventLedgerTrace, and SymmetricTimelineTrace. Each submodel is the item shape of one axis-prefixed list field (goal_success_*, path_quality_*, answer_correctness_*) on one of those three top-level trace models.
ROLE IN CODEBASE: Imported exclusively by vidbyte/trace/continual/prebuilt.py, which annotates SymmetricChecklistTraceModel/SymmetricEventLedgerTraceModel/SymmetricTimelineTraceModel fields with `list[SubModel]`. TraceSchema.from_model (vidbyte/lib/dataclasses/trace.py) recurses into every class here the same way it recurses into any nested BaseModel/list[BaseModel] annotation, so each class needs its own Field(description=...) on every attribute, the same requirement enforced at the top level. Draws its closed vocabularies from vidbyte/lib/enums/continual_trace.py, reusing GoalSuccessVerdict/PathQualityVerdict/AnswerCorrectnessVerdict rather than declaring axis-local status vocabularies.
ARCHITECTURE NOTE: This file exists purely to keep vidbyte/trace/continual/prebuilt.py readable: the six top-level TraceModel/TraceSchema pairs a caller actually imports stay in prebuilt.py, while the nine smaller per-check/per-event/per-snapshot records that back their list fields live here — the same split vidbyte/trace/continual/prebuilt_events.py uses in PR #398 for the five performance schemas there, documented at field-guide/vidbyte-sdk/tracing-shape-contracts.md. No class in this file is itself converted to a TraceSchema or exported outside vidbyte/trace/continual — a class here only ever appears as another model's list-item shape, never as a schema a caller passes to TraceOption.continual directly. Every class stays deliberately flat (no field on any class here is itself another nested BaseModel), which keeps every schema well under MAX_TRACE_FIELD_NESTING_DEPTH.
COMMON MODIFICATION PATTERNS: Add a new field to an existing helper class here, then confirm the class still parses under TraceSchema.from_model by running scripts/test-symmetric-continual-traces.py. Add a brand-new helper class here only when introducing a new list field on one of the three top-level models in prebuilt.py that need it; the model in prebuilt.py that references it must import the class name from this file.
KNOWN EDGE CASES: Every axis in a given schema (Checklist/EventLedger/Timeline) gets its own dedicated submodel even where the shape is structurally symmetric across axes, matching the axis-specific enum type each submodel's status/verdict field carries (GoalSuccessVerdict vs. PathQualityVerdict vs. AnswerCorrectnessVerdict) — do not collapse the three per-schema submodels into one shared class, since that would erase the axis-specific enum typing. Several classes carry a stable `*_id` field specifically so a later record can join back to the record it concerns by id rather than by iteration number, since two records can share the same iteration.
RELATED DOCS: docs/design/symmetric-continual-trace-schemas.md, field-guide/vidbyte-sdk/tracing-shape-contracts.md, field-guide/vidbyte-sdk/model-facing-tool-contracts.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_symmetric_continual_traces.py, scripts/test-symmetric-continual-traces.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.enums.continual_trace import (
    AnswerCorrectnessErrorType,
    AnswerCorrectnessVerdict,
    ErrorSeverity,
    GoalSuccessVerdict,
    JudgmentStability,
    PathQualityErrorType,
    PathQualityVerdict,
)


# ---------------------------------------------------------------------------
# SymmetricChecklistTrace helpers
# ---------------------------------------------------------------------------
class GoalSuccessCheckEntry(BaseModel):
    """One independently-evaluated criterion the goal itself implies, judged only on goal completion."""

    criterion_id: str = Field(
        description=(
            "A stable identifier for the criterion this entry evaluates, such as 'covers-explicit-"
            "constraint-1' or 'matches-stated-format'. Reuse the same identifier every time this "
            "criterion is re-evaluated so a reader can group every entry for one criterion together "
            "and take the highest-iteration entry as its current state. Assign it the first time the "
            "criterion is identified and never change it for the life of the run."
        )
    )
    criterion: str = Field(
        description=(
            "The specific, checkable requirement the goal implies, phrased narrowly enough to be "
            "judged as met or not met on its own — 'matches explicit user intent' or 'satisfies the "
            "stated length constraint' rather than a vague restatement of the whole goal. This is the "
            "human-readable identity of the criterion; every other field on this entry is a judgment "
            "about it."
        )
    )
    met: bool = Field(
        description=(
            "Whether this specific criterion is currently satisfied, as a plain binary reader-facing "
            "signal independent of the richer verdict field below. Set it purely on this one "
            "criterion's own evidence — never let a path_quality or answer_correctness finding change "
            "it, since those are separate axes evaluated on their own entries elsewhere in this schema."
        )
    )
    verdict: GoalSuccessVerdict = Field(
        description=(
            "The finer-grained read on this one criterion drawn from the shared GoalSuccessVerdict "
            "vocabulary, distinguishing states `met` alone cannot — a criterion can be genuinely "
            "unattemptable yet, actively regressing after once being met, or blocked by something "
            "external to the agent's own work. Judge it against this criterion alone, not the goal as "
            "a whole."
        )
    )
    evidence: str = Field(
        description=(
            "The specific, concrete fact from the current context that justifies this entry's met and "
            "verdict values — a quoted requirement, a specific output excerpt, or a specific constraint "
            "check. State the fact itself rather than a restatement of the criterion, since the "
            "criterion is already captured above and this field exists to let a reader audit the "
            "judgment independently."
        )
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of how confidently this specific criterion could be checked against the "
            "current context, tracked per-entry rather than once for the whole checklist. A criterion "
            "that cannot yet be checked at all should carry a low confidence value alongside an "
            "honest verdict, rather than being marked met on an optimistic guess."
        )
    )
    blocking: bool = Field(
        description=(
            "Whether this criterion being unmet is, on its own, enough to prevent overall goal "
            "success — as opposed to a minor or optional criterion whose failure is survivable. This "
            "lets a reader triage a long checklist by scanning for blocking=True entries first rather "
            "than weighing every criterion as equally important."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which this entry was recorded. Because entries are never edited in "
            "place — a criterion whose answer changes gets a brand-new entry with the current "
            "iteration and the same criterion_id — a reader takes the entry with the highest iteration "
            "for a given criterion_id as that criterion's current state."
        )
    )


class PathQualityCheckEntry(BaseModel):
    """One independently-evaluated criterion about how the work was carried out, judged only on process."""

    criterion_id: str = Field(
        description=(
            "A stable identifier for the criterion this entry evaluates, such as 'no-redundant-tool-"
            "calls' or 'followed-stated-plan'. Reuse the same identifier every time this criterion is "
            "re-evaluated so a reader can group every entry for one criterion together and take the "
            "highest-iteration entry as current. Assign it once, the first time the criterion is "
            "identified, and never change it."
        )
    )
    criterion: str = Field(
        description=(
            "The specific, checkable process requirement being evaluated — 'no redundant tool calls' "
            "or 'no unsafe action taken without a stated reason' rather than a vague sense of overall "
            "process quality. This is the human-readable identity of the criterion that every other "
            "field on this entry judges."
        )
    )
    met: bool = Field(
        description=(
            "Whether this specific process criterion is currently satisfied. Scored purely on the "
            "path taken so far — a path criterion should never fail just because the goal ultimately "
            "wasn't reached, and should never pass just because the final output happened to be "
            "correct despite a messy process."
        )
    )
    verdict: PathQualityVerdict = Field(
        description=(
            "The finer-grained read on this one criterion drawn from the shared PathQualityVerdict "
            "vocabulary, distinguishing states `met` alone cannot — a criterion can be actively "
            "recovering from an earlier violation, currently blocked, or redundant without yet being "
            "outright unsafe. Judge it against this one criterion, not the path as a whole."
        )
    )
    evidence: str = Field(
        description=(
            "The specific action, tool call, or step from the current context that justifies this "
            "entry's met and verdict values. Name the concrete step rather than restating the "
            "criterion, since the criterion is already captured above and this field is what lets a "
            "reader audit the judgment independently of the agent's own self-report."
        )
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of how confidently this specific criterion could be checked against the "
            "actions taken so far, tracked per-entry. A step whose safety or efficiency cannot yet be "
            "fully assessed should carry a low confidence value alongside an honest verdict, rather "
            "than defaulting to met=True."
        )
    )
    blocking: bool = Field(
        description=(
            "Whether this criterion being unmet is, on its own, severe enough to call the whole path "
            "unsafe or unusable — as opposed to a minor inefficiency that does not threaten the run. "
            "This lets a reader triage a long checklist for the process failures that actually matter "
            "without weighing every entry equally."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which this entry was recorded. Entries are never edited in place — "
            "a criterion whose answer changes gets a new entry with the current iteration and the same "
            "criterion_id — so a reader takes the highest-iteration entry per criterion_id as current."
        )
    )


class AnswerCorrectnessCheckEntry(BaseModel):
    """One independently-evaluated criterion about the factual content of a claim, judged only on correctness."""

    criterion_id: str = Field(
        description=(
            "A stable identifier for the criterion this entry evaluates, such as 'claims-are-sourced' "
            "or 'no-internal-contradictions'. Reuse the same identifier every time this criterion is "
            "re-evaluated so a reader can group every entry for one criterion together and take the "
            "highest-iteration entry as current. Assign it once and never change it."
        )
    )
    criterion: str = Field(
        description=(
            "The specific, checkable factual requirement being evaluated — 'every numeric claim is "
            "traceable to a source' or 'no two claims contradict each other' rather than a vague sense "
            "of overall trustworthiness. This is the human-readable identity of the criterion every "
            "other field on this entry judges."
        )
    )
    met: bool = Field(
        description=(
            "Whether this specific correctness criterion is currently satisfied. Scored purely on the "
            "claims and evidence available so far — a criterion here should never be marked met just "
            "because the goal was reached through a clean path, since correctness is judged "
            "independently of both the outcome and the process."
        )
    )
    verdict: AnswerCorrectnessVerdict = Field(
        description=(
            "The finer-grained read on this one criterion drawn from the shared AnswerCorrectnessVerdict "
            "vocabulary, distinguishing states `met` alone cannot — a criterion can be pending "
            "verification, stale relative to newer information, or self-contradictory without yet "
            "being outright disproven. Judge it against this one criterion, not the answer as a whole."
        )
    )
    evidence: str = Field(
        description=(
            "The specific source, quoted fact, or logical check from the current context that "
            "justifies this entry's met and verdict values. State the concrete evidence rather than "
            "restating the criterion, since this field is what lets a reader audit the judgment "
            "without re-deriving it from scratch."
        )
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of how confidently this specific criterion could be checked against "
            "available evidence, tracked per-entry. A claim that cannot yet be verified one way or the "
            "other should carry a low confidence value alongside an honest 'unverified'-leaning "
            "verdict, rather than a confident but unsupported met=True."
        )
    )
    blocking: bool = Field(
        description=(
            "Whether this criterion being unmet is, on its own, severe enough to call the whole "
            "answer untrustworthy — as opposed to a minor phrasing nitpick that does not threaten "
            "correctness. This lets a reader triage a long checklist for the correctness failures that "
            "actually matter."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which this entry was recorded. Entries are never edited in place — "
            "a criterion whose answer changes gets a new entry with the current iteration and the same "
            "criterion_id — so a reader takes the highest-iteration entry per criterion_id as current."
        )
    )


# ---------------------------------------------------------------------------
# SymmetricEventLedgerTrace helpers
# ---------------------------------------------------------------------------
class GoalSuccessEvent(BaseModel):
    """One status change on a single subgoal within the overall goal."""

    iteration: int = Field(
        description=(
            "The run iteration at which this event was recorded. Because events are never edited in "
            "place, a reader takes the event with the highest iteration for a given subgoal_id as that "
            "subgoal's current state; earlier events for the same subgoal_id remain in the record as "
            "history, not as something to overwrite."
        )
    )
    subgoal_id: str = Field(
        description=(
            "A stable identifier for the subgoal this event describes. Reuse the same identifier every "
            "time this subgoal is mentioned again, even across many updates, so a reader can group "
            "every event for one subgoal together. Assign it the first time a subgoal is identified and "
            "never change it for the life of the run."
        )
    )
    status: GoalSuccessVerdict = Field(
        description=(
            "The current read on this specific subgoal drawn from the shared GoalSuccessVerdict "
            "vocabulary, scoped only to this subgoal and not to the overall goal. Judge it "
            "independently of how this subgoal's own steps were carried out and independently of "
            "whether its claims have been verified — those are separate axes recorded on their own "
            "event ledgers."
        )
    )
    previous_status: GoalSuccessVerdict | None = Field(
        default=None,
        description=(
            "The status this same subgoal_id held immediately before this event, or left unset for the "
            "subgoal's very first event. Recording it here, alongside the new status, lets a reader see "
            "the transition directly on one event rather than diffing two separate log entries, which "
            "matters most for catching a regression such as achieved reverting to in_progress."
        ),
    )
    description: str = Field(
        description=(
            "What actually happened to cause this status change — the specific action, discovery, or "
            "piece of new information involved. Phrase it as a concrete event rather than a restatement "
            "of the status value, since the status field already captures the verdict and this field "
            "exists to explain why it changed."
        )
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in this event's status value, tracked per-event rather than "
            "once for the whole ledger, since confidence in an early subgoal read can differ sharply "
            "from confidence in a later one. Base it on how much of the subgoal's own success criteria "
            "could actually be checked against the current context at the time of this event."
        )
    )
    triggered_by: str = Field(
        description=(
            "What in the agent's own work caused this event to be recorded — a specific tool result, a "
            "specific piece of reasoning, or a specific piece of user-provided context. This is what "
            "turns the ledger from a bare state log into an explainable trail a later reader can follow "
            "back to the actual cause of each transition."
        )
    )
    blocking: bool = Field(
        description=(
            "Whether this subgoal being unresolved currently blocks the overall goal from being "
            "considered met. A subgoal can be behind schedule without being blocking if the overall "
            "goal does not strictly require it; this field lets a reader separate the subgoals that "
            "actually gate completion from those that do not."
        )
    )


class PathQualityEvent(BaseModel):
    """One meaningful action taken during the run, scored for efficiency and safety independent of outcome."""

    iteration: int = Field(
        description=(
            "The run iteration at which this action was taken and this event recorded. Combined with "
            "step_id, this is what lets a reader reconstruct the exact sequence of meaningful actions "
            "across the run, including which actions happened concurrently within the same iteration."
        )
    )
    step_id: str = Field(
        description=(
            "A stable identifier for this specific action. A retried action gets a brand-new step_id "
            "rather than reusing the original one, so the ledger reflects that a retry is a distinct "
            "event with its own risk and outcome, not a mutation of the step that came before it."
        )
    )
    action: str = Field(
        description=(
            "What the agent actually did — the specific tool call, decision, or step taken, phrased "
            "concretely enough that a reader unfamiliar with this run can picture the action without "
            "opening the main agent's own transcript."
        )
    )
    status: PathQualityVerdict = Field(
        description=(
            "The current read on this specific action drawn from the shared PathQualityVerdict "
            "vocabulary, scoped only to this one action rather than the path as a whole. A single "
            "risky or blocked action does not need to make every other action in the ledger risky or "
            "blocked; each event carries its own independent read."
        )
    )
    risk_flag: ErrorSeverity = Field(
        description=(
            "How much risk this specific action carried, drawn from the shared ErrorSeverity scale — "
            "the same axis-independent severity vocabulary used for classified mistakes elsewhere in "
            "this SDK's continual-trace schemas, reused here to describe risk rather than an already-"
            "realized error. A trivial risk_flag on an otherwise ordinary action needs no further "
            "explanation; a severe or higher value should be backed up by the action field describing "
            "specifically what made it risky."
        )
    )
    tool_name: str | None = Field(
        default=None,
        description=(
            "The name of the tool this action invoked, when the action was a tool call, or left unset "
            "for an action that was purely reasoning with no tool involved. This lets a reader filter "
            "the ledger down to tool-driven risk specifically, which is often where the highest-"
            "consequence actions concentrate."
        ),
    )
    recoverable: bool = Field(
        description=(
            "Whether this action's effects, if they turn out to have been wrong, can still be undone "
            "or corrected later in the run — as opposed to an action with a permanent, irreversible "
            "consequence. This is often more decision-relevant than risk_flag alone, since a "
            "recoverable risky action is a very different situation from an irreversible one."
        )
    )
    error_type: PathQualityErrorType | None = Field(
        default=None,
        description=(
            "The category of process mistake this action represents, drawn from the shared "
            "PathQualityErrorType vocabulary, or left unset when this event describes ordinary or good "
            "process rather than a mistake. Only set this when status and risk_flag together already "
            "indicate something went wrong with how the action was carried out."
        ),
    )


class AnswerCorrectnessEvent(BaseModel):
    """One claim checked against available evidence, scored for correctness independent of goal or process."""

    iteration: int = Field(
        description=(
            "The run iteration at which this claim was checked and this event recorded. A claim can be "
            "re-checked at a later iteration as new information arrives, producing a second event with "
            "the same claim_id and a later iteration rather than replacing the first."
        )
    )
    claim_id: str = Field(
        description=(
            "A stable identifier for the specific claim this event checks. Reuse the same identifier "
            "every time this claim is re-verified so a reader can fold the log and take the "
            "highest-iteration event per claim_id as that claim's current standing, while still seeing "
            "the full verification history if needed."
        )
    )
    claim_text: str = Field(
        description=(
            "The specific factual assertion being checked, quoted or closely paraphrased from the "
            "agent's own output, precisely enough that a reader can judge for themselves whether the "
            "verdict and verified fields below are justified."
        )
    )
    verdict: AnswerCorrectnessVerdict = Field(
        description=(
            "The current read on this specific claim drawn from the shared AnswerCorrectnessVerdict "
            "vocabulary, distinguishing states the plain verified boolean cannot — a claim can be "
            "pending verification, stale relative to newer information, or self-contradictory with "
            "another claim without yet being outright disproven."
        )
    )
    verified: bool = Field(
        description=(
            "Whether this specific claim currently holds up against available evidence, as a plain "
            "binary reader-facing signal independent of the richer verdict field above. Judge it purely "
            "on this claim's own evidence, independent of whether the goal was reached or the path was "
            "efficient."
        )
    )
    source: str | None = Field(
        default=None,
        description=(
            "The specific document, tool result, or verifiable fact this claim was checked against, or "
            "left unset when no checkable source exists yet for this claim. This is what lets a reader "
            "audit verified and verdict independently rather than taking them on faith."
        ),
    )
    error_type: AnswerCorrectnessErrorType | None = Field(
        default=None,
        description=(
            "The category of factual mistake this claim represents, drawn from the shared "
            "AnswerCorrectnessErrorType vocabulary, or left unset when this event describes a verified "
            "or not-yet-disproven claim rather than a mistake. Only set this once verdict and verified "
            "together already indicate something is actually wrong with the claim."
        ),
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in this event's verdict and verified values, tracked "
            "per-event since confidence in an early, lightly-checked claim can differ sharply from a "
            "claim checked against a strong source later in the run."
        )
    )


# ---------------------------------------------------------------------------
# SymmetricTimelineTrace helpers
# ---------------------------------------------------------------------------
class GoalSuccessSnapshot(BaseModel):
    """One per-pass reading of overall goal status, appended to build a trend line rather than only a final value."""

    iteration: int = Field(
        description=(
            "The run iteration this snapshot was taken at. Snapshots are appended exactly once per "
            "trace-agent pass and never edited in place, so the full ordered sequence of iteration "
            "values is what lets a reader reconstruct the trend across the run."
        )
    )
    status: GoalSuccessVerdict = Field(
        description=(
            "The current overall goal-success read at this point in the run, drawn from the shared "
            "GoalSuccessVerdict vocabulary. A reversal — status moving backward from a later iteration "
            "to an earlier one, such as achieved regressing to in_progress — should be visible directly "
            "in the sequence of snapshots, not smoothed away by only keeping the latest value."
        )
    )
    confidence: float = Field(
        description=(
            "A 0-1 estimate of confidence in this snapshot's status value, recorded fresh at every "
            "pass so a reader can see not just whether the status changed but whether the agent's own "
            "certainty about it grew or shrank over the run."
        )
    )
    completion_pct: float = Field(
        description=(
            "0-1. How much of the goal's scope is done as of this snapshot, tracked alongside status "
            "so a reader can distinguish steady incremental progress from a status value that jumps "
            "without the underlying completion actually moving."
        )
    )
    note: str = Field(
        description=(
            "A short prose note on what changed since the previous snapshot, or why nothing changed. "
            "Write this fresh at every pass rather than restating the same note snapshot after "
            "snapshot, since a flat, unchanging note across many entries is itself a signal something "
            "may not actually be getting re-evaluated."
        )
    )
    blocking_issue: str | None = Field(
        default=None,
        description=(
            "The single biggest thing currently preventing goal success at this point in the run, or "
            "left unset when nothing is currently blocking. This is what a reader scanning the timeline "
            "for the moment things went wrong should look at first."
        ),
    )
    changed_since_last: bool = Field(
        description=(
            "Whether status, confidence, or completion_pct actually moved since the previous snapshot "
            "in this timeline. This lets a reader quickly filter a long timeline down to the passes "
            "that mattered without re-diffing every consecutive pair of snapshots by hand."
        )
    )
    stability: JudgmentStability = Field(
        description=(
            "How stable the goal-success read has been across the most recent snapshots, drawn from "
            "the shared JudgmentStability vocabulary. A status that keeps flipping between snapshots is "
            "a materially different situation from one that has held steady even at a middling "
            "confidence, and this field is what surfaces that difference explicitly."
        )
    )


class PathQualitySnapshot(BaseModel):
    """One per-pass reading of overall path quality, appended to build a trend line of efficiency and risk over the run."""

    iteration: int = Field(
        description=(
            "The run iteration this snapshot was taken at. Snapshots are appended exactly once per "
            "trace-agent pass and never edited in place, so the ordered sequence of iteration values is "
            "what lets a reader reconstruct how the path evolved."
        )
    )
    efficiency: float = Field(
        description=(
            "0-1. The absence of redundant or wasted steps among the actions taken up to this point in "
            "the run, read fresh at every pass rather than carried forward unchanged, since new "
            "redundancy can appear at any point."
        )
    )
    risky_action_count: int = Field(
        description=(
            "The cumulative count of actions flagged as carrying meaningful risk, counted from the "
            "start of the run up to and including this snapshot's iteration — not a per-pass delta. A "
            "single entry is therefore always enough to read the running total at that point in the run "
            "without summing across prior snapshots."
        )
    )
    status: PathQualityVerdict = Field(
        description=(
            "The current overall path-quality read at this point in the run, drawn from the shared "
            "PathQualityVerdict vocabulary. This can move independently of efficiency and "
            "risky_action_count in either direction — a still-efficient path can turn risky through a "
            "single consequential action, and a recovering path can regain a healthy status while "
            "efficiency stays temporarily depressed."
        )
    )
    note: str = Field(
        description=(
            "A short prose note on what changed in the path since the previous snapshot, or why "
            "nothing changed. Written fresh at every pass; call out specifically which action, if any, "
            "moved risky_action_count or status since the last entry."
        )
    )
    blocked_duration_iterations: int = Field(
        description=(
            "How many consecutive iterations the path has currently been in a blocked or "
            "significantly-impaired state, reset to zero once the path recovers. This turns a bare "
            "status label into a measurable duration a reader can use to judge how serious the current "
            "blockage actually is."
        )
    )
    recovered_from_risk: bool = Field(
        description=(
            "Whether this specific snapshot represents a recovery from a risky or blocked state "
            "recorded in an earlier snapshot in this same timeline. This lets a reader distinguish a "
            "path that is risky for the first time from one that has already recovered once and is now "
            "risky again, which is a meaningfully different pattern."
        )
    )
    stability: JudgmentStability = Field(
        description=(
            "How stable the path-quality read has been across the most recent snapshots, drawn from "
            "the shared JudgmentStability vocabulary. A status oscillating between efficient and risky "
            "snapshot to snapshot is a materially different situation from one trending steadily in "
            "either direction."
        )
    )


class AnswerCorrectnessSnapshot(BaseModel):
    """One per-pass reading of overall claim correctness, appended to build a trend line of verification progress over the run."""

    iteration: int = Field(
        description=(
            "The run iteration this snapshot was taken at. Snapshots are appended exactly once per "
            "trace-agent pass and never edited in place, so the ordered sequence of iteration values is "
            "what lets a reader reconstruct how verification progressed."
        )
    )
    verified_claim_count: int = Field(
        description=(
            "The cumulative count of claims verified against evidence as of this snapshot's iteration, "
            "counted from the start of the run — not a per-pass delta. A single entry is therefore "
            "enough to read the running total without summing across prior snapshots."
        )
    )
    contradiction_count: int = Field(
        description=(
            "The cumulative count of contradictions found among claims as of this snapshot's "
            "iteration, again as a running total rather than a delta. A value that rises partway "
            "through the run and never falls back is itself a meaningful signal this field is meant to "
            "preserve, since it means an earlier contradiction was never actually resolved."
        )
    )
    status: AnswerCorrectnessVerdict = Field(
        description=(
            "The current overall answer-correctness read at this point in the run, drawn from the "
            "shared AnswerCorrectnessVerdict vocabulary. This can move independently of the two raw "
            "counts above in either direction — a high verified_claim_count does not guarantee a "
            "'verified' status if even one significant contradiction remains unresolved."
        )
    )
    note: str = Field(
        description=(
            "A short prose note on what changed in claim correctness since the previous snapshot, or "
            "why nothing changed. Written fresh at every pass; call out specifically which claim, if "
            "any, moved verified_claim_count or contradiction_count since the last entry."
        )
    )
    unverified_claim_count: int = Field(
        description=(
            "The cumulative count of claims made so far that have not yet been checked against any "
            "evidence, as a running total. Tracked separately from verified_claim_count and "
            "contradiction_count so a reader can distinguish claims that are actively wrong from claims "
            "that simply have not been examined yet."
        )
    )
    retracted_claim_count: int = Field(
        description=(
            "The cumulative count of claims that were once verified or asserted and have since been "
            "explicitly withdrawn or superseded, as a running total. A rising retracted_claim_count "
            "alongside a rising verified_claim_count indicates active self-correction rather than "
            "steady accumulation of unchecked confidence."
        )
    )
    stability: JudgmentStability = Field(
        description=(
            "How stable the answer-correctness read has been across the most recent snapshots, drawn "
            "from the shared JudgmentStability vocabulary. A status that keeps flipping between "
            "snapshots as new claims surface is a materially different situation from one that has "
            "held steady even while the raw counts keep climbing."
        )
    )


__all__ = [
    "AnswerCorrectnessCheckEntry",
    "AnswerCorrectnessEvent",
    "AnswerCorrectnessSnapshot",
    "GoalSuccessCheckEntry",
    "GoalSuccessEvent",
    "GoalSuccessSnapshot",
    "PathQualityCheckEntry",
    "PathQualityEvent",
    "PathQualitySnapshot",
]
