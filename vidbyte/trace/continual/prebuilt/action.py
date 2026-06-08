"""Context Protocol Header

Description:
    Defines the action-oriented continual trace schema (execution lens).
Purpose:
    Gives developers a ready-made typed schema for recording what an agent is
    trying to do, the work it has performed, mistakes, and its current status.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ActionTraceModel(BaseModel):
    """Action-oriented continual trace describing goal, work, mistakes, and status."""

    goal: str = Field(
        title="Goal",
        min_length=1,
        description=(
            "The original or current high-level goal the main agent is working toward, capturing what the developer asked for and any explicit success criteria or constraints attached to the request. "
            "Write this as a single, complete statement that names the target outcome precisely enough that someone who has not seen the original prompt can understand what done looks like. "
            "If the goal is refined or narrowed during the run, record the most current understanding rather than the first phrasing, since the latest formulation reflects what the agent is actually optimizing for. "
            "Keep this field stable across updates unless the context clearly redefines the objective, because spurious rewrites destroy its value as an anchor for a handoff reader. "
            "This is one of the first things a successor agent or human reviewer will read, so precision and completeness here reduce the chance of misaligned continuation."
        ),
    )
    subgoals: list[str] = Field(
        title="Subgoals",
        min_length=0,
        default_factory=list,
        description=(
            "The intermediate objectives the agent is pursuing on the way to the main goal, whether stated explicitly by the user or inferable from the agent's behavior and tool calls. "
            "Each entry should be a short, concrete subgoal phrased as a desired outcome rather than as an action, so a reader can check whether it was achieved. "
            "Append new subgoals as they emerge during the run and do not restate ones already captured, since the list should grow without duplication. "
            "This field lets a successor quickly see the decomposition of work the original agent committed to, allowing it to pick up an incomplete subgoal without re-deriving the breakdown from scratch. "
            "If a subgoal is superseded, leave it in place and reflect the change in the goal field rather than removing it, preserving the evolution of intent."
        ),
    )
    success_criteria: list[str] = Field(
        title="Success Criteria",
        min_length=0,
        default_factory=list,
        description=(
            "The concrete conditions that would mean the task is done correctly, drawn from anything measurable or checkable visible in the context such as tests passing, a specific file existing, or an API returning a given result. "
            "Each entry should be a testable statement rather than a vague quality claim, so a successor can verify completion without interpretation. "
            "Append newly discovered criteria as they surface and keep prior ones unless the context explicitly supersedes them, since all success conditions remain relevant until definitively retired. "
            "A well-maintained list here is critical for a handoff because it lets a successor declare the task done with confidence rather than guessing what the original requester expected. "
            "If a criterion is met, leave it in this field and reflect completion in completed_steps rather than removing it, so the full contract remains visible throughout the run."
        ),
    )
    constraints: list[str] = Field(
        title="Constraints",
        min_length=0,
        default_factory=list,
        description=(
            "Explicit limits, requirements, or rules the agent must respect during the run, such as allowed tools, scope boundaries, style rules, forbidden actions, or performance budgets. "
            "Each entry should state the constraint precisely enough that a successor knows when it would be violated, not just that some limit exists in the abstract. "
            "Append each constraint as it appears in the context and do not remove earlier ones, since a constraint that was in place at any point may still govern what can be undone. "
            "This field matters especially for handoffs because it explains why some paths were avoided and prevents a successor from unknowingly violating a rule the original agent was respecting. "
            "Include the source of the constraint when visible, such as a user instruction or a system policy, so a reviewer can assess whether it remains authoritative."
        ),
    )
    actions_taken: list[str] = Field(
        title="Actions Taken",
        min_length=0,
        default_factory=list,
        description=(
            "An ordered log of the important actions, tool calls, decisions, or steps the agent has already performed, each phrased as a short, concrete statement of what happened and why it mattered when that context is available. "
            "Append new meaningful actions rather than rewriting history, so the list grows as an audit trail that a reviewer can replay in sequence to understand the run's progression. "
            "Omit trivial or repetitive steps that add no value, such as a read that confirmed nothing new, and focus on actions that changed state, advanced understanding, or produced an output. "
            "This field is the backbone of an action trace handoff: a successor reading it should be able to reconstruct what was tried and what succeeded, saving it from duplicating effort already expended. "
            "When an action produced a notable result, include the outcome in the same entry rather than requiring the reader to cross-reference another field."
        ),
    )
    current_action: str = Field(
        title="Current Action",
        min_length=0,
        default="",
        description=(
            "What the agent is doing right now, as of the latest snapshot, expressed as the single most-current step or pending tool call in progress. "
            "Overwrite this field on every update to reflect the present moment, because its value as a handoff signal depends entirely on being current rather than historical. "
            "Use a short, specific phrase that identifies the exact operation underway rather than summarizing recent work, so a reader can orient immediately without scanning the history. "
            "A successor reading this field mid-run should be able to understand where execution stopped without first scanning the full actions_taken log to find the latest step. "
            "Leave this empty only if the agent has finished all work, not while mid-step, so an empty value reliably signals completion rather than an update gap."
        ),
    )
    next_action: str = Field(
        title="Next Action",
        min_length=0,
        default="",
        description=(
            "The immediate next step the agent appears about to take, inferred from the latest context and the current trajectory of work toward the goal. "
            "Write the single most likely next action and overwrite this field as the situation evolves, so it always reflects the agent's current intention rather than a stale plan. "
            "Be specific enough that a successor could execute this step without ambiguity rather than stating something general like continue working. "
            "This field has its highest value during a mid-run handoff, where it allows a successor to begin executing without first re-deriving what comes next from the accumulated history. "
            "If the next action depends on an outstanding result or decision, note that dependency in the same entry so the successor understands the precondition before acting."
        ),
    )
    completed_steps: list[str] = Field(
        title="Completed Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Steps that are finished and verified as done according to the context, each stated as a past-tense concrete achievement rather than a plan item. "
            "Append each step as it completes and never remove completed steps on later updates, so this list remains a faithful record of what has been accomplished across the full run. "
            "Use phrasing specific enough that a reviewer can confirm the step without re-running it, naming files, functions, or outputs where relevant. "
            "This field separates accomplished work from ongoing work and lets a successor skip re-doing things that are already settled, which is essential for efficient continuation. "
            "If a completed step is later found to be incorrect, record the correction in mistakes rather than removing the entry here, keeping the history honest about what was believed to be done."
        ),
    )
    pending_steps: list[str] = Field(
        title="Pending Steps",
        min_length=0,
        default_factory=list,
        description=(
            "Steps that still remain to reach the goal, identified from the current context as work the agent knows it has not yet performed. "
            "Append newly identified pending steps as the run reveals more work, and it is acceptable for an item here to later also appear under completed_steps as progress is made. "
            "State each pending step as specifically as a completed step would be, so a successor can execute it directly rather than needing to interpret a vague task label. "
            "This field gives a successor the most important orientation signal about what is left to do, without requiring it to diff the goal against completed steps on its own. "
            "Do not remove entries that turn out to be unnecessary; instead reflect the descoping in the goal or constraints fields so the reasoning behind the change is visible."
        ),
    )
    mistakes: list[str] = Field(
        title="Mistakes",
        min_length=0,
        default_factory=list,
        description=(
            "Mistakes, failed attempts, incorrect assumptions, dead ends, or recoveries observed so far, each recorded with enough detail to understand what went wrong and what context surrounded the failure. "
            "Record what happened and, where the context reveals it, the correction that followed, pairing each mistake with its resolution in a single entry or a linked recoveries entry. "
            "Keep prior entries unchanged even if the mistake was later corrected, since the correction belongs in recoveries and the mistake itself is a permanent fact of the run's history. "
            "This is one of the most valuable fields for a handoff because it stops a future agent from repeating the same error and saves the cost of rediscovering what does not work. "
            "Include the approximate point in the run when the mistake occurred when that context is available, so a reader can correlate it with the actions_taken log for fuller understanding."
        ),
    )
    recoveries: list[str] = Field(
        title="Recoveries",
        min_length=0,
        default_factory=list,
        description=(
            "How the agent corrected or worked around each mistake or blocker, described specifically enough that a successor could apply the same recovery if it encounters the same problem. "
            "Pair each recovery with the problem it resolved when possible, either in the same entry or by referencing the corresponding mistakes entry, so the context is self-contained. "
            "Append new recoveries as they occur and do not overwrite earlier ones, since each recovery is a permanently useful data point about what the agent learned to do differently. "
            "This field complements mistakes and together they form the error-correction narrative of the run, which is the part of a handoff most likely to save a successor significant time. "
            "If a recovery was partial or temporary, note that explicitly so a successor knows the underlying issue may resurface and plan accordingly."
        ),
    )
    blockers: list[str] = Field(
        title="Blockers",
        min_length=0,
        default_factory=list,
        description=(
            "Conditions currently preventing progress, such as missing input, a failing dependency, an awaited external result, or a permission boundary that has not been cleared. "
            "Each entry should name the blocker specifically and, when known, what resolving it requires, so a reader understands both the obstacle and its unblocking condition. "
            "Append each blocker as it appears; a blocker that is later resolved should be reflected in current_status rather than deleted here, so the history of what impeded the run is preserved. "
            "A successor reading this field knows immediately what prevented the original agent from finishing and what it would need to address first before resuming work productively. "
            "If a blocker is time-sensitive or likely to expire, note that in time_sensitive_notes as well so it is not overlooked during a handoff delay."
        ),
    )
    assumptions: list[str] = Field(
        title="Assumptions",
        min_length=0,
        default_factory=list,
        description=(
            "Assumptions the agent is relying on that have not yet been confirmed by the context, such as beliefs about input shape, environment state, user intent, or the behavior of external systems. "
            "Each entry should state the assumption as a claim that could be falsified, so a reviewer can identify exactly what would need to be verified to validate it. "
            "Append each assumption as it is recognized and keep all entries even after the run ends, since unverified assumptions are risks that outlast the agent that made them. "
            "This field is particularly valuable for a handoff because a successor can immediately see which of the original agent's beliefs were uncertain, allowing it to validate before trusting derived conclusions. "
            "If an assumption is later confirmed or refuted, record that outcome in decisions or mistakes rather than deleting the assumption entry, so the verification history is preserved."
        ),
    )
    decisions: list[str] = Field(
        title="Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Notable choices the agent committed to during the run, each recorded with the brief reasoning behind it when that reasoning is visible in the context. "
            "State each decision as a specific commitment rather than an abstract option, making clear what alternative was rejected and why the chosen path was preferred. "
            "Append each decision as it is made and never remove earlier ones, so the reasoning trail behind the actions taken remains intact for a reviewer or successor. "
            "This field prevents a successor from undoing a deliberate choice without understanding why it was made, which is one of the most common and costly mistakes in handoff scenarios. "
            "If a decision was later reversed, record the reversal as a new entry that references the original rather than modifying or removing the original entry."
        ),
    )
    inputs_received: list[str] = Field(
        title="Inputs Received",
        min_length=0,
        default_factory=list,
        description=(
            "The inputs, parameters, files, user messages, or fetched data the agent was given or retrieved during the run, each identified specifically enough to be located or reproduced. "
            "Append each distinct input in the order it was received or fetched, including both initial inputs and any additional context acquired mid-run through tool calls or user messages. "
            "Name file paths, API endpoints, or message identifiers rather than summarizing vaguely, so a successor or auditor can retrieve the same inputs and verify the agent's starting conditions. "
            "This field establishes the full input surface of the run, which is essential for reproducibility audits and for a successor that needs to re-fetch a resource the original agent used. "
            "If an input arrived in a transformed or parsed form, note the original source alongside the transformation so the provenance chain is clear and re-verification is possible."
        ),
    )
    outputs_produced: list[str] = Field(
        title="Outputs Produced",
        min_length=0,
        default_factory=list,
        description=(
            "The concrete outputs the agent has produced so far, including answers, files, artifacts, API results, or any other deliverable that emerged from the run. "
            "Append each output as it is created, naming it specifically with a file path, identifier, or short description of the content, so a reader can locate it without re-running the agent. "
            "Include intermediate outputs as well as final ones, since a successor may need to build on an intermediate artifact rather than starting from scratch. "
            "This field gives a handoff reader an immediate inventory of what value the original agent created, preventing redundant work and making it easy to assess how close to done the run was. "
            "If an output was later superseded or invalidated, note that in mistakes rather than removing it here, so the full production history including rework is visible."
        ),
    )
    tools_used: list[str] = Field(
        title="Tools Used",
        min_length=0,
        default_factory=list,
        description=(
            "The tools or capabilities the agent has invoked during the run, recorded as a high-level set that gives a reader a quick map of which capabilities were exercised. "
            "Append each tool name the first time it is used and do not duplicate names already present, since this is a set of distinct capabilities rather than a call-by-call log. "
            "For a detailed call-by-call record with arguments and results, prefer the actions_taken or external_resources fields; this field is intentionally a high-level summary. "
            "Knowing which tools were used helps a successor understand the agent's operational profile and check whether any critical capability was overlooked or unavailable during the original run. "
            "If a tool was available but deliberately not used, record that reasoning in decisions rather than here, since this field records actual usage rather than capability analysis."
        ),
    )
    external_resources: list[str] = Field(
        title="External Resources",
        min_length=0,
        default_factory=list,
        description=(
            "External systems the agent touched during the run, including files read or written, APIs called, services queried, URLs fetched, or databases accessed, each identified with enough detail to be re-accessed. "
            "Append each resource in the order it was accessed, noting the nature of the interaction such as whether it was read, written, or queried, so the agent's external footprint is fully visible. "
            "Include both successful and failed access attempts, since a failed attempt is still part of the external interaction log and may explain a blocker or an unexpected result. "
            "This field is important for reproducibility and for assessing side effects: a successor or auditor can see exactly what the agent touched outside its local state without reading the full actions log. "
            "If a resource required credentials or configuration that may have expired, note that in time_sensitive_notes as well so the dependency is not overlooked during a handoff delay."
        ),
    )
    progress_summary: str = Field(
        title="Progress Summary",
        min_length=0,
        default="",
        description=(
            "A short narrative of how far the agent has come overall relative to the goal, written as prose that a reader can absorb in seconds without needing to scan the full actions log. "
            "Overwrite this field each update with the single most-current summary of progress, so it always reflects the state as of the latest snapshot rather than an earlier moment in the run. "
            "Write two to four sentences that cover what has been accomplished, what is still outstanding, and any significant obstacles, balancing completeness with conciseness. "
            "This field is the first stop for a human reviewer or orchestrator trying to triage a run quickly, so clarity and accuracy here directly affect how fast they can act. "
            "Do not simply list completed steps; synthesize them into a coherent narrative that conveys momentum and identifies where things stand relative to the definition of done."
        ),
    )
    current_status: str = Field(
        title="Current Status",
        min_length=0,
        default="",
        description=(
            "The latest known state of the task, summarizing how far the agent has progressed, what it is currently doing, what still remains unresolved, and any blocking condition or pending result as of the most recent context. "
            "Overwrite this field on every update to reflect the present moment, because stale status is worse than no status and misleads a successor about what actually needs to happen next. "
            "Write in the present tense and be specific about the immediate situation, naming files, steps, or conditions rather than describing them abstractly. "
            "This is typically the highest-value field for a mid-run handoff because a successor reading it should be able to orient instantly and begin executing without first replaying the entire history. "
            "Distinguish between work that is progressing normally, work blocked waiting on an external condition, and work that has definitively stalled, so a reader knows what kind of action is required."
        ),
    )
    iteration_notes: list[str] = Field(
        title="Iteration Notes",
        min_length=0,
        default_factory=list,
        description=(
            "Brief per-iteration observations worth preserving, capturing what was notable about each iteration of the agent loop rather than what was accomplished, which belongs in actions_taken. "
            "Append one short note per meaningful iteration in the order iterations occur, without rewriting earlier notes, so the sequence of observations remains auditable over time. "
            "Focus on things that would surprise a reader who only looked at the actions log: an unexpected direction change, a performance observation, a narrowing of scope, or context that shifted the agent's strategy. "
            "This field is particularly useful for diagnosing runs that took longer or shorter than expected, since it provides a timestamped feel for the agent's pace and decision rhythm. "
            "Keep entries brief enough to scan quickly; detailed analysis belongs in decisions, mistakes, or recoveries rather than being embedded in iteration notes."
        ),
    )
    open_questions: list[str] = Field(
        title="Open Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Unresolved questions that would matter to a later handoff or a human reviewer, each phrased as a concrete question rather than a vague concern so that answering it is an actionable task. "
            "Append new questions as they surface during the run and keep all questions until the context answers them, at which point note the answer in decisions rather than deleting from here. "
            "Prioritize questions whose answers would materially change the agent's direction or a successor's approach, rather than recording every minor uncertainty encountered. "
            "This field is one of the highest-leverage handoff signals: a successor that can answer an open question the original agent could not often avoids hours of work that the original agent could not complete due to unresolved uncertainty. "
            "Phrase each question specifically enough to be answerable by someone with access to the codebase, environment, or user, rather than as a reflection on the agent's internal uncertainty."
        ),
    )
    confidence: str = Field(
        title="Confidence",
        min_length=0,
        default="",
        description=(
            "A brief qualitative assessment of how likely the agent is to succeed given current progress, typically expressed as low, medium, or high followed by a one-line explanation of the primary driver behind that rating. "
            "Overwrite this field on each update to reflect the latest read on the run's trajectory, since confidence can shift substantially as blockers appear or are resolved throughout the run. "
            "Base the rating on concrete evidence visible in the context such as the ratio of completed to pending steps, the severity of active blockers, or the number of unresolved open questions. "
            "A successor or orchestrator reading this field can immediately gauge whether the run needs intervention, additional resources, or simply continuation, making it a high-value triage signal. "
            "Avoid false precision: a simple low, medium, or high with a one-sentence reason is more useful than a numeric score without context, because the reason explains what would change the assessment."
        ),
    )
    time_sensitive_notes: list[str] = Field(
        title="Time-Sensitive Notes",
        min_length=0,
        default_factory=list,
        description=(
            "Anything time-bound that a successor must know quickly to avoid an irreversible or costly outcome, such as expiring sessions, rate limits that were hit, approaching deadlines, or state that will become stale. "
            "Each entry should name the specific time constraint, when it expires or was triggered, and what action it requires, so a reader can assess urgency without further investigation. "
            "Append each note as it becomes relevant and do not remove earlier notes even after they expire, since the history of time pressures is valuable context for understanding why the agent prioritized as it did. "
            "This field is especially important during handoff delays: a successor picking up a trace hours or days later needs to know which assumptions about external state may no longer hold. "
            "If a time-sensitive note is also reflected in blockers or external_resources, duplicate the key information here rather than relying on a cross-reference, since this field is meant to surface urgency immediately."
        ),
    )


ActionTrace = TraceSchema.from_model(
    ActionTraceModel,
    name="action_trace",
    description="Tracks the agent goal, work performed, mistakes, and current status.",
)

__all__ = [
    "ActionTrace",
    "ActionTraceModel",
]
