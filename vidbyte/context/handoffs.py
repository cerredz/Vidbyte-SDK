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
            "Situation": "The patient's current status and the immediate reason for the handoff.",
            "Background": "Relevant history, admissions, and context leading to now.",
            "Assessment": "The current clinical assessment and working diagnosis.",
            "Recommendation": "What the receiving clinician should do next.",
            "Pending Tasks": "Orders, labs, or actions still outstanding.",
            "Watch-fors": "Warning signs or changes that require immediate attention.",
        }


class CareTransitionHandoff(Handoff):
    """Prebuilt handoff for transferring a patient's ongoing care."""

    DEFAULT_TITLE = "Care Transition Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on continuity of treatment across a care transition.
        return {
            "Diagnosis & Status": "Primary diagnoses and the patient's current condition.",
            "Medications": "Active medications, recent changes, and administration notes.",
            "Procedures Done/Pending": "Procedures completed and those still scheduled.",
            "Follow-up Plan": "The ongoing care plan after this transition.",
            "Red Flags": "Conditions or symptoms that should trigger escalation.",
        }


class DiagnosticWorkupHandoff(Handoff):
    """Prebuilt handoff for an in-progress diagnostic workup."""

    DEFAULT_TITLE = "Diagnostic Workup Handoff"

    def default_sections(self) -> dict[str, str]:
        # Differential-driven structure for transferring a diagnostic investigation.
        return {
            "Presentation": "The presenting symptoms and findings.",
            "Differential": "The differential diagnoses under consideration.",
            "Tests Ordered/Resulted": "Investigations ordered and any results returned.",
            "Leading Diagnosis": "The current most likely diagnosis and supporting evidence.",
            "Next Steps": "The next diagnostic or treatment actions.",
        }


class ContractReviewHandoff(Handoff):
    """Prebuilt handoff for reviewing a legal contract."""

    DEFAULT_TITLE = "Contract Review Handoff"

    def default_sections(self) -> dict[str, str]:
        # Recommendation-oriented structure for a contract review in progress.
        return {
            "Parties & Purpose": "Who the agreement is between and what it covers.",
            "Key Terms": "The material terms and obligations.",
            "Risk Flags": "Clauses that create legal or commercial risk.",
            "Redlines Proposed": "Changes proposed and their rationale.",
            "Open Negotiation Points": "Terms still under negotiation.",
            "Recommendation": "Whether to sign, revise, or escalate, and why.",
        }


class LegalResearchHandoff(Handoff):
    """Prebuilt handoff for a legal research question."""

    DEFAULT_TITLE = "Legal Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Authority-and-application structure for transferring legal research.
        return {
            "Issue": "The legal question being researched.",
            "Authorities Found": "Statutes, cases, and sources located.",
            "Holdings & Application": "What each authority holds and how it applies.",
            "Counterarguments": "Opposing positions and their strength.",
            "Confidence & Gaps": "How settled the answer is and what remains unresearched.",
        }


class DueDiligenceHandoff(Handoff):
    """Prebuilt handoff for a due-diligence review."""

    DEFAULT_TITLE = "Due Diligence Handoff"

    def default_sections(self) -> dict[str, str]:
        # Coverage-and-risk structure for handing off a diligence effort.
        return {
            "Scope": "What the diligence review covers.",
            "Findings by Category": "Material findings grouped by area.",
            "Material Risks": "Issues that could affect the transaction or decision.",
            "Documents Reviewed": "What was examined, for traceability.",
            "Outstanding Requests": "Information still needed from the counterparty.",
        }


class TicketEscalationHandoff(Handoff):
    """Prebuilt handoff for escalating a customer support ticket."""

    DEFAULT_TITLE = "Ticket Escalation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Escalation structure so a higher tier can continue without re-asking the customer.
        return {
            "Customer Goal": "What the customer is trying to accomplish.",
            "Actions Tried": "Troubleshooting already attempted.",
            "Current State": "Where the issue stands now.",
            "Reproduction": "How to reproduce the problem, if known.",
            "Why Escalated": "The reason this needs a higher tier or specialist.",
            "Suggested Next Step": "The recommended next action for the receiver.",
        }


class AccountHealthHandoff(Handoff):
    """Prebuilt handoff for transferring a customer account in success management."""

    DEFAULT_TITLE = "Account Health Handoff"

    def default_sections(self) -> dict[str, str]:
        # Relationship-and-risk structure for handing off account ownership.
        return {
            "Account Status": "The account's current standing and key facts.",
            "Usage & Risk Signals": "Engagement metrics and churn or risk indicators.",
            "Open Issues": "Unresolved problems or requests.",
            "Relationship Notes": "Stakeholders, sentiment, and history.",
            "Renewal/Expansion Posture": "The outlook for renewal or growth and next moves.",
        }


class AlertTriageHandoff(Handoff):
    """Prebuilt handoff for a security operations alert-triage shift."""

    DEFAULT_TITLE = "Alert Triage Handoff"

    def default_sections(self) -> dict[str, str]:
        # Queue-state structure for a SOC shift handoff.
        return {
            "Alerts in Queue": "Outstanding alerts awaiting triage.",
            "Triaged & Dispositioned": "Alerts already handled and their outcomes.",
            "Under Investigation": "Alerts actively being investigated and current findings.",
            "Suspected Scope": "The estimated blast radius or affected assets.",
            "Next Actions": "What the next analyst should pick up first.",
        }


class ThreatHuntHandoff(Handoff):
    """Prebuilt handoff for an in-progress threat hunt."""

    DEFAULT_TITLE = "Threat Hunt Handoff"

    def default_sections(self) -> dict[str, str]:
        # Hypothesis-elimination structure applied to threat hunting.
        return {
            "Hypothesis": "The threat hypothesis being investigated.",
            "Data Sources Queried": "Logs, telemetry, and tools examined.",
            "Findings": "Evidence gathered so far.",
            "Ruled Out": "Hypotheses or indicators eliminated, with reasoning.",
            "Open Leads": "Promising threads still to pursue.",
        }


class InvestmentThesisHandoff(Handoff):
    """Prebuilt handoff for an investment thesis under development."""

    DEFAULT_TITLE = "Investment Thesis Handoff"

    def default_sections(self) -> dict[str, str]:
        # Thesis-and-risk structure for transferring an investment analysis.
        return {
            "Thesis": "The core investment argument.",
            "Supporting Evidence": "Data and analysis backing the thesis.",
            "Key Risks": "What could invalidate the thesis.",
            "Valuation View": "The current valuation assessment.",
            "Catalysts": "Events expected to move the position.",
            "Open Diligence": "Analysis still outstanding.",
        }


class DealHandoff(Handoff):
    """Prebuilt handoff for an in-progress deal or transaction."""

    DEFAULT_TITLE = "Deal Handoff"

    def default_sections(self) -> dict[str, str]:
        # Workstream-status structure for handing off a live deal.
        return {
            "Deal Status": "Where the deal stands in its lifecycle.",
            "Workstreams": "The active workstreams and their owners.",
            "Open Items by Workstream": "Outstanding tasks per workstream.",
            "Key Risks": "Risks that could derail or reprice the deal.",
            "Next Milestones": "Upcoming deadlines and gating events.",
        }


class CreditAnalysisHandoff(Handoff):
    """Prebuilt handoff for a credit analysis."""

    DEFAULT_TITLE = "Credit Analysis Handoff"

    def default_sections(self) -> dict[str, str]:
        # Assessment-and-decision structure for transferring a credit review.
        return {
            "Borrower & Facility": "Who is being assessed and the proposed terms.",
            "Financial Assessment": "Key financial metrics and trends analyzed.",
            "Risk Factors": "Credit risks identified.",
            "Rating/Recommendation": "The proposed rating or credit decision and rationale.",
            "Open Questions": "Information or analysis still needed.",
        }


class ContextWindowHandoff(Handoff):
    """Prebuilt agent-native handoff for continuing across a context-window boundary."""

    DEFAULT_TITLE = "Context Window Handoff"

    def default_sections(self) -> dict[str, str]:
        # Compaction-aware structure: what survives the window versus what is dropped.
        return {
            "Task State": "What the agent is doing and how far along it is.",
            "Key Facts to Preserve": "Facts that must survive into the fresh context.",
            "Decisions Made": "Choices already committed that should not be revisited.",
            "Compacted/Dropped Context": "What was removed from the window and why it is safe to drop.",
            "Active Working Set": "The files, variables, or entities currently in play.",
            "Resume Instructions": "Exactly how to continue from here.",
        }


class ToolTrajectoryHandoff(Handoff):
    """Prebuilt agent-native handoff for a tool-using agent's call trace."""

    DEFAULT_TITLE = "Tool Trajectory Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure mirroring the tool-call lifecycle so tool work can resume.
        return {
            "Available Tools": "The tools the agent can call.",
            "Calls Made & Results": "Tool calls executed and what they returned.",
            "Failed Calls & Errors": "Calls that failed and the errors encountered.",
            "Current Tool State": "Any side effects or state established by prior calls.",
            "Next Tool Action": "The next tool call to make and why.",
        }


class SubAgentDelegationHandoff(Handoff):
    """Prebuilt agent-native handoff for a supervisor delegating to sub-agents."""

    DEFAULT_TITLE = "Sub-Agent Delegation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Delegation structure tracking spawned subagents and synthesis of their results.
        return {
            "Top Goal": "The overall objective being delegated.",
            "Subagents Spawned": "Which subagents were created and their assignments.",
            "Results Received": "What each subagent has returned so far.",
            "Pending Delegations": "Subtasks still waiting on a subagent.",
            "Synthesis State": "How subagent outputs are being combined.",
            "Next Delegation": "The next subtask to delegate.",
        }


class OrchestrationHandoff(Handoff):
    """Prebuilt agent-native handoff for multi-agent orchestration."""

    DEFAULT_TITLE = "Orchestration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Plan-and-assignment structure for handing off a multi-agent execution.
        return {
            "Plan": "The multi-agent plan or DAG being executed.",
            "Agent Assignments": "Which agent owns which part.",
            "Completed/In-Flight/Blocked": "Status of each part of the plan.",
            "Cross-Agent Conflicts": "Disagreements or contention between agents.",
            "Next Dispatch": "The next agent to invoke and with what input.",
        }


class HumanEscalationHandoff(Handoff):
    """Prebuilt agent-native handoff for escalating from an agent to a human."""

    DEFAULT_TITLE = "Human Escalation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure that turns a stuck agent into an actionable human decision.
        return {
            "What I Was Doing": "The task the agent was working on.",
            "Where I'm Stuck": "The exact point of failure or uncertainty.",
            "What I Tried": "Approaches already attempted.",
            "Specific Decision Needed": "The precise question the human must answer.",
            "Options & Recommendation": "The choices available and the agent's recommended one.",
        }


class CheckpointResumeHandoff(Handoff):
    """Prebuilt agent-native handoff for checkpointing a long-horizon run."""

    DEFAULT_TITLE = "Checkpoint Resume Handoff"

    def default_sections(self) -> dict[str, str]:
        # Checkpoint structure capturing the exact place and state to resume from.
        return {
            "Goal": "The long-running objective.",
            "Progress So Far": "What has been accomplished up to this checkpoint.",
            "Current Step": "The step in progress when the checkpoint was taken.",
            "Environment State": "External state the resume depends on (files, services, sessions).",
            "Blockers": "Anything currently preventing progress.",
            "Resume Point": "The exact place and action to continue from.",
        }


class DeepResearchHandoff(Handoff):
    """Prebuilt agent-native handoff for an agentic multi-hop research run."""

    DEFAULT_TITLE = "Deep Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Query-and-synthesis structure for transferring an autonomous research run.
        return {
            "Question": "The research question driving the investigation.",
            "Search Queries Run": "Queries already executed.",
            "Sources Gathered": "Sources collected and their relevance.",
            "Synthesis So Far": "The current synthesized understanding.",
            "Contradictions": "Conflicting evidence encountered.",
            "Confidence & Next Queries": "How sure the findings are and what to search next.",
        }


class RetrievalHandoff(Handoff):
    """Prebuilt agent-native handoff for a retrieval-augmented agent."""

    DEFAULT_TITLE = "Retrieval Handoff"

    def default_sections(self) -> dict[str, str]:
        # Retrieval structure capturing what was fetched and what coverage remains.
        return {
            "Query": "The retrieval query or information need.",
            "Chunks Retrieved": "The passages or documents retrieved.",
            "Relevance Assessment": "How relevant each retrieved item is.",
            "Coverage Gaps": "Aspects of the query not yet covered by retrieval.",
            "Re-query Plan": "How to refine retrieval next.",
        }


class BrowserSessionHandoff(Handoff):
    """Prebuilt agent-native handoff for a browser-automation agent (live-state shape)."""

    DEFAULT_TITLE = "Browser Session Handoff"

    def default_sections(self) -> dict[str, str]:
        # Live-state structure capturing where the browser is and how to resume.
        return {
            "Current Location": "The current URL and page state.",
            "Session & Auth State": "Login state, cookies, and tokens, and what expires.",
            "Action Trail": "The navigations and interactions performed, with selectors that worked.",
            "Extracted Data": "Data captured so far and where it lives.",
            "Blockers": "Broken selectors, captchas, or dynamic content encountered.",
            "Next Action": "The next browser action from this state.",
        }


class ComputerUseHandoff(Handoff):
    """Prebuilt agent-native handoff for a desktop computer-use agent."""

    DEFAULT_TITLE = "Computer Use Handoff"

    def default_sections(self) -> dict[str, str]:
        # Live-state structure for a GUI/desktop agent's session.
        return {
            "Desktop State": "The current screen and focused application.",
            "Apps & Windows Open": "Applications and windows currently active.",
            "Action Trail": "The clicks, keystrokes, and steps performed.",
            "Files Touched": "Files created, opened, or modified.",
            "Blockers": "Dialogs, permissions, or UI states blocking progress.",
            "Next Step": "The next desktop action to take.",
        }


class MemoryHandoff(Handoff):
    """Prebuilt agent-native handoff for a memory-backed agent."""

    DEFAULT_TITLE = "Memory Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure separating working memory from durable facts worth persisting.
        return {
            "Working Memory": "What the agent is actively holding in mind.",
            "Long-Term Facts Learned": "Durable facts worth persisting.",
            "Updated/Stale Beliefs": "Beliefs that changed or are now outdated.",
            "Open Questions": "Unresolved questions to revisit.",
            "What to Persist": "What should be written to long-term memory.",
        }


class VerificationHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent self-verifying its output."""

    DEFAULT_TITLE = "Verification Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure separating verified claims from asserted-but-unchecked ones.
        return {
            "Claims Made": "The assertions in the agent's output.",
            "Verified vs Unverified": "Which claims were checked and which were not.",
            "Failed Checks": "Claims that did not hold up, with evidence.",
            "Confidence per Claim": "How confident the agent is in each claim.",
            "What Still Needs Checking": "Verification work remaining.",
        }


class ReasoningTraceHandoff(Handoff):
    """Prebuilt agent-native handoff for transferring a chain of reasoning."""

    DEFAULT_TITLE = "Reasoning Trace Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure capturing the reasoning chain, assumptions, and dead ends.
        return {
            "Goal": "What the reasoning is trying to achieve.",
            "Reasoning So Far": "The chain of reasoning up to this point.",
            "Key Inferences": "The important conclusions drawn.",
            "Assumptions Made": "Assumptions the reasoning depends on.",
            "Dead Ends": "Lines of reasoning abandoned and why.",
            "Current Direction": "Where the reasoning is heading next.",
        }


class GuardrailHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent that hit a guardrail or policy stop."""

    DEFAULT_TITLE = "Guardrail Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure for handing off a blocked action with safe alternatives.
        return {
            "Requested Action": "The action the agent attempted.",
            "Policy Triggered": "The guardrail, permission, or policy that fired.",
            "What Was Blocked": "Precisely what was prevented.",
            "Safe Alternatives": "Permitted approaches that achieve a similar goal.",
            "Needs Human Approval": "Items that require human authorization to proceed.",
        }


class EvaluationHandoff(Handoff):
    """Prebuilt agent-native handoff for an agent grading or evaluating against a rubric."""

    DEFAULT_TITLE = "Evaluation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Rubric-progress structure for transferring an evaluation in progress.
        return {
            "Rubric": "The criteria being evaluated against.",
            "Items Graded": "What has been scored so far.",
            "Scores & Rationale": "The scores assigned and the reasoning.",
            "Uncertain/Disputed": "Items where the grade is unclear or contested.",
            "Remaining to Grade": "What still needs evaluation.",
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
