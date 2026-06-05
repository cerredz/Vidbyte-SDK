"""Context Protocol Header

Description:
    Defines the knowledge-oriented continual trace schema (research/knowledge lens).
Purpose:
    Gives developers a ready-made typed schema for recording the facts an agent
    learns, their sources, contradictions, gaps, and synthesized understanding.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class KnowledgeTraceModel(BaseModel):
    """Knowledge-oriented continual trace: facts learned, sources, gaps, and synthesis."""

    goal: str = Field(
        description=(
            "What the agent is trying to learn or find out. Capture the overall information objective. "
            "Keep this stable unless the context redefines it."
        ),
    )
    question: str = Field(
        default="",
        description=(
            "The specific information need driving the current investigation. Overwrite with the single "
            "most-current question being researched."
        ),
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Smaller questions the main question decomposes into. Append each sub-question as it is "
            "identified."
        ),
    )
    facts_learned: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete facts the agent has discovered, each stated plainly. Append every new fact; never "
            "overwrite earlier facts, so the knowledge base only grows."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "Where each key fact came from (URLs, documents, tool outputs). Append each source so findings "
            "can be re-verified later."
        ),
    )
    source_reliability: list[str] = Field(
        default_factory=list,
        description=(
            "An assessment of how trustworthy each source is. Append one entry per source whose reliability "
            "the agent judged."
        ),
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Supporting evidence behind the facts, beyond the bare source citation. Append each piece of "
            "evidence as it is gathered."
        ),
    )
    confirmations: list[str] = Field(
        default_factory=list,
        description=(
            "Facts corroborated by more than one source. Append each confirmation so strongly-supported "
            "findings stand out."
        ),
    )
    contradictions: list[str] = Field(
        default_factory=list,
        description=(
            "Conflicting evidence between sources. Append each contradiction; keep it until resolved, then "
            "record the resolution in facts_learned."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Questions still unanswered. Phrase each as a concrete question and append it; keep until the "
            "context answers it."
        ),
    )
    answered_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Questions that have been resolved, with the answer. Append each answered question so progress "
            "on the inquiry is visible."
        ),
    )
    hypotheses: list[str] = Field(
        default_factory=list,
        description=(
            "Tentative explanations the agent is testing against the evidence. Append each hypothesis as it "
            "is formed."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Unverified assumptions the current understanding rests on. Append each so a reviewer can check "
            "whether conclusions hold if an assumption fails."
        ),
    )
    gaps: list[str] = Field(
        default_factory=list,
        description=(
            "Known holes in the agent's knowledge, where information is missing. Append each gap so a "
            "successor knows what still needs to be found."
        ),
    )
    entities: list[str] = Field(
        default_factory=list,
        description=(
            "Key people, systems, concepts, or objects discovered during research. Append each significant "
            "entity as it appears."
        ),
    )
    relationships: list[str] = Field(
        default_factory=list,
        description=(
            "Relationships between entities, phrased like 'A relates to B because ...'. Append each "
            "relationship the agent establishes."
        ),
    )
    definitions: list[str] = Field(
        default_factory=list,
        description=(
            "Definitions of terms or jargon clarified during the run. Append each definition so a successor "
            "shares the same vocabulary."
        ),
    )
    quotes: list[str] = Field(
        default_factory=list,
        description=(
            "Short verbatim excerpts worth preserving exactly, with their source. Append each quote; keep "
            "it exact rather than paraphrasing."
        ),
    )
    dead_ends: list[str] = Field(
        default_factory=list,
        description=(
            "Searches or sources that proved unproductive. Append each dead end so a successor does not "
            "repeat fruitless queries."
        ),
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description=(
            "Findings the agent holds with low confidence. Append each uncertain item so a reader knows "
            "where the knowledge is soft."
        ),
    )
    next_queries: list[str] = Field(
        default_factory=list,
        description=(
            "The most valuable next searches or questions to pursue. Append each planned query; overwrite "
            "is unnecessary since pursued ones move into answered_questions."
        ),
    )
    summary: str = Field(
        default="",
        description=(
            "The agent's current synthesized understanding across all findings. Overwrite with the single "
            "most-current synthesis as knowledge accumulates."
        ),
    )
    confidence: str = Field(
        default="",
        description=(
            "A brief qualitative read on how settled the overall answer is (low/medium/high with a one-line "
            "reason). Overwrite with the latest assessment."
        ),
    )


KnowledgeTrace = TraceSchema.from_model(
    KnowledgeTraceModel,
    name="knowledge_trace",
    description="Tracks facts learned, sources, contradictions, gaps, and synthesized understanding.",
)

__all__ = [
    "KnowledgeTrace",
    "KnowledgeTraceModel",
]
