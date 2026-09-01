"""FILE: vidbyte/trace/continual/prebuilt.py

PURPOSE: Defines ready-made continual trace schemas developers can pass directly to TraceOption.continual, covering a general action log (ActionTrace) and five schemas scoring pure agent task performance across three separately-tracked axes: goal success, path quality, and answer correctness.
ROLE IN CODEBASE: Every schema here is a Pydantic model converted to a module-level TraceSchema constant via TraceSchema.from_model, re-exported by vidbyte.trace.continual, vidbyte.trace, and vidbyte.__init__ in that order.
ARCHITECTURE NOTE: The five performance schemas use TraceField's nested fields/items capability by annotating a field with a submodel (or list[submodel]) instead of dict[str, Any] — each submodel field still needs its own Field(description=...), recursively, the same requirement TraceSchema.from_model already enforces at the top level. No schema here ever combines the three axes into one number; each stays a separate field, and any array meant to accumulate across trace-agent passes is declared as its own top-level ARRAY field rather than nested inside an OBJECT field.
COMMON MODIFICATION PATTERNS: Add a new prebuilt schema as a Pydantic model plus a TraceSchema.from_model(...) constant, then export both from vidbyte/trace/continual/__init__.py, vidbyte/trace/__init__.py, and vidbyte/__init__.py in that order, matching ActionTrace's existing position in all three files.
KNOWN EDGE CASES: A submodel used only as an OBJECT field's shape (not a list item) needs no docstring, since only a list[SubModel] item shape falls back to a generated description when the submodel's own docstring is empty.
RELATED DOCS: docs/design/nested-continual-trace-shapes.md, docs/design/continual-trace-agent.md, skills/vidbyte-sdk/continual-tracing.md
TESTS: tests/test_continual_trace.py, scripts/test-continual-trace.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.lib.enums.continual_trace import (
    AnswerCorrectnessErrorType,
    AnswerCorrectnessVerdict,
    CalibratedAxis,
    CalibrationTrend,
    GoalSuccessErrorType,
    GoalSuccessVerdict,
    JudgmentStability,
    PathQualityErrorType,
    PathQualityVerdict,
    PathRegretAssessment,
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
            "can currently be trusted the most. Replace this in full every update as more resolutions "
            "accumulate."
        )
    )
    worst_calibrated_axis: CalibratedAxis = Field(
        description=(
            "Which axis currently has the largest average calibration_gap across its resolved "
            "predictions — where a reader should discount the agent's own stated confidence and check "
            "independently rather than take it at face value. Replace this in full every update."
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


class PathQualityJudgment(BaseModel):
    """One independent judgment of path quality, made as part of a self-consistency pass."""

    iteration: int = Field(description="The run iteration at which this independent judgment was made.")
    verdict: PathQualityVerdict = Field(
        description="This judgment's own conclusion about path quality, reasoned independently of any other judgment already recorded for this axis."
    )
    confidence: float = Field(description="How confident this specific judgment is in its own verdict.")
    reasoning: str = Field(description="The reasoning this specific judgment used to reach its verdict.")


class AnswerCorrectnessJudgment(BaseModel):
    """One independent judgment of answer correctness, made as part of a self-consistency pass."""

    iteration: int = Field(description="The run iteration at which this independent judgment was made.")
    verdict: AnswerCorrectnessVerdict = Field(
        description="This judgment's own conclusion about correctness, reasoned independently of any other judgment already recorded for this axis."
    )
    confidence: float = Field(description="How confident this specific judgment is in its own verdict.")
    reasoning: str = Field(
        description=(
            "The reasoning this specific judgment used to reach its verdict, including which sources or "
            "evidence it actually consulted so a later reader can assess how independent it really was "
            "from the other judgments in the ensemble."
        )
    )


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
            "judgment log over time rather than as a single snapshot. Replace this in full every update."
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


class GoalInterpretationSwitchEvent(BaseModel):
    """One instance of the agent actually changing its working interpretation of the goal mid-run."""

    iteration: int = Field(description="The run iteration at which the interpretation actually changed.")
    from_interpretation: str = Field(description="The reading of the goal the agent was working from immediately before this switch.")
    to_interpretation: str = Field(description="The reading of the goal the agent adopted from this point forward.")
    trigger: str = Field(
        description="What specifically caused the switch — new information, a contradiction discovered in the prior reading, or explicit clarification — rather than simply noting that a switch occurred."
    )


class PathDecisionPoint(BaseModel):
    """One point where more than one way of proceeding was genuinely available."""

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


class PathRegretEvent(BaseModel):
    """One instance of a past decision being realized, later, to have been the wrong one."""

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
