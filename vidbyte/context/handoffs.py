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
]
