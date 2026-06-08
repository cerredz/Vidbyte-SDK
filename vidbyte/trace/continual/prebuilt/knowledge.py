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
        title="Goal",
        min_length=1,
        description=(
            "What the agent is trying to learn or find out, recorded as the overall information objective that frames every fact, source, and gap captured in this trace. "
            "Write this as a clear statement of the knowledge the agent needs to acquire so a reviewer can assess whether the facts gathered are relevant and the gaps identified are real blockers. "
            "Keep this field stable unless the context redefines the information objective, since the goal is the lens through which all accumulated knowledge should be interpreted. "
            "A reviewer or successor reading this field can filter and prioritize the knowledge base based on its relevance to the stated objective rather than treating all entries as equally important. "
            "If the information objective evolved during the run, note the evolution here so a reviewer understands why the knowledge base may contain entries spanning multiple phases with different targets."
        ),
    )
    question: str = Field(
        title="Current Question",
        min_length=0,
        default="",
        description=(
            "The specific information need driving the current investigation, expressed as a concrete question so a reader knows exactly what the agent is trying to answer right now. "
            "Overwrite this field with the single most-current question being actively researched on every update, keeping it synchronized with the agent's present focus. "
            "This field is more specific than goal: the goal describes the overall knowledge objective while this field names the particular question the agent is working through at this moment. "
            "A successor reading this field can immediately understand what the original agent was investigating when the trace was last updated, and can either continue that inquiry or decide it has already been answered. "
            "Leave this empty only when no specific question is actively under investigation, such as when the agent is synthesizing already-gathered information rather than actively seeking new facts."
        ),
    )
    sub_questions: list[str] = Field(
        title="Sub-Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Smaller questions the main question or overall goal decomposes into, each recorded as a specific, answerable question that contributes to resolving the larger inquiry. "
            "Append each sub-question as it is identified during the research process, so the full structure of the investigation is visible as a set of discrete information needs. "
            "Breaking the main question into sub-questions is important for research runs because it reveals the logical structure of the inquiry and makes progress measurable in terms of how many sub-questions have been answered. "
            "A successor reading this field can immediately see the decomposition of the research problem and identify which sub-questions have been answered versus which still need investigation. "
            "If a sub-question turns out to be unnecessary or is subsumed by a broader finding, note that in answered_questions rather than removing the sub-question entry, preserving the full picture of how the inquiry evolved."
        ),
    )
    facts_learned: list[str] = Field(
        title="Facts Learned",
        min_length=0,
        default_factory=list,
        description=(
            "Concrete facts the agent has discovered during the run, each stated as a specific, verifiable claim so the knowledge base contains actionable information rather than vague impressions. "
            "Append every new fact as it is confirmed and never overwrite earlier facts, so the knowledge base only grows and the full history of discovery is preserved. "
            "A fact belongs in this field only when it is confirmed rather than merely suspected: unconfirmed claims belong in hypotheses until they are verified. "
            "A successor reading this field inherits the factual foundation the original agent built and can skip re-discovering things that are already known, focusing instead on gaps in the knowledge base. "
            "If a previously recorded fact is later found to be wrong, add a correction entry rather than removing the original, since the correction is itself a new fact and the history of the error may be informative."
        ),
    )
    sources: list[str] = Field(
        title="Sources",
        min_length=0,
        default_factory=list,
        description=(
            "Where each key fact came from, expressed as URLs, document names, tool outputs, or other identifiers specific enough that a reviewer or successor can re-verify the fact from the same source. "
            "Append each source as it is used to confirm a fact, pairing the source with the fact it supports so the provenance of the knowledge base is explicit. "
            "Recording sources allows a reviewer to assess the quality and credibility of the knowledge base without needing to independently re-derive each fact from scratch. "
            "A successor reading this field can re-fetch the original sources if a fact needs to be re-verified, which is important when facts may have changed since they were first recorded. "
            "If a source was used for multiple facts, record it once per fact rather than once overall, so the provenance mapping from fact to source is complete and unambiguous."
        ),
    )
    source_reliability: list[str] = Field(
        title="Source Reliability",
        min_length=0,
        default_factory=list,
        description=(
            "An assessment of how trustworthy each source is, each recorded as a judgment of the source's authority, freshness, and independence relative to other sources used for the same facts. "
            "Append one reliability assessment per source whose trustworthiness the agent evaluated, noting the basis for the assessment so a reviewer can agree or disagree with the judgment. "
            "Source reliability distinguishes a fact confirmed by an authoritative primary source from one confirmed only by a secondary or potentially biased source, which affects how much confidence to place in the fact. "
            "A reviewer reading this field can quickly identify which parts of the knowledge base rest on high-reliability sources versus which are based on less authoritative evidence. "
            "If a source's reliability is uncertain, note that explicitly rather than defaulting to an optimistic assessment, since overconfidence in low-reliability sources is one of the most common causes of incorrect conclusions."
        ),
    )
    evidence: list[str] = Field(
        title="Evidence",
        min_length=0,
        default_factory=list,
        description=(
            "Supporting evidence behind the facts, going beyond the bare source citation to capture the specific content, data, or observation that demonstrates each claim. "
            "Append each piece of evidence as it is gathered, pairing it with the fact it supports so a reviewer can see not just where the fact came from but what specifically confirmed it. "
            "Evidence is more granular than a source: a source is where the agent looked, while evidence is what the agent found there that confirmed the fact. "
            "A reviewer reading this field can assess the quality of the confirmation for each fact, which is important for deciding how much to rely on the knowledge base in high-stakes decisions. "
            "If evidence is ambiguous or can be interpreted in more than one way, note the alternative interpretations alongside the primary reading so a reviewer can assess whether the chosen interpretation was well-supported."
        ),
    )
    confirmations: list[str] = Field(
        title="Confirmations",
        min_length=0,
        default_factory=list,
        description=(
            "Facts corroborated by more than one independent source, each recorded to distinguish strongly-supported findings from facts that rest on a single source that could be mistaken or biased. "
            "Append each confirmation as it is established, noting the fact being confirmed and the additional source that independently corroborates it. "
            "Multi-source confirmation is one of the strongest signals of fact reliability: a reviewer reading this field can immediately identify which parts of the knowledge base are most secure. "
            "A successor reading this field can rely most confidently on confirmed facts and should apply more scrutiny to facts that appear in facts_learned but not here. "
            "If a fact is confirmed by many sources, still record it with a note of the additional sources rather than treating corroboration beyond the second source as redundant, since the degree of confirmation matters."
        ),
    )
    contradictions: list[str] = Field(
        title="Contradictions",
        min_length=0,
        default_factory=list,
        description=(
            "Conflicting evidence between sources, each recorded with a description of what the contradiction is, which sources conflict, and the agent's current assessment of how the contradiction should be resolved. "
            "Append each contradiction as it is discovered and keep it in the field until it is resolved, then record the resolution in facts_learned so the full arc from contradiction to resolved fact is visible. "
            "A contradiction that is left unresolved is a known weakness in the knowledge base: a reviewer needs to know about it to avoid over-relying on a fact whose truth is still in dispute. "
            "A successor reading this field knows where the knowledge base is internally inconsistent and can prioritize investigating those areas before making decisions that depend on the disputed facts. "
            "If a contradiction cannot be resolved within the run because it requires information that is not accessible, note that explicitly so a reviewer knows escalation or additional research is needed."
        ),
    )
    open_questions: list[str] = Field(
        title="Open Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Questions still unanswered at the time of each update, each phrased as a concrete, specific question so a reviewer or successor can take action to answer it. "
            "Append each open question as it arises and reflect resolution by adding the answer to answered_questions rather than removing the question, so the full inquiry history is preserved. "
            "An open question that blocks a significant decision or a pending artifact is higher priority than a background informational gap, and that distinction should be noted in the entry. "
            "A successor reading this field has an immediate list of the unresolved informational needs the original agent carried and can prioritize investigating them before making further commitments. "
            "If a question cannot be answered within the run because it requires external access the agent does not have, note that explicitly so a reviewer knows human intervention or a different tool is needed."
        ),
    )
    answered_questions: list[str] = Field(
        title="Answered Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Questions that have been resolved during the run, each recorded with the answer alongside the original question so the resolution is immediately readable without cross-referencing other fields. "
            "Append each answered question as it is resolved, including both sub_questions and open_questions that have been closed, so progress on the overall inquiry is visible over time. "
            "Recording the answer alongside the question is essential: a list of closed questions without their answers is not useful to a reviewer who needs to understand what was learned. "
            "A successor reading this field can see exactly which questions the original agent resolved and what it found, building confidence in the parts of the knowledge base that are no longer in doubt. "
            "If an answer was later revised due to new information, add a new entry with the revised answer rather than modifying the original, so the evolution of the understanding is fully traceable."
        ),
    )
    hypotheses: list[str] = Field(
        title="Hypotheses",
        min_length=0,
        default_factory=list,
        description=(
            "Tentative explanations the agent is testing against the evidence, each recorded as a specific falsifiable claim that could move to facts_learned if confirmed or be discarded if refuted. "
            "Append each hypothesis as it is formed during the investigation, distinguishing them from confirmed facts so a reviewer understands which claims are still provisional. "
            "A hypothesis is more speculative than a fact but more structured than an uncertainty: it represents the agent's current best guess about something it has not yet confirmed. "
            "A successor reading this field can evaluate the current hypotheses against any new evidence it discovers, helping it decide quickly whether to confirm, refute, or refine each claim. "
            "If a hypothesis is refuted by new evidence, note the refutation and move the corrected understanding to facts_learned rather than leaving the discredited hypothesis in place without resolution."
        ),
    )
    assumptions: list[str] = Field(
        title="Assumptions",
        min_length=0,
        default_factory=list,
        description=(
            "Unverified assumptions the current understanding rests on, each recorded clearly so a reviewer can check whether conclusions hold if a particular assumption turns out to be false. "
            "Append each assumption as it is identified in the reasoning process, noting which conclusions or facts depend on each assumption being correct. "
            "An assumption should be stated as a specific claim the agent is treating as true without direct verification, not as a vague background condition. "
            "A successor reading this field knows which parts of the knowledge base are contingent on unverified premises and can prioritize verifying the most critical assumptions before relying on the conclusions they underpin. "
            "If an assumption is later confirmed or refuted by new evidence, record the outcome in confirmations or facts_learned rather than removing the original assumption, preserving the full picture of the knowledge base's foundations."
        ),
    )
    gaps: list[str] = Field(
        title="Knowledge Gaps",
        min_length=0,
        default_factory=list,
        description=(
            "Known holes in the agent's knowledge where information is missing or incomplete, each recorded specifically enough that a successor knows what to look for and where to look. "
            "Append each gap as it is identified during the run and remove or resolve it when the gap is filled, so the field always reflects current unresolved information needs. "
            "State each gap as a specific missing piece of information rather than a vague uncertainty, since a specific gap creates an actionable research task while a vague one does not. "
            "A successor reading this field has an immediate list of research priorities: the gaps the original agent could not fill are the areas where the successor needs to focus its investigative work. "
            "If a gap cannot be filled within the run because the required information is not accessible from the available environment, note that explicitly so a reviewer knows external input or escalation is needed."
        ),
    )
    entities: list[str] = Field(
        title="Entities",
        min_length=0,
        default_factory=list,
        description=(
            "Key people, systems, concepts, or objects discovered during the research that are central to understanding the domain and the answers being sought. "
            "Append each significant entity as it appears in the research, noting what the entity is and why it is relevant to the investigation. "
            "Entities are the vocabulary of the knowledge domain: a reviewer who knows the key entities can understand the facts, relationships, and conclusions much more quickly than one reading cold. "
            "A successor reading this field inherits the domain vocabulary the original agent built and can apply it immediately without needing to re-learn who or what the key players are. "
            "If an entity's definition or role became clearer during the run, record the updated understanding as a new entry rather than modifying the original, so the evolution of understanding is preserved."
        ),
    )
    relationships: list[str] = Field(
        title="Relationships",
        min_length=0,
        default_factory=list,
        description=(
            "Relationships between entities discovered during the investigation, each recorded using a clear pairing like 'A relates to B because ...' so the relational structure of the knowledge domain is explicit. "
            "Append each relationship as it is established, since relationships are often more informative than isolated entity descriptions and are the connective tissue of a coherent knowledge model. "
            "A relationship entry should capture why the two entities are related rather than just noting that a relationship exists, since the nature of the relationship is what makes it useful for reasoning. "
            "A successor reading this field can immediately understand the structure of the domain the original agent was researching and can apply that understanding to new questions without starting from scratch. "
            "If a relationship was initially understood one way and later corrected, record the correction as a new entry and note which original entry is superseded, keeping the full history of how the model evolved."
        ),
    )
    definitions: list[str] = Field(
        title="Definitions",
        min_length=0,
        default_factory=list,
        description=(
            "Definitions of terms or jargon clarified during the run, each recorded with the term and its precise meaning in the context of this investigation so a successor shares the same vocabulary. "
            "Append each definition as it is clarified, especially for terms that are used in domain-specific ways that differ from their common meaning. "
            "Shared definitions prevent misunderstanding: a successor that uses a term differently than the original agent would is likely to misinterpret facts and make incorrect decisions. "
            "A reviewer reading this field can verify that the agent used terminology consistently and correctly, which is important for assessing the reliability of the conclusions it reached. "
            "If a term's definition was ambiguous or contested in the sources, note the ambiguity alongside the working definition the agent adopted so a successor knows the definition is a choice, not an established fact."
        ),
    )
    quotes: list[str] = Field(
        title="Quotes",
        min_length=0,
        default_factory=list,
        description=(
            "Short verbatim excerpts worth preserving exactly because they capture a key fact, definition, or conclusion in the authoritative source's own words, each recorded with the source. "
            "Append each quote as it is identified, keeping the text exact rather than paraphrasing, since the verbatim content is the point of this field. "
            "Quotes are particularly valuable for facts that depend on precise wording, such as legal, technical, or procedural claims where paraphrasing could alter the meaning. "
            "A reviewer reading this field can verify the exact source text behind key claims without needing to locate and re-read the original documents. "
            "If a quote requires context to be interpretable, add a brief one-line note of context alongside the verbatim text rather than paraphrasing the quote itself."
        ),
    )
    dead_ends: list[str] = Field(
        title="Dead Ends",
        min_length=0,
        default_factory=list,
        description=(
            "Searches, sources, or approaches that proved unproductive, each recorded specifically enough that a successor does not repeat the same fruitless effort. "
            "Append each dead end as it is encountered, noting what was tried and why it failed to produce useful information. "
            "A dead end recorded here prevents a successor from wasting time on an already-exhausted path, which can be a significant time saving in a complex research run. "
            "A reviewer reading this field can assess whether the agent explored the space thoroughly and whether the dead ends it encountered were genuinely unproductive or might yield results with a different approach. "
            "If a dead end was only a dead end given a specific framing and might be productive under a different framing, note that so a successor knows the path is not absolutely closed."
        ),
    )
    uncertainties: list[str] = Field(
        title="Uncertainties",
        min_length=0,
        default_factory=list,
        description=(
            "Findings the agent holds with low confidence, each recorded with the specific claim and the reason the confidence is low so a reviewer knows where the knowledge base is soft. "
            "Append each uncertain finding as it is identified rather than only recording high-confidence facts, since a reviewer needs to know where the agent was not sure in order to apply appropriate skepticism. "
            "An uncertain finding is different from an open question: an uncertainty is something the agent believes is probably true but cannot confirm, while an open question is something the agent does not know yet. "
            "A successor reading this field knows which parts of the knowledge base to treat as tentative and can prioritize gathering stronger evidence for the most critical uncertainties. "
            "If an uncertainty is later resolved by new evidence, move the resolved claim to facts_learned rather than leaving it in uncertainties, so the distinction between settled and unsettled knowledge stays current."
        ),
    )
    next_queries: list[str] = Field(
        title="Next Queries",
        min_length=0,
        default_factory=list,
        description=(
            "The most valuable next searches or questions to pursue in order to fill knowledge gaps or resolve open questions, each recorded specifically enough to be executed without further deliberation. "
            "Append each planned query as it is identified, describing the specific search, source, or tool call that would be most productive rather than a vague research direction. "
            "Prioritizing the next queries allows a successor to immediately continue the investigation from the most valuable next step rather than spending time deciding where to look first. "
            "A successor reading this field has an immediate, prioritized research agenda prepared by the original agent and can execute the top query without needing to re-analyze the knowledge gaps. "
            "Once a query has been pursued, its results should move into facts_learned, contradictions, or dead_ends rather than being removed from here, so the full research trail is preserved."
        ),
    )
    summary: str = Field(
        title="Knowledge Summary",
        min_length=0,
        default="",
        description=(
            "The agent's current synthesized understanding across all findings, expressed as a coherent narrative that a reviewer can read in under a minute to understand what the agent has learned. "
            "Overwrite this field with the most-current synthesis on every update, distilling the highest-value insights and facts from all other knowledge fields into a compact, readable summary. "
            "Write in the present tense and focus on what is most important now rather than on the history of how the knowledge was built up, since the full history is available in the other fields. "
            "A successor reading this field gets the most important context it needs to continue the research intelligently without needing to read every individual knowledge entry first. "
            "If the summary would be longer than a short paragraph, that is a signal to be more selective about what truly belongs in a quick synthesis versus what belongs in the more detailed fields."
        ),
    )
    confidence: str = Field(
        title="Knowledge Confidence",
        min_length=0,
        default="",
        description=(
            "A brief qualitative assessment of how settled the overall answer or knowledge base is, expressed as low, medium, or high with a one-line reason so a reader can immediately calibrate how much to rely on the knowledge base. "
            "Overwrite this field with the latest assessment on every update, since confidence may increase as more facts are confirmed or decrease as contradictions and uncertainties are discovered. "
            "Be calibrated rather than optimistic: a medium confidence assessment that accurately reflects genuine uncertainty is more useful than a high confidence claim that leads a reviewer to skip scrutiny the knowledge deserves. "
            "A reviewer reading this field can quickly decide how much weight to place on the knowledge base and whether to invest in re-verification before relying on it for a critical decision. "
            "If confidence is particularly low in a specific area, name that area alongside the overall assessment so a reader knows where to focus skepticism rather than applying it uniformly across the whole knowledge base."
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
