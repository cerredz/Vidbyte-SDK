"""Context Protocol Header

Description:
    Defines the Handoff context primitive and its prebuilt off-the-shelf variants.
Purpose:
    Gives developers a single object that is simultaneously a context primitive
    (droppable into another agent's context_items), the spec describing a handoff
    document's structure, and the produced, filled handoff document.
Architecture:
    - Handoff: Base sectioned-document primitive implementing the ContextItem protocol.
    - EngineeringHandoff / ResearchHandoff / MinimalHandoff: Prebuilt subclasses that
      preset a curated section mapping of titles to guidance descriptions.
Relations:
    Implements the ContextItem protocol from vidbyte.context.primitives, is consumed by
    vidbyte.agents.handoff.HandoffAgent, and is accepted by BaseAgent(handoff=...) and
    ContextManager. Re-exported through vidbyte.context and the root vidbyte namespace.
Similar Files:
    - vidbyte/context/primitives.py: The other standard context item primitives.
    - vidbyte/agents/handoff.py: The agent that fills a Handoff spec from a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class Handoff:
    """Sectioned handoff document that doubles as a ContextItem primitive and a HandoffAgent spec."""

    DEFAULT_TITLE: str = "Handoff"
    DEFAULT_INSTRUCTIONS: str = ""

    def __init__(self, *, sections: Mapping[str, str] | None = None, title: str | None = None, instructions: str | None = None, metadata: Mapping[str, Any] | None = None, primitive_id: str | None = None, primitive_frozen: bool = False) -> None:
        # Resolve section map, title, and instructions from arguments or subclass defaults.
        self.sections: dict[str, str] = dict(sections) if sections is not None else self.default_sections()
        self.title: str = title if title is not None else self.DEFAULT_TITLE
        self.instructions: str = instructions if instructions is not None else self.DEFAULT_INSTRUCTIONS
        self.kind: str = "handoff"
        self.metadata: dict[str, Any] = dict(metadata or {})
        self.primitive_id: str | None = primitive_id
        self.primitive_frozen: bool = primitive_frozen

    def default_sections(self) -> dict[str, str]:
        # Return the prebuilt section mapping for this variant; base Handoff has none.
        return {}

    def to_context_text(self) -> str:
        # Render the handoff as a titled, instruction-led, sectioned markdown block for context injection.
        head = self.title if not self.instructions else f"{self.title}\n{self.instructions}"
        if not self.sections:
            return head
        body = "\n\n".join(f"## {title}\n{self._coerce(value)}" for title, value in self.sections.items())
        return f"{head}\n\n{body}"

    def render_section_brief(self) -> str:
        # Render "- Title: description" lines used to instruct the generating model.
        return "\n".join(f"- {title}: {self._coerce(value)}" for title, value in self.sections.items())

    def fill(self, sections: Mapping[str, str]) -> "Handoff":
        # Return a produced copy of the same concrete subclass with content sections and filled metadata.
        return type(self)(
            sections=dict(sections),
            title=self.title,
            instructions=self.instructions,
            metadata={**self.metadata, "filled": True},
            primitive_id=self.primitive_id,
            primitive_frozen=self.primitive_frozen,
        )

    @property
    def is_filled(self) -> bool:
        # Report whether this handoff carries produced content rather than template descriptions.
        return bool(self.metadata.get("filled", False))

    def section_titles(self) -> tuple[str, ...]:
        # Return the ordered section titles for this handoff.
        return tuple(self.sections.keys())

    @staticmethod
    def _coerce(value: Any) -> str:
        # Coerce any section value to a string so rendering never raises on non-string content.
        return value if isinstance(value, str) else str(value)


def _section_guidance(purpose: str, output: str, continuity: str) -> str:
    """Build detailed model-facing guidance for prebuilt handoff sections."""
    return (
        f"{purpose}. "
        f"Output {output}. "
        "Aim for roughly 500 tokens for this section when the task has enough substance, using concise bullets or compact paragraphs to stay scannable. "
        f"Include {continuity} so the next agent can continue without reconstructing context."
    )


class EngineeringHandoff(Handoff):
    """Prebuilt handoff for continuing software-engineering work."""

    DEFAULT_TITLE = "Engineering Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for a coding agent's work so the next engineer can continue cold.
        return {
            "Objective": "The original goal and what success looks like.",
            "Changes Made": "Files touched and what changed in each, with the reasoning behind the approach.",
            "Verification Status": "What was actually tested or proven versus what is still assumed to work.",
            "Open Threads": "Unfinished work and decisions still in flight.",
            "Risks & Gotchas": "Landmines, fragile areas, and non-obvious constraints for whoever continues.",
            "Next Steps": "Ordered, concrete actions to take next.",
        }


class ResearchHandoff(Handoff):
    """Prebuilt handoff for continuing a research or investigation task."""

    DEFAULT_TITLE = "Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for an investigative agent so findings and gaps transfer cleanly.
        return {
            "Question": "The question or objective the research set out to answer.",
            "Findings": "The substantive conclusions reached so far, with supporting detail.",
            "Sources": "Where each key finding came from, so it can be re-verified.",
            "Confidence & Gaps": "How sure each finding is and what is still unknown or unverified.",
            "Recommended Next Queries": "The most valuable next questions or searches to pursue.",
        }


class MinimalHandoff(Handoff):
    """Prebuilt minimal handoff; the default spec when none is provided."""

    DEFAULT_TITLE = "Handoff"

    def default_sections(self) -> dict[str, str]:
        # The smallest useful handoff: what happened and what to do next.
        return {
            "Summary": "What was accomplished, in a few sentences.",
            "Next Steps": "Concrete actions for whoever continues the work.",
        }


class TreeSearchHandoff(Handoff):
    """Prebuilt handoff for branching exploration with pruning (search-frontier shape)."""

    DEFAULT_TITLE = "Tree Search Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the open frontier and what was pruned, so search is not repeated.
        return {
            "Search Goal": "The goal the search is trying to reach and what a solution looks like.",
            "Frontier": "Open branches still worth expanding, ranked by promise.",
            "Explored Branches": "Paths already taken and their evaluated scores or outcomes.",
            "Pruned / Dead Branches": "Branches abandoned and why, so they are not re-explored.",
            "Best So Far": "The strongest complete or partial solution found to date.",
            "Next Expansion": "Which frontier node to expand next, and the reason.",
        }


class DecompositionHandoff(Handoff):
    """Prebuilt handoff for divide-and-conquer work (subproblem-tree shape)."""

    DEFAULT_TITLE = "Decomposition Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the subproblem tree and the pending composition step.
        return {
            "Top-Level Problem": "The overall problem being decomposed.",
            "Decomposition": "How the problem was split into subproblems (the tree).",
            "Solved Subproblems": "Which subproblems are done and their results.",
            "Open Subproblems": "Which subproblems remain and how they depend on each other.",
            "Composition Status": "How solved parts combine and what blocks final assembly.",
            "Next Steps": "The next subproblem to tackle or composition step to perform.",
        }


class RefinementLoopHandoff(Handoff):
    """Prebuilt handoff for draft-critique-revise work (iteration-journal shape)."""

    DEFAULT_TITLE = "Refinement Loop Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the iteration history and whether the work is converging.
        return {
            "Objective": "What the work product needs to achieve.",
            "Current Draft State": "Where the artifact stands right now.",
            "Iteration Log": "Each refinement pass: what was critiqued and what changed.",
            "Open Critiques": "Known problems identified but not yet addressed.",
            "Convergence Status": "Whether quality is improving, plateauing, or oscillating.",
            "Next Revision": "The next change to make to the draft.",
        }


class ConstraintSatisfactionHandoff(Handoff):
    """Prebuilt handoff for satisfying a requirement set (constraint-ledger shape)."""

    DEFAULT_TITLE = "Constraint Satisfaction Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the constraint ledger and the conflicts between constraints.
        return {
            "Objective": "The goal the solution must achieve.",
            "Constraints": "The full set of requirements, each marked satisfied, violated, or unknown.",
            "Current Candidate": "The working solution under evaluation.",
            "Conflicts & Tensions": "Constraints that pull against one another.",
            "Trade-offs Made": "Which constraints were relaxed or prioritized, and why.",
            "Next Steps": "What to adjust to satisfy the remaining constraints.",
        }


class BacktrackingHandoff(Handoff):
    """Prebuilt handoff for commit-and-rollback work (decision-stack shape)."""

    DEFAULT_TITLE = "Backtracking Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the decision stack and safe points to revert to.
        return {
            "Objective": "The goal being pursued through a sequence of choices.",
            "Decision Stack": "Ordered choices committed to reach the current state.",
            "Tentative Choices": "Decisions made but not yet confirmed.",
            "Backtrack Points": "Where to safely revert if the current path fails.",
            "Abandoned Paths": "Choices already undone and the reason.",
            "Next Steps": "The next choice to commit or path to explore.",
        }


class TradeoffHandoff(Handoff):
    """Prebuilt handoff for balancing competing objectives (Pareto-frontier shape)."""

    DEFAULT_TITLE = "Trade-off Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the objectives and the non-dominated option frontier.
        return {
            "Decision to Make": "The decision that requires balancing competing objectives.",
            "Objectives & Priorities": "The competing goals and their relative weights.",
            "Options Evaluated": "Candidate options and how each scores against the objectives.",
            "Frontier": "The non-dominated options still worth considering.",
            "Leaning / Chosen": "The current preferred option and its justification.",
            "Open Questions": "What remains unresolved before committing.",
        }


class GoalStackHandoff(Handoff):
    """Prebuilt handoff for hierarchical goals (goal-hierarchy shape)."""

    DEFAULT_TITLE = "Goal Stack Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the nested goal hierarchy and the currently active path.
        return {
            "Root Goal": "The top-level goal everything serves.",
            "Goal Hierarchy": "The tree of goals and their subgoals.",
            "Active Path": "The current chain from the root to the goal being worked now.",
            "Satisfied Goals": "Completed subgoals and their outputs.",
            "Suspended Goals": "Goals paused while awaiting a prerequisite.",
            "Next Steps": "The next subgoal to pursue.",
        }


class CoverageHandoff(Handoff):
    """Prebuilt handoff for exhaustively sweeping a space (coverage-map shape)."""

    DEFAULT_TITLE = "Coverage Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the coverage map of done, pending, and skipped regions.
        return {
            "Objective & Scope": "The space that must be fully covered.",
            "Coverage Map": "Regions or items marked done, pending, or skipped.",
            "Completed": "What has been visited and the result for each.",
            "Gaps & Skipped": "What remains and why anything was skipped.",
            "Systematic Next": "The next region to cover and the ordering rule.",
        }


class BudgetBoundedHandoff(Handoff):
    """Prebuilt handoff for progress under a fixed budget (budget-curve shape)."""

    DEFAULT_TITLE = "Budget-Bounded Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on budget consumed versus remaining and the cut line.
        return {
            "Objective": "The goal being pursued under a fixed budget.",
            "Budget Status": "Resources consumed versus remaining (tokens, time, calls, or cost).",
            "Value Delivered": "What has been accomplished so far, ranked by importance.",
            "Remaining Work": "What is left, ordered by value per unit cost.",
            "Cut Line": "What to drop first if the budget runs out.",
            "Next Steps": "The highest-value work to do next.",
        }


class MigrationHandoff(Handoff):
    """Prebuilt handoff for moving a system from one state to another (state-delta shape)."""

    DEFAULT_TITLE = "Migration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the delta between the current and target states.
        return {
            "Target State": "The end-state the system is being migrated toward.",
            "Current State": "Where the system is now, mid-transition.",
            "Completed Migrations": "Steps already applied.",
            "Remaining Delta": "The gap between the current and target states.",
            "Reversibility": "What is safely revertible versus the point of no return.",
            "Next Steps": "The next migration step to apply.",
        }


class CodeReviewHandoff(Handoff):
    """Prebuilt handoff for reviewing a pull request or diff."""

    DEFAULT_TITLE = "Code Review Handoff"

    def default_sections(self) -> dict[str, str]:
        # Verdict-oriented structure so another reviewer can pick up the review state.
        return {
            "Scope Reviewed": "Which files, diffs, or areas were actually reviewed.",
            "Blocking Issues": "Problems that must be fixed before merge, with locations.",
            "Non-Blocking Suggestions": "Improvements that are optional or can be follow-ups.",
            "Approved Aspects": "What was checked and found correct.",
            "Unresolved Threads": "Open discussion points awaiting the author or a decision.",
            "Verdict": "Approve, request changes, or needs another review, and why.",
        }


class BugFixHandoff(Handoff):
    """Prebuilt handoff for fixing a defect."""

    DEFAULT_TITLE = "Bug Fix Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure that ties the symptom to the root cause, the fix, and regression coverage.
        return {
            "Symptom": "The observed incorrect behavior, precisely.",
            "Reproduction": "Steps and conditions that reliably trigger the bug.",
            "Root Cause": "The underlying defect and why it produced the symptom.",
            "Fix Applied": "What was changed to address the root cause.",
            "Tests Added": "Tests that now cover the bug and prevent regression.",
            "Regression Risk": "Areas that could be affected by the fix and need watching.",
        }


class RefactorHandoff(Handoff):
    """Prebuilt handoff for restructuring code without changing behavior."""

    DEFAULT_TITLE = "Refactor Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on proving behavior was preserved across the restructure.
        return {
            "Motivation": "Why the refactor was undertaken.",
            "Scope & Boundaries": "What was restructured and what was deliberately left untouched.",
            "Behavior-Preservation Evidence": "How equivalence was verified (tests, diffs, parity checks).",
            "Changes by Module": "The structural changes, grouped by area.",
            "Risk Areas": "Places where behavior could have subtly shifted.",
            "Follow-up Cleanups": "Further refactors deferred for later.",
        }


class PerformanceOptimizationHandoff(Handoff):
    """Prebuilt handoff for profiling and optimization work."""

    DEFAULT_TITLE = "Performance Optimization Handoff"

    def default_sections(self) -> dict[str, str]:
        # Before/after measurement structure so gains and trade-offs are concrete.
        return {
            "Baseline Metrics": "The measured performance before changes.",
            "Bottlenecks Identified": "Where time or memory was actually being spent.",
            "Optimizations Applied": "The changes made to address each bottleneck.",
            "Measured Improvement": "Performance after changes, against the baseline.",
            "Trade-offs": "Costs incurred (complexity, memory, readability) for the gains.",
            "Remaining Hotspots": "Bottlenecks not yet addressed.",
        }


class TestAuthoringHandoff(Handoff):
    """Prebuilt handoff for writing tests or improving coverage."""

    DEFAULT_TITLE = "Test Authoring Handoff"

    def default_sections(self) -> dict[str, str]:
        # Coverage-oriented structure highlighting what is and is not yet tested.
        return {
            "Coverage Goal": "What the testing effort set out to cover.",
            "Areas Covered": "Components and behaviors now under test.",
            "Test Cases Added": "The specific cases written and what each verifies.",
            "Gaps & Untested Paths": "Behaviors still lacking coverage.",
            "Flaky/Skipped Tests": "Tests that are unreliable or intentionally skipped, and why.",
            "Next Tests": "The most valuable tests to write next.",
        }


class APIDesignHandoff(Handoff):
    """Prebuilt handoff for designing an endpoint or contract."""

    DEFAULT_TITLE = "API Design Handoff"

    def default_sections(self) -> dict[str, str]:
        # Contract-oriented structure covering schemas, versioning, and errors.
        return {
            "Purpose & Consumers": "What the API is for and who will call it.",
            "Endpoints/Contracts": "The operations exposed and their semantics.",
            "Request/Response Schemas": "The shapes of inputs and outputs.",
            "Versioning & Compatibility": "How change is handled and what must stay stable.",
            "Error Model": "How failures are represented and returned.",
            "Open Design Questions": "Unresolved decisions about the interface.",
        }


class SchemaMigrationHandoff(Handoff):
    """Prebuilt handoff for a database schema change."""

    DEFAULT_TITLE = "Schema Migration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Migration structure emphasizing compatibility and data integrity.
        return {
            "Schema Change": "The data-model change being made.",
            "Migration Steps": "The ordered operations to apply the change.",
            "Backfill Plan": "How existing data is transformed or populated.",
            "Forward/Backward Compatibility": "How old and new code coexist during rollout.",
            "Data-Integrity Checks": "Validations confirming the data is correct after migration.",
            "Rollback Plan": "How to revert safely if the migration fails.",
        }


class DependencyUpgradeHandoff(Handoff):
    """Prebuilt handoff for a library or framework version bump."""

    DEFAULT_TITLE = "Dependency Upgrade Handoff"

    def default_sections(self) -> dict[str, str]:
        # Upgrade structure centered on breaking changes and compatibility verification.
        return {
            "Target Versions": "Which dependencies are moving to which versions.",
            "Breaking Changes": "API or behavior changes that affect this codebase.",
            "Code Adjustments Made": "Changes applied to accommodate the upgrade.",
            "Compatibility Verification": "How the upgrade was validated (build, tests, runtime).",
            "Remaining Deprecations": "Deprecated usages still to be addressed.",
            "Rollback": "How to pin back to the previous versions if needed.",
        }


class IncidentResponseHandoff(Handoff):
    """Prebuilt handoff for an on-call incident or outage."""

    DEFAULT_TITLE = "Incident Response Handoff"

    def default_sections(self) -> dict[str, str]:
        # Timeline-oriented structure for handing off an active incident.
        return {
            "Impact & Severity": "What is affected, for whom, and how badly.",
            "Timeline": "Key events from detection to the current moment.",
            "Current Mitigation": "What is in place right now to limit impact.",
            "Root-Cause Status": "Confirmed, suspected, or unknown, with evidence.",
            "Action Items": "Outstanding tasks to fully resolve the incident, with owners.",
            "Comms Status": "What has been communicated, to whom, and what is pending.",
        }


class ArchitectureDecisionHandoff(Handoff):
    """Prebuilt handoff for a system design or architecture decision."""

    DEFAULT_TITLE = "Architecture Decision Handoff"

    def default_sections(self) -> dict[str, str]:
        # ADR-style structure recording the decision and its consequences.
        return {
            "Problem & Context": "The decision to be made and the forces shaping it.",
            "Options Considered": "The viable approaches evaluated.",
            "Decision & Rationale": "The chosen approach and why it was selected.",
            "Consequences & Trade-offs": "What this decision enables and what it costs.",
            "Open Risks": "Uncertainties or risks the decision carries.",
            "Next Steps": "What must happen to act on the decision.",
        }


class CodebaseOnboardingHandoff(Handoff):
    """Prebuilt handoff for understanding an unfamiliar codebase."""

    DEFAULT_TITLE = "Codebase Onboarding Handoff"

    def default_sections(self) -> dict[str, str]:
        # Map-oriented structure for transferring a mental model of a codebase.
        return {
            "Goal": "What understanding the codebase exploration aimed to build.",
            "System Map": "The high-level structure and major modules.",
            "Key Components & Responsibilities": "What each important part is responsible for.",
            "Entry Points & Data Flow": "Where execution starts and how data moves through.",
            "Conventions & Gotchas": "Patterns, idioms, and traps specific to this codebase.",
            "Open Questions": "Parts still not understood.",
        }


class CICDPipelineHandoff(Handoff):
    """Prebuilt handoff for build, test, or deploy pipeline work."""

    DEFAULT_TITLE = "CI/CD Pipeline Handoff"

    def default_sections(self) -> dict[str, str]:
        # Stage-status structure for handing off pipeline configuration work.
        return {
            "Pipeline Goal": "What the pipeline is meant to build, test, or deploy.",
            "Stages & Status": "Each stage and whether it is passing, failing, or incomplete.",
            "Build/Deploy Config": "Where the configuration lives and how it is structured.",
            "Secrets & Environments": "Required credentials and target environments.",
            "Failing/Flaky Stages": "Stages that are broken or unreliable, with symptoms.",
            "Next Steps": "What to fix or add next.",
        }


class IntegrationHandoff(Handoff):
    """Prebuilt handoff for a third-party API or service integration."""

    DEFAULT_TITLE = "Integration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Contract-and-failure-mode structure for an external integration.
        return {
            "Integration Goal": "What external system is being integrated and why.",
            "External Contract": "The third-party API or protocol and its relevant behavior.",
            "Auth & Credentials": "How authentication works and where secrets live.",
            "Implemented Surface": "Which parts of the integration are built and working.",
            "Edge Cases & Failure Modes": "How the integration behaves under errors, limits, and timeouts.",
            "Untested Paths": "Integration behavior not yet verified.",
        }


class SecurityRemediationHandoff(Handoff):
    """Prebuilt handoff for fixing security vulnerabilities."""

    DEFAULT_TITLE = "Security Remediation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Remediation structure pairing each vulnerability with its fix and residual risk.
        return {
            "Vulnerabilities": "The security issues being addressed.",
            "Severity & Exploitability": "How serious each is and how readily it can be exploited.",
            "Fixes Applied": "The remediations made for each vulnerability.",
            "Verification": "How each fix was confirmed effective.",
            "Residual Risk": "Risk that remains after the fixes.",
            "Remaining Items": "Vulnerabilities not yet remediated.",
        }


class ReleaseHandoff(Handoff):
    """Prebuilt handoff for cutting a release or deployment."""

    DEFAULT_TITLE = "Release Handoff"

    def default_sections(self) -> dict[str, str]:
        # Checklist-oriented structure for handing off a release in progress.
        return {
            "Release Scope": "What is included in this release.",
            "Changelog": "User- and developer-facing changes since the last release.",
            "Pre-Deploy Checklist": "Conditions that must hold before deploying.",
            "Deploy Steps": "The ordered procedure to ship the release.",
            "Verification & Smoke": "Checks confirming the release is healthy post-deploy.",
            "Rollback Plan": "How to revert the release if problems appear.",
        }


class PatientHandoff(Handoff):
    """Prebuilt handoff for a clinical patient transfer (SBAR shape)."""

    DEFAULT_TITLE = "Patient Handoff"

    def default_sections(self) -> dict[str, str]:
        # SBAR structure, the standard clinical shift-change handoff format.
        return {
            "Situation": _section_guidance("Describe the current clinical situation and why this patient needs a handoff now", "the presenting problem, acuity, clinical trajectory, location, and immediate context", "time sensitivity, active uncertainty, and who currently owns care"),
            "Background": _section_guidance("Summarize the patient context that changes how the receiver should interpret the situation", "relevant history, diagnoses, allergies, recent events, baseline status, and constraints", "only details that affect next decisions, not a full chart dump"),
            "Assessment": _section_guidance("Explain the current assessment and how confident the team is in it", "vital findings, working diagnoses, ruled-out concerns, response to treatment, and unresolved possibilities", "what is known, what is suspected, and what remains uncertain"),
            "Recommendation": _section_guidance("State the recommended care plan for the receiver", "next clinical actions, priorities, rationale, and expected timing", "the decision points that should change the plan if new data arrives"),
            "Pending Tasks": _section_guidance("List work that has been ordered or promised but not completed", "pending labs, imaging, consults, medications, documentation, discharge steps, and ownership", "expected result timing and what the receiver should do with each result"),
            "Watch-fors": _section_guidance("Identify clinical changes that would require attention or escalation", "specific symptoms, vital sign changes, lab thresholds, complications, and safety concerns", "what escalation path or response should follow each trigger"),
            "Medications & Treatments": _section_guidance("Capture active medications and treatments that matter for continuity", "current doses, recent changes, held medications, fluids, procedures, and treatment response", "why each item is active or held and what needs reassessment"),
            "Care Team & Family Context": _section_guidance("Name the people and communication context surrounding the patient", "primary team, consultants, family contacts, surrogate decision makers, and communication preferences", "sensitive conversations already had and messages that still need alignment"),
            "Escalation Criteria": _section_guidance("Define when the receiver should call for help or change level of care", "clear escalation thresholds, responsible services, backup plans, and urgent contact points", "the rationale for each threshold and any special handling instructions"),
        }


class CareTransitionHandoff(Handoff):
    """Prebuilt handoff for transferring a patient's ongoing care."""

    DEFAULT_TITLE = "Care Transition Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on continuity of treatment across a care transition.
        return {
            "Diagnosis & Status": _section_guidance("Describe the diagnosis and current status at the moment of transfer", "the primary diagnosis, secondary concerns, stability, trajectory, and transition reason", "what has improved, worsened, or remains unresolved"),
            "Medications": _section_guidance("Transfer the medication plan without ambiguity", "active medications, recent changes, stopped or held medications, timing, and monitoring needs", "why changes were made and what adverse effects to watch for"),
            "Procedures Done/Pending": _section_guidance("Summarize interventions already completed and those still needed", "procedures, lines, drains, wound care, pending interventions, and responsible services", "post-procedure status, complications, and handoff-sensitive timing"),
            "Follow-up Plan": _section_guidance("Lay out the follow-up plan after the care transition", "appointments, labs, imaging, referrals, home services, and accountable owners", "dates, dependencies, and what failure to follow up could risk"),
            "Red Flags": _section_guidance("Define warning signs after transition", "symptoms, vital changes, lab findings, medication issues, and care-access problems", "the response expected from the receiving team or patient"),
            "Receiving Team Responsibilities": _section_guidance("Clarify what the receiving team must actively take over", "monitoring duties, medication reconciliation, education tasks, and unresolved decisions", "handoff boundaries so no task falls between teams"),
            "Patient Constraints": _section_guidance("Capture patient-specific constraints that affect the transition", "mobility, transportation, caregiver support, language, cost, adherence, and access barriers", "practical accommodations needed for the plan to work"),
            "Documentation Gaps": _section_guidance("Identify missing or incomplete transition documentation", "forms, discharge summaries, orders, prior records, consent status, and pending signatures", "who needs to complete each item and why it matters"),
        }


class DiagnosticWorkupHandoff(Handoff):
    """Prebuilt handoff for an in-progress diagnostic workup."""

    DEFAULT_TITLE = "Diagnostic Workup Handoff"

    def default_sections(self) -> dict[str, str]:
        # Differential-driven structure for transferring a diagnostic investigation.
        return {
            "Presentation": _section_guidance("Describe the presentation that triggered diagnostic work", "symptoms, signs, timeline, severity, relevant exposures, and patient context", "features that anchor the differential and features that do not fit"),
            "Differential": _section_guidance("Lay out the active differential diagnosis", "candidate diagnoses, supporting evidence, contradicting evidence, likelihood, and danger level", "why each diagnosis remains in or out of the active workup"),
            "Tests Ordered/Resulted": _section_guidance("Track the diagnostic data pipeline", "tests ordered, results returned, abnormal values, pending timing, and interpretation", "what each result does or does not prove"),
            "Leading Diagnosis": _section_guidance("Explain the current leading diagnosis", "the most likely diagnosis, evidence chain, confidence level, and remaining caveats", "what would confirm it or force a pivot"),
            "Next Steps": _section_guidance("Specify the next diagnostic and clinical steps", "tests, consults, empiric treatments, monitoring, and decision deadlines", "ordering priority and dependencies between steps"),
            "Ruled-Out Concerns": _section_guidance("Document important possibilities already deprioritized", "conditions considered, tests or reasoning used to rule them out, and residual risk", "why the receiver should not repeat work unless the picture changes"),
            "Urgency & Safety Plan": _section_guidance("Frame how urgent the diagnostic uncertainty is", "time-critical risks, safe observation windows, fallback treatments, and escalation thresholds", "what to do if the patient worsens before diagnosis is closed"),
            "Consults & Ownership": _section_guidance("Clarify which teams are involved in the workup", "consultants contacted, recommendations received, pending callbacks, and owner for each workstream", "who should make the next diagnostic decision"),
        }


class ContractReviewHandoff(Handoff):
    """Prebuilt handoff for reviewing a legal contract."""

    DEFAULT_TITLE = "Contract Review Handoff"

    def default_sections(self) -> dict[str, str]:
        # Recommendation-oriented structure for a contract review in progress.
        return {
            "Parties & Purpose": _section_guidance("Identify the deal context for the contract review", "the parties, transaction purpose, commercial objective, governing documents, and review posture", "assumptions about business intent that shape legal interpretation"),
            "Key Terms": _section_guidance("Summarize the terms that materially affect obligations or value", "payment, scope, duration, termination, warranties, liability, data rights, and service levels", "which clauses are standard, unusual, or especially important"),
            "Risk Flags": _section_guidance("Explain the legal and commercial risks found in the draft", "problem clauses, severity, affected party, likely consequence, and negotiation priority", "why each issue matters and what happens if it remains unchanged"),
            "Redlines Proposed": _section_guidance("Describe the proposed contract edits", "redline themes, clause-level changes, fallback language, and rationale", "how each edit mitigates a risk or clarifies the bargain"),
            "Open Negotiation Points": _section_guidance("Track unresolved points for negotiation", "open terms, party positions, acceptable fallbacks, leverage, and dependencies", "what the next negotiator should ask for or concede"),
            "Recommendation": _section_guidance("Give the receiver a clear decision recommendation", "whether to sign, revise, reject, or escalate, with rationale and conditions", "the minimum changes needed before approval"),
            "Business Context": _section_guidance("Capture non-legal context that affects the review", "deal urgency, strategic value, stakeholder priorities, budget impact, and relationship considerations", "trade-offs between legal protection and business objectives"),
            "Fallback Positions": _section_guidance("Prepare the next negotiator with acceptable compromises", "preferred language, fallback language, walk-away positions, and approval requirements", "which concessions require business or legal escalation"),
            "Approval Path": _section_guidance("Clarify how the contract can move to execution", "required reviewers, signatories, outstanding approvals, conditions precedent, and timing", "who owns each approval and what evidence they need"),
        }


class LegalResearchHandoff(Handoff):
    """Prebuilt handoff for a legal research question."""

    DEFAULT_TITLE = "Legal Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Authority-and-application structure for transferring legal research.
        return {
            "Issue": _section_guidance("Frame the legal question precisely", "the jurisdiction, procedural posture, facts assumed, legal standard, and question presented", "scope limits that prevent the receiver from researching the wrong issue"),
            "Authorities Found": _section_guidance("Catalog the authorities already located", "statutes, regulations, cases, secondary sources, dates, hierarchy, and citations", "which authorities are binding, persuasive, outdated, or merely background"),
            "Holdings & Application": _section_guidance("Connect the authorities to the facts", "key holdings, rules, factual analogies, distinctions, and practical implications", "the reasoning path from authority to likely answer"),
            "Counterarguments": _section_guidance("Present opposing positions fairly", "adverse authorities, factual distinctions, policy arguments, and likely opponent framing", "how strong each counterargument is and how to respond"),
            "Confidence & Gaps": _section_guidance("State how settled the research answer is", "confidence level, unresolved sources, missing facts, jurisdictional gaps, and research limits", "what additional work would change or harden the conclusion"),
            "Research Trail": _section_guidance("Record how the research was performed", "queries, databases, filters, citations checked, and source paths", "where the receiver should resume without duplicating searches"),
            "Fact Dependencies": _section_guidance("Separate legal conclusions from factual assumptions", "facts assumed, facts missing, disputed facts, and facts that would alter the analysis", "questions the receiver should ask the client or record owner"),
            "Draft Answer": _section_guidance("Give a usable working answer", "the short answer, reasoning summary, caveats, and recommended next research or drafting step", "language that can seed a memo, email, or brief"),
        }


class DueDiligenceHandoff(Handoff):
    """Prebuilt handoff for a due-diligence review."""

    DEFAULT_TITLE = "Due Diligence Handoff"

    def default_sections(self) -> dict[str, str]:
        # Coverage-and-risk structure for handing off a diligence effort.
        return {
            "Scope": _section_guidance("Define the diligence scope and boundaries", "business areas, time periods, document categories, stakeholders, and exclusions", "why the scope is sufficient or where it remains narrow"),
            "Findings by Category": _section_guidance("Organize diligence findings by workstream", "material findings for legal, financial, technical, operational, commercial, and compliance areas as applicable", "evidence behind each finding and its transaction relevance"),
            "Material Risks": _section_guidance("Surface risks that affect valuation, terms, or go-forward decisions", "risk description, severity, likelihood, mitigation, owner, and deal implication", "which risks require escalation before proceeding"),
            "Documents Reviewed": _section_guidance("Create a traceable record of reviewed materials", "document names, versions, dates, sources, gaps, and notable excerpts or themes", "where evidence lives so reviewers can verify conclusions"),
            "Outstanding Requests": _section_guidance("List information still needed from the counterparty or internal teams", "open requests, request owners, priority, due dates, and dependencies", "why each request matters to closing diligence"),
            "Decision Impact": _section_guidance("Translate findings into deal impact", "price, structure, reps, covenants, indemnities, integration effort, and go or no-go considerations", "what the decision maker should do with the information"),
            "Assumptions & Limits": _section_guidance("Make diligence limitations explicit", "data limitations, unverified claims, sampling choices, unavailable records, and reliance assumptions", "how those limits should temper conclusions"),
            "Next Review Pass": _section_guidance("Tell the next reviewer where to spend time", "highest-value follow-up checks, sequencing, owners, and expected outputs", "what would meaningfully reduce risk before the next milestone"),
        }


class TicketEscalationHandoff(Handoff):
    """Prebuilt handoff for escalating a customer support ticket."""

    DEFAULT_TITLE = "Ticket Escalation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Escalation structure so a higher tier can continue without re-asking the customer.
        return {
            "Customer Goal": _section_guidance("Explain what the customer is trying to accomplish", "desired outcome, business context, urgency, affected users, and success criteria", "customer language that helps the receiver preserve trust"),
            "Actions Tried": _section_guidance("Document troubleshooting already completed", "steps attempted, commands or settings changed, results, timestamps, and who performed them", "what should not be repeated unless new information appears"),
            "Current State": _section_guidance("Describe the ticket state at escalation", "current behavior, error messages, environment, severity, customer sentiment, and latest communication", "whether the issue is stable, worsening, or blocked"),
            "Reproduction": _section_guidance("Provide the best known reproduction path", "preconditions, steps, sample inputs, observed outcome, expected outcome, and reproducibility rate", "logs or artifacts needed to validate the reproduction"),
            "Why Escalated": _section_guidance("Justify why this needs another tier or specialist", "technical blocker, permission boundary, product area, customer impact, and escalation trigger", "what expertise or access the receiver needs"),
            "Suggested Next Step": _section_guidance("Recommend the next support action", "diagnostic step, owner, customer message, expected result, and fallback plan", "how the receiver should communicate progress"),
            "Environment Details": _section_guidance("Capture the customer environment precisely", "versions, plan, region, browser, operating system, integrations, identifiers, and configuration", "details that usually change troubleshooting outcomes"),
            "Artifacts & Evidence": _section_guidance("List evidence already collected", "screenshots, logs, traces, ticket links, recordings, attachments, and notable excerpts", "where each artifact is stored and how to interpret it"),
            "Customer Communication": _section_guidance("Summarize communication history and commitments", "messages sent, promises made, expected update cadence, tone, and sensitive context", "what the receiver must say next to avoid confusion"),
        }


class AccountHealthHandoff(Handoff):
    """Prebuilt handoff for transferring a customer account in success management."""

    DEFAULT_TITLE = "Account Health Handoff"

    def default_sections(self) -> dict[str, str]:
        # Relationship-and-risk structure for handing off account ownership.
        return {
            "Account Status": _section_guidance("Summarize the account's current standing", "plan, contract status, health rating, strategic value, recent activity, and immediate priorities", "what the new owner should understand on day one"),
            "Usage & Risk Signals": _section_guidance("Explain usage patterns and risk indicators", "adoption metrics, feature usage, drop-offs, support volume, executive sentiment, and churn signals", "which signals are improving, worsening, or ambiguous"),
            "Open Issues": _section_guidance("List unresolved account problems", "bugs, requests, escalations, commercial blockers, owners, due dates, and customer expectations", "priority and customer impact for each issue"),
            "Relationship Notes": _section_guidance("Transfer relationship context", "stakeholders, champions, detractors, communication preferences, history, and sensitive dynamics", "how to engage without losing continuity or trust"),
            "Renewal/Expansion Posture": _section_guidance("Describe the commercial outlook", "renewal timing, expansion opportunities, risks, pricing context, procurement status, and next commercial steps", "what would improve or weaken the opportunity"),
            "Success Plan": _section_guidance("Document the active success strategy", "goals, milestones, adoption plays, enablement actions, and ownership", "how progress will be measured before the next business review"),
            "Executive Narrative": _section_guidance("Prepare the story for leadership or account reviews", "headline status, key wins, top risks, asks, and forecast confidence", "what leadership needs to know without reading the full account history"),
            "Next Touchpoints": _section_guidance("Lay out upcoming customer interactions", "meetings, QBRs, renewal calls, technical sessions, agendas, and prep needs", "who should attend and what outcome each touchpoint should drive"),
        }


class AlertTriageHandoff(Handoff):
    """Prebuilt handoff for a security operations alert-triage shift."""

    DEFAULT_TITLE = "Alert Triage Handoff"

    def default_sections(self) -> dict[str, str]:
        # Queue-state structure for a SOC shift handoff.
        return {
            "Alerts in Queue": _section_guidance("Summarize alerts still awaiting triage", "alert IDs, severities, sources, affected assets, timestamps, and why they remain open", "ordering guidance for the next analyst"),
            "Triaged & Dispositioned": _section_guidance("Record alerts already handled this shift", "dispositions, evidence, false-positive rationale, escalations, and closure notes", "what should be trusted and what may need quality review"),
            "Under Investigation": _section_guidance("Explain active investigations in progress", "hypotheses, evidence collected, current status, involved systems, and open questions", "where the next analyst should resume analysis"),
            "Suspected Scope": _section_guidance("Estimate blast radius and affected surface", "users, hosts, accounts, networks, data, timelines, and confidence level", "what needs confirmation before containment or closure"),
            "Next Actions": _section_guidance("Prioritize the next SOC actions", "queries, containment steps, escalations, owner assignments, and deadlines", "the reason each action is ordered where it is"),
            "Evidence Collected": _section_guidance("List security evidence gathered so far", "logs, detections, endpoint data, screenshots, SIEM links, and notable indicators", "how reliable each evidence source is"),
            "Containment Status": _section_guidance("Describe containment or response steps already taken", "blocked indicators, disabled accounts, isolated hosts, notifications, and pending approvals", "residual exposure and reversibility concerns"),
            "Escalation Path": _section_guidance("Clarify when and how to escalate", "severity thresholds, incident commander contacts, legal or privacy triggers, and communication channels", "what evidence must accompany escalation"),
        }


class ThreatHuntHandoff(Handoff):
    """Prebuilt handoff for an in-progress threat hunt."""

    DEFAULT_TITLE = "Threat Hunt Handoff"

    def default_sections(self) -> dict[str, str]:
        # Hypothesis-elimination structure applied to threat hunting.
        return {
            "Hypothesis": _section_guidance("State the hunt hypothesis being tested", "suspected actor behavior, technique, target surface, rationale, and expected traces", "what evidence would confirm or falsify the hypothesis"),
            "Data Sources Queried": _section_guidance("Document telemetry already searched", "data sources, query names, time windows, filters, coverage, and limitations", "where the next analyst should and should not rerun queries"),
            "Findings": _section_guidance("Summarize evidence discovered during the hunt", "signals, anomalies, matching events, affected entities, confidence, and interpretation", "links between evidence and the original hypothesis"),
            "Ruled Out": _section_guidance("Capture eliminated paths to avoid duplicate hunting", "indicators, techniques, hosts, accounts, or time windows ruled out and why", "the evidence standard used to rule each item out"),
            "Open Leads": _section_guidance("List promising hunt leads still worth pursuing", "entities, indicators, queries, pivots, enrichments, and expected value", "priority order and reasoning for the next hunter"),
            "Coverage Map": _section_guidance("Explain what parts of the environment were covered", "asset classes, identity stores, cloud accounts, endpoints, network ranges, and blind spots", "coverage gaps that could hide activity"),
            "Detection Opportunities": _section_guidance("Identify durable detection improvements", "rules, thresholds, enrichment, logging changes, and false-positive considerations", "how the hunt should improve future alerting"),
            "Response Readiness": _section_guidance("Prepare for possible incident response if the hunt confirms activity", "containment candidates, stakeholders, communication channels, and required evidence", "what must happen before moving from hunt to incident"),
        }


class InvestmentThesisHandoff(Handoff):
    """Prebuilt handoff for an investment thesis under development."""

    DEFAULT_TITLE = "Investment Thesis Handoff"

    def default_sections(self) -> dict[str, str]:
        # Thesis-and-risk structure for transferring an investment analysis.
        return {
            "Thesis": _section_guidance("State the core investment argument", "the claim, time horizon, expected return drivers, market view, and why the opportunity exists", "what would make the thesis compelling or invalid"),
            "Supporting Evidence": _section_guidance("Summarize evidence backing the thesis", "data points, comps, management commentary, industry trends, unit economics, and source quality", "how each evidence item supports a return driver"),
            "Key Risks": _section_guidance("Explain risks that could break the thesis", "business, market, regulatory, financing, execution, and timing risks with severity", "early warning indicators and mitigation ideas"),
            "Valuation View": _section_guidance("Present the current valuation assessment", "methodology, assumptions, range, sensitivity, peer context, and margin of safety", "which assumptions matter most to upside and downside"),
            "Catalysts": _section_guidance("Identify events that could move value", "near-term catalysts, long-term catalysts, expected timing, probability, and evidence to monitor", "how each catalyst affects the thesis"),
            "Open Diligence": _section_guidance("List diligence still required before conviction increases", "questions, data needs, expert calls, model work, document review, and owners", "what each diligence item would decide"),
            "Positioning & Sizing": _section_guidance("Frame portfolio implications", "suggested sizing, liquidity, drawdown tolerance, hedges, correlations, and constraints", "how conviction and risk translate into action"),
            "Variant Views": _section_guidance("Compare credible alternative cases", "base case, bull case, bear case, probabilities, and assumptions that separate them", "what evidence would shift weight between cases"),
            "Monitoring Plan": _section_guidance("Define how the thesis should be monitored after action", "metrics, filings, news, price levels, management signals, and review cadence", "when to add, hold, reduce, or exit"),
        }


class DealHandoff(Handoff):
    """Prebuilt handoff for an in-progress deal or transaction."""

    DEFAULT_TITLE = "Deal Handoff"

    def default_sections(self) -> dict[str, str]:
        # Workstream-status structure for handing off a live deal.
        return {
            "Deal Status": _section_guidance("Describe where the deal stands now", "stage, transaction type, parties, economics, approvals, latest movement, and blockers", "what changed recently and what is time-sensitive"),
            "Workstreams": _section_guidance("Map the active deal workstreams", "legal, finance, technical, diligence, integration, commercial, and stakeholder workstreams with owners", "dependencies between workstreams"),
            "Open Items by Workstream": _section_guidance("List outstanding work by owner and workstream", "tasks, blockers, due dates, status, required inputs, and expected outputs", "which items are on the critical path"),
            "Key Risks": _section_guidance("Explain risks that could derail or reprice the deal", "risk source, likelihood, impact, mitigation, escalation owner, and decision implication", "which risks require immediate attention"),
            "Next Milestones": _section_guidance("Lay out upcoming deal milestones", "deadlines, gating events, meetings, filings, approvals, and deliverables", "what must be true before each milestone"),
            "Negotiation State": _section_guidance("Summarize the current negotiation posture", "open terms, party positions, concessions made, fallback positions, and unresolved issues", "where the next negotiator has room to move"),
            "Stakeholder Map": _section_guidance("Identify internal and external stakeholders", "decision makers, approvers, advisors, blockers, champions, and communication channels", "who needs what information next"),
            "Integration or Closing Readiness": _section_guidance("Capture readiness for closing or post-close execution", "closing checklist, integration assumptions, transition risks, operational handoffs, and Day One needs", "what could delay close or impair execution"),
        }


class CreditAnalysisHandoff(Handoff):
    """Prebuilt handoff for a credit analysis."""

    DEFAULT_TITLE = "Credit Analysis Handoff"

    def default_sections(self) -> dict[str, str]:
        # Assessment-and-decision structure for transferring a credit review.
        return {
            "Borrower & Facility": _section_guidance("Describe the borrower and proposed facility", "borrower profile, ownership, facility type, amount, tenor, collateral, purpose, and key terms", "the credit decision being requested"),
            "Financial Assessment": _section_guidance("Summarize financial performance and capacity", "revenue, margins, leverage, coverage, liquidity, cash flow, trends, and peer context", "how the numbers support or weaken repayment ability"),
            "Risk Factors": _section_guidance("Explain material credit risks", "business, industry, collateral, covenant, liquidity, management, and macro risks with severity", "early warning indicators for each risk"),
            "Rating/Recommendation": _section_guidance("State the proposed credit view", "rating, approval recommendation, conditions, pricing view, and rationale", "what would cause an upgrade, downgrade, decline, or escalation"),
            "Open Questions": _section_guidance("List remaining information needs", "missing documents, clarifications, sensitivity cases, legal questions, and borrower follow-ups", "why each item matters to approval"),
            "Covenants & Protections": _section_guidance("Capture lender protections under consideration", "financial covenants, reporting requirements, collateral controls, guarantees, and default triggers", "which protections are essential versus negotiable"),
            "Scenario Analysis": _section_guidance("Describe downside and sensitivity work", "stress cases, assumptions, break points, recovery estimates, and liquidity runway", "how scenarios affect recommendation and structure"),
            "Approval Conditions": _section_guidance("Clarify what must happen before credit approval or funding", "committee approvals, documentation, diligence, conditions precedent, and responsible owners", "what blocks final decision or closing"),
        }


class ContextWindowHandoff(Handoff):
    """Prebuilt agent-native handoff for continuing across a context-window boundary."""

    DEFAULT_TITLE = "Context Window Handoff"

    def default_sections(self) -> dict[str, str]:
        # Compaction-aware structure: what survives the window versus what is dropped.
        return {
            "Task State": _section_guidance("Describe the current state of the task at the context boundary", "goal, progress, active step, completion estimate, and what triggered the handoff", "the exact state needed to resume without replaying the full transcript"),
            "Key Facts to Preserve": _section_guidance("Identify facts that must survive compaction", "user constraints, decisions, IDs, file paths, assumptions, tool results, and domain facts", "which facts are authoritative and which still need verification"),
            "Decisions Made": _section_guidance("Record committed decisions that should not be reopened casually", "decision, rationale, alternatives rejected, owner, timestamp or sequence, and dependencies", "what would justify revisiting a decision"),
            "Compacted/Dropped Context": _section_guidance("Explain what context was removed or compressed", "omitted discussion, summarized logs, stale attempts, superseded drafts, and why each can be dropped", "anything that might be dangerous to forget"),
            "Active Working Set": _section_guidance("List the objects currently in play", "files, symbols, tabs, tasks, variables, artifacts, branches, and external state", "which items are primary versus background context"),
            "Resume Instructions": _section_guidance("Give exact continuation instructions", "next action, commands or reasoning steps, expected result, and fallback if it fails", "the shortest path from this handoff to useful progress"),
            "Token Budget Strategy": _section_guidance("Explain how the next agent should manage limited context", "what to keep verbatim, what to summarize, what to fetch lazily, and what to ignore", "priority rules for future compaction"),
            "Validation Needed": _section_guidance("Call out what must be checked after resuming", "tests, source checks, user confirmations, stale assumptions, and high-risk claims", "the verification order that protects against context loss errors"),
            "Lost Nuance": _section_guidance("Preserve nuance that may not fit cleanly into facts", "tone, unresolved disagreement, preference signals, caveats, and subtle constraints", "why the nuance matters to the next response or action"),
        }


class ToolTrajectoryHandoff(Handoff):
    """Prebuilt agent-native handoff for a tool-using agent's call trace."""

    DEFAULT_TITLE = "Tool Trajectory Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure mirroring the tool-call lifecycle so tool work can resume.
        return {
            "Available Tools": _section_guidance("Describe the tool surface available to the agent", "tool names, capabilities, constraints, permissions, required inputs, and important quirks", "which tools are safe, risky, unavailable, or preferred"),
            "Calls Made & Results": _section_guidance("Summarize successful tool calls already executed", "call order, parameters, outputs, artifacts, state changes, and relevant excerpts", "how each result changed the task state"),
            "Failed Calls & Errors": _section_guidance("Document failed or partial tool calls", "inputs, errors, stack traces, retry attempts, suspected cause, and current status", "what should be retried, avoided, or debugged differently"),
            "Current Tool State": _section_guidance("Capture side effects established by tool use", "files changed, browser state, sessions, environment variables, processes, caches, and locks", "state that future calls depend on"),
            "Next Tool Action": _section_guidance("Recommend the next tool operation", "tool name, exact inputs, expected output, rationale, and fallback plan", "why this call is the best next step"),
            "Artifacts Produced": _section_guidance("List durable artifacts created by tools", "file paths, attachment IDs, logs, screenshots, reports, generated data, and ownership", "how the receiver should inspect or reuse each artifact"),
            "Permission Boundaries": _section_guidance("Make tool permission limits explicit", "read or write boundaries, approval needs, sandbox constraints, network limits, and destructive-action risks", "what must not be attempted without user approval"),
            "Ordering Dependencies": _section_guidance("Explain dependencies between tool calls", "required sequence, prerequisites, cleanup steps, race conditions, and invalid states", "what breaks if the order changes"),
        }


class SubAgentDelegationHandoff(Handoff):
    """Prebuilt agent-native handoff for a supervisor delegating to sub-agents."""

    DEFAULT_TITLE = "Sub-Agent Delegation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Delegation structure tracking spawned subagents and synthesis of their results.
        return {
            "Top Goal": _section_guidance("State the overall objective for the delegation tree", "goal, success criteria, decomposition rationale, constraints, and current progress", "how subagent work maps back to the parent task"),
            "Subagents Spawned": _section_guidance("List subagents that have been assigned work", "agent names or roles, prompts, scopes, inputs, deadlines, and expected artifacts", "which assignments overlap or depend on each other"),
            "Results Received": _section_guidance("Summarize completed subagent outputs", "findings, artifacts, confidence, citations, decisions, and unresolved caveats", "how each output should influence synthesis"),
            "Pending Delegations": _section_guidance("Track work still waiting on subagents", "open assignments, blockers, expected return format, priority, and follow-up timing", "what the parent should do while waiting"),
            "Synthesis State": _section_guidance("Explain how subagent outputs are being combined", "agreements, conflicts, merged conclusions, gaps, and synthesis method", "what remains before a final answer or action is possible"),
            "Next Delegation": _section_guidance("Recommend the next delegation move", "subtask, target role, prompt inputs, expected deliverable, and reason for delegation", "why delegating beats doing the work directly"),
            "Conflict Resolution": _section_guidance("Capture disagreements between subagent outputs", "conflicting claims, evidence on each side, confidence levels, and arbitration criteria", "how the supervisor should resolve or escalate conflicts"),
            "Quality Gates": _section_guidance("Define quality checks for subagent work", "acceptance criteria, verification steps, completeness checks, and failure handling", "how to decide whether a subagent result is usable"),
            "Shared Context": _section_guidance("Identify context that all future subagents need", "common facts, constraints, files, definitions, prior results, and forbidden assumptions", "what should be passed into the next spawned worker"),
        }


class OrchestrationHandoff(Handoff):
    """Prebuilt agent-native handoff for multi-agent orchestration."""

    DEFAULT_TITLE = "Orchestration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Plan-and-assignment structure for handing off a multi-agent execution.
        return {
            "Plan": _section_guidance("Describe the multi-agent plan being executed", "workflow, DAG or sequence, objective, constraints, and current phase", "why the plan is structured this way"),
            "Agent Assignments": _section_guidance("Map agents to responsibilities", "agent roles, owned tasks, inputs, outputs, authority, and expected completion conditions", "handoff boundaries between agents"),
            "Completed/In-Flight/Blocked": _section_guidance("Report status for every plan component", "completed work, active work, blocked work, owners, blockers, and dependencies", "what changed since the previous orchestration checkpoint"),
            "Cross-Agent Conflicts": _section_guidance("Surface conflicts across agents or workstreams", "resource contention, contradictory findings, duplicated work, incompatible assumptions, and resolution options", "which conflicts need supervisor action"),
            "Next Dispatch": _section_guidance("Specify the next orchestration action", "agent to invoke, input payload, context to include, expected result, and scheduling reason", "what should happen if the dispatch fails"),
            "Shared State": _section_guidance("Capture state shared across the orchestrated system", "global facts, artifacts, queues, locks, budgets, and mutable resources", "how agents should coordinate around this state"),
            "Coordination Rules": _section_guidance("Document rules that govern agent interaction", "communication protocol, sequencing constraints, ownership rules, escalation paths, and stop conditions", "how to prevent duplicated or conflicting work"),
            "Completion Criteria": _section_guidance("Define what makes the orchestration complete", "deliverables, acceptance checks, quality gates, residual risks, and final synthesis needs", "the evidence required before ending the run"),
        }


class HumanEscalationHandoff(Handoff):
    """Prebuilt agent-native handoff for escalating from an agent to a human."""

    DEFAULT_TITLE = "Human Escalation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure that turns a stuck agent into an actionable human decision.
        return {
            "What I Was Doing": _section_guidance("Explain the task state before escalation", "goal, context, progress, constraints, and why the work matters", "the minimum background the human needs to decide"),
            "Where I'm Stuck": _section_guidance("Pinpoint the failure or uncertainty", "blocking question, failed assumption, missing permission, ambiguous requirement, or risky decision", "why the agent cannot proceed responsibly"),
            "What I Tried": _section_guidance("Summarize attempted approaches", "steps taken, evidence gathered, alternatives explored, failures, and partial successes", "what should not be repeated without new information"),
            "Specific Decision Needed": _section_guidance("Ask the human for a concrete decision", "the exact question, decision deadline, required format, and consequences of each answer", "how the response will unblock execution"),
            "Options & Recommendation": _section_guidance("Present clear options for the human", "available choices, trade-offs, risks, expected outcomes, and the agent's recommendation", "why the recommendation is preferred"),
            "Risk of Proceeding": _section_guidance("Explain what could go wrong without human input", "policy risk, data loss, user harm, wasted work, incorrect assumptions, and reversibility", "why escalation is justified"),
            "Needed Context From Human": _section_guidance("List information only the human can provide", "preferences, credentials, approvals, missing facts, subjective priorities, and business constraints", "which answer parts are mandatory versus helpful"),
            "Safe Holding Pattern": _section_guidance("Define what can happen while waiting", "safe checks, reversible prep work, documentation, monitoring, and tasks to avoid", "how to maintain progress without crossing the escalation boundary"),
        }


class CheckpointResumeHandoff(Handoff):
    """Prebuilt agent-native handoff for checkpointing a long-horizon run."""

    DEFAULT_TITLE = "Checkpoint Resume Handoff"

    def default_sections(self) -> dict[str, str]:
        # Checkpoint structure capturing the exact place and state to resume from.
        return {
            "Goal": _section_guidance("State the long-running objective being checkpointed", "goal, success criteria, constraints, stakeholders, and current completion horizon", "why the work should resume rather than restart"),
            "Progress So Far": _section_guidance("Summarize completed progress", "milestones reached, files or artifacts created, decisions made, and verified outcomes", "what can be treated as done"),
            "Current Step": _section_guidance("Describe the step active at checkpoint time", "current action, inputs in use, partial output, expected next result, and local context", "exactly where execution paused"),
            "Environment State": _section_guidance("Capture external state needed for resume", "working directory, branch, process state, services, sessions, env vars, and file changes", "what the receiver should inspect before continuing"),
            "Blockers": _section_guidance("List anything preventing forward progress", "technical blockers, missing decisions, failing checks, unavailable services, and dependency waits", "the owner or workaround for each blocker"),
            "Resume Point": _section_guidance("Give precise resume instructions", "first command or action, expected output, next branch in logic, and fallback if it fails", "how to continue with minimal context rebuilding"),
            "Verification Snapshot": _section_guidance("Record the last known verification state", "tests run, checks passed, failures, untested paths, and confidence level", "what must be rerun after resuming"),
            "Rollback or Recovery": _section_guidance("Explain how to recover if resume goes wrong", "safe revert points, backup artifacts, cleanup commands, and irreversible changes", "how to avoid compounding partial-work errors"),
            "Budget Remaining": _section_guidance("Estimate remaining resource budget", "time, tokens, API calls, user patience, deadlines, and highest-value next work", "how the receiver should prioritize under constraints"),
        }


class DeepResearchHandoff(Handoff):
    """Prebuilt agent-native handoff for an agentic multi-hop research run."""

    DEFAULT_TITLE = "Deep Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Query-and-synthesis structure for transferring an autonomous research run.
        return {
            "Question": _section_guidance("Frame the research question being investigated", "main question, subquestions, scope boundaries, definitions, and desired answer format", "what counts as sufficient evidence"),
            "Search Queries Run": _section_guidance("Document the search strategy already used", "queries, databases, filters, dates, source types, and why each query was run", "which search paths are exhausted or promising"),
            "Sources Gathered": _section_guidance("Summarize gathered sources and their relevance", "source titles, authors, dates, credibility, key claims, and links or identifiers", "how each source supports or challenges the emerging answer"),
            "Synthesis So Far": _section_guidance("Present the current synthesized understanding", "main findings, evidence relationships, caveats, and tentative conclusions", "what is ready to use versus still provisional"),
            "Contradictions": _section_guidance("Call out conflicting evidence or interpretations", "claims in tension, source quality, possible reconciliation, and unresolved disputes", "what additional evidence could resolve the conflict"),
            "Confidence & Next Queries": _section_guidance("Assess confidence and prescribe next research", "confidence by claim, evidence gaps, query ideas, target sources, and expected value", "how to improve certainty efficiently"),
            "Source Quality Notes": _section_guidance("Evaluate the reliability of the evidence base", "primary versus secondary sources, recency, bias, methodology, and corroboration", "which sources should be quoted, cited cautiously, or ignored"),
            "Unanswered Subquestions": _section_guidance("List remaining research questions", "subquestions, priority, current best guess, needed source type, and decision impact", "what answering each subquestion would change"),
            "Citation Trail": _section_guidance("Preserve traceability for final synthesis", "source IDs, URLs, line references, excerpts to verify, and citation notes", "where the next researcher should retrieve support without starting over"),
        }


class RetrievalHandoff(Handoff):
    """Prebuilt agent-native handoff for a retrieval-augmented agent."""

    DEFAULT_TITLE = "Retrieval Handoff"

    def default_sections(self) -> dict[str, str]:
        # Retrieval structure capturing what was fetched and what coverage remains.
        return {
            "Query": _section_guidance("Describe the retrieval need precisely", "original query, expanded terms, filters, corpus, desired evidence, and answer target", "which interpretation of the query is being pursued"),
            "Chunks Retrieved": _section_guidance("List the material retrieved so far", "chunk IDs, document names, snippets, scores, metadata, and retrieval order", "where the receiver can inspect the underlying text"),
            "Relevance Assessment": _section_guidance("Assess how useful each retrieval result is", "relevance, redundancy, contradictions, missing context, and confidence", "which chunks should feed the answer or be discarded"),
            "Coverage Gaps": _section_guidance("Identify what retrieval has not covered", "missing topics, time ranges, document classes, entities, and likely blind spots", "why the current result set is incomplete"),
            "Re-query Plan": _section_guidance("Recommend the next retrieval strategy", "query rewrites, filters, embeddings, keyword pivots, reranking, and expected improvements", "how to close the most important gaps"),
            "Corpus Assumptions": _section_guidance("Clarify assumptions about the searched corpus", "included sources, excluded sources, freshness, indexing limits, and access constraints", "how corpus limits affect confidence"),
            "Answer Candidates": _section_guidance("Extract candidate answer material from retrieval", "claims, supporting chunks, conflicting chunks, and tentative synthesis", "which evidence should be cited in a final response"),
            "Deduplication Notes": _section_guidance("Track duplicate or overlapping retrieval results", "near-duplicate chunks, repeated claims, canonical source choice, and redundancy impact", "how to avoid over-weighting repeated text"),
        }


class BrowserSessionHandoff(Handoff):
    """Prebuilt agent-native handoff for a browser-automation agent (live-state shape)."""

    DEFAULT_TITLE = "Browser Session Handoff"

    def default_sections(self) -> dict[str, str]:
        # Live-state structure capturing where the browser is and how to resume.
        return {
            "Current Location": _section_guidance("Describe the browser's current page state", "URL, page title, visible region, selected tab, form state, and relevant DOM landmarks", "how the receiver can recognize the same state"),
            "Session & Auth State": _section_guidance("Capture authentication and session context", "login status, account identity, cookies or tokens conceptually, expiry risks, and permission limits", "what must be preserved or reauthenticated"),
            "Action Trail": _section_guidance("Summarize browser actions already performed", "navigation path, clicks, inputs, selectors that worked, waits, and observed outcomes", "what should not be repeated unless state changed"),
            "Extracted Data": _section_guidance("List data captured from the browser", "fields, tables, screenshots, downloads, copied text, storage locations, and confidence", "how the data should be used or verified"),
            "Blockers": _section_guidance("Document browser-specific blockers", "broken selectors, captchas, modals, permissions, network errors, dynamic loading, and anti-automation issues", "workarounds attempted and next safe options"),
            "Next Action": _section_guidance("Specify the next browser interaction", "target page or element, selector strategy, input values, expected result, and fallback path", "how to continue without disturbing page state"),
            "Viewport & Timing Notes": _section_guidance("Capture UI timing and viewport constraints", "viewport size, scroll position, lazy loading, animations, waits, and responsive layout issues", "conditions needed for reliable automation"),
            "Download or Upload State": _section_guidance("Track file transfers in the session", "downloaded files, upload fields, pending file choosers, paths, and completion status", "what file operation should happen next"),
            "Safety Constraints": _section_guidance("Record interaction boundaries for the page", "forms not to submit, purchases not to confirm, destructive buttons, privacy limits, and approval needs", "actions that require explicit user consent"),
        }


class ComputerUseHandoff(Handoff):
    """Prebuilt agent-native handoff for a desktop computer-use agent."""

    DEFAULT_TITLE = "Computer Use Handoff"

    def default_sections(self) -> dict[str, str]:
        # Live-state structure for a GUI/desktop agent's session.
        return {
            "Desktop State": _section_guidance("Describe the visible desktop state", "focused app, active window, visible controls, cursor context, and screen region of interest", "how the receiver can orient before acting"),
            "Apps & Windows Open": _section_guidance("List relevant applications and windows", "app names, document titles, window order, modal dialogs, and background processes", "which windows matter and which can be ignored"),
            "Action Trail": _section_guidance("Summarize GUI actions already taken", "clicks, keystrokes, menu choices, dialog responses, copy or paste actions, and observed outcomes", "what actions are safe or unsafe to repeat"),
            "Files Touched": _section_guidance("Track local files affected by computer use", "paths, created files, edited files, saved state, temporary files, and unsaved changes", "which files need verification or cleanup"),
            "Blockers": _section_guidance("Document desktop or app blockers", "permission prompts, modal dialogs, missing apps, crashes, disabled controls, and unclear UI states", "what has been tried to resolve each blocker"),
            "Next Step": _section_guidance("Specify the next desktop action", "target app, control, gesture or shortcut, expected state change, and fallback", "how to proceed without losing work"),
            "Input State": _section_guidance("Capture active input context", "selected text, clipboard contents, cursor position, active field, and keyboard mode", "what could be overwritten accidentally"),
            "System Constraints": _section_guidance("Record machine-level constraints", "OS, permissions, display scaling, network state, installed tools, and resource limits", "constraints that affect future GUI actions"),
            "Recovery Notes": _section_guidance("Explain how to recover the session if interrupted", "saved checkpoints, reopen steps, undo options, backup paths, and restart risks", "how to avoid losing in-progress desktop work"),
        }


class MemoryHandoff(Handoff):
    """Prebuilt agent-native handoff for a memory-backed agent."""

    DEFAULT_TITLE = "Memory Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure separating working memory from durable facts worth persisting.
        return {
            "Working Memory": _section_guidance("Summarize the agent's active working memory", "current goal, recent context, temporary assumptions, active entities, and short-term priorities", "what can expire after this task"),
            "Long-Term Facts Learned": _section_guidance("Identify durable facts discovered during the run", "stable user preferences, project facts, decisions, relationships, and reusable knowledge", "why each fact is likely worth preserving"),
            "Updated/Stale Beliefs": _section_guidance("Track beliefs that changed or became outdated", "old belief, new belief, evidence, confidence, and downstream effects", "what memory should be corrected or invalidated"),
            "Open Questions": _section_guidance("List unresolved questions for future memory refinement", "unknowns, suspected facts, needed verification, source targets, and decision impact", "how future agents should resolve them"),
            "What to Persist": _section_guidance("Recommend memory writes explicitly", "candidate memory entries, scope, wording, priority, and retention rationale", "what should be stored versus left ephemeral"),
            "What Not to Persist": _section_guidance("Identify information that should stay out of long-term memory", "sensitive, temporary, low-confidence, irrelevant, or user-private details", "why persistence would be harmful or noisy"),
            "Source Evidence": _section_guidance("Attach evidence to memory candidates", "messages, files, tool outputs, timestamps, and confidence markers supporting each memory", "how a future agent can audit the memory"),
            "Memory Conflicts": _section_guidance("Surface conflicts between new and existing memory", "contradictory facts, ambiguity, competing interpretations, and proposed resolution", "what should be merged, superseded, or escalated"),
        }


class VerificationHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent self-verifying its output."""

    DEFAULT_TITLE = "Verification Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure separating verified claims from asserted-but-unchecked ones.
        return {
            "Claims Made": _section_guidance("List claims that need or received verification", "claim text, source in the output, importance, risk level, and dependency on other claims", "which claims are central versus incidental"),
            "Verified vs Unverified": _section_guidance("Separate checked claims from unchecked claims", "verification method, evidence, result, unverified items, and reason for not checking", "what can be relied on now"),
            "Failed Checks": _section_guidance("Document claims that failed verification", "failed claim, evidence against it, severity, correction needed, and affected outputs", "what must be fixed before finalizing"),
            "Confidence per Claim": _section_guidance("Assign confidence at claim level", "confidence rating, supporting evidence, uncertainty drivers, and sensitivity to missing data", "how confidence should affect downstream use"),
            "What Still Needs Checking": _section_guidance("Prioritize remaining verification work", "checks, sources, commands, owners, expected evidence, and order of operations", "what would most reduce risk"),
            "Verification Methods": _section_guidance("Record how verification was performed", "tests, source lookup, calculations, code review, tool commands, and manual inspection", "which methods are strong enough for the stakes"),
            "Corrections Applied": _section_guidance("Track corrections made during verification", "original issue, correction, evidence, files or text changed, and remaining caveats", "what still needs rechecking after correction"),
            "Residual Risk": _section_guidance("Summarize verification risk that remains", "unchecked areas, weak evidence, time limits, assumptions, and likely failure modes", "how the next agent should communicate uncertainty"),
        }


class ReasoningTraceHandoff(Handoff):
    """Prebuilt agent-native handoff for transferring a chain of reasoning."""

    DEFAULT_TITLE = "Reasoning Trace Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure capturing the reasoning chain, assumptions, and dead ends.
        return {
            "Goal": _section_guidance("State what the reasoning process is trying to achieve", "problem statement, desired output, constraints, and evaluation criteria", "how to judge whether reasoning is complete"),
            "Reasoning So Far": _section_guidance("Summarize the reasoning path without exposing unnecessary private deliberation", "high-level steps, evidence considered, decisions made, and current conclusion", "what matters for continuity and auditability"),
            "Key Inferences": _section_guidance("List the important inferences already drawn", "inference, supporting evidence, confidence, dependency, and practical implication", "which inferences future work should preserve"),
            "Assumptions Made": _section_guidance("Make active assumptions explicit", "assumption, source, confidence, risk, and how it affects the conclusion", "what should be verified or revised next"),
            "Dead Ends": _section_guidance("Record abandoned reasoning paths", "path explored, why it failed, evidence discovered, and lessons retained", "why the receiver should avoid re-entering the path"),
            "Current Direction": _section_guidance("Describe the next reasoning direction", "planned inference, evidence needed, expected outcome, and fallback if disproven", "how to continue the chain productively"),
            "Decision Points": _section_guidance("Highlight forks where reasoning could branch", "options, trade-offs, conditions, and recommendation for each fork", "which branch is currently preferred and why"),
            "Evidence Ledger": _section_guidance("Tie reasoning to evidence", "facts, sources, calculations, observations, and uncertainty for each key step", "how to audit the reasoning without replaying it"),
            "Output Implications": _section_guidance("Explain how reasoning affects the final deliverable", "conclusion impact, wording implications, risks, caveats, and next action", "what should change in the answer or implementation"),
        }


class GuardrailHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent that hit a guardrail or policy stop."""

    DEFAULT_TITLE = "Guardrail Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure for handing off a blocked action with safe alternatives.
        return {
            "Requested Action": _section_guidance("Describe the action that encountered a guardrail", "user request, intended operation, context, target system, and desired outcome", "what part of the request is permissible versus problematic"),
            "Policy Triggered": _section_guidance("Identify the guardrail or policy involved", "policy category, permission boundary, safety concern, or runtime restriction", "why the guardrail applies to this situation"),
            "What Was Blocked": _section_guidance("Specify exactly what the agent did not do", "blocked content, command, data access, transaction, or tool action with scope", "how much of the original task remains possible"),
            "Safe Alternatives": _section_guidance("Offer compliant ways to continue", "allowed substitutes, narrower actions, educational framing, redacted outputs, or user-confirmation paths", "how each alternative preserves useful progress"),
            "Needs Human Approval": _section_guidance("List actions requiring explicit human authorization", "approval item, approver, risk, required confirmation, and expected next step", "what authorization would and would not permit"),
            "Risk Rationale": _section_guidance("Explain the risk behind the guardrail", "potential harm, privacy issue, security exposure, irreversible action, or compliance concern", "why caution is appropriate"),
            "Allowed Progress": _section_guidance("Clarify work that can safely continue", "analysis, documentation, reversible checks, summaries, planning, and non-sensitive alternatives", "what the next agent should do while respecting the boundary"),
            "Escalation Record": _section_guidance("Preserve an audit trail for the guardrail event", "time, request context, decision made, alternatives offered, and user response if any", "how future reviewers can understand the stop"),
        }


class EvaluationHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent grading or evaluating against a rubric."""

    DEFAULT_TITLE = "Evaluation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Rubric-progress structure for transferring an evaluation in progress.
        return {
            "Rubric": _section_guidance("Describe the evaluation rubric being used", "criteria, scale, weights, pass thresholds, definitions, and examples", "how to apply the rubric consistently"),
            "Items Graded": _section_guidance("List items already evaluated", "item identifiers, status, score, evaluator, evidence reviewed, and completion notes", "which items are final versus provisional"),
            "Scores & Rationale": _section_guidance("Explain assigned scores", "score per criterion, rationale, supporting evidence, deductions, and confidence", "why another evaluator should agree or revisit the score"),
            "Uncertain/Disputed": _section_guidance("Capture ambiguous or contested evaluations", "item, disputed criterion, competing interpretations, missing evidence, and proposed resolution", "what would settle the dispute"),
            "Remaining to Grade": _section_guidance("Prioritize evaluation work still open", "ungraded items, order, required evidence, expected difficulty, and owner", "how to finish the evaluation efficiently"),
            "Calibration Notes": _section_guidance("Record rubric calibration decisions", "benchmark examples, edge cases, score adjustments, and consistency rules", "how future grading should match prior grading"),
            "Evidence Reviewed": _section_guidance("Track evidence used in the evaluation", "documents, outputs, logs, citations, screenshots, and source quality", "where to verify each score"),
            "Finalization Criteria": _section_guidance("Define what is required before results are final", "review steps, approval needs, tie-break rules, quality checks, and reporting format", "what blocks publication or downstream use"),
        }


__all__ = [
    "Handoff",
    "EngineeringHandoff",
    "ResearchHandoff",
    "MinimalHandoff",
    "TreeSearchHandoff",
    "DecompositionHandoff",
    "RefinementLoopHandoff",
    "ConstraintSatisfactionHandoff",
    "BacktrackingHandoff",
    "TradeoffHandoff",
    "GoalStackHandoff",
    "CoverageHandoff",
    "BudgetBoundedHandoff",
    "MigrationHandoff",
    "CodeReviewHandoff",
    "BugFixHandoff",
    "RefactorHandoff",
    "PerformanceOptimizationHandoff",
    "TestAuthoringHandoff",
    "APIDesignHandoff",
    "SchemaMigrationHandoff",
    "DependencyUpgradeHandoff",
    "IncidentResponseHandoff",
    "ArchitectureDecisionHandoff",
    "CodebaseOnboardingHandoff",
    "CICDPipelineHandoff",
    "IntegrationHandoff",
    "SecurityRemediationHandoff",
    "ReleaseHandoff",
    "PatientHandoff",
    "CareTransitionHandoff",
    "DiagnosticWorkupHandoff",
    "ContractReviewHandoff",
    "LegalResearchHandoff",
    "DueDiligenceHandoff",
    "TicketEscalationHandoff",
    "AccountHealthHandoff",
    "AlertTriageHandoff",
    "ThreatHuntHandoff",
    "InvestmentThesisHandoff",
    "DealHandoff",
    "CreditAnalysisHandoff",
    "ContextWindowHandoff",
    "ToolTrajectoryHandoff",
    "SubAgentDelegationHandoff",
    "OrchestrationHandoff",
    "HumanEscalationHandoff",
    "CheckpointResumeHandoff",
    "DeepResearchHandoff",
    "RetrievalHandoff",
    "BrowserSessionHandoff",
    "ComputerUseHandoff",
    "MemoryHandoff",
    "VerificationHandoff",
    "ReasoningTraceHandoff",
    "GuardrailHandoff",
    "EvaluationHandoff",
]
