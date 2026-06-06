"""Context Protocol Header

Description:
    Defines the decision-oriented continual trace schema (commitment lens).
Purpose:
    Gives developers a ready-made typed schema for an ADR-style running record of
    the choices an agent commits to, the alternatives, and the rationale.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class DecisionTraceModel(BaseModel):
    """Decision-oriented continual trace: a running record of committed choices and rationale."""

    goal: str = Field(
        title="Goal",
        min_length=1,
        description=(
            "The objective the decisions serve, recorded to frame every choice in the trace within the same context the agent was operating under when each commitment was made. "
            "Write this as a clear statement of what the agent set out to accomplish so a reviewer can assess whether each decision in the log was appropriate and well-aligned with the stated objective. "
            "Keep this field stable across updates unless the context clearly redefines the objective, since rewrites create ambiguity about which goal each recorded decision was made in service of. "
            "A reviewer or successor reading this field can evaluate whether the agent's decisions were coherent and directed rather than reactive and scattered. "
            "If the goal evolved during the run in a way that changed what decisions were appropriate, note the evolution here so a reviewer understands why the decision log may contain choices that appear inconsistent across phases."
        ),
    )
    decisions: list[str] = Field(
        title="Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Each choice the agent committed to, paired with the rationale at the time, forming an append-only ADR log that a successor can read to understand the accumulated set of commitments. "
            "Append one entry per decision in the order it was made and never overwrite earlier ones, so the commitment trail stays intact as a faithful record of what was decided and when. "
            "Focus on decisions that affected the run's direction, approach, or output rather than routine choices that any agent would make without deliberation, so the log stays focused on meaningful commitments. "
            "A successor inheriting the run can read this log to understand the constraints it must respect and the choices it should not re-litigate without new information justifying a reversal. "
            "Keep each entry specific by naming the actual choice made rather than the category of decision, since specificity is what makes the log useful for handoffs and audits."
        ),
    )
    pending_decisions: list[str] = Field(
        title="Pending Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Decisions the agent knows it must make but has not yet committed to, each recorded as a specific choice that is upcoming rather than a vague area of uncertainty. "
            "Append each pending decision as it surfaces during the run, so the queue of upcoming commitments is visible to a reviewer or successor without requiring a full re-analysis of the situation. "
            "A pending decision should describe what will be chosen between, not merely that a decision is coming, so a successor has enough context to begin thinking about the choice before encountering it. "
            "This field gives a successor an advance view of the commitments it will need to make, allowing it to collect relevant information proactively rather than encountering the decision cold. "
            "When a pending decision is resolved, reflect it by adding an entry to decisions rather than removing it from here, so the progression from pending to committed is visible."
        ),
    )
    decision_points: list[str] = Field(
        title="Decision Points",
        min_length=0,
        default_factory=list,
        description=(
            "Junctures in the run where a meaningful choice was required, each recorded with enough context to explain why the situation called for a deliberate commitment rather than a default action. "
            "Append each decision point in the order it was encountered, so the full sequence of choice-requiring moments is visible alongside the decisions that were made at each one. "
            "This field captures the structure of the choice space the agent navigated, which is distinct from the decisions themselves and helps a reviewer understand why certain choices arose. "
            "A successor reading this field can anticipate similar junctures that may appear in the remaining work and prepare its decision-making process in advance. "
            "If a decision point arose from an unexpected situation rather than a planned branch in the process, note that so a reviewer can assess whether the agent correctly identified the significance of the moment."
        ),
    )
    options_considered: list[str] = Field(
        title="Options Considered",
        min_length=0,
        default_factory=list,
        description=(
            "Candidate options evaluated at each decision point, each recorded with enough detail to make clear what the option entailed and why it was a plausible choice. "
            "Append each option considered at each decision point, including options that were quickly dismissed, so the breadth of analysis the agent performed is fully visible. "
            "Recording all options considered rather than only the chosen one gives a reviewer confidence that the agent explored the space rather than committing to the first plausible option it encountered. "
            "A successor reading this field knows which alternatives the original agent evaluated, preventing redundant re-evaluation of options that were already weighed and found inferior. "
            "If an option was considered briefly and rejected without deep analysis, note that alongside the entry so a reviewer can assess whether the quick dismissal was appropriate or premature."
        ),
    )
    rejected_options: list[str] = Field(
        title="Rejected Options",
        min_length=0,
        default_factory=list,
        description=(
            "Options the agent explicitly rejected at each decision point, each recorded with the reason for rejection so the negative-space map of the decision process is preserved. "
            "Append each rejected option as it is ruled out, even when the rejection is quick and obvious, because the complete set of rejections is what allows a successor to avoid revisiting discarded paths. "
            "State the rejection reason specifically rather than vaguely, since a reason like 'would violate the API rate limit constraint' prevents a successor from proposing the same option in a different frame. "
            "A successor reading this field immediately knows what has been tried and eliminated, which can save significant time when the agent explored a large option space before converging on the viable approach. "
            "If an option was rejected conditionally and might become viable under different circumstances, note that explicitly so a successor knows the rejection was not absolute and can revisit it if conditions change."
        ),
    )
    rationale: list[str] = Field(
        title="Rationale",
        min_length=0,
        default_factory=list,
        description=(
            "The reasoning behind each significant decision, expanded beyond the one-line note in the decisions field to capture the full thought process that led to each commitment. "
            "Append one rationale entry per significant decision in the order decisions were made, so a reviewer can pair each decision with its reasoning without needing to cross-reference by position. "
            "Being specific about the reasoning behind a decision is what distinguishes a useful decision log from a simple list of choices: a reviewer needs to understand why, not just what was chosen. "
            "A successor reading a clear rationale can judge whether the reasoning still applies given the current state of the run, and can decide whether to honor the commitment or revisit it with a different analysis. "
            "Even a brief rationale is more valuable than none at all, since even a short explanation prevents a successor from reversing a decision made for a non-obvious reason without realizing what it is undoing."
        ),
    )
    criteria: list[str] = Field(
        title="Criteria",
        min_length=0,
        default_factory=list,
        description=(
            "The criteria or priorities the agent used to choose between options at each decision point, each stated explicitly so the basis for the final commitment is transparent and auditable. "
            "Append each criterion as it is applied in the decision process, noting which decision it was applied to when multiple decisions used different criteria. "
            "Explicit criteria transform a decision from a judgment call into a reasoned choice: a reviewer can disagree with a criterion but still understand why the agent chose as it did. "
            "A successor reading this field can apply the same criteria to future decision points in the run, maintaining consistency with the original agent's decision-making framework. "
            "If the criteria changed between decisions, note the change and the reason, since a shift in decision criteria mid-run is a significant signal about how the agent's priorities evolved."
        ),
    )
    assumptions: list[str] = Field(
        title="Assumptions",
        min_length=0,
        default_factory=list,
        description=(
            "Unverified assumptions underlying the decisions, each recorded clearly so a reviewer can check whether each decision still holds if a particular assumption turns out to be false. "
            "Append each assumption as it is identified during the deliberation process, noting which decision or set of decisions depends on each one. "
            "An assumption should be stated as a specific factual claim the agent is treating as true for the purposes of the decision, not as a vague background condition. "
            "A successor reading this field knows which parts of the decision log are contingent on assumptions that have not been verified, and can prioritize verifying the most critical ones before proceeding. "
            "If an assumption is later confirmed or refuted, record the outcome rather than removing the original assumption, since the history of which assumptions held and which did not is important for auditing the decisions that rested on them."
        ),
    )
    tradeoffs: list[str] = Field(
        title="Tradeoffs",
        min_length=0,
        default_factory=list,
        description=(
            "Costs accepted or benefits forgone for each significant decision, each recorded to make the price of each commitment explicit alongside its benefits. "
            "Append one tradeoff entry per significant decision, stating what was sacrificed or accepted as a downside in order to make the chosen commitment. "
            "Recording tradeoffs is important because a decision that looks optimal in isolation may look different when the cost it imposed is made visible to a reviewer. "
            "A successor reading this field can assess whether the tradeoffs the original agent accepted are still acceptable given the current state of the run, and can propose a different commitment if circumstances have changed. "
            "If a decision had no meaningful tradeoffs because one option was strictly better than all others, note that explicitly so a reviewer knows the agent is not missing a hidden cost."
        ),
    )
    constraints: list[str] = Field(
        title="Constraints",
        min_length=0,
        default_factory=list,
        description=(
            "Hard limits that shaped or restricted the decisions available to the agent, each recorded specifically enough that a reviewer can verify the agent respected them throughout the run. "
            "Append each constraint as it becomes relevant to the decision-making process, including constraints that came from user instructions, system policies, and environmental facts discovered mid-run. "
            "State each constraint as a specific condition that must be satisfied, not as a general principle, so a reviewer can directly check compliance without interpreting vague guidance. "
            "A successor reading this field knows exactly what it cannot do when continuing the run, preventing it from proposing or taking actions that the original agent was explicitly prohibited from taking. "
            "If a constraint conflicted with the goal or with another constraint, note the tension and how it was resolved, since unresolved constraint conflicts are one of the most common sources of decision-making errors."
        ),
    )
    reversibility: list[str] = Field(
        title="Reversibility",
        min_length=0,
        default_factory=list,
        description=(
            "For each significant decision, whether it is easily reversible, costly to reverse, or a point of no return, each recorded so a successor knows what flexibility remains in the committed choices. "
            "Append one reversibility assessment per significant decision, paired with the corresponding entry in decisions so a reader can immediately see which commitments are locked in. "
            "A decision marked as a point of no return is one a successor must respect unconditionally; one marked as easily reversible can be reconsidered if new information warrants it. "
            "This field is critical for handoffs where the successor may be tempted to reconsider prior decisions: it provides an upfront assessment of which decisions can be safely revisited and which would be expensive to undo. "
            "If the reversibility of a decision changed after it was made, such as when an intermediate output became public, update the entry to reflect the new status and note what changed."
        ),
    )
    dependencies: list[str] = Field(
        title="Dependencies",
        min_length=0,
        default_factory=list,
        description=(
            "Decisions that depend on other decisions, each recorded using a clear pairing like 'decision B assumes decision A is in force', so the dependency graph of the decision log is preserved. "
            "Append each dependency relationship as it is identified, since dependencies often become clear only during implementation when a later decision relies on an earlier one being stable. "
            "Recording dependencies prevents a successor from reversing an earlier decision without realizing it undermines a later one, which can cause cascading failures in the run's commitments. "
            "A successor reading this field can understand which decisions are foundational and which are derived, so it knows what would need to change if any single decision were reversed. "
            "If a dependency is conditional rather than absolute, note the condition explicitly so a reviewer knows when the dependency applies and when the decisions are free to vary independently."
        ),
    )
    reversed_decisions: list[str] = Field(
        title="Reversed Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Decisions the agent later changed its mind on, each recorded with the original commitment, the new commitment, and the reason the reversal was warranted. "
            "Append each reversal as it occurs and keep the original decision entry in the decisions field rather than removing it, so the full history of commitments and changes is preserved. "
            "A reversal should be notable and driven by new information or a recognized error, not by casual reconsideration, since frequent reversals indicate an unstable decision process. "
            "A reviewer reading this field can assess whether the agent was appropriately adaptive in response to new information or whether it was inconsistent and indecisive. "
            "A successor reading this field knows which prior commitments are no longer in force and can safely proceed with the revised commitment rather than honoring the original one."
        ),
    )
    deferred_decisions: list[str] = Field(
        title="Deferred Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Decisions the agent consciously postponed, each recorded with the reason for deferral and any trigger or condition that should prompt revisiting the deferred choice. "
            "Append each deferral as it happens and do not remove it until the decision is actually made, so the set of outstanding deferred decisions is always visible. "
            "State the reason for deferral specifically, distinguishing between deferral due to missing information, deferral because the decision is premature, and deferral because the decision is low priority. "
            "A successor reading this field knows which decisions the original agent intentionally left open and can either make them now or continue deferring them based on the same or revised reasoning. "
            "If the trigger for a deferred decision has occurred since the deferral was recorded, note that as well so a reviewer knows the deferred decision has become eligible for resolution."
        ),
    )
    risks: list[str] = Field(
        title="Risks",
        min_length=0,
        default_factory=list,
        description=(
            "Risks each significant decision introduces, each recorded with the decision it is associated with and the nature of the downside it creates. "
            "Append each risk as it is identified in the decision process, noting whether the risk was accepted knowingly or whether it was discovered after the decision was already made. "
            "A risk that was knowingly accepted tells a different story than one that was missed: the former demonstrates deliberate cost-benefit analysis, the latter may indicate a gap in the decision process. "
            "A successor reading this field knows where the run's commitments have created exposure and can monitor those areas proactively rather than discovering risk only when it materializes. "
            "If a risk has already materialized by the time a successor reads this field, cross-reference the relevant error or deviation entry so the outcome of the risk is immediately visible alongside its prediction."
        ),
    )
    stakeholders: list[str] = Field(
        title="Stakeholders",
        min_length=0,
        default_factory=list,
        description=(
            "Who or what is affected by the decisions made during the run, each recorded to make the impact surface of each commitment explicit to a reviewer. "
            "Append each stakeholder as it becomes relevant to a decision, noting which decision affects them and in what way the decision changes their situation. "
            "Stakeholders include the user, downstream systems, other agents in the pipeline, external services, and any human or system that depends on the run's outputs. "
            "A reviewer reading this field can assess whether the agent adequately considered all affected parties when making its decisions, or whether important stakeholders were overlooked. "
            "If a stakeholder was unintentionally affected by a decision rather than deliberately considered, note that so a reviewer can assess whether the unintended impact is acceptable or needs to be addressed."
        ),
    )
    evidence: list[str] = Field(
        title="Evidence",
        min_length=0,
        default_factory=list,
        description=(
            "Facts or observations that informed the decisions, each recorded to ground each commitment in concrete evidence rather than leaving it as an unsupported judgment call. "
            "Append each piece of evidence as it is gathered and connected to a decision, noting which decision the evidence supports and what the evidence specifically demonstrates. "
            "Evidence distinguishes a well-reasoned decision from a guess: a reviewer can evaluate the quality of the evidence and assess whether the decision it supports is as solid as the agent believed. "
            "A successor reading this field can verify the evidence independently if needed, confirming that the foundations of the decision log are still accurate in the current context. "
            "If evidence was gathered but did not ultimately support the decision made, still record it as non-confirming evidence rather than omitting it, since the full evidence base including disconfirming evidence is important for a fair audit."
        ),
    )
    confidence: list[str] = Field(
        title="Confidence",
        min_length=0,
        default_factory=list,
        description=(
            "A per-decision confidence note expressing how sure the agent was that each choice was correct at the time it was made, with a brief explanation of what drove the level. "
            "Append one confidence entry per significant decision, using a consistent qualitative scale such as high, medium, or low, so confidence levels are comparable across the log. "
            "Be calibrated rather than uniformly optimistic: a medium confidence claim that accurately reflects genuine uncertainty is more useful than a high confidence claim that leads a reviewer to skip scrutiny the decision deserves. "
            "A successor reading a sequence of low-confidence decisions knows that those areas of the run rest on shaky foundations and may need re-verification before the outputs can be trusted. "
            "If confidence in a decision changed after new information arrived, record the updated confidence in a new entry rather than modifying the original, so the evolution of confidence across the run is visible."
        ),
    )
    open_questions: list[str] = Field(
        title="Open Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Unresolved questions that bear on future decisions, each phrased as a specific concrete question so a reviewer or successor can take action to answer it. "
            "Append each open question as it arises and reflect resolution by adding an answer rather than deleting the entry, so a reader can see both the question and when it was answered. "
            "An open question that affects a pending decision is higher priority than one that affects only background understanding, and that distinction should be noted in the entry. "
            "A successor reading this field has an immediate list of the unresolved informational needs the original agent carried, and knows which to prioritize resolving before making further commitments. "
            "If a question cannot be answered within the run because it requires information the agent cannot access, note that explicitly so a human reviewer knows escalation or external input is needed."
        ),
    )
    current_decision: str = Field(
        title="Current Decision",
        min_length=0,
        default="",
        description=(
            "The decision the agent is actively weighing right now, expressed as a specific description of the choice being deliberated, so a reader can immediately understand what commitment is in progress. "
            "Overwrite this field with the single most-current decision in progress on every update, so a reader arriving mid-deliberation knows exactly what the agent is working through. "
            "Include what the agent is choosing between rather than just that a choice is being made, so a successor can pick up the deliberation rather than starting from scratch. "
            "A successor reading this field can immediately see where the original agent was in its decision-making process and continue the deliberation with full context rather than rediscovering what was being weighed. "
            "Leave this empty only when no decision is actively being deliberated, so an empty value reliably signals that the agent is in an execution phase rather than a deliberation phase."
        ),
    )
    next_decision: str = Field(
        title="Next Decision",
        min_length=0,
        default="",
        description=(
            "The next decision the agent expects to face after the current one, expressed specifically enough that a successor can begin thinking about it before encountering it in the run. "
            "Overwrite this field with the most-current anticipated next decision on every update, so it always reflects the agent's current expectation rather than a stale prediction. "
            "Include what options are likely to be available and what information the agent expects to need to make the decision well. "
            "A successor reading this field can prepare for the next major commitment point before reaching it, which leads to faster and better-considered decisions at critical junctures. "
            "If no significant decision is anticipated in the near term because the work ahead is straightforward, write that explicitly so a reader knows the next phase is execution rather than deliberation."
        ),
    )
    decision_count: int = Field(
        title="Decision Count",
        default=0,
        description=(
            "The running total of committed decisions recorded in the decisions field, giving a quick sense of the decision density of the run without requiring a reader to count entries manually. "
            "Overwrite this field with the latest count on every update, keeping it synchronized with the actual number of entries in the decisions field so the count is always accurate. "
            "A high decision count relative to the run's output may indicate a run with extensive deliberation or an agent facing unusually complex trade-offs that required many explicit commitments. "
            "A reviewer seeing an unexpectedly high or low decision count relative to the run's complexity can use that signal to investigate whether decisions were being recorded faithfully or whether some were made implicitly without documentation. "
            "If the count diverges from the length of the decisions field due to summarization or compaction, provide the best available approximation with a note rather than leaving this at zero."
        ),
    )


DecisionTrace = TraceSchema.from_model(
    DecisionTraceModel,
    name="decision_trace",
    description="A running record of the agent's committed choices, alternatives, and rationale.",
)

__all__ = [
    "DecisionTrace",
    "DecisionTraceModel",
]
