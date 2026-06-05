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
        description=(
            "The objective the decisions serve. Capture what the agent is deciding toward. Keep this stable "
            "unless the context redefines it."
        ),
    )
    decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Each choice the agent committed to, paired with the rationale at the time. Append every "
            "decision; never overwrite earlier ones, so the commitment trail stays intact for a successor."
        ),
    )
    pending_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Decisions the agent knows it must make but has not yet committed. Append each pending decision "
            "as it surfaces."
        ),
    )
    decision_points: list[str] = Field(
        default_factory=list,
        description=(
            "Junctures in the run where a meaningful choice was required. Append each decision point so the "
            "structure of the choice space is visible."
        ),
    )
    options_considered: list[str] = Field(
        default_factory=list,
        description=(
            "Candidate options evaluated at each decision point. Append each option considered, even ones "
            "not chosen, to preserve the breadth of analysis."
        ),
    )
    rejected_options: list[str] = Field(
        default_factory=list,
        description=(
            "Options the agent explicitly rejected, with the reason. Append each so a successor does not "
            "revisit a discarded option without new information."
        ),
    )
    rationale: list[str] = Field(
        default_factory=list,
        description=(
            "The reasoning behind each decision, expanded beyond the one-line note in decisions. Append one "
            "rationale entry per significant decision."
        ),
    )
    criteria: list[str] = Field(
        default_factory=list,
        description=(
            "The criteria or priorities the agent used to choose between options. Append each criterion so "
            "the basis for decisions is explicit."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Assumptions underlying the decisions that are not yet confirmed. Append each so a reviewer can "
            "check whether a decision still holds if an assumption fails."
        ),
    )
    tradeoffs: list[str] = Field(
        default_factory=list,
        description=(
            "Costs accepted or benefits forgone for each decision. Append each tradeoff so the price of "
            "each choice is recorded."
        ),
    )
    constraints: list[str] = Field(
        default_factory=list,
        description=(
            "Hard limits that shaped or restricted the decisions. Append each constraint as it becomes "
            "relevant."
        ),
    )
    reversibility: list[str] = Field(
        default_factory=list,
        description=(
            "For each decision, whether it is reversible, committed, or a point of no return. Append one "
            "entry per decision so a successor knows what can still be undone."
        ),
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Decisions that depend on other decisions, phrased like 'decision B assumes decision A'. Append "
            "each dependency so the decision graph is preserved."
        ),
    )
    reversed_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Decisions the agent later changed its mind on, noting old versus new and why. Append each "
            "reversal to keep the history honest."
        ),
    )
    deferred_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Decisions consciously postponed, with the reason and any trigger for revisiting. Append each "
            "deferral as it happens."
        ),
    )
    risks: list[str] = Field(
        default_factory=list,
        description=(
            "Risks each decision introduces. Append each risk so the downside of committed choices is "
            "visible."
        ),
    )
    stakeholders: list[str] = Field(
        default_factory=list,
        description=(
            "Who or what is affected by the decisions (the user, downstream systems, other agents). Append "
            "each stakeholder as it becomes relevant."
        ),
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Facts or observations that informed the decisions. Append each piece of evidence supporting a "
            "choice."
        ),
    )
    confidence: list[str] = Field(
        default_factory=list,
        description=(
            "A per-decision confidence note (how sure the agent is each choice is right). Append one entry "
            "per significant decision."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Unresolved questions that bear on future decisions. Phrase each as a concrete question and "
            "append it; keep it until answered."
        ),
    )
    current_decision: str = Field(
        default="",
        description=(
            "The decision the agent is actively weighing right now. Overwrite with the single most-current "
            "decision in progress."
        ),
    )
    next_decision: str = Field(
        default="",
        description=(
            "The next decision the agent expects to face. Overwrite with the most-current anticipated next "
            "decision."
        ),
    )
    decision_count: int = Field(
        default=0,
        description=(
            "The running total of committed decisions. Overwrite with the latest count."
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
