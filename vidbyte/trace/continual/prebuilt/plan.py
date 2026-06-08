"""Context Protocol Header

Description:
    Defines the plan-oriented continual trace schema (planning lens).
Purpose:
    Gives developers a ready-made typed schema for recording an agent's intended
    plan, the status of each step, deviations, and what remains.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class PlanTraceModel(BaseModel):
    """Plan-oriented continual trace describing intended structure and execution progress."""

    goal: str = Field(
        title="Goal",
        min_length=1,
        description=(
            "The overall objective the plan is meant to achieve, stated with enough precision that a reader who has not seen the original prompt can understand what success looks like. "
            "Include success criteria when they are known, since the plan exists to satisfy them and they anchor every step the agent lays out. "
            "Keep this field stable across updates unless the context clearly redefines the objective, because the goal is the reference point against which all steps, deviations, and replans are measured. "
            "If the goal narrows or shifts during execution, record the most current formulation rather than the original one, since the agent is optimizing for what it currently understands as the target. "
            "A successor reading this field should be able to orient immediately and judge whether any proposed action advances or undermines the stated objective."
        ),
    )
    plan_summary: str = Field(
        title="Plan Summary",
        min_length=0,
        default="",
        description=(
            "A short narrative description of the agent's current overall plan or strategy, capturing how it intends to reach the goal at a level of abstraction above individual steps. "
            "Overwrite this field with the single most-current description of the strategy on every update, so it always reflects the agent's latest intent rather than an earlier approach. "
            "Write two to four sentences that explain the chosen approach and why it was preferred over obvious alternatives, giving a successor enough context to evaluate whether to continue or revise. "
            "This field is particularly valuable after a replan: the updated summary should immediately signal the new direction so a successor does not execute against a superseded strategy. "
            "Avoid simply listing steps here; this is a synthesis of the approach, not a duplicate of plan_steps, and its value comes from the strategic framing it provides."
        ),
    )
    plan_steps: list[str] = Field(
        title="Plan Steps",
        min_length=0,
        default_factory=list,
        description=(
            "The ordered steps of the plan as the agent has laid them out, each stated as a concrete action or deliverable that advances the goal. "
            "Append new steps as the plan is elaborated during the run and do not rewrite the whole list, so the plan's evolution stays visible and earlier steps are preserved even if later superseded. "
            "State each step specifically enough that a successor could execute it without ambiguity, naming targets, tools, or outputs where relevant. "
            "This field is the structural backbone of the plan trace: a successor reading it can see the entire intended sequence and compare it against completed_steps to understand what remains. "
            "If a step is found to be incorrect or unnecessary, reflect that in deviations or skipped_steps rather than removing it here, preserving the original plan's shape alongside the actual execution."
        ),
    )
    current_step: str = Field(
        title="Current Step",
        min_length=0,
        default="",
        description=(
            "The single step the agent is actively working on right now, identified specifically enough that a successor can locate it in plan_steps and resume without confusion. "
            "Overwrite this field on every update to point at the present step, because its value as a handoff signal depends entirely on being current rather than stale. "
            "Use the same phrasing as the corresponding entry in plan_steps when possible, so a reader can cross-reference without ambiguity. "
            "A successor reading this field mid-run should be able to orient immediately and begin executing the correct step rather than scanning the full history to discover where work stopped. "
            "Leave this empty only when all steps are finished, not while mid-step, so an empty value reliably signals plan completion."
        ),
    )
    current_step_index: int = Field(
        title="Current Step Index",
        default=0,
        description=(
            "The zero-based index of the current step within plan_steps, giving a reader a quick numeric sense of how far through the plan the agent has progressed. "
            "Overwrite with the latest index on every update, keeping it synchronized with current_step so both fields agree on which step is active. "
            "Use this in combination with the total length of plan_steps to compute a rough completion percentage, which is useful for orchestrators triaging multiple runs. "
            "This field is intentionally a simple integer rather than a fraction or percentage, because the source-of-truth for progress is the plan_steps list itself and this index is just a pointer into it. "
            "If the plan is revised and steps are inserted or removed, update this index to reflect the new position of the current step rather than leaving a stale value."
        ),
    )
    completed_steps: list[str] = Field(
        title="Completed Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Plan steps that are finished, each recorded using the same phrasing as the corresponding entry in plan_steps so a reader can match them without ambiguity. "
            "Append each step as it completes and never remove completed steps on later updates, so this list remains a faithful permanent record of what was accomplished. "
            "Use past-tense phrasing to make it immediately clear that these items are done rather than in progress, reducing the cognitive load on a reader scanning the plan. "
            "This field separates accomplished work from remaining work and lets a successor avoid re-doing things that are already settled, which is essential for efficient plan continuation. "
            "If a completed step is later found to be incorrect, record the correction in deviations or replans rather than removing the entry here, keeping the execution history honest."
        ),
    )
    remaining_steps: list[str] = Field(
        title="Remaining Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Plan steps not yet started, identified as work the agent knows remains before the goal can be reached. "
            "Append newly identified remaining steps as the plan is elaborated, and it is acceptable for an item here to later appear in completed_steps once executed. "
            "State each remaining step as specifically as a completed step would be, so a successor can execute it directly rather than needing to interpret a vague label. "
            "This field gives a successor the most important orientation signal about what work is still ahead, without requiring it to diff plan_steps against completed_steps on its own. "
            "If a step turns out to be unnecessary, reflect that in skipped_steps rather than deleting it here, so the reasoning behind the change in scope is preserved."
        ),
    )
    skipped_steps: list[str] = Field(
        title="Skipped Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Steps the agent deliberately decided not to execute, recorded with the reason for skipping when that reason is visible in the context. "
            "Each entry should pair the skipped step with the rationale, such as a constraint that made it unnecessary or a decision that rendered it redundant, so a reviewer understands the omission. "
            "Append each skipped step as the decision is made and do not remove earlier entries, since the history of descoping decisions is valuable for understanding the final shape of execution. "
            "This field prevents a successor from re-introducing work the original agent consciously excluded, which is a common and costly mistake when picking up a partially completed plan. "
            "If the reason for skipping was time pressure or a temporary constraint, note that explicitly so a successor can evaluate whether the step should be revisited."
        ),
    )
    blocked_steps: list[str] = Field(
        title="Blocked Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Steps that cannot proceed because of a specific blocker, each recorded with the step name and the blocking cause when known, so a reader understands both what is stuck and why. "
            "Append blocked steps as they arise and do not remove them when the blocker is resolved; instead, reflect the resolution in status or completed_steps so the blocking history is preserved. "
            "State the blocking cause specifically, naming the missing input, failing dependency, or awaited result rather than describing it abstractly. "
            "This field is a critical handoff signal: a successor seeing a blocked step knows immediately what prevented progress and what precondition must be satisfied before resuming that step. "
            "If a blocked step becomes unblocked and completes, add it to completed_steps and note the resolution in status rather than removing it from blocked_steps."
        ),
    )
    step_dependencies: list[str] = Field(
        title="Step Dependencies",
        min_length=0,
        default_factory=list,
        description=(
            "Ordering or prerequisite relationships between steps, each phrased clearly to identify which step must complete before another can begin, such as step B depends on step A. "
            "Append each dependency the context reveals so a successor preserves correct ordering when executing remaining steps. "
            "Include both explicit dependencies stated in the plan and implicit ones inferred from the nature of the work, since an implicit dependency violated by a successor can cause subtle failures. "
            "This field is particularly important for complex plans where steps are not simply sequential: knowing the dependency graph allows a successor to parallelize safely or sequence correctly. "
            "If a dependency is resolved or found to be unnecessary, note that in replans rather than removing it here, so the evolution of the plan's structure is traceable."
        ),
    )
    milestones: list[str] = Field(
        title="Milestones",
        min_length=0,
        default_factory=list,
        description=(
            "Significant checkpoints in the plan that mark meaningful progress, each defined clearly enough that a reader can determine whether it has been reached by inspecting the run's state. "
            "Append milestones as they are defined or discovered and keep them stable once recorded, since changing the definition of a milestone retroactively confuses the record of when it was reached. "
            "A milestone should represent a qualitatively meaningful state of the plan rather than just the completion of an individual step, such as all reads complete or initial draft ready. "
            "This field is useful for human reviewers and orchestrators monitoring long runs: the milestone list provides coarse-grained progress signals without requiring a full read of the step log. "
            "Reference milestones in milestones_reached using exactly the same phrasing used here, so a reader can match entries across the two fields without ambiguity."
        ),
    )
    milestones_reached: list[str] = Field(
        title="Milestones Reached",
        min_length=0,
        default_factory=list,
        description=(
            "Milestones the agent has actually achieved, each recorded using the same phrasing as the corresponding entry in milestones so a reader can match them without ambiguity. "
            "Append each milestone when the context confirms it was reached, providing a brief note of when or how it was achieved when that context is available. "
            "Never remove entries from this list once they are added, since reached milestones are permanent facts of the run's history regardless of what happens later. "
            "This field allows a reader to quickly gauge overall plan progress at a coarse level without scanning the full step log, making it especially valuable for triage in long-running plans. "
            "If a milestone is later found to have been reached prematurely or incorrectly, note that in deviations rather than removing the entry here, keeping the history accurate."
        ),
    )
    deviations: list[str] = Field(
        title="Deviations",
        min_length=0,
        default_factory=list,
        description=(
            "Places where execution diverged from the stated plan, each recorded with enough detail to explain what changed and why the agent chose a different path than originally laid out. "
            "Append each deviation as it occurs and do not remove earlier entries, so the cumulative record of departures from the plan is preserved for a reviewer or successor. "
            "Include both intentional deviations driven by new information and unintentional ones caused by unexpected obstacles, since both are important for understanding why the actual run differs from the intended plan. "
            "This field is high-value for a handoff because it explains gaps between plan_steps and completed_steps that would otherwise require a reader to reverse-engineer the cause of the discrepancy. "
            "Reference the specific plan step that was deviated from in each entry so a reader can locate the divergence point without scanning the entire plan."
        ),
    )
    replans: list[str] = Field(
        title="Replans",
        min_length=0,
        default_factory=list,
        description=(
            "Points where the agent revised its plan, each recorded with a description of what changed, why the change was made, and what new direction was adopted. "
            "Append each replanning event to preserve the strategy's history, so a reader can understand not just the current plan but how it evolved and what prompted each revision. "
            "Include the trigger for the replan, such as a failed step, new information, or a user correction, since the trigger is often as important as the change itself for understanding the plan's current shape. "
            "This field is especially valuable for a successor taking over a partially executed plan: seeing why previous plans were abandoned helps it avoid re-adopting a strategy that already failed. "
            "Reference the specific steps or milestones that changed in each replan entry so a reader can understand the scope of the revision without re-reading the entire plan."
        ),
    )
    assumptions: list[str] = Field(
        title="Assumptions",
        min_length=0,
        default_factory=list,
        description=(
            "Assumptions the plan depends on that have not yet been confirmed, such as beliefs about the availability of resources, the behavior of dependencies, or the scope of the task. "
            "Each entry should state the assumption as a falsifiable claim so a reviewer can identify what would need to be verified to validate the plan's foundations. "
            "Append each assumption as it is recognized and keep all entries even after the plan completes, since unverified assumptions are risks that may affect the validity of the outputs. "
            "This field allows a reviewer to check whether the plan still holds after the run by testing each assumption, which is especially important when the plan will be reused or adapted. "
            "If an assumption is later confirmed or refuted, record the outcome in replans or deviations rather than deleting the assumption, so the verification history is preserved."
        ),
    )
    risks: list[str] = Field(
        title="Risks",
        min_length=0,
        default_factory=list,
        description=(
            "Things that could cause the plan to fail or need rework, each identified specifically enough that a reviewer can assess its likelihood and severity. "
            "Append each identified risk as it surfaces and keep prior risks unless the context shows they no longer apply, since a risk that was present earlier may still be relevant to the run's outputs. "
            "Pair each risk with a brief assessment of its impact when that assessment is possible, such as whether it would block the plan entirely or require only a local correction. "
            "This field is valuable for a human reviewer deciding whether to approve a plan or a successor deciding whether to continue: a high-severity risk that has not been mitigated is a signal to pause. "
            "If a risk materializes, record that in deviations or blockers and note the connection to the original risk entry so the prediction-outcome chain is visible."
        ),
    )
    contingencies: list[str] = Field(
        title="Contingencies",
        min_length=0,
        default_factory=list,
        description=(
            "Fallback plans or alternative approaches the agent has prepared in case the primary plan fails, each described specifically enough to be actionable without further elaboration. "
            "Append each contingency as it is considered, even if the primary plan is still on track, since a prepared fallback is more valuable than one invented under pressure. "
            "Pair each contingency with the risk or failure mode it addresses so a successor knows which fallback to activate if a specific thing goes wrong. "
            "This field is a high-value handoff signal: a successor inheriting a blocked plan can immediately check whether a contingency exists rather than re-deriving alternatives from scratch. "
            "If a contingency is activated and becomes the primary plan, record that transition in replans and update plan_summary to reflect the new direction."
        ),
    )
    success_criteria: list[str] = Field(
        title="Success Criteria",
        min_length=0,
        default_factory=list,
        description=(
            "Concrete conditions that would mean the plan succeeded, each stated as a testable or observable outcome rather than a vague quality claim. "
            "Append newly discovered criteria as they surface during the run and keep prior ones unless the context explicitly supersedes them. "
            "Each criterion should be specific enough that a reviewer can check it against the run's outputs without interpretation, naming artifacts, test results, or states to verify. "
            "This field is the arbiter of completion for the plan: a successor or reviewer reads it to determine whether the run can be declared done or whether further work is needed. "
            "If a criterion is met, reflect that in milestones_reached or completed_steps rather than removing it here, so the full set of expectations remains visible alongside the evidence of their fulfillment."
        ),
    )
    estimated_remaining_effort: str = Field(
        title="Estimated Remaining Effort",
        min_length=0,
        default="",
        description=(
            "A qualitative estimate of how much work is left to complete the plan, expressed in terms of steps, time, or complexity rather than as a precise numeric prediction. "
            "Overwrite this field with the latest estimate on every update, since remaining effort changes as steps complete, new steps are discovered, or blockers are resolved. "
            "Express the estimate in concrete terms such as roughly two more steps or most of the work remains rather than vague terms like some work left, so a reader can calibrate without further investigation. "
            "An orchestrator or human reviewer reading this field can immediately gauge whether the run needs more time, resources, or intervention without needing to count remaining steps manually. "
            "If the estimate shifts significantly from one update to the next, note the reason in replans or deviations so a reader understands what changed the scope."
        ),
    )
    blockers: list[str] = Field(
        title="Blockers",
        min_length=0,
        default_factory=list,
        description=(
            "Active conditions preventing the plan from advancing, each named specifically with the step it is blocking and the cause when known. "
            "Append each blocker as it arises and reflect its resolution in status or blocked_steps rather than deleting the entry, so the history of what impeded the plan is preserved. "
            "State the blocking condition precisely, naming the missing resource, failing dependency, or awaited input rather than describing it abstractly. "
            "A successor reading this field knows immediately what prevented the original agent from finishing and what precondition must be satisfied before the plan can resume. "
            "If a blocker is time-sensitive or likely to change on its own, note that in the same entry so a successor can assess whether waiting is an option or immediate action is required."
        ),
    )
    next_action: str = Field(
        title="Next Action",
        min_length=0,
        default="",
        description=(
            "The immediate next action the plan calls for, expressed as the single most-current concrete step the agent intends to execute next. "
            "Overwrite this field with the most-current next action as execution proceeds, keeping it synchronized with current_step so both fields agree on what is happening now. "
            "Be specific enough that a successor could execute this action without ambiguity rather than stating something abstract like continue the plan. "
            "This field has its highest value during a mid-run handoff, where it allows a successor to begin executing immediately without first re-deriving what step comes next from the accumulated history. "
            "If the next action is blocked by a pending result or an unresolved decision, note that dependency in the same entry so the successor understands the precondition before acting."
        ),
    )
    plan_confidence: str = Field(
        title="Plan Confidence",
        min_length=0,
        default="",
        description=(
            "A brief qualitative read on how likely the current plan is to succeed, typically expressed as low, medium, or high followed by a one-line explanation of the primary factor driving that assessment. "
            "Overwrite this field on each update to reflect the latest view of the plan's viability, since confidence can shift substantially as blockers appear, steps complete, or new risks are identified. "
            "Base the rating on concrete signals visible in the context such as the proportion of steps completed, the severity of active blockers, or the number of unresolved risks. "
            "A successor or orchestrator reading this field can immediately gauge whether the plan needs revision, additional resources, or simply continuation before investing further execution effort. "
            "A simple low, medium, or high with a one-sentence reason is more useful than a numeric score without context, because the reason explains what evidence drove the assessment."
        ),
    )
    status: str = Field(
        title="Status",
        min_length=0,
        default="",
        description=(
            "The overall status of the plan right now, summarizing how far along it is, what is currently in progress, and what blocks or conditions prevent completion, as of the most recent context. "
            "Overwrite this field on every update to reflect the most current reality, because stale status misleads a successor about what actually needs to happen next. "
            "Write in the present tense and be specific, naming the active step, any blockers, and a brief characterization of whether progress is normal, slowed, or stalled. "
            "A successor reading this field should be able to triage the plan instantly and decide whether to continue, escalate, or revise without first reading the full step and blocker history. "
            "Include the most recent significant event that changed the status when that context is available, so a reader understands what drove the current state."
        ),
    )


PlanTrace = TraceSchema.from_model(
    PlanTraceModel,
    name="plan_trace",
    description="Tracks the agent's plan, step status, deviations, and remaining work.",
)

__all__ = [
    "PlanTrace",
    "PlanTraceModel",
]
