"""Context Protocol Header

Description:
    Defines the reasoning-oriented continual trace schema (the "why" lens).
Purpose:
    Gives developers a ready-made typed schema for recording an agent's chain of
    reasoning, inferences, hypotheses, assumptions, and dead ends.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ReasoningTraceModel(BaseModel):
    """Reasoning-oriented continual trace describing the agent's thinking and inferences."""

    goal: str = Field(
        description=(
            "What the agent's reasoning is ultimately trying to establish or accomplish. Capture the "
            "objective the thinking serves. Keep this stable unless the context clearly redefines it."
        ),
    )
    question: str = Field(
        default="",
        description=(
            "The specific question or sub-problem the agent is currently reasoning about. Overwrite this "
            "with the single most-current question under active consideration."
        ),
    )
    reasoning_steps: list[str] = Field(
        default_factory=list,
        description=(
            "The chain of reasoning as it developed, each entry one logical step. Append new steps as the "
            "agent reasons; do not rewrite earlier steps, so the reasoning trail stays intact and auditable."
        ),
    )
    key_inferences: list[str] = Field(
        default_factory=list,
        description=(
            "The important conclusions the agent drew from its reasoning. Append each inference; these are "
            "the load-bearing conclusions a successor should not have to re-derive."
        ),
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Observations, facts, or context that support the reasoning. Append each piece of evidence and, "
            "when useful, note which inference it backs."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Assumptions the reasoning depends on that are not yet verified. Append each so a reviewer can "
            "tell which conclusions would collapse if an assumption fails."
        ),
    )
    hypotheses: list[str] = Field(
        default_factory=list,
        description=(
            "Candidate explanations or theories the agent is entertaining. Append each hypothesis as it is "
            "raised; track its fate in confirmed_hypotheses or rejected_hypotheses."
        ),
    )
    confirmed_hypotheses: list[str] = Field(
        default_factory=list,
        description=(
            "Hypotheses the context has supported or proven. Append each confirmed hypothesis with the "
            "evidence that settled it when visible."
        ),
    )
    rejected_hypotheses: list[str] = Field(
        default_factory=list,
        description=(
            "Hypotheses the agent ruled out, with the disconfirming evidence. Append each; this prevents a "
            "successor from re-investigating a settled dead theory."
        ),
    )
    dead_ends: list[str] = Field(
        default_factory=list,
        description=(
            "Lines of reasoning the agent abandoned and why. Append each dead end so future reasoning does "
            "not retread unproductive paths."
        ),
    )
    alternatives_considered: list[str] = Field(
        default_factory=list,
        description=(
            "Alternative approaches or interpretations the agent weighed. Append each alternative, even "
            "ones not chosen, to preserve the breadth of the reasoning."
        ),
    )
    tradeoffs: list[str] = Field(
        default_factory=list,
        description=(
            "Tensions the agent balanced between competing considerations. Append each tradeoff and, when "
            "visible, how it was resolved."
        ),
    )
    counterarguments: list[str] = Field(
        default_factory=list,
        description=(
            "Objections or opposing considerations against the agent's current direction. Append each "
            "counterargument so the reasoning's weaknesses stay visible."
        ),
    )
    contradictions: list[str] = Field(
        default_factory=list,
        description=(
            "Conflicting evidence or inconsistencies the agent encountered. Append each contradiction; keep "
            "it until the context resolves it, then capture the resolution in key_inferences."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Unresolved questions the reasoning has surfaced. Phrase each as a concrete question and append "
            "it; remove nothing, but treat answered ones via key_inferences."
        ),
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description=(
            "Areas where the agent is unsure or lacks information. Append each uncertainty so a successor "
            "knows where the reasoning is soft."
        ),
    )
    decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Conclusions the reasoning committed to that drive action. Append each decision with its brief "
            "justification when visible."
        ),
    )
    rationale: str = Field(
        default="",
        description=(
            "The current overall justification for the agent's chosen direction, in a few sentences. "
            "Overwrite with the single most-current rationale as thinking evolves."
        ),
    )
    revisions: list[str] = Field(
        default_factory=list,
        description=(
            "Beliefs or conclusions the agent changed during the run, noting old versus new. Append each "
            "revision so the evolution of the agent's understanding is traceable."
        ),
    )
    mental_model: str = Field(
        default="",
        description=(
            "The agent's current working understanding of the problem and its domain. Overwrite with the "
            "latest synthesized model of how things fit together."
        ),
    )
    confidence: str = Field(
        default="",
        description=(
            "A brief qualitative read on how confident the agent is in its current reasoning "
            "(low/medium/high with a one-line reason). Overwrite with the latest assessment."
        ),
    )
    current_direction: str = Field(
        default="",
        description=(
            "Where the reasoning is heading next. Overwrite this with the single most-current intended "
            "direction of thought."
        ),
    )


ReasoningTrace = TraceSchema.from_model(
    ReasoningTraceModel,
    name="reasoning_trace",
    description="Tracks the agent's reasoning chain, inferences, hypotheses, and dead ends.",
)

__all__ = [
    "ReasoningTrace",
    "ReasoningTraceModel",
]
