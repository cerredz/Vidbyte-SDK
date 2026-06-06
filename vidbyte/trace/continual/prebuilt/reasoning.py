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
        title="Goal",
        min_length=1,
        description=(
            "What the agent's reasoning is ultimately trying to establish or accomplish, capturing the objective that the entire chain of thought is in service of. "
            "Write this as a clear statement of the epistemic or practical target, precise enough that a reader can judge whether each reasoning step advances it. "
            "Keep this field stable unless the context clearly redefines the objective, because the goal anchors the reasoning trace and changes to it invalidate the relative value of prior steps. "
            "If the goal is refined or narrowed during the run, record the most current understanding rather than the first formulation, since the agent's thinking is organized around what it currently believes it needs to establish. "
            "A successor reading this field should immediately understand what question the original agent was trying to answer and be able to continue reasoning toward the same target."
        ),
    )
    question: str = Field(
        title="Current Question",
        min_length=0,
        default="",
        description=(
            "The specific question or sub-problem the agent is currently reasoning about, narrowed from the overall goal to the immediate focus of active thought. "
            "Overwrite this field with the single most-current question under active consideration on every update, so it always reflects the present focus rather than a past one. "
            "State the question as precisely as possible so a reader can understand exactly what the agent is trying to resolve, not just the general area it is thinking about. "
            "A successor reading this field mid-run can immediately pick up the active thread of reasoning without first reconstructing what sub-problem was under investigation from the broader history. "
            "Leave this empty only when the overall goal has been answered, not while mid-question, so an empty value reliably signals that reasoning has reached a conclusion."
        ),
    )
    reasoning_steps: list[str] = Field(
        title="Reasoning Steps",
        min_length=0,
        default_factory=list,
        description=(
            "The chain of reasoning as it developed, each entry representing one logical step from premise to conclusion or from observation to inference. "
            "Append new steps as the agent reasons and do not rewrite earlier steps, so the reasoning trail stays intact and auditable from start to finish. "
            "State each step as a self-contained logical move, connecting the evidence or prior step to the new position it supports, so a reader can follow the chain without reconstructing the logic. "
            "This field is the core audit trail of the reasoning trace: a reviewer or successor can replay it to understand not just what the agent concluded but how it got there. "
            "If a step is later found to be flawed, record the correction in revisions rather than modifying the original entry, keeping the history of the reasoning's evolution intact."
        ),
    )
    key_inferences: list[str] = Field(
        title="Key Inferences",
        min_length=0,
        default_factory=list,
        description=(
            "The important conclusions the agent drew from its reasoning, each stated as a clear, standalone claim that a reader can understand without re-reading the full reasoning chain. "
            "Append each inference as it is reached and do not remove earlier ones, since these are the load-bearing conclusions a successor should not have to re-derive from scratch. "
            "Distinguish inferences from raw observations by capturing the interpretive step: not just what the agent observed but what it concluded from that observation. "
            "This field is the primary output of the reasoning trace: a successor who reads only this field should emerge with the most important conclusions the original agent reached. "
            "If an inference is later revised or overturned, record the change in revisions rather than deleting the original entry, so the evolution of the agent's understanding is traceable."
        ),
    )
    evidence: list[str] = Field(
        title="Evidence",
        min_length=0,
        default_factory=list,
        description=(
            "Observations, facts, data points, or context that support or inform the reasoning, each recorded specifically enough that a reader can locate or verify the source. "
            "Append each piece of evidence as it is gathered and, when useful, note which inference or hypothesis it supports, so the connection between evidence and conclusion is explicit. "
            "Include evidence that cuts against the current direction as well as evidence that supports it, since a complete evidence base is more trustworthy than a selective one. "
            "This field allows a successor or reviewer to assess the quality of the reasoning independently: strong evidence supporting a key inference inspires more confidence than speculation alone. "
            "If evidence is later found to be unreliable or misinterpreted, record that correction in contradictions or revisions rather than removing the original evidence entry."
        ),
    )
    assumptions: list[str] = Field(
        title="Assumptions",
        min_length=0,
        default_factory=list,
        description=(
            "Assumptions the reasoning depends on that have not yet been verified by the context, each stated as a falsifiable claim so a reviewer can identify exactly what would need to be tested to validate it. "
            "Append each assumption as it is recognized during the reasoning process and keep all entries even after the run ends, since unverified assumptions are risks that outlast the agent that made them. "
            "Distinguish assumptions from established facts by their status as believed-but-unconfirmed, so a reader knows where the reasoning is on solid ground versus where it is built on faith. "
            "This field is particularly valuable for a handoff because a successor can immediately see which of the original agent's beliefs were uncertain and decide which to verify before trusting the derived conclusions. "
            "If an assumption is confirmed or refuted during the run, record that outcome in confirmed_hypotheses, rejected_hypotheses, or key_inferences rather than deleting the assumption."
        ),
    )
    hypotheses: list[str] = Field(
        title="Hypotheses",
        min_length=0,
        default_factory=list,
        description=(
            "Candidate explanations or theories the agent is entertaining as possible answers to the question or goal, each stated as a testable proposition rather than a vague possibility. "
            "Append each hypothesis as it is raised during reasoning and track its fate by moving it to confirmed_hypotheses or rejected_hypotheses once the evidence settles the question. "
            "State each hypothesis precisely enough that a reader can understand what evidence would confirm or refute it, rather than just noting that the agent considered something. "
            "This field preserves the full space of possibilities the agent explored, which is valuable for a successor who may want to re-examine a hypothesis the original agent had not yet resolved. "
            "If a hypothesis is revised rather than confirmed or rejected outright, record the revised formulation as a new entry that references the original formulation."
        ),
    )
    confirmed_hypotheses: list[str] = Field(
        title="Confirmed Hypotheses",
        min_length=0,
        default_factory=list,
        description=(
            "Hypotheses the context has supported or proven, each recorded with the evidence or reasoning that settled the question in favor of the hypothesis. "
            "Append each confirmed hypothesis when the agent determines it is supported, including a brief note of the confirming evidence so a reader can assess the strength of the confirmation. "
            "Never remove entries from this list once added, since a confirmed hypothesis is a permanent fact of the run's epistemic state regardless of what happens later in the reasoning. "
            "This field gives a successor a fast summary of what the original agent established with confidence, allowing it to build on those conclusions without re-investigating settled questions. "
            "If a confirmation is later found to be premature or based on flawed evidence, record the correction in revisions rather than removing the entry, keeping the history of beliefs intact."
        ),
    )
    rejected_hypotheses: list[str] = Field(
        title="Rejected Hypotheses",
        min_length=0,
        default_factory=list,
        description=(
            "Hypotheses the agent ruled out, each recorded with the disconfirming evidence or reasoning that closed the question in the negative. "
            "Append each rejected hypothesis with enough context that a reader understands why it was abandoned, not just that it was. "
            "Never remove entries once added, since a rejected hypothesis is a permanent part of the reasoning history and prevents a successor from re-investigating a dead theory without new information. "
            "This field saves a successor significant time by making it clear which explanations the original agent already tested and found wanting, preventing redundant investigation. "
            "If new information later resurrects a rejected hypothesis, record that development as a new hypotheses entry rather than restoring the original rejected entry, so the reversal is visible."
        ),
    )
    dead_ends: list[str] = Field(
        title="Dead Ends",
        min_length=0,
        default_factory=list,
        description=(
            "Lines of reasoning the agent abandoned and why, each recorded with enough detail that a reader understands what path was tried and what made it unproductive. "
            "Append each dead end as the agent recognizes it, noting both the direction that was pursued and the reason it did not lead toward the goal. "
            "Include near-misses as well as clear failures, since a path that was almost correct but wrong in a specific way is useful information for a successor trying to find the right direction. "
            "This field prevents a successor from retrying unproductive paths that the original agent already exhausted, which is one of the most direct efficiency gains from a well-maintained reasoning trace. "
            "If a dead end turns out to have been prematurely abandoned, record that as a new entry in hypotheses rather than removing the dead-end entry, preserving the full history of what was tried."
        ),
    )
    alternatives_considered: list[str] = Field(
        title="Alternatives Considered",
        min_length=0,
        default_factory=list,
        description=(
            "Alternative approaches, interpretations, or explanations the agent weighed during reasoning, each recorded even if it was not ultimately chosen. "
            "Append each alternative as it is considered, including a brief note of why it was weighed and what led the agent to prefer or reject it. "
            "Including unchosen alternatives is as important as recording the chosen path, since a successor or reviewer may judge that a discarded alternative was actually correct. "
            "This field preserves the breadth of the reasoning by capturing what the agent looked at beyond its final direction, which is valuable for auditing whether the reasoning was thorough. "
            "If the agent later revisits a previously discarded alternative, record the reconsideration as a new entry in hypotheses rather than modifying the original alternatives entry."
        ),
    )
    tradeoffs: list[str] = Field(
        title="Tradeoffs",
        min_length=0,
        default_factory=list,
        description=(
            "Tensions the agent balanced between competing considerations during reasoning, each recorded with the competing factors and how the agent resolved or navigated the tension. "
            "Append each tradeoff as it arises and, when visible, note how it was resolved so a reader understands what the agent was willing to sacrifice and what it was not. "
            "State each tradeoff concretely, naming the competing values or constraints rather than describing the tension abstractly, so a reviewer can assess whether the resolution was appropriate. "
            "This field is important for understanding the normative dimensions of the reasoning: where the agent could have gone multiple ways, this field shows which way it leaned and why. "
            "A successor who disagrees with a tradeoff resolution can use this field to identify precisely where to revise the reasoning rather than re-deriving the full decision landscape."
        ),
    )
    counterarguments: list[str] = Field(
        title="Counterarguments",
        min_length=0,
        default_factory=list,
        description=(
            "Objections or opposing considerations that push against the agent's current direction, each recorded with enough detail that a reader can assess whether the original agent engaged with it adequately. "
            "Append each counterargument as the agent encounters or generates it, whether it ultimately accepts or rebuts the objection. "
            "Include both counterarguments the agent addressed and ones it acknowledged but did not fully resolve, distinguishing between them so a reviewer can see where the reasoning is robust versus exposed. "
            "This field keeps the reasoning's weaknesses visible, which is essential for a reviewer assessing whether the agent's conclusions are trustworthy or should be challenged. "
            "If a counterargument is decisive enough to change the agent's direction, record that development in revisions or replans as well, so the impact is visible at the plan level."
        ),
    )
    contradictions: list[str] = Field(
        title="Contradictions",
        min_length=0,
        default_factory=list,
        description=(
            "Conflicting evidence or inconsistencies the agent encountered during reasoning, each recorded with both sides of the conflict so a reader understands what is in tension. "
            "Append each contradiction as it is recognized and keep it in this field until the context resolves it, at which point capture the resolution in key_inferences. "
            "State each contradiction specifically enough that a reader can locate the conflicting elements and understand why they cannot both be true as currently understood. "
            "Unresolved contradictions are the clearest indicator of where the reasoning is incomplete, and this field makes them immediately visible to a successor or reviewer. "
            "If a contradiction is resolved by new evidence that revises a prior belief, record that in revisions as well, so the impact of the resolution on the broader reasoning chain is clear."
        ),
    )
    open_questions: list[str] = Field(
        title="Open Questions",
        min_length=0,
        default_factory=list,
        description=(
            "Unresolved questions the reasoning has surfaced, each phrased as a concrete, answerable question rather than a vague area of uncertainty. "
            "Append new questions as they surface during the run and keep all questions until the context answers them, at which point record the answer in key_inferences. "
            "Prioritize questions whose answers would materially affect the agent's conclusions or a successor's approach, rather than recording every minor uncertainty that arose. "
            "This field is one of the most valuable handoff signals: a successor that can answer an open question the original agent could not often unlocks progress that was previously blocked. "
            "Phrase each question specifically enough to be answerable by someone with access to the relevant information, rather than as a reflection on the agent's internal uncertainty."
        ),
    )
    uncertainties: list[str] = Field(
        title="Uncertainties",
        min_length=0,
        default_factory=list,
        description=(
            "Areas where the agent is unsure or lacks information needed to reason with confidence, each identified specifically enough that a reader understands what would need to be known to reduce the uncertainty. "
            "Append each uncertainty as it is recognized and keep it in this field until the context resolves it or it is determined to be irreducible. "
            "Distinguish uncertainties from open_questions by their character: uncertainties are areas of incomplete knowledge whereas open questions are specific answerable queries derived from those areas. "
            "This field lets a successor or reviewer see where the reasoning is soft and assess whether the conclusions are robust enough to act on or require further investigation. "
            "If an uncertainty is resolved, record the resolution in key_inferences or confirmed_hypotheses rather than deleting the uncertainty entry, so the full epistemic journey is preserved."
        ),
    )
    decisions: list[str] = Field(
        title="Reasoning Decisions",
        min_length=0,
        default_factory=list,
        description=(
            "Conclusions the reasoning committed to that drive subsequent action or further reasoning, each recorded with the brief justification that made the commitment feel warranted. "
            "Append each decision as it is reached and do not remove earlier ones, so the trail of commitments that shaped the reasoning's direction is fully preserved. "
            "State each decision as a specific commitment rather than an abstract conclusion, making clear what the agent is now treating as settled and what implications follow from that settlement. "
            "This field connects the reasoning trace to the action trace: a reader can see which conclusions drove which actions by cross-referencing decisions here with actions_taken in the action trace. "
            "If a decision is later reversed, record the reversal as a new entry in revisions rather than modifying or removing the original decision."
        ),
    )
    rationale: str = Field(
        title="Rationale",
        min_length=0,
        default="",
        description=(
            "The current overall justification for the agent's chosen direction of reasoning, synthesizing the key evidence and inferences that make this path the most promising one available. "
            "Overwrite this field with the single most-current rationale as thinking evolves, so it always reflects the agent's latest understanding of why its current direction is correct. "
            "Write two to four sentences that capture the core argument for the current approach, not a list of supporting points but a coherent statement of why the direction is well-founded. "
            "A successor reading this field should immediately understand why the original agent was headed in the direction it was, making it easier to evaluate whether to continue or revise. "
            "If the rationale shifts substantially due to new evidence or a realization, update this field and also record the change in revisions so the evolution of the justification is traceable."
        ),
    )
    revisions: list[str] = Field(
        title="Revisions",
        min_length=0,
        default_factory=list,
        description=(
            "Beliefs, conclusions, or reasoning steps the agent changed during the run, each recorded with the old position, the new position, and the evidence or event that prompted the change. "
            "Append each revision as it occurs and do not overwrite earlier ones, so the complete history of belief changes is preserved for a reviewer assessing the quality of the reasoning. "
            "Include the trigger for each revision, since a revision caused by strong new evidence is more trustworthy than one caused by an arbitrary preference change. "
            "This field makes the evolution of the agent's understanding traceable, which is essential for a successor who needs to know not just what the agent concluded but how confident those conclusions should be. "
            "If a revision reverses a previous revision, record that as a new entry rather than modifying the original, keeping the history honest even when the reasoning zigzags."
        ),
    )
    mental_model: str = Field(
        title="Mental Model",
        min_length=0,
        default="",
        description=(
            "The agent's current working understanding of the problem and its domain, synthesizing the key entities, relationships, constraints, and mechanisms that structure how the agent thinks about the situation. "
            "Overwrite this field with the latest synthesized model of how things fit together on every update, since the mental model should reflect the agent's current understanding rather than an earlier, less informed one. "
            "Write a coherent description of the agent's world model rather than a list of facts, capturing how the elements relate to each other and what that implies for the reasoning. "
            "A successor reading this field gets an accelerated understanding of the problem domain as the original agent came to understand it, allowing it to reason about new inputs without starting from scratch. "
            "If the mental model changes significantly, record the key shift in revisions as well so a reader understands when and why the underlying model of the problem changed."
        ),
    )
    confidence: str = Field(
        title="Confidence",
        min_length=0,
        default="",
        description=(
            "A brief qualitative read on how confident the agent is in its current reasoning and conclusions, typically expressed as low, medium, or high followed by a one-line explanation of the primary driver. "
            "Overwrite this field on each update to reflect the latest assessment of the reasoning's solidity, since confidence can shift substantially as evidence accumulates or contradictions are resolved. "
            "Base the rating on concrete signals such as the number of unresolved contradictions, the quality of the evidence base, or the degree to which alternatives have been eliminated. "
            "A successor or reviewer reading this field can immediately gauge whether the conclusions are trustworthy enough to act on or require further investigation before being relied upon. "
            "A simple low, medium, or high with a one-sentence reason is more useful than a numeric score without context, because the reason identifies what evidence or resolution would change the rating."
        ),
    )
    current_direction: str = Field(
        title="Current Direction",
        min_length=0,
        default="",
        description=(
            "Where the reasoning is heading next, expressed as the specific line of inquiry or logical step the agent intends to pursue from its current position. "
            "Overwrite this field with the single most-current intended direction of thought on every update, so it always reflects the agent's next move rather than a past one. "
            "Be specific enough that a successor could continue the reasoning without re-deriving where to go next from the accumulated history of steps and inferences. "
            "This field has its highest value during a mid-run handoff: a successor reading it can continue reasoning from exactly where the original agent left off without retracing the path to get there. "
            "Leave this empty only when the reasoning has reached a conclusion, not while mid-inquiry, so an empty value reliably signals that the reasoning is complete."
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
