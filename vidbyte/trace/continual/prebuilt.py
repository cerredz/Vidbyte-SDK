"""FILE: vidbyte/trace/continual/prebuilt.py

PURPOSE: Defines ready-made continual trace schemas developers can pass directly to TraceOption.continual, covering a general action log (ActionTrace) and five schemas scoring pure agent task performance across three separately-tracked axes: goal success, path quality, and answer correctness.
ROLE IN CODEBASE: Every schema here is a Pydantic model converted to a module-level TraceSchema constant via TraceSchema.from_model, re-exported by vidbyte.trace.continual, vidbyte.trace, and vidbyte.__init__ in that order. The many smaller per-event/per-prediction submodels each schema's list and nested-object fields are shaped by live in vidbyte/trace/continual/prebuilt_events.py and are imported from there rather than defined here.
ARCHITECTURE NOTE: The five performance schemas use TraceField's nested fields/items capability by annotating a field with a submodel (or list[submodel]) instead of dict[str, Any] — each submodel field still needs its own Field(description=...), recursively, the same requirement TraceSchema.from_model already enforces at the top level. No schema here ever combines the three axes into one number; each stays a separate field, and any array meant to accumulate across trace-agent passes is declared as its own top-level ARRAY field rather than nested inside an OBJECT field. Only the top-level TraceModel/TraceSchema pairs a caller actually imports live in this file; every smaller helper submodel lives in the sibling prebuilt_events.py so this file stays a readable index of what a caller can pass to TraceOption.continual.
COMMON MODIFICATION PATTERNS: Add a new prebuilt schema as a Pydantic model plus a TraceSchema.from_model(...) constant, then export both from vidbyte/trace/continual/__init__.py, vidbyte/trace/__init__.py, and vidbyte/__init__.py in that order, matching ActionTrace's existing position in all three files. Any helper submodel the new schema's list/nested-object fields need belongs in vidbyte/trace/continual/prebuilt_events.py, imported here by name — do not define a new helper class inline in this file.
KNOWN EDGE CASES: A submodel used only as an OBJECT field's shape (not a list item) needs no docstring, since only a list[SubModel] item shape falls back to a generated description when the submodel's own docstring is empty.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, docs/design/continual-trace-agent.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_continual_trace.py, scripts/test-continual-trace.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.lib.enums.continual_trace import (
    CalibratedAxis,
    CalibrationTrend,
    JudgmentStability,
    PathQualityVerdict,
)
from vidbyte.trace.continual.prebuilt_events import (
    AnswerCorrectnessErrorEvent,
    AnswerCorrectnessJudgment,
    ClaimConfidencePrediction,
    ClaimConfidenceResolution,
    CorrectnessSourceAlternative,
    CorrectnessSourceConflictEvent,
    GoalCompletionPrediction,
    GoalCompletionResolution,
    GoalInterpretationAlternative,
    GoalInterpretationSwitchEvent,
    GoalSuccessErrorEvent,
    GoalSuccessJudgment,
    PathDecisionPoint,
    PathEfficiencyPrediction,
    PathEfficiencyResolution,
    PathQualityErrorEvent,
    PathQualityJudgment,
    PathRegretEvent,
    ReworkEvent,
    TaskNodeEvent,
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


# ---------------------------------------------------------------------------
# HierarchicalTaskTreeTrace
# ---------------------------------------------------------------------------
class HierarchicalTaskTreeTraceModel(BaseModel):
    """Scores goal success, path quality, and answer correctness at every node of the task's own decomposition tree, and separately tracks the structural health of that decomposition."""

    task_nodes: list[TaskNodeEvent] = Field(
        default_factory=list,
        description=(
            "The full event log of the task-tree decomposition, one entry per status change on any "
            "node at any depth. This is the primary record the rest of this schema summarizes; every "
            "other field here is a derived observation computed by reading across this log rather than "
            "an independent measurement. Append a new event whenever a node is first identified or any "
            "one of its three verdicts changes."
        ),
    )
    root_task_summary: str = Field(
        description=(
            "A prose account of how the tree as a whole is trending, written by actually reading across "
            "task_nodes rather than mechanically combining the individual verdicts into one number. "
            "Focus on what has changed since the last update and what a reader most needs to know before "
            "looking at the raw event log. Replace this in full every update."
        )
    )
    deepest_unresolved_node: str = Field(
        description=(
            "The identifier and description of the single deepest node in the tree that is still "
            "unresolved on any of the three axes — the actual bottleneck the run is currently working "
            "through. When several nodes at the same depth are unresolved, name the one blocking the "
            "most other work. Replace this in full every update."
        )
    )
    nodes_with_goal_issues: list[str] = Field(
        default_factory=list,
        description=(
            "Identifiers of nodes currently flagged for a goal-success problem, kept separate from the "
            "path- and correctness-flagged lists below so a reader can immediately see which axis is "
            "driving trouble in which part of the tree without cross-referencing the full event log."
        ),
    )
    nodes_with_path_issues: list[str] = Field(
        default_factory=list,
        description=(
            "Identifiers of nodes currently flagged for a path-quality problem. A node can appear here "
            "and also be free of goal or correctness issues, since a node's process can be inefficient "
            "or risky even while it eventually reaches a correct, complete result."
        ),
    )
    nodes_with_correctness_issues: list[str] = Field(
        default_factory=list,
        description=(
            "Identifiers of nodes currently flagged for a correctness problem in the claims that node "
            "produced. A node can appear here independent of its goal or path standing, since a node can "
            "execute efficiently and still reach a factually wrong conclusion."
        ),
    )
    sibling_consistency_notes: str = Field(
        description=(
            "Whether subtasks sharing the same parent node have been handled with comparable quality, or "
            "whether quality has varied sharply between siblings that should reasonably have received "
            "similar treatment. Sharp variance between siblings is often a stronger signal of a systemic "
            "problem than any single node's own verdict. Replace this in full every update."
        )
    )
    critical_path_nodes: list[str] = Field(
        default_factory=list,
        description=(
            "The full chain of node identifiers from the root task down to whatever is currently "
            "blocking overall progress, in order — not just the blocking node itself but every node "
            "that has to resolve before it can. This is what a reader should look at first to understand "
            "what actually stands between the current state and completion."
        ),
    )
    orphaned_node_count: int = Field(
        description=(
            "How many nodes have been recorded whose declared parent_node_id has itself never appeared "
            "as a node in task_nodes. This is a data-quality signal about the tree's own construction, "
            "not about the task's progress, and a nonzero value means the hierarchy should be repaired "
            "before its other summary fields are trusted."
        )
    )
    tree_completeness_estimate: str = Field(
        description=(
            "The agent's own read on whether the task has been decomposed into all the subtasks it "
            "actually needs, or whether further decomposition is still likely required before the tree "
            "can be considered a reliable map of the work. This is a judgment about the plan's shape, "
            "separate from how well any existing node is being executed. Replace this in full every "
            "update."
        )
    )
    rework_events: list[ReworkEvent] = Field(
        default_factory=list,
        description=(
            "The append-only log of every instance where a node previously treated as resolved had to "
            "be reopened. A high rate of rework relative to the size of the tree is a strong signal that "
            "earlier verdicts in task_nodes were being recorded too optimistically and should be read "
            "with added skepticism."
        ),
    )
    longest_unbroken_success_chain: str = Field(
        description=(
            "A description of the longest parent-to-child chain of nodes that all currently hold a "
            "clean verdict on every axis at once. This highlights the part of the tree that is working "
            "well, which is just as useful to a later reader as knowing where the problems are. Replace "
            "this in full every update."
        )
    )
    tree_depth_reached: int = Field(
        description=(
            "The maximum depth value observed across task_nodes so far. A steadily growing value shows "
            "the agent is continuing to decompose the task further; a value that stops growing while "
            "work continues can mean the current decomposition has stabilized or that decomposition has "
            "stalled — the other fields on this schema are what distinguish the two."
        )
    )
    leaf_node_count: int = Field(
        description=(
            "How many distinct nodes have been identified with no children recorded against them — the "
            "actual count of indivisible units of work this run currently believes the task breaks down "
            "into. This number can rise across the run as further decomposition uncovers more leaf-level "
            "work."
        )
    )


HierarchicalTaskTreeTrace = TraceSchema.from_model(
    HierarchicalTaskTreeTraceModel,
    name="hierarchical_task_tree_trace",
    description="Scores goal success, path quality, and answer correctness at every node of the task's own decomposition tree.",
)


# ---------------------------------------------------------------------------
# CalibrationTrace
# ---------------------------------------------------------------------------
class CalibrationTraceModel(BaseModel):
    """Links early self-reported predictions to their later-known outcomes across all three performance axes, so how trustworthy the agent's own confidence is becomes visible alongside its raw performance."""

    goal_completion_predictions: list[GoalCompletionPrediction] = Field(
        default_factory=list,
        description=(
            "The append-only log of every goal-completion estimate the agent has committed to so far. "
            "Add an entry whenever the agent states a specific belief about how complete the goal "
            "currently is, before that belief can be confirmed against the true outcome."
        ),
    )
    goal_completion_resolutions: list[GoalCompletionResolution] = Field(
        default_factory=list,
        description=(
            "The append-only log of true outcomes for previously made goal-completion predictions, each "
            "linked back to its prediction by prediction_id. An entry here is only added once the actual "
            "outcome for a specific prior prediction becomes knowable."
        ),
    )
    path_efficiency_predictions: list[PathEfficiencyPrediction] = Field(
        default_factory=list,
        description=(
            "The append-only log of every efficiency estimate the agent has made about an approach that "
            "was still in progress at the time. Add an entry whenever the agent forecasts how efficient "
            "its current approach will turn out to be."
        ),
    )
    path_efficiency_resolutions: list[PathEfficiencyResolution] = Field(
        default_factory=list,
        description=(
            "The append-only log of true efficiency measurements for previously predicted approaches, "
            "each linked back to its prediction by prediction_id, recorded once the approach concludes "
            "and can be measured directly rather than estimated."
        ),
    )
    claim_confidence_predictions: list[ClaimConfidencePrediction] = Field(
        default_factory=list,
        description=(
            "The append-only log of every stated confidence level attached to a specific claim at the "
            "moment that claim was made. Add an entry for any claim worth later checking, not only ones "
            "the agent is already unsure about."
        ),
    )
    claim_confidence_resolutions: list[ClaimConfidenceResolution] = Field(
        default_factory=list,
        description=(
            "The append-only log of verification outcomes for previously made claims, each linked back to "
            "its original confidence prediction by prediction_id, recorded once the claim is actually "
            "checked against evidence."
        ),
    )
    goal_completion_calibration_trend: CalibrationTrend = Field(
        description=(
            "Whether goal-completion predictions have been getting better or worse calibrated as the run "
            "progresses, judged by comparing calibration_gap values across goal-completion resolutions "
            "over time rather than looking at any single resolution in isolation. Replace this in full "
            "every update."
        )
    )
    path_efficiency_overconfidence_flag: bool = Field(
        description=(
            "Whether the agent has been systematically overestimating its own path efficiency across "
            "resolved predictions so far, judged by whether predicted_efficiency values have tended to "
            "run higher than the matching actual_efficiency values rather than by any single comparison."
        )
    )
    claim_confidence_underconfidence_examples: list[str] = Field(
        default_factory=list,
        description=(
            "Claims the agent stated low confidence in that verification later found to be true. This is "
            "a hedging problem rather than an accuracy problem, and it is worth tracking separately from "
            "outright wrong claims because the appropriate correction is different: the agent should "
            "trust itself more in similar situations, not check more carefully."
        ),
    )
    claim_confidence_overconfidence_examples: list[str] = Field(
        default_factory=list,
        description=(
            "Claims the agent stated high confidence in that verification later found to be false. This "
            "is the more consequential direction of miscalibration, since a reader relying on stated "
            "confidence to decide what to double-check would have been misled by exactly these claims."
        ),
    )
    best_calibrated_axis: CalibratedAxis = Field(
        description=(
            "Which of the three performance axes currently has the smallest average calibration_gap "
            "across its resolved predictions — in other words, where the agent's own stated confidence "
            "can currently be trusted the most. Use one of the *_TIED members, or ALL_AXES_EQUAL, when "
            "two or more axes are genuinely too close to call rather than arbitrarily picking one as "
            "best. Replace this in full every update as more resolutions accumulate."
        )
    )
    worst_calibrated_axis: CalibratedAxis = Field(
        description=(
            "Which axis currently has the largest average calibration_gap across its resolved "
            "predictions — where a reader should discount the agent's own stated confidence and check "
            "independently rather than take it at face value. Use one of the *_TIED members, or "
            "ALL_AXES_EQUAL, when two or more axes are genuinely tied for worst rather than arbitrarily "
            "picking one. Replace this in full every update."
        )
    )
    unresolved_prediction_count: int = Field(
        description=(
            "How many predictions across all three axes currently have no matching resolution yet. This "
            "tells a reader how much of the calibration picture is still open and therefore how much "
            "weight the other summary fields on this schema currently deserve — a small number of "
            "resolutions supports much weaker conclusions than a large one."
        )
    )


CalibrationTrace = TraceSchema.from_model(
    CalibrationTraceModel,
    name="calibration_trace",
    description="Links self-reported predictions to their later-known outcomes across all three performance axes.",
)


# ---------------------------------------------------------------------------
# ErrorTaxonomyTrace
# ---------------------------------------------------------------------------
class ErrorTaxonomyTraceModel(BaseModel):
    """Classifies every observed failure against a fixed vocabulary per performance axis, then tracks a distinct second-order pattern for each axis rather than repeating the same summary field three times over."""

    goal_success_error_events: list[GoalSuccessErrorEvent] = Field(
        default_factory=list,
        description=(
            "The append-only classified log of every mistake found that worked against the stated goal. "
            "Add an entry for each new mistake identified; a mistake that keeps recurring should be "
            "logged again each time it recurs rather than only once."
        ),
    )
    goal_success_recurring_pattern: str = Field(
        description=(
            "Set only once the same error_type has occurred more than once within the goal-success error "
            "log, naming the recurring category and roughly when it has recurred. Leave this empty while "
            "every goal-success mistake so far has been a distinct, one-off kind of error. Replace this "
            "in full every update."
        )
    )
    goal_success_root_cause_hypothesis: str = Field(
        description=(
            "The agent's own best explanation for why its goal-success mistakes keep happening, reasoned "
            "from the pattern across the goal-success error log rather than restated from any single "
            "entry. This is a hypothesis, not a certainty, and should be revised as more evidence "
            "accumulates. Replace this in full every update."
        )
    )
    goal_success_error_free_streak: int = Field(
        description=(
            "How many consecutive iterations have passed with no new entry added to the goal-success "
            "error log. This resets whenever a new mistake is logged and gives a reader a quick read on "
            "recent trajectory without having to scan the full event log's timestamps."
        )
    )
    path_quality_error_events: list[PathQualityErrorEvent] = Field(
        default_factory=list,
        description=(
            "The append-only classified log of every mistake found in how the agent carried out its "
            "work, independent of whether the outcome was ultimately acceptable."
        ),
    )
    path_quality_disagreement_with_plan: str = Field(
        description=(
            "The largest gap identified so far between what the agent explicitly said it planned to do "
            "and what it actually did. This is a distinct signal from the classified error log: a "
            "deviation from a stated plan can be perfectly reasonable, or it can itself be the root cause "
            "behind several entries in the path-quality error log. Replace this in full every update."
        )
    )
    path_quality_most_common_error_type: str = Field(
        description=(
            "Which error_type value from the path-quality error log has occurred most often so far. "
            "Unlike a recurring-pattern flag that only fires on an exact repeat, this tracks the overall "
            "plurality across every distinct category observed, which is more informative once several "
            "different kinds of mistakes have accumulated. Replace this in full every update."
        )
    )
    path_quality_recovery_success_rate: float = Field(
        description=(
            "Of the times the agent hit a logged path-quality mistake and then visibly attempted to "
            "recover from it, the fraction of those attempts that actually worked. This measures the "
            "agent's resilience after a mistake, which is a different skill from avoiding the mistake in "
            "the first place. Replace this in full every update."
        )
    )
    correctness_error_events: list[AnswerCorrectnessErrorEvent] = Field(
        default_factory=list,
        description="The append-only classified log of every factual mistake found in the agent's stated claims.",
    )
    correctness_recurring_pattern: str = Field(
        description=(
            "Set only once the same error_type has occurred more than once within the correctness error "
            "log. Leave this empty while every correctness mistake so far has been a distinct, one-off "
            "kind of error. Replace this in full every update."
        )
    )
    correctness_error_clustering_note: str = Field(
        description=(
            "Whether the correctness mistakes recorded so far cluster around a specific topic, source, or "
            "kind of claim rather than being spread evenly across everything the agent has stated. A "
            "tight cluster is a stronger and more actionable signal than the same number of errors spread "
            "thin. Replace this in full every update."
        )
    )
    correctness_self_caught_error_count: int = Field(
        description=(
            "How many of the entries in the correctness error log the agent identified and flagged "
            "itself, as opposed to only being caught by an external check. This measures the agent's own "
            "self-monitoring ability, which matters independently of the raw error count."
        )
    )


ErrorTaxonomyTrace = TraceSchema.from_model(
    ErrorTaxonomyTraceModel,
    name="error_taxonomy_trace",
    description="Classifies every observed failure against a fixed vocabulary per performance axis.",
)


# ---------------------------------------------------------------------------
# SelfConsistencyEnsembleTrace
# ---------------------------------------------------------------------------
class SelfConsistencyEnsembleTraceModel(BaseModel):
    """Judges each performance axis multiple times independently and reports a distinct facet of that ensemble's behavior per axis, rather than collapsing repeated judgments into a single number for all three."""

    goal_success_independent_judgments: list[GoalSuccessJudgment] = Field(
        default_factory=list,
        description=(
            "The append-only log of every independent goal-success judgment made so far. Add a new entry "
            "each time the axis is judged again from scratch, rather than revising a prior entry, so "
            "disagreement between passes stays visible instead of being averaged away."
        ),
    )
    goal_success_agreement_rate: float = Field(
        description=(
            "The fraction of entries in the goal-success judgment log that currently agree with the "
            "majority verdict among them. This measures how consistent repeated judgment of this axis has "
            "been, separate from what that majority verdict actually is. Replace this in full every "
            "update."
        )
    )
    goal_success_confidence_spread: float = Field(
        description=(
            "The difference between the highest and lowest confidence values across the goal-success "
            "judgment log. This can be large even when every judgment reaches the same verdict, which is "
            "itself informative: agreement on the conclusion does not always mean agreement on how "
            "certain that conclusion is. Replace this in full every update."
        )
    )
    goal_success_judgment_stability: JudgmentStability = Field(
        description=(
            "Whether repeated goal-success judgments over the course of the run are trending toward "
            "agreement, trending apart, or holding steady, read as a trend across the goal-success "
            "judgment log over time rather than as a single snapshot. Use UNANIMOUS when every judgment "
            "so far agrees outright, SPLIT when dissent has settled into two comparably sized factions "
            "rather than a clear majority and minority, and INSUFFICIENT_DATA when fewer than two "
            "independent judgments have been recorded yet. Replace this in full every update."
        )
    )
    path_quality_independent_judgments: list[PathQualityJudgment] = Field(
        default_factory=list,
        description="The append-only log of every independent path-quality judgment made so far, following the same append-only, judge-from-scratch convention as the goal-success log above.",
    )
    path_quality_disagreement_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only specific reasons why two independent path-quality judgments reached different "
            "verdicts, recorded whenever that happens. This captures the substance of a disagreement in a "
            "way the raw judgment log alone does not make easy to scan."
        ),
    )
    path_quality_majority_verdict: PathQualityVerdict = Field(
        description=(
            "The current consolidated majority verdict across the path-quality judgment log — the "
            "conclusion itself, as distinct from the disagreement notes above which describe why any "
            "dissent exists rather than what the ensemble currently concludes. Replace this in full every "
            "update."
        )
    )
    path_quality_minority_reasoning_summary: str = Field(
        description=(
            "A condensed account of what the dissenting path-quality judgments actually argued, when "
            "there currently is a minority. Leave this empty when the ensemble is unanimous. Replace this "
            "in full every update."
        )
    )
    correctness_independent_judgments: list[AnswerCorrectnessJudgment] = Field(
        default_factory=list,
        description="The append-only log of every independent correctness judgment made so far, following the same append-only, judge-from-scratch convention as the other two axis logs.",
    )
    correctness_outlier_judgment: str = Field(
        description=(
            "A description of the single most divergent correctness judgment from the current majority, "
            "and what specifically made its reasoning different from the rest of the ensemble. Leave this "
            "empty when every judgment currently agrees. Replace this in full every update."
        )
    )
    correctness_judgment_source_diversity: str = Field(
        description=(
            "Whether the independent correctness judgments actually drew on different verification "
            "methods or sources of evidence, or effectively repeated the same check under a different "
            "iteration number. This is a validity check on the ensemble itself: judgments that are not "
            "genuinely independent overstate how much confidence their agreement should inspire. Replace "
            "this in full every update."
        )
    )
    correctness_flip_flop_count: int = Field(
        description=(
            "How many times the majority correctness verdict has changed direction over the course of "
            "the run. A high count signals persistent uncertainty on this axis, distinct from what any "
            "single outlier judgment shows, and is worth surfacing even when the current majority looks "
            "settled."
        )
    )


SelfConsistencyEnsembleTrace = TraceSchema.from_model(
    SelfConsistencyEnsembleTraceModel,
    name="self_consistency_ensemble_trace",
    description="Judges each performance axis multiple times independently and tracks the ensemble's own agreement.",
)


# ---------------------------------------------------------------------------
# CounterfactualAlternativesTrace
# ---------------------------------------------------------------------------
class CounterfactualAlternativesTraceModel(BaseModel):
    """At meaningful points on each performance axis, records what alternatives genuinely existed and whether the choice actually made held up, rather than only recording what happened."""

    goal_interpretation_alternatives: list[GoalInterpretationAlternative] = Field(
        default_factory=list,
        description=(
            "The append-only log of every point where the stated goal was genuinely open to more than "
            "one reasonable reading. Add an entry only where a plausible alternative reading actually "
            "existed, not for routine interpretation that was never really in doubt."
        ),
    )
    goal_interpretation_switch_events: list[GoalInterpretationSwitchEvent] = Field(
        default_factory=list,
        description=(
            "The append-only log of every time the agent's working interpretation of the goal actually "
            "changed mid-run, distinct from the alternatives log above, which records alternatives that "
            "were considered and set aside rather than ones later adopted."
        ),
    )
    goal_unexplored_interpretation_risk: str = Field(
        description=(
            "A plausible alternative reading of the goal that the agent never seriously considered, that "
            "could still turn out to be the one the requester actually intended. Leave this empty when no "
            "such gap is currently identified. Replace this in full every update."
        )
    )
    goal_alternative_confidence_gap: float = Field(
        description=(
            "How close the second-best interpretation was to the one actually chosen, in the agent's own "
            "confidence, at the most recent interpretation decision — a low value means no real "
            "alternative existed, a high value means the choice was close to arbitrary. Replace this in "
            "full every update."
        )
    )
    path_decision_points: list[PathDecisionPoint] = Field(
        default_factory=list,
        description=(
            "The append-only log of every point where more than one way of proceeding was genuinely "
            "available. Add an entry only where a real choice existed, not for steps where only one "
            "reasonable action was ever on the table."
        ),
    )
    path_regret_events: list[PathRegretEvent] = Field(
        default_factory=list,
        description=(
            "The append-only log of past decisions realized, later, to have been the wrong call — "
            "distinct from the regret_assessment already recorded on each path-decision-point entry, "
            "since this log specifically captures realizations that came after the decision was logged, "
            "not judgments made at the time of the decision itself."
        ),
    )
    path_unconsidered_shortcut: str = Field(
        description=(
            "A shortcut or better approach the agent only recognizes in hindsight, that was not even "
            "considered as an alternative at the time it mattered. This differs from an entry in the "
            "decision-point log because it names a blind spot rather than a choice that was actually "
            "weighed. Leave this empty when none is currently identified. Replace this in full every "
            "update."
        )
    )
    path_alternative_quality_gap: float = Field(
        description=(
            "The estimated efficiency difference between the path actually taken and the best alternative "
            "path identified in hindsight, including any unconsidered shortcut named above. Replace this "
            "in full every update."
        )
    )
    correctness_source_alternatives: list[CorrectnessSourceAlternative] = Field(
        default_factory=list,
        description=(
            "The append-only log of every claim for which more than one source of evidence was genuinely "
            "available. Add an entry only where a real alternative source existed, not for claims checked "
            "against the only available source."
        ),
    )
    correctness_source_conflict_events: list[CorrectnessSourceConflictEvent] = Field(
        default_factory=list,
        description=(
            "The append-only log of every instance where two considered sources for the same claim "
            "actually disagreed with each other, distinct from the alternatives log above, which records "
            "that multiple sources existed without necessarily implying they conflicted."
        ),
    )
    correctness_unexplored_source_risk: str = Field(
        description=(
            "A claim for which only one source was checked and no alternative source was even sought, "
            "flagged because a single-source claim carries more risk than its verified status alone "
            "suggests. Leave this empty when no such gap is currently identified. Replace this in full "
            "every update."
        )
    )
    correctness_alternative_confidence_gap: float = Field(
        description=(
            "How close the second-most-trusted source's implied answer was to the one actually used, for "
            "the most recently resolved claim with more than one source available. Replace this in full "
            "every update."
        )
    )


CounterfactualAlternativesTrace = TraceSchema.from_model(
    CounterfactualAlternativesTraceModel,
    name="counterfactual_alternatives_trace",
    description="Records what alternatives genuinely existed at key points on each performance axis and whether the choice made held up.",
)


__all__ = [
    "ActionTrace",
    "ActionTraceModel",
    "CalibrationTrace",
    "CalibrationTraceModel",
    "CounterfactualAlternativesTrace",
    "CounterfactualAlternativesTraceModel",
    "ErrorTaxonomyTrace",
    "ErrorTaxonomyTraceModel",
    "HierarchicalTaskTreeTrace",
    "HierarchicalTaskTreeTraceModel",
    "SelfConsistencyEnsembleTrace",
    "SelfConsistencyEnsembleTraceModel",
]
