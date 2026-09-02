"""FILE: vidbyte/trace/continual/prebuilt_events.py

PURPOSE: Defines the smaller "helper" Pydantic submodels that back the five nested performance-focused prebuilt continual trace schemas in vidbyte/trace/continual/prebuilt.py — one status-event, prediction, resolution, judgment, or decision-point record per submodel, each used as the item shape of a list field or the shape of a single nested OBJECT field on one of those five top-level trace models.
ROLE IN CODEBASE: Imported exclusively by vidbyte/trace/continual/prebuilt.py, which annotates HierarchicalTaskTreeTraceModel, CalibrationTraceModel, ErrorTaxonomyTraceModel, SelfConsistencyEnsembleTraceModel, and CounterfactualAlternativesTraceModel fields with these classes (directly for a nested OBJECT field, or as `list[SubModel]` for a nested ARRAY field). TraceSchema.from_model (vidbyte/lib/dataclasses/trace.py) recurses into every class here the same way it recurses into any nested BaseModel/list[BaseModel] annotation, so each class needs its own Field(description=...) on every attribute, the same requirement enforced at the top level. Draws its closed vocabularies from vidbyte/lib/enums/continual_trace.py.
ARCHITECTURE NOTE: This file exists purely to keep vidbyte/trace/continual/prebuilt.py readable: the five top-level TraceModel/TraceSchema pairs a caller actually imports stay in prebuilt.py, while the many smaller per-event/per-prediction records that back their list and nested-object fields live here. No class in this file is itself converted to a TraceSchema or exported outside vidbyte/trace/continual — a class here only ever appears as another model's nested field shape, never as a schema a caller passes to TraceOption.continual directly.
COMMON MODIFICATION PATTERNS: Add a new field to an existing helper class here, then confirm the class still parses under TraceSchema.from_model by running scripts/test-continual-trace.py's prebuilt-schema cases (they assert exact top-level field counts on the five schemas in prebuilt.py, not on the classes in this file, so adding fields here is safe on its own). Add a brand-new helper class here only when introducing a new list/nested-object field on one of the five top-level models in prebuilt.py; the model in prebuilt.py that references it must import the class name from this file.
WHAT NOT TO DO IN THIS FILE: Do not define a top-level TraceModel or call TraceSchema.from_model here; those live in prebuilt.py only. Do not add closed string vocabularies inline as Literal types; add a new member (or a new enum) to vidbyte/lib/enums/continual_trace.py instead, matching this file's existing pattern of typing verdict/category/severity fields against a shared ContinualTraceEnum subclass. Do not duplicate a helper class that already exists here for a different schema — check this file before adding a near-identical record shape.
KNOWN EDGE CASES: Every class here is deliberately flat (no field on any class in this file is itself another nested BaseModel), which keeps every schema well under MAX_TRACE_FIELD_NESTING_DEPTH even though prebuilt.py's own fields already spend one level of nesting to reach these classes. Several classes carry a stable `*_id` field specifically so a later record (a resolution, a rework event, a regret event) can join back to the record it concerns by id rather than by iteration number, since two records can share the same iteration.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, docs/design/continual-trace-agent.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_continual_trace.py, scripts/test-continual-trace.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.enums.continual_trace import (
    AnswerCorrectnessErrorType,
    AnswerCorrectnessVerdict,
    CalibratedAxis,
    ErrorSeverity,
    GoalSuccessErrorType,
    GoalSuccessVerdict,
    PathQualityErrorType,
    PathQualityVerdict,
    PathRegretAssessment,
)


# ---------------------------------------------------------------------------
# HierarchicalTaskTreeTrace helpers
# ---------------------------------------------------------------------------
class TaskNodeEvent(BaseModel):
    """One status event for a single node in the task's own decomposition tree."""

    node_id: str = Field(
        description=(
            "A stable identifier for the task-tree node this event describes. Reuse the same "
            "identifier every time this node is mentioned again, even across many updates, so a "
            "reader can group every event for one node together and take the latest one as current. "
            "Assign it the first time a node is identified and never change it for the life of the run."
        )
    )
    parent_node_id: str | None = Field(
        default=None,
        description=(
            "The node_id of the node this one was decomposed from, or left unset for the root task "
            "itself. This is what turns a flat list of events into a tree: a reader reconstructs the "
            "hierarchy purely from these parent references rather than from any nesting in the data. "
            "Keep it stable once set, even as the node's own status changes many times afterward."
        ),
    )
    depth: int = Field(
        description=(
            "How many decomposition steps separate this node from the root task, with the root task "
            "itself at the shallowest depth. Depth grows every time a node is broken into smaller "
            "subtasks and lets a reader judge how granular the current decomposition has become "
            "without walking the whole parent chain."
        )
    )
    description: str = Field(
        description=(
            "What this specific node of work actually is, phrased narrowly enough to distinguish it "
            "from its siblings and its parent. This is the human-readable identity of the node; every "
            "other field on this event describes a judgment about it. Keep the phrasing stable across "
            "events for the same node_id so a reader can recognize repeated mentions at a glance."
        )
    )
    goal_success_verdict: GoalSuccessVerdict = Field(
        description=(
            "The current judgment on whether this specific node's own objective has been met, scoped "
            "only to this node's work and not to the task as a whole. Judge it independently of how "
            "this node's own steps were carried out and independently of whether its claims have been "
            "verified — those are separate judgments recorded elsewhere on this same event."
        )
    )
    path_quality_verdict: PathQualityVerdict = Field(
        description=(
            "The current judgment on how efficiently and safely this node's own work was carried out, "
            "independent of whether the node's objective was ultimately met. A node can reach a good "
            "outcome through a wasteful or risky process, or a poor outcome through a clean one; this "
            "field records only the process, scoped to this node."
        )
    )
    correctness_verdict: AnswerCorrectnessVerdict = Field(
        description=(
            "The current judgment on whether any claims produced specifically by this node's work hold "
            "up against available evidence, independent of the other two verdicts on this event. Leave "
            "it at its default unverified state until this node has actually produced a checkable claim "
            "worth judging."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which this event was recorded. Because events are never edited in "
            "place, a reader takes the event with the highest iteration for a given node_id as that "
            "node's current state; earlier events for the same node_id remain in the record as history, "
            "not as something to overwrite."
        )
    )


class ReworkEvent(BaseModel):
    """One instance of a task-tree node needing to be reopened after it was already marked resolved."""

    node_id: str = Field(
        description=(
            "The identifier of the node being reopened, matching a node_id already recorded in the "
            "task-tree event log. Reuse the exact same identifier so a reader can connect this rework "
            "back to the original node's full history rather than treating it as an unrelated event."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which the need for rework was discovered, not the iteration the node "
            "was originally resolved at. This lets a reader measure how much later a mistaken resolution "
            "surfaced, which is itself a signal about how confidently earlier verdicts should be trusted."
        )
    )
    reason: str = Field(
        description=(
            "Why a node that was already considered finished had to be reopened. State the actual cause "
            "discovered — new information, a missed constraint, a downstream failure that traced back to "
            "this node — rather than simply restating that a mistake occurred, since the cause is what "
            "makes this event useful to a later reader."
        )
    )
    axis_reopened: CalibratedAxis = Field(
        description=(
            "Which of the three performance axes actually turned out to be wrong and drove the need for "
            "rework — the node's goal-success verdict, its path-quality verdict, or its correctness "
            "verdict. A single rework event should name the one axis whose prior verdict was mistaken, "
            "not the node as a whole, since a node's other two axes may have been judged correctly all "
            "along."
        )
    )
    previous_verdict: str = Field(
        description=(
            "The exact verdict value the reopened axis held immediately before this rework event, taken "
            "verbatim from the most recent matching task_nodes entry. Recording it here, rather than "
            "requiring a reader to look it up, is what makes it possible to measure how far off a "
            "prematurely confident verdict actually was."
        )
    )
    corrected_verdict: str = Field(
        description=(
            "The verdict value the reopened axis was updated to as a direct result of this rework event. "
            "Compare it against previous_verdict to see the exact size and direction of the correction; "
            "the next task_nodes entry for this node_id should carry this same value forward on the "
            "axis named by axis_reopened."
        )
    )
    discovered_by: str = Field(
        description=(
            "What actually surfaced the need for rework — a self-check the agent ran on its own work, a "
            "downstream node failing in a way that traced back here, a sibling comparison that exposed "
            "an inconsistency, or an explicit external correction. This is a distinct signal from reason: "
            "reason explains the underlying mistake, this explains how it was caught."
        )
    )
    downstream_nodes_affected: list[str] = Field(
        default_factory=list,
        description=(
            "Identifiers of other nodes whose own resolution had to wait on, or be reconsidered because "
            "of, this rework event. An empty list means the correction was fully contained to this one "
            "node; a long list is a strong signal that this node sat on the tree's critical path when the "
            "mistake was discovered."
        ),
    )
    rework_resolved: bool = Field(
        description=(
            "Whether the reopened node has, as of the most recent update, actually reached a new stable "
            "verdict on the axis named by axis_reopened. False means the node is currently back in an "
            "open, unresolved state following this rework event and should not yet be treated as settled."
        )
    )


# ---------------------------------------------------------------------------
# CalibrationTrace helpers
# ---------------------------------------------------------------------------
class GoalCompletionPrediction(BaseModel):
    """One self-reported estimate of how complete the goal is, made before the true outcome is known."""

    prediction_id: str = Field(
        description=(
            "A stable identifier for this specific prediction, generated when the prediction is made. "
            "The matching resolution event, once the true outcome becomes known, must reuse this exact "
            "identifier so the two records can be joined; without a matching resolution, a prediction "
            "stays open and contributes nothing to calibration statistics yet."
        )
    )
    iteration_made: int = Field(
        description=(
            "The run iteration at which this estimate was made. This anchors the prediction in time "
            "independent of when it is later resolved, which is what makes it possible to measure how "
            "far in advance the agent's self-assessment was formed relative to how long it took to "
            "actually find out whether that assessment was right."
        )
    )
    predicted_pct: float = Field(
        description=(
            "The agent's own estimate, at the time this prediction was made, of how much of the stated "
            "goal is complete, expressed on a scale from fully unmet to fully met. This is a genuine "
            "forecast made under uncertainty, not a restatement of a verdict recorded elsewhere — it "
            "should reflect what the agent actually believed before the outcome was confirmed."
        )
    )
    stated_reasoning: str = Field(
        description=(
            "Why the agent settled on this particular estimate rather than a higher or lower one. "
            "Recording the reasoning, not just the number, is what makes it possible to later diagnose "
            "whether a miscalibration came from a bad process, missing information, or a sound process "
            "that was simply overtaken by later events."
        )
    )
    confidence_in_estimate: float = Field(
        description=(
            "A separate, meta-level confidence in predicted_pct itself — how sure the agent is that its "
            "own percentage estimate is close to correct, as distinct from the percentage estimate. Two "
            "predictions can share the same predicted_pct while one is a near-certain read and the other "
            "is a rough guess; only this field distinguishes them."
        )
    )
    key_uncertainty: str = Field(
        description=(
            "The single biggest unknown driving how far off predicted_pct could plausibly turn out to "
            "be. Naming it explicitly gives a later reader the fastest way to judge whether a large "
            "calibration_gap was a foreseeable risk the agent already knew about, or a genuine surprise."
        )
    )
    evidence_considered: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete signals the agent actually weighed when forming this estimate — specific completed "
            "subtasks, tool results, or stated requirements — rather than a restatement of stated_reasoning "
            "in list form. An empty list is itself informative: it means the estimate was made with little "
            "or no concrete grounding."
        ),
    )
    previous_prediction_id: str | None = Field(
        default=None,
        description=(
            "The prediction_id of an earlier goal-completion prediction this one revises, or left unset "
            "if this is the first prediction made about this goal. Chaining predictions this way lets a "
            "reader trace how the agent's own estimate evolved across the run, separate from how the true "
            "outcome eventually resolved."
        ),
    )
    iteration_of_last_goal_change: int = Field(
        description=(
            "The most recent run iteration at which the stated goal itself was refined or reinterpreted, "
            "as of when this prediction was made. A prediction made shortly after a goal change deserves "
            "less trust than one made against a goal understanding that has been stable for a while, since "
            "the agent has had less time to reassess against the new goal."
        )
    )


class GoalCompletionResolution(BaseModel):
    """The true outcome of a goal-completion prediction, recorded once it becomes known."""

    prediction_id: str = Field(
        description=(
            "The identifier of the prediction this resolution closes out. It must match a prediction_id "
            "already recorded among goal-completion predictions; a resolution with no matching "
            "prediction is meaningless on its own and should not be recorded."
        )
    )
    iteration_resolved: int = Field(
        description=(
            "The run iteration at which the true outcome became known, which may be much later than the "
            "iteration the original prediction was made at. The gap between the two iterations is itself "
            "informative about how long this kind of prediction typically takes to confirm."
        )
    )
    actual_outcome: GoalSuccessVerdict = Field(
        description=(
            "What actually happened with the goal, now that it can be judged directly rather than "
            "estimated. This is the ground truth the original predicted_pct is measured against; record "
            "it as the honest outcome even when it contradicts what was predicted."
        )
    )
    calibration_gap: float = Field(
        description=(
            "How far the original prediction was from what actually happened, computed by comparing "
            "predicted_pct against actual_outcome on a shared scale. A value near the low end means the "
            "agent's self-assessment was trustworthy for this prediction; a large value means it was not, "
            "regardless of whether the prediction was optimistic or pessimistic."
        )
    )
    bias_direction: str = Field(
        description=(
            "Whether the original estimate ran optimistic (predicted more completion than actually "
            "happened) or pessimistic (predicted less), stated in plain language rather than as a signed "
            "number. This is the direction calibration_gap alone cannot express, and a run of resolutions "
            "biased the same direction is a stronger signal than any single gap value."
        )
    )
    resolution_evidence: str = Field(
        description=(
            "What concretely established actual_outcome — the specific check, verification, or terminal "
            "state that made the true outcome knowable. This lets a later reader judge how trustworthy "
            "the ground truth itself is, since a weakly evidenced resolution should be trusted less than "
            "one grounded in a direct, verifiable check."
        )
    )
    surprise_factor: float = Field(
        description=(
            "How unexpected actual_outcome was, not against the specific predicted_pct number but against "
            "what a reasonable observer following the run would have expected at the time. This can differ "
            "from calibration_gap: a prediction can be numerically far off while the eventual outcome was "
            "still broadly foreseeable, or numerically close while the outcome was genuinely surprising."
        )
    )
    contributing_factor: str = Field(
        description=(
            "The single largest driver of the gap between what was predicted and what actually happened — "
            "new information that emerged after the prediction, a misjudgment at prediction time, or an "
            "external event outside the agent's control. Naming one dominant factor, rather than listing "
            "every possible contributor, keeps this field actionable for a later reader."
        )
    )
    lessons_applied: bool = Field(
        description=(
            "Whether this resolution's lesson is already visibly reflected in later goal-completion "
            "predictions — for example, a later prediction citing this same key_uncertainty or adjusting "
            "its confidence_in_estimate in the direction this resolution suggests. False does not "
            "necessarily mean the lesson was ignored; it may simply be too early to tell."
        )
    )


class PathEfficiencyPrediction(BaseModel):
    """One self-reported estimate of how efficient the current approach will turn out to be."""

    prediction_id: str = Field(
        description=(
            "A stable identifier for this prediction, generated when it is made and reused unchanged by "
            "its matching resolution so the two can be joined later."
        )
    )
    iteration_made: int = Field(
        description=(
            "The run iteration at which this efficiency estimate was made, anchoring it in time relative "
            "to when the approach it describes was actually still in progress."
        )
    )
    predicted_efficiency: float = Field(
        description=(
            "The agent's own forecast, made while the current approach is still underway, of how "
            "efficient that approach will turn out to have been once it concludes. This should reflect a "
            "genuine forecast under uncertainty rather than a measurement of something already finished."
        )
    )
    stated_reasoning: str = Field(
        description=(
            "Why the agent settled on this particular efficiency forecast rather than a higher or lower "
            "one. Recording the reasoning is what lets a later reader diagnose, once the resolution is "
            "known, whether a miscalibration came from a flawed process or from events the agent could "
            "not have reasonably anticipated at prediction time."
        )
    )
    confidence_in_estimate: float = Field(
        description=(
            "A separate, meta-level confidence in predicted_efficiency itself, distinct from the forecast "
            "value. A confident forecast that turns out wrong is a more informative miscalibration signal "
            "than a hedged one that turns out wrong by the same amount."
        )
    )
    assumed_remaining_steps: int = Field(
        description=(
            "The number of further steps the agent assumed it would still need when it formed this "
            "estimate. This is the concrete assumption predicted_efficiency was built on; comparing it "
            "later against steps_actually_taken on the matching resolution is what turns a bare efficiency "
            "number into a checkable claim."
        )
    )
    risk_factors_considered: list[str] = Field(
        default_factory=list,
        description=(
            "Specific things that could derail or slow the approach, which the agent explicitly weighed "
            "when forming this prediction. An obstacle that later appears among the resolution's "
            "unexpected_obstacles but not here is a genuine blind spot, not a factor the agent simply "
            "chose to discount."
        ),
    )
    baseline_reference: str = Field(
        description=(
            "What this efficiency estimate is actually being measured against — an ideal minimal path for "
            "this kind of task, a prior similar approach earlier in the same run, or a general expectation "
            "for tasks of this shape. Without stating the baseline, a bare efficiency number has no fixed "
            "meaning across different predictions."
        )
    )


class PathEfficiencyResolution(BaseModel):
    """The true efficiency of an approach, measured once it has actually concluded."""

    prediction_id: str = Field(
        description=(
            "The identifier of the prediction this resolution closes out, matching an entry already "
            "recorded among path-efficiency predictions."
        )
    )
    iteration_resolved: int = Field(
        description=(
            "The run iteration at which the approach actually concluded and its true efficiency could be "
            "measured directly, rather than estimated."
        )
    )
    actual_efficiency: float = Field(
        description=(
            "The measured efficiency of the approach once it concluded, judged on the same scale as the "
            "original prediction so the two are directly comparable."
        )
    )
    calibration_gap: float = Field(
        description=(
            "How far the original efficiency prediction was from what was actually measured. This is "
            "what turns a bare performance number into a statement about the trustworthiness of the "
            "agent's own forecasting, independent of whether the approach itself was good or bad."
        )
    )
    bias_direction: str = Field(
        description=(
            "Whether the original forecast ran optimistic (predicted higher efficiency than was actually "
            "achieved) or pessimistic (predicted lower), stated in plain language. Tracking this direction "
            "across many resolutions is what path_efficiency_overconfidence_flag on the parent schema is "
            "ultimately derived from."
        )
    )
    resolution_evidence: str = Field(
        description=(
            "What concretely established actual_efficiency — a direct step count, a comparison against "
            "baseline_reference, or an explicit efficiency check — so a later reader can judge how solid "
            "the measurement itself is, not just trust the number at face value."
        )
    )
    unexpected_obstacles: list[str] = Field(
        default_factory=list,
        description=(
            "Obstacles that actually slowed the approach but were not named among the original "
            "prediction's risk_factors_considered — genuine blind spots rather than known risks that "
            "simply materialized. A pattern of the same kind of unexpected obstacle recurring across "
            "resolutions is more actionable than any single instance."
        ),
    )
    steps_actually_taken: int = Field(
        description=(
            "The true number of steps the approach ended up taking, compared directly against the "
            "matching prediction's assumed_remaining_steps to show exactly how the plan's own scope "
            "estimate held up, separate from the qualitative efficiency judgment."
        )
    )
    lessons_applied: bool = Field(
        description=(
            "Whether this resolution's lesson is already visibly reflected in later path-efficiency "
            "predictions — for example, a later prediction citing an obstacle from unexpected_obstacles "
            "among its own risk_factors_considered. False does not necessarily mean the lesson was "
            "ignored; it may simply be too early to tell."
        )
    )


class ClaimConfidencePrediction(BaseModel):
    """One self-reported confidence level attached to a specific claim, recorded when the claim is made."""

    prediction_id: str = Field(
        description=(
            "A stable identifier for this specific confidence prediction, generated when the claim is "
            "made and reused unchanged by its matching resolution."
        )
    )
    claim_text: str = Field(
        description=(
            "The specific factual claim this confidence level is attached to, stated precisely enough "
            "that a reader can independently judge later whether it turned out to be true."
        )
    )
    iteration_made: int = Field(description="The run iteration at which the claim was made and its confidence recorded.")
    predicted_confidence: float = Field(
        description=(
            "How confident the agent was in this specific claim at the moment it was made, expressed on "
            "a scale from no confidence to full confidence. This should reflect the agent's genuine "
            "internal certainty, not be inflated or deflated to look well-calibrated after the fact."
        )
    )
    evidence_at_time: list[str] = Field(
        default_factory=list,
        description=(
            "The specific evidence the agent had actually gathered and relied on when it made this claim, "
            "not evidence discovered later. This is what lets a reader distinguish a confident claim made "
            "on thin evidence from one genuinely well-supported at the time it was made."
        ),
    )
    alternative_considered: str = Field(
        description=(
            "A plausible alternative claim the agent weighed and rejected in favor of claim_text, if one "
            "existed. Leave this at a value indicating none was considered when the claim was never "
            "genuinely in doubt, since forcing an alternative into existence for every claim would make "
            "this field noise rather than signal."
        )
    )
    stakes: str = Field(
        description=(
            "What actually depends on this specific claim being true — a downstream decision, another "
            "claim built on top of it, or the goal itself. This is what tells a later reader whether a "
            "given claim's confidence calibration matters a great deal or barely at all to the run's "
            "outcome."
        )
    )
    source_type: str = Field(
        description=(
            "Where the claim's basis actually came from — direct tool output, prior background knowledge, "
            "or an inference drawn from other claims already made. Claims inferred from other claims "
            "inherit and can compound the uncertainty of what they were built on, which this field makes "
            "explicit rather than leaving implicit in stated confidence alone."
        )
    )


class ClaimConfidenceResolution(BaseModel):
    """Whether a claim actually held up, checked once verification becomes possible."""

    prediction_id: str = Field(
        description=(
            "The identifier of the confidence prediction this resolution closes out, matching an entry "
            "already recorded among claim-confidence predictions."
        )
    )
    iteration_resolved: int = Field(
        description=(
            "The run iteration at which the claim was actually checked against evidence, which may be "
            "well after the iteration it was originally made at."
        )
    )
    verified: bool = Field(
        description=(
            "Whether the claim actually held up once checked. This is the ground truth the original "
            "predicted_confidence is measured against, recorded honestly even when it contradicts the "
            "confidence that was originally stated."
        )
    )
    calibration_gap: float = Field(
        description=(
            "How far the original stated confidence was from what verification actually found — high "
            "confidence in a claim that turned out false, or low confidence in one that turned out true, "
            "both produce a large gap here even though they represent opposite kinds of miscalibration."
        )
    )
    verification_method: str = Field(
        description=(
            "How the claim was actually checked — a specific tool call, a cross-reference against another "
            "source, or direct observation of the outcome it predicted. A verification method that is "
            "itself weak deserves the same skepticism applied to the claim it is meant to settle."
        )
    )
    contradicting_evidence: str | None = Field(
        default=None,
        description=(
            "The specific evidence that contradicted the claim, when verified is false. Leave this unset "
            "when the claim was verified true, or when it turned out false for a reason other than "
            "conflicting evidence (for example, the claim became moot before it could be checked)."
        ),
    )
    bias_direction: str = Field(
        description=(
            "Whether the original stated confidence ran overconfident (higher than verification "
            "warranted) or underconfident (lower than verification warranted), stated in plain language. "
            "This is exactly the distinction claim_confidence_overconfidence_examples and "
            "claim_confidence_underconfidence_examples on the parent schema are built from."
        )
    )
    lessons_applied: bool = Field(
        description=(
            "Whether this resolution's lesson is already visibly reflected in later claim-confidence "
            "predictions — for example, a later prediction on a similarly sourced claim stating a "
            "confidence level shifted in the direction this resolution suggests. False does not "
            "necessarily mean the lesson was ignored; it may simply be too early to tell."
        )
    )


# ---------------------------------------------------------------------------
# ErrorTaxonomyTrace helpers
# ---------------------------------------------------------------------------
class GoalSuccessErrorEvent(BaseModel):
    """One classified mistake that worked against the agent's stated goal."""

    error_type: GoalSuccessErrorType = Field(
        description=(
            "Which category of goal-success mistake this event belongs to. Classifying against a fixed, "
            "closed set rather than free text is what makes it possible to later notice that the same "
            "kind of mistake keeps recurring instead of reading every entry as a one-off."
        )
    )
    description: str = Field(
        description=(
            "What actually happened in this specific instance, concrete enough that a later reader can "
            "judge for themselves whether error_type was the right classification, not just a restatement "
            "of the category name."
        )
    )
    iteration: int = Field(
        description=(
            "The run iteration at which this mistake was identified, which may be after the step that "
            "actually caused it. This is what lets a reader order the error history and measure how "
            "quickly problems are being caught relative to when they occur."
        )
    )
    severity: ErrorSeverity = Field(
        description=(
            "How much this specific mistake actually mattered to the goal, on a shared ascending scale "
            "used identically across every error axis in this schema. A high recurrence of low-severity "
            "mistakes and a single occurrence of a critical one call for very different responses, which "
            "the raw error_type classification alone cannot distinguish."
        )
    )
    detected_by: str = Field(
        description=(
            "How this mistake was actually caught — the agent's own self-check, a downstream failure that "
            "traced back to it, or an explicit external correction. This measures the agent's own "
            "self-monitoring on this specific instance, complementing the schema-level "
            "correctness_self_caught_error_count aggregate."
        )
    )
    correction_applied: str | None = Field(
        default=None,
        description=(
            "What the agent actually did in response once this mistake was identified, if anything. "
            "Leave this unset when no correction has been applied yet, which is itself informative about "
            "whether a known goal-success problem is still outstanding."
        ),
    )
    related_node_id: str | None = Field(
        default=None,
        description=(
            "The identifier of a specific task-tree node (from a paired HierarchicalTaskTreeTrace, when "
            "one is in use alongside this schema) that this mistake traces back to, when a clear one "
            "exists. Leave this unset when the mistake is not cleanly attributable to a single node."
        ),
    )
    recurrence_count: int = Field(
        description=(
            "How many times this specific instance-level mistake — not the broader error_type category, "
            "but this particular manifestation of it — has now been observed. This is a finer-grained "
            "signal than goal_success_recurring_pattern, which only tracks recurrence at the category "
            "level."
        )
    )


class PathQualityErrorEvent(BaseModel):
    """One classified mistake in how the agent went about the task, independent of the outcome reached."""

    error_type: PathQualityErrorType = Field(
        description=(
            "Which category of process mistake this event belongs to. This judges the approach taken, "
            "not whether that approach happened to still produce an acceptable result."
        )
    )
    description: str = Field(
        description="What actually happened in this specific instance, concrete enough to stand on its own without requiring the reader to already know the context that produced it."
    )
    iteration: int = Field(description="The run iteration at which this process mistake was identified.")
    severity: ErrorSeverity = Field(
        description=(
            "How much this specific process mistake actually mattered to how the work got done, on the "
            "same shared ascending scale used identically across every error axis in this schema. A "
            "redundant step that cost one extra tool call is a different order of problem than one that "
            "derailed the whole approach, and only this field distinguishes them."
        )
    )
    detected_by: str = Field(
        description=(
            "How this mistake was actually caught — the agent's own self-check, a later step that "
            "exposed it, or an explicit external correction. Complements path_quality_recovery_success_rate "
            "on the parent schema by explaining how each individual mistake entered the record in the "
            "first place."
        )
    )
    correction_applied: str | None = Field(
        default=None,
        description=(
            "What the agent actually did to recover from this specific mistake, if anything. Leave this "
            "unset when no recovery attempt has been made yet — this is one of the raw signals "
            "path_quality_recovery_success_rate is aggregated from."
        ),
    )
    time_lost_estimate: str = Field(
        description=(
            "A qualitative account of how much time, effort, or how many steps this specific mistake "
            "actually cost, in plain language. This is a process-specific cost measure distinct from "
            "severity: a low-severity mistake by outcome can still have wasted a disproportionate amount "
            "of effort to work around."
        )
    )
    recurrence_count: int = Field(
        description=(
            "How many times this specific instance-level mistake — not the broader error_type category, "
            "but this particular manifestation of it — has now been observed. This is a finer-grained "
            "signal than path_quality_most_common_error_type, which only tracks the plurality at the "
            "category level."
        )
    )


class AnswerCorrectnessErrorEvent(BaseModel):
    """One classified mistake in the factual content of a claim the agent made."""

    error_type: AnswerCorrectnessErrorType = Field(
        description=(
            "Which category of factual mistake this event belongs to. This judges the truth of what was "
            "stated, independent of how well-reasoned the process that produced it was."
        )
    )
    description: str = Field(
        description="What the claim actually got wrong and, where it is known, what the correct fact or source should have been instead."
    )
    iteration: int = Field(
        description="The run iteration at which this factual mistake was identified, which is often well after the iteration the claim was originally made at."
    )
    severity: ErrorSeverity = Field(
        description=(
            "How much this specific factual mistake actually mattered, on the same shared ascending scale "
            "used identically across every error axis in this schema. A stale but inconsequential detail "
            "and a hallucinated fact the final answer depends on both count as one entry each in "
            "correctness_error_events, but only this field distinguishes how seriously to weigh them."
        )
    )
    detected_by: str = Field(
        description=(
            "How this mistake was actually caught — the agent's own self-check, cross-referencing against "
            "another claim or source, or an explicit external correction. This is the per-instance signal "
            "correctness_self_caught_error_count on the parent schema is aggregated from."
        )
    )
    correction_applied: str | None = Field(
        default=None,
        description=(
            "What the agent actually did once this factual mistake was identified — retracting the claim, "
            "issuing a corrected version, or flagging it as unresolved. Leave this unset when no correction "
            "has been applied yet."
        ),
    )
    affected_downstream_claims: list[str] = Field(
        default_factory=list,
        description=(
            "Other claims the agent made that relied on this now-known-incorrect one, and therefore "
            "inherit its error even though they were not independently wrong. An empty list means the "
            "mistake was self-contained; a long list means the error propagated and every listed claim "
            "should be treated as suspect until independently re-checked."
        ),
    )
    recurrence_count: int = Field(
        description=(
            "How many times this specific instance-level mistake — not the broader error_type category, "
            "but this particular manifestation of it — has now been observed. This is a finer-grained "
            "signal than correctness_error_clustering_note, which describes clustering qualitatively "
            "rather than counting a single recurring instance."
        )
    )


# ---------------------------------------------------------------------------
# SelfConsistencyEnsembleTrace helpers
# ---------------------------------------------------------------------------
class GoalSuccessJudgment(BaseModel):
    """One independent judgment of whether the goal has been met, made as part of a self-consistency pass."""

    iteration: int = Field(description="The run iteration at which this independent judgment was made.")
    verdict: GoalSuccessVerdict = Field(
        description=(
            "This judgment's own conclusion about goal success, reasoned independently of any other "
            "judgment already recorded for this axis rather than anchored on a prior one."
        )
    )
    confidence: float = Field(
        description="How confident this specific judgment is in its own verdict, independent of how confident any other judgment in the ensemble happens to be."
    )
    reasoning: str = Field(
        description=(
            "The reasoning this specific judgment used to reach its verdict, recorded in enough detail "
            "that a reader can later tell whether two disagreeing judgments actually considered different "
            "evidence or reached different conclusions from the same evidence."
        )
    )
    evidence_reviewed: list[str] = Field(
        default_factory=list,
        description=(
            "The specific pieces of evidence this judgment actually consulted before reaching its verdict. "
            "Comparing evidence_reviewed across two disagreeing judgments is what tells a reader whether "
            "the disagreement reflects genuinely independent evidence or the same evidence read two "
            "different ways."
        ),
    )
    judge_pass_number: int = Field(
        description=(
            "Which numbered independent pass over this axis this judgment represents — the first, second, "
            "third, and so on. This is distinct from iteration, which records when the pass happened; "
            "judge_pass_number records how many independent looks at this axis have now accumulated."
        )
    )
    agreed_with_prior_majority: bool = Field(
        description=(
            "Whether this judgment's verdict matched the majority verdict as it stood immediately before "
            "this pass was added. Tracking this per-judgment, rather than only as an aggregate agreement "
            "rate, is what lets a reader see exactly which pass first broke from or restored consensus."
        )
    )
    dissent_reason: str | None = Field(
        default=None,
        description=(
            "If this judgment broke from the prior majority, why — what evidence or reasoning led it to a "
            "different conclusion. Leave this unset when agreed_with_prior_majority is true, since a "
            "judgment that agrees with the majority has nothing to dissent about."
        ),
    )


class PathQualityJudgment(BaseModel):
    """One independent judgment of path quality, made as part of a self-consistency pass."""

    iteration: int = Field(description="The run iteration at which this independent judgment was made.")
    verdict: PathQualityVerdict = Field(
        description="This judgment's own conclusion about path quality, reasoned independently of any other judgment already recorded for this axis."
    )
    confidence: float = Field(description="How confident this specific judgment is in its own verdict.")
    reasoning: str = Field(description="The reasoning this specific judgment used to reach its verdict.")
    evidence_reviewed: list[str] = Field(
        default_factory=list,
        description=(
            "The specific steps, tool calls, or decisions this judgment actually reviewed before reaching "
            "its verdict on path quality. This is what lets a reader tell whether two disagreeing "
            "judgments examined the same portion of the run or focused on different parts of it."
        ),
    )
    judge_pass_number: int = Field(
        description=(
            "Which numbered independent pass over this axis this judgment represents. This is distinct "
            "from iteration, which records when the pass happened; judge_pass_number records how many "
            "independent looks at path quality have now accumulated."
        )
    )
    agreed_with_prior_majority: bool = Field(
        description=(
            "Whether this judgment's verdict matched the majority verdict as it stood immediately before "
            "this pass was added, letting a reader see exactly which pass first broke from or restored "
            "consensus on path quality."
        )
    )
    dissent_reason: str | None = Field(
        default=None,
        description=(
            "If this judgment broke from the prior majority, why. Leave this unset when "
            "agreed_with_prior_majority is true."
        ),
    )


class AnswerCorrectnessJudgment(BaseModel):
    """One independent judgment of answer correctness, made as part of a self-consistency pass."""

    iteration: int = Field(description="The run iteration at which this independent judgment was made.")
    verdict: AnswerCorrectnessVerdict = Field(
        description="This judgment's own conclusion about correctness, reasoned independently of any other judgment already recorded for this axis."
    )
    confidence: float = Field(description="How confident this specific judgment is in its own verdict.")
    reasoning: str = Field(
        description=(
            "The reasoning chain this specific judgment used to reach its verdict — how it moved from the "
            "evidence in evidence_reviewed to a conclusion — kept separate from the raw list of sources so "
            "a reader can evaluate the logic and the evidence base independently of each other."
        )
    )
    evidence_reviewed: list[str] = Field(
        default_factory=list,
        description=(
            "Which specific sources or evidence this judgment actually consulted, so a later reader can "
            "assess how independent it really was from the other judgments in the ensemble — two "
            "judgments that consulted disjoint sources and still agree are stronger evidence of "
            "correctness than two that consulted the same source."
        ),
    )
    judge_pass_number: int = Field(
        description=(
            "Which numbered independent pass over this axis this judgment represents. This is distinct "
            "from iteration, which records when the pass happened; judge_pass_number records how many "
            "independent looks at correctness have now accumulated."
        )
    )
    agreed_with_prior_majority: bool = Field(
        description=(
            "Whether this judgment's verdict matched the majority verdict as it stood immediately before "
            "this pass was added. A judgment that disagrees is exactly the kind of event "
            "correctness_flip_flop_count on the parent schema is counting."
        )
    )
    dissent_reason: str | None = Field(
        default=None,
        description=(
            "If this judgment broke from the prior majority, why — grounds this specific pass gives for "
            "reaching a different correctness conclusion. Leave this unset when agreed_with_prior_majority "
            "is true."
        ),
    )


# ---------------------------------------------------------------------------
# CounterfactualAlternativesTrace helpers
# ---------------------------------------------------------------------------
class GoalInterpretationAlternative(BaseModel):
    """One point where the stated goal was genuinely open to more than one reasonable reading."""

    iteration: int = Field(description="The run iteration at which this interpretation choice was made.")
    chosen_interpretation: str = Field(description="The reading of the goal the agent actually committed to at this point.")
    alternative_interpretations: list[str] = Field(
        default_factory=list,
        description=(
            "Other readings of the goal that were genuinely plausible at this point but were not chosen. "
            "Only include readings a reasonable reader could actually have taken from the same original "
            "request, not readings invented purely for the sake of having an alternative to list."
        ),
    )
    why_chosen: str = Field(
        description="The specific signal in the original request, or in context gathered since, that made the chosen interpretation more likely correct than the alternatives listed alongside it."
    )
    confidence_in_choice: float = Field(
        description=(
            "How confident the agent was, at the time this interpretation was chosen, that it was reading "
            "the goal correctly. A low value paired with a request that never revisits this choice is a "
            "risk worth surfacing even if the interpretation is never actually challenged."
        )
    )
    ambiguity_source: str = Field(
        description=(
            "What specifically in the original request created the ambiguity in the first place — vague "
            "wording, an unstated assumption, or a genuine conflict between two stated goals. Naming the "
            "source is what makes this record useful beyond this one instance, since the same source of "
            "ambiguity can recur across other interpretation points in the same run."
        )
    )
    revisited: bool = Field(
        description=(
            "Whether this interpretation choice was later reconsidered at all, whether or not it ended up "
            "changing. A choice that is never revisited despite a low confidence_in_choice is a stronger "
            "risk signal than one that was reconsidered and confirmed."
        )
    )
    outcome_if_wrong: str = Field(
        description=(
            "What would actually go wrong, concretely, if chosen_interpretation later turns out to be the "
            "incorrect reading. This is what lets a reader triage which unresolved ambiguities in the run "
            "actually matter and which are low-stakes even if technically unresolved."
        )
    )


class GoalInterpretationSwitchEvent(BaseModel):
    """One instance of the agent actually changing its working interpretation of the goal mid-run."""

    iteration: int = Field(description="The run iteration at which the interpretation actually changed.")
    from_interpretation: str = Field(description="The reading of the goal the agent was working from immediately before this switch.")
    to_interpretation: str = Field(description="The reading of the goal the agent adopted from this point forward.")
    trigger: str = Field(
        description="What specifically caused the switch — new information, a contradiction discovered in the prior reading, or explicit clarification — rather than simply noting that a switch occurred."
    )
    work_invalidated: list[str] = Field(
        default_factory=list,
        description=(
            "Prior work — task-tree nodes, claims, or completed steps — that had to be redone or discarded "
            "specifically because it was built on from_interpretation and does not carry over to "
            "to_interpretation. An empty list means the switch was caught early enough to cost nothing."
        ),
    )
    cost_of_switch: str = Field(
        description=(
            "A qualitative account of how expensive and disruptive this switch actually was, beyond the "
            "literal list in work_invalidated — whether it meant restarting a small piece of analysis or "
            "unwinding a substantial portion of the run's progress."
        )
    )
    could_have_been_avoided: bool = Field(
        description=(
            "A retrospective judgment on whether better upfront disambiguation — asking a clarifying "
            "question, or reading the original request more carefully — would plausibly have avoided this "
            "switch entirely. This distinguishes an avoidable process failure from a switch that only made "
            "sense once genuinely new information arrived."
        )
    )
    confidence_in_new_interpretation: float = Field(
        description=(
            "How confident the agent is in to_interpretation at the moment of this switch. A low value "
            "here means the run is still not settled on a stable reading of the goal and another switch "
            "may follow."
        )
    )


class PathDecisionPoint(BaseModel):
    """One point where more than one way of proceeding was genuinely available."""

    decision_id: str = Field(
        description=(
            "A stable identifier for this specific decision, generated when the decision is made. A later "
            "PathRegretEvent that concerns this decision reuses this identifier as its join key, rather "
            "than relying on iteration alone, since two distinct decisions can occur in the same iteration."
        )
    )
    iteration: int = Field(description="The run iteration at which this decision was made.")
    decision: str = Field(description="What specifically had to be decided at this point in the work.")
    alternatives_considered: list[str] = Field(
        default_factory=list,
        description="Other ways of proceeding that were genuinely available at this point, whether or not they were seriously weighed before being set aside.",
    )
    chosen_action: str = Field(description="The option the agent actually took at this decision point.")
    regret_assessment: PathRegretAssessment = Field(
        description=(
            "A retrospective judgment, made once enough is known to say, on whether the chosen action was "
            "actually the right call compared to the alternatives that were available at the time. This "
            "should be revisited and updated later if new information changes the answer."
        )
    )
    deciding_factor: str = Field(
        description=(
            "The single consideration that actually tipped the choice toward chosen_action over the other "
            "entries in alternatives_considered. This is what lets a reader judge whether the deciding "
            "factor still holds up in hindsight, separate from whether the outcome itself turned out well."
        )
    )
    reversibility: str = Field(
        description=(
            "Whether this decision could realistically be undone later if it turned out to be wrong — a "
            "cheaply reversible choice versus a one-way door. A poor decision that was still reversible "
            "carries much less risk than an equally poor one that locked in irreversible consequences, "
            "even though both might receive the same regret_assessment."
        )
    )
    confidence_at_decision_time: float = Field(
        description=(
            "How confident the agent was in chosen_action at the moment this decision was made, before any "
            "of the consequences were known. Comparing this against the eventual regret_assessment shows "
            "whether the agent's own sense of a decision's soundness tends to hold up."
        )
    )


class PathRegretEvent(BaseModel):
    """One instance of a past decision being realized, later, to have been the wrong one."""

    decision_id: str = Field(
        description=(
            "The decision_id of the PathDecisionPoint entry this regret concerns, joined by identifier "
            "rather than by iteration so that two decisions made in the same iteration cannot be confused "
            "with one another."
        )
    )
    decision_iteration: int = Field(description="The run iteration at which the original decision this regret concerns was made.")
    regretted_at_iteration: int = Field(
        description=(
            "The run iteration at which it became clear the original decision was wrong, which is "
            "typically well after the decision itself was made. The gap between the two iterations shows "
            "how long the consequences of a bad decision took to surface."
        )
    )
    what_should_have_happened: str = Field(
        description="What the agent now believes it should have done instead, stated specifically enough that a later reader facing a similar decision could actually apply the lesson."
    )
    cost_of_mistake: str = Field(
        description=(
            "The concrete cost this decision actually incurred once it was recognized as wrong — wasted "
            "steps, discarded work, or a materially worse final result — stated specifically enough to "
            "judge whether this regret matters a great deal or only marginally."
        )
    )
    severity: ErrorSeverity = Field(
        description=(
            "How much this specific regretted decision actually mattered, on the same shared ascending "
            "scale used identically for classified errors elsewhere in this schema family. This lets a "
            "reader triage path regrets by real impact rather than treating every entry in "
            "path_regret_events as equally significant."
        )
    )
    trigger_for_realization: str = Field(
        description=(
            "What specifically caused the agent to realize, at regretted_at_iteration, that the earlier "
            "decision was wrong — a downstream failure, new information, or an explicit external "
            "correction. This is distinct from what_should_have_happened, which describes the fix rather "
            "than what exposed the need for one."
        )
    )
    corrective_action_taken: str | None = Field(
        default=None,
        description=(
            "What the agent actually did in response once this regret was recognized, if anything. Leave "
            "this unset when the mistake was identified but no corrective action has been taken yet — "
            "for example, because the decision was irreversible per the original decision point's "
            "reversibility field."
        ),
    )


class CorrectnessSourceAlternative(BaseModel):
    """One claim for which more than one source of evidence was genuinely available."""

    claim: str = Field(description="The specific claim this record concerns.")
    sources_considered: list[str] = Field(
        default_factory=list,
        description="Every source that was genuinely available to check this claim against, not only the one that was ultimately used.",
    )
    source_used: str = Field(description="Which of the considered sources the claim was actually verified against.")
    source_reliability_rank: int = Field(
        description=(
            "Where the source actually used ranks against the other considered sources in reliability, "
            "with the most reliable source ranked first. A claim verified against a source ranked far "
            "from first deserves less confidence than the raw verified flag alone would suggest."
        )
    )
    source_selection_reasoning: str = Field(
        description=(
            "Why source_used was chosen over the other entries in sources_considered, even when it is not "
            "the top-ranked one by source_reliability_rank — for example, because a more reliable source "
            "was unavailable or too costly to consult. This is what distinguishes a deliberate tradeoff "
            "from an oversight."
        )
    )
    confidence_in_claim: float = Field(
        description=(
            "How confident the agent is in the claim given the source actually used, as distinct from how "
            "confident it would be if it had used the top-ranked source instead. This is the honest, "
            "source-adjusted confidence rather than an idealized one."
        )
    )
    source_recency: str = Field(
        description=(
            "How current or stale source_used actually is. Correctness claims can go stale even when the "
            "source itself was reliable at the time it was published, so this is a distinct risk factor "
            "from source_reliability_rank, which measures trustworthiness rather than freshness."
        )
    )
    would_change_with_better_source: bool = Field(
        description=(
            "Whether the agent believes consulting a higher-ranked source from sources_considered, had it "
            "been used instead, could plausibly have changed the claim's outcome. True flags this as a "
            "claim worth re-checking against a better source if one becomes available later in the run."
        )
    )


class CorrectnessSourceConflictEvent(BaseModel):
    """One instance where two considered sources for the same claim actually disagreed."""

    claim: str = Field(description="The specific claim the conflicting sources concern.")
    source_a: str = Field(description="One of the two sources that disagreed.")
    source_b: str = Field(description="The other source that disagreed.")
    resolution: str = Field(
        description=(
            "How the conflict was actually resolved — which source was trusted and why, or that the "
            "conflict remains unresolved and the claim should be treated as unsettled rather than as "
            "confidently verified."
        )
    )
    conflict_severity: ErrorSeverity = Field(
        description=(
            "How much this specific source disagreement actually matters to the claim's trustworthiness, "
            "on the same shared ascending scale used identically for classified errors elsewhere in this "
            "schema family. A minor wording discrepancy between sources is a very different problem from "
            "two sources flatly contradicting each other on the substance of the claim."
        )
    )
    source_a_position: str = Field(
        description=(
            "What source_a actually asserts about the claim, stated specifically enough that a reader can "
            "judge the disagreement without needing to consult the original source directly."
        )
    )
    source_b_position: str = Field(
        description=(
            "What source_b actually asserts about the claim, stated specifically enough that a reader can "
            "judge the disagreement without needing to consult the original source directly, and can "
            "directly compare against source_a_position."
        )
    )
    resolution_confidence: float = Field(
        description=(
            "How confident the agent actually is that its own resolution correctly identified the more "
            "trustworthy source, as distinct from resolution itself, which only states what was decided. "
            "A low value here means the claim should still be treated with some caution even though a "
            "resolution was recorded."
        )
    )


__all__ = [
    "AnswerCorrectnessErrorEvent",
    "AnswerCorrectnessJudgment",
    "ClaimConfidencePrediction",
    "ClaimConfidenceResolution",
    "CorrectnessSourceAlternative",
    "CorrectnessSourceConflictEvent",
    "GoalCompletionPrediction",
    "GoalCompletionResolution",
    "GoalInterpretationAlternative",
    "GoalInterpretationSwitchEvent",
    "GoalSuccessErrorEvent",
    "GoalSuccessJudgment",
    "PathDecisionPoint",
    "PathEfficiencyPrediction",
    "PathEfficiencyResolution",
    "PathQualityErrorEvent",
    "PathQualityJudgment",
    "PathRegretEvent",
    "ReworkEvent",
    "TaskNodeEvent",
]
