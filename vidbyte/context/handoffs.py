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


def _section_guidance(purpose: str, output: str, detail: str) -> str:
    # Build rich section guidance with explicit output expectations and bounded length.
    return f"{purpose} {output} {detail} Aim for up to 500 tokens, using concise paragraphs or bullets that are dense enough for a new agent to continue without asking for the same context again."


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
            "Scope Reviewed": _section_guidance("State exactly which files, commits, diffs, generated artifacts, and user flows were reviewed.", "Output the reviewed scope as a bounded inventory, including any important files or behaviors deliberately left out.", "Include enough detail for a follow-up reviewer to avoid re-reading areas you already covered and to focus on the unchecked surface."),
            "Review Method": _section_guidance("Explain how the review was performed, including static reading, local execution, tests, screenshots, or reasoning-only checks.", "Output the commands, tools, fixtures, and inspection passes used, plus anything that could not be run.", "Call out whether the review prioritized correctness, security, API compatibility, performance, UX, or maintainability."),
            "Blocking Issues": _section_guidance("List every issue that must be fixed before merge, ordered by severity and confidence.", "Output file paths, line references when available, observed behavior, expected behavior, and why the issue is blocking.", "If there are no blockers, say that explicitly and identify the highest-risk area that was still checked."),
            "Non-Blocking Suggestions": _section_guidance("Capture improvements that are useful but not required for merge.", "Output each suggestion with the affected area, expected benefit, and whether it should be addressed now or in a follow-up.", "Keep the distinction from blockers crisp so the next reviewer does not accidentally escalate optional polish."),
            "Approved Aspects": _section_guidance("Document the parts of the change that appear correct and do not need repeated scrutiny.", "Output concrete behaviors, patterns, interfaces, and tests that were examined and found acceptable.", "Explain the evidence briefly rather than offering generic approval language."),
            "Test & Verification Notes": _section_guidance("Summarize the validation performed during review and what each check proved.", "Output command results, manual checks, mocked scenarios, and any expected failures or environmental blockers.", "Separate tests that actually ran from tests that would be valuable but were not executed."),
            "Compatibility & API Impact": _section_guidance("Describe whether the change affects public imports, constructor contracts, serialized data, migrations, or documented workflows.", "Output compatibility observations and any downstream callers that may need updates.", "If the change is purely internal, state why the public surface is unchanged."),
            "Security & Data Handling": _section_guidance("Record security-sensitive observations such as auth boundaries, secret handling, unsafe execution, prompt injection, or user data exposure.", "Output the specific risks reviewed and whether the implementation mitigates or avoids them.", "If security was not materially relevant, say that and name the reason."),
            "Unresolved Threads": _section_guidance("Preserve any open questions, ambiguous reviewer requests, author follow-ups, or assumptions not fully resolved.", "Output each thread with the owner or next decision needed when that is known.", "Make clear which threads block merge and which are informational."),
            "Verdict": _section_guidance("Give the review outcome in a way another reviewer can act on immediately.", "Output approve, request changes, comment-only, or needs another review, followed by the decisive reasons.", "Tie the verdict directly to the blockers, verification status, and unresolved threads above."),
        }


class BugFixHandoff(Handoff):
    """Prebuilt handoff for fixing a defect."""

    DEFAULT_TITLE = "Bug Fix Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure that ties the symptom to the root cause, the fix, and regression coverage.
        return {
            "Symptom": _section_guidance("Describe the incorrect behavior exactly as users, tests, logs, or operators observed it.", "Output the visible failure, affected environment, frequency, and any relevant error messages or data examples.", "Distinguish confirmed symptoms from guesses so the next engineer does not chase unsupported leads."),
            "Impact & Priority": _section_guidance("Explain who or what is affected and how urgent the fix is.", "Output affected users, workflows, data integrity concerns, revenue or reliability impact, and any severity labels already assigned.", "Include enough prioritization context for a handoff recipient to decide whether to ship, escalate, or keep investigating."),
            "Reproduction": _section_guidance("Give the smallest reliable path that triggers the bug.", "Output setup requirements, input data, commands or UI steps, expected result, actual result, and whether reproduction is deterministic.", "If reproduction is partial or unavailable, describe the closest evidence and what would make it reproducible."),
            "Investigation Trail": _section_guidance("Record the debugging path that led to the root cause.", "Output hypotheses tested, traces inspected, files read, experiments run, and evidence that ruled out false leads.", "Include failed attempts only when they prevent a future engineer from repeating wasted work."),
            "Root Cause": _section_guidance("Identify the underlying defect and connect it directly to the symptom.", "Output the responsible code path, state transition, data assumption, dependency behavior, or race condition.", "Explain why the bug occurred now if timing, recent changes, or environment differences matter."),
            "Fix Applied": _section_guidance("Describe the code or configuration changes made to remove the root cause.", "Output changed files, key functions, new guards or invariants, and why this approach is preferable to alternatives considered.", "Keep implementation detail specific enough that a reviewer can verify the fix without reconstructing the whole investigation."),
            "Tests Added": _section_guidance("List the regression coverage added or updated for the bug.", "Output test names, scenarios, fixtures, assertions, and which part of the root cause each test protects.", "If no tests were added, state the reason and the most appropriate missing test."),
            "Verification Results": _section_guidance("Summarize every check that was run after the fix.", "Output exact commands, manual checks, expected failures, and the pass or fail result for each.", "Call out the strongest evidence that the symptom is fixed."),
            "Regression Risk": _section_guidance("Identify areas that might be affected by the fix even if the original bug is resolved.", "Output related modules, edge cases, backward-compatibility concerns, and monitoring signals to watch after deploy.", "Separate likely risks from low-probability concerns."),
            "Follow-up Work": _section_guidance("Capture cleanup, broader prevention, observability, or documentation work that remains after the immediate fix.", "Output concrete next tasks with owners or ordering when known.", "Mark anything required before release differently from longer-term hardening."),
        }


class RefactorHandoff(Handoff):
    """Prebuilt handoff for restructuring code without changing behavior."""

    DEFAULT_TITLE = "Refactor Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on proving behavior was preserved across the restructure.
        return {
            "Motivation": _section_guidance("Explain why the refactor was worth doing now.", "Output the maintainability, readability, duplication, layering, performance, or safety problem the refactor addresses.", "Tie the motivation to concrete code pain rather than broad style preference."),
            "Scope & Boundaries": _section_guidance("Define exactly what was restructured and what was intentionally left untouched.", "Output the modules, classes, functions, interfaces, and generated files inside and outside the refactor boundary.", "Call out any tempting adjacent cleanup that was deferred to keep review scope controlled."),
            "Old Structure": _section_guidance("Summarize the pre-refactor organization that a future engineer may still see in older commits or docs.", "Output the prior responsibilities, coupling, duplicated flows, or naming that made the change necessary.", "Keep this short but concrete enough to make the diff rationale understandable."),
            "New Structure": _section_guidance("Describe the resulting organization and responsibility split after the refactor.", "Output new ownership boundaries, renamed concepts, moved logic, and the intended way to extend the code now.", "Include import or call-flow changes that matter for future edits."),
            "Changes by Module": _section_guidance("Walk through the structural changes grouped by file or subsystem.", "Output what changed in each area and how it maps from the old structure to the new one.", "Avoid restating every line of the diff; focus on the conceptual moves a maintainer needs."),
            "Behavior-Preservation Evidence": _section_guidance("Show why runtime behavior should be unchanged.", "Output tests, parity checks, snapshots, manual comparisons, and any reasoning about public API compatibility.", "If equivalence is assumed rather than proven, state that explicitly and name the unverified behavior."),
            "Compatibility Notes": _section_guidance("Record any public import, method signature, serialization, config, or documentation compatibility implications.", "Output whether callers need migration work and which old paths still work.", "If the refactor is purely internal, explain the evidence that external behavior is unchanged."),
            "Risk Areas": _section_guidance("Identify the places where behavior could have subtly shifted despite refactor intent.", "Output risky control flow, shared state, error handling, timing, dependency injection, or data-shape areas.", "Prioritize risks that reviewers and testers should inspect first."),
            "Follow-up Cleanups": _section_guidance("List cleanup intentionally deferred beyond this refactor.", "Output each task with the reason it was deferred and whether it depends on this change landing.", "Separate optional polish from cleanup that should happen soon to avoid technical debt."),
            "Reviewer Notes": _section_guidance("Tell reviewers how to evaluate the refactor efficiently.", "Output suggested diff reading order, files that deserve close attention, and checks that best prove behavior preservation.", "Mention any noisy mechanical changes that can be skimmed safely."),
        }


class PerformanceOptimizationHandoff(Handoff):
    """Prebuilt handoff for profiling and optimization work."""

    DEFAULT_TITLE = "Performance Optimization Handoff"

    def default_sections(self) -> dict[str, str]:
        # Before/after measurement structure so gains and trade-offs are concrete.
        return {
            "Performance Goal": _section_guidance("State the target performance improvement and why it matters.", "Output the user-facing or system-facing goal, such as latency, throughput, memory, startup time, cost, or tail behavior.", "Include any explicit SLO, benchmark target, or acceptance threshold."),
            "Baseline Metrics": _section_guidance("Record the measured performance before optimization.", "Output exact metrics, sample sizes, hardware or environment, data sets, warmup behavior, and measurement commands.", "Make the baseline reproducible enough that another engineer can compare future runs fairly."),
            "Profiling Method": _section_guidance("Explain how bottlenecks were identified.", "Output profilers, traces, logs, benchmark harnesses, synthetic loads, or production observations used.", "Call out measurement limitations, noise, and whether results are local, staging, or production."),
            "Bottlenecks Identified": _section_guidance("Describe where time, memory, calls, locks, allocation, or bandwidth was actually spent.", "Output each bottleneck with evidence and its estimated contribution to the total problem.", "Avoid speculative bottlenecks unless clearly labeled as hypotheses."),
            "Optimizations Applied": _section_guidance("List each change made to address a measured bottleneck.", "Output the code paths changed, mechanism of improvement, and the bottleneck each optimization targets.", "Keep the mapping from measurement to change explicit."),
            "Measured Improvement": _section_guidance("Compare post-change performance to the baseline.", "Output before and after values, percentage or absolute improvement, variance, and whether the target was met.", "If results are mixed, explain which scenarios improved and which regressed."),
            "Correctness Safeguards": _section_guidance("Show that optimization did not change behavior incorrectly.", "Output tests, invariants, data comparisons, rollout checks, and validation of edge cases affected by the optimization.", "Mention any correctness areas that still need deeper verification."),
            "Trade-offs": _section_guidance("Describe costs introduced by the optimization.", "Output added complexity, memory use, cache invalidation concerns, readability impact, operational risk, or dependency changes.", "Explain why the trade-off is acceptable relative to the measured gain."),
            "Remaining Hotspots": _section_guidance("Identify bottlenecks not addressed by the current change.", "Output the remaining evidence, likely next optimizations, and why they were deferred.", "Prioritize by expected performance impact and implementation risk."),
            "Monitoring Plan": _section_guidance("Describe how performance should be watched after merge or deploy.", "Output metrics, dashboards, alerts, logs, or smoke checks that can catch regressions.", "Include thresholds or patterns that should trigger rollback or deeper investigation."),
        }


class TestAuthoringHandoff(Handoff):
    """Prebuilt handoff for writing tests or improving coverage."""

    DEFAULT_TITLE = "Test Authoring Handoff"

    def default_sections(self) -> dict[str, str]:
        # Coverage-oriented structure highlighting what is and is not yet tested.
        return {
            "Coverage Goal": _section_guidance("State the behavior, risk, or contract the testing effort set out to cover.", "Output the target modules, user flows, failure modes, regressions, or acceptance criteria.", "Explain why this coverage matters now and how it relates to recent changes or known risk."),
            "Test Strategy": _section_guidance("Describe the testing approach chosen and why it fits the behavior.", "Output the balance of unit, integration, end-to-end, property, snapshot, fixture, or manual tests.", "Mention mocks, fakes, real services, and boundaries where tests intentionally stop."),
            "Areas Covered": _section_guidance("List the components and behaviors now under test.", "Output concrete files, functions, scenarios, and assertions at a level useful for future maintainers.", "Make clear which behavior is covered by automated tests versus manual validation."),
            "Test Cases Added": _section_guidance("Enumerate the specific test cases written or changed.", "Output test names, setup, inputs, expected outputs, and the bug or contract each protects.", "Group related cases so the next engineer can find and extend them quickly."),
            "Fixtures & Test Data": _section_guidance("Document any new fixtures, sample data, factories, snapshots, or fake services.", "Output where they live, what assumptions they encode, and how they should be updated.", "Call out brittle fixture details that could cause false failures."),
            "Execution Results": _section_guidance("Record the actual verification run for the test work.", "Output exact commands, pass/fail results, expected failures, skipped tests, and environment details.", "Separate tests introduced by this work from broader suite checks."),
            "Gaps & Untested Paths": _section_guidance("Identify behavior still lacking meaningful coverage.", "Output untested edge cases, failure modes, concurrency paths, provider variants, or UI states.", "Explain whether each gap is acceptable, blocked, or should be handled immediately."),
            "Flaky/Skipped Tests": _section_guidance("Capture unreliable or intentionally skipped tests and the reason.", "Output the symptoms, skip markers, issue links if any, and what evidence is still missing.", "Avoid burying flaky behavior in generic notes because it can mask regressions."),
            "Maintenance Notes": _section_guidance("Explain how future contributors should maintain the tests.", "Output naming conventions, helper usage, fixture update rules, and pitfalls in extending the suite.", "Mention any expensive checks that should stay out of fast test paths."),
            "Next Tests": _section_guidance("Rank the most valuable tests to add next.", "Output concrete scenarios, expected assertions, and why each closes a meaningful risk.", "Order the list by risk reduction rather than ease of implementation."),
        }


class APIDesignHandoff(Handoff):
    """Prebuilt handoff for designing an endpoint or contract."""

    DEFAULT_TITLE = "API Design Handoff"

    def default_sections(self) -> dict[str, str]:
        # Contract-oriented structure covering schemas, versioning, and errors.
        return {
            "Purpose & Consumers": _section_guidance("Describe what the API is for and who will call it.", "Output primary consumers, use cases, non-goals, and the decisions the interface must support.", "Include any known client constraints that shape the contract."),
            "Endpoints/Contracts": _section_guidance("Define the operations exposed by the API or interface.", "Output endpoint names, methods, function signatures, events, or protocol messages and their semantics.", "Clarify ordering, idempotency, side effects, and ownership boundaries where relevant."),
            "Request/Response Schemas": _section_guidance("Specify the input and output shapes in enough detail to implement clients and servers.", "Output required fields, optional fields, defaults, constraints, examples, and nested objects.", "Call out ambiguous types, nullability, pagination, streaming, or binary payload concerns."),
            "Authentication & Authorization": _section_guidance("Record how callers prove identity and what they are allowed to do.", "Output auth mechanisms, scopes, roles, tenancy boundaries, and security-sensitive assumptions.", "If auth is out of scope, state why and what layer owns it."),
            "State & Side Effects": _section_guidance("Explain what persistent state changes, external calls, or asynchronous work the API triggers.", "Output state transitions, eventual consistency behavior, retries, deduplication, and cleanup responsibilities.", "Make hidden side effects explicit so consumers do not misuse the contract."),
            "Versioning & Compatibility": _section_guidance("Describe how the API can evolve without breaking consumers.", "Output version strategy, backward-compatible changes, deprecation paths, and fields or behaviors that must stay stable.", "Include migration expectations for existing clients if the API replaces something."),
            "Error Model": _section_guidance("Define how failures are represented and how consumers should react.", "Output status codes, exception types, error payloads, retryability, validation errors, and partial-success behavior.", "Distinguish user-correctable errors from server or integration failures."),
            "Examples & Edge Cases": _section_guidance("Provide representative examples and unusual cases that shape the design.", "Output sample requests and responses, boundary values, malformed inputs, and concurrency or race scenarios.", "Use examples to disambiguate the contract rather than repeating the schema."),
            "Implementation Notes": _section_guidance("Capture technical guidance for implementing the contract consistently.", "Output modules to touch, helper APIs to reuse, serialization concerns, and observability requirements.", "Keep this implementation-focused but avoid dictating irrelevant internal details."),
            "Open Design Questions": _section_guidance("List unresolved interface decisions that still need input.", "Output each question with available options, trade-offs, and the decision owner if known.", "Separate blocking questions from questions that can be resolved after an initial version ships."),
        }


class SchemaMigrationHandoff(Handoff):
    """Prebuilt handoff for a database schema change."""

    DEFAULT_TITLE = "Schema Migration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Migration structure emphasizing compatibility and data integrity.
        return {
            "Schema Change": _section_guidance("Describe the data-model change being made.", "Output tables, collections, fields, indexes, constraints, defaults, and deleted or renamed structures.", "Explain the user or system behavior that requires the schema change."),
            "Current Data Shape": _section_guidance("Summarize the existing production or source data shape before migration.", "Output known row counts, null distributions, legacy values, data quality issues, and important variants.", "Include enough context to judge migration cost and data-integrity risk."),
            "Target Data Shape": _section_guidance("Define the desired post-migration data shape.", "Output final schema expectations, invariants, ownership rules, and how new writes should behave.", "Make any transitional fields or compatibility columns explicit."),
            "Migration Steps": _section_guidance("List the ordered operations required to apply the change safely.", "Output DDL, data transforms, deploy sequencing, feature flags, background jobs, and operational commands.", "Include dependencies between steps so the next operator can resume midstream."),
            "Backfill Plan": _section_guidance("Explain how existing records will be transformed or populated.", "Output selection criteria, batching strategy, idempotency, retry behavior, and progress tracking.", "Call out records that need manual handling or can be skipped."),
            "Forward/Backward Compatibility": _section_guidance("Describe how old and new code coexist during rollout.", "Output read/write compatibility, dual-write or read-fallback behavior, deployment ordering, and safe rollback windows.", "Identify the point where backward compatibility is intentionally dropped."),
            "Data-Integrity Checks": _section_guidance("Define validations confirming the data is correct after migration.", "Output queries, counts, checksums, invariants, sample inspections, and acceptable thresholds.", "Say when checks should run and who should act on failures."),
            "Operational Risks": _section_guidance("Identify risks related to locks, runtime, load, replication, data loss, or operator error.", "Output risk triggers, mitigations, monitoring, and any maintenance-window requirements.", "Prioritize risks that can interrupt production traffic or corrupt data."),
            "Rollback Plan": _section_guidance("Explain how to revert safely if the migration fails.", "Output reversible steps, backup requirements, restore commands, data-loss caveats, and decision points.", "State clearly if any step is irreversible and what compensating action exists."),
            "Post-Migration Cleanup": _section_guidance("List cleanup needed after the migration is verified.", "Output fields, flags, compatibility code, jobs, dashboards, or docs to remove or update.", "Separate cleanup that can happen immediately from cleanup that must wait for adoption or retention windows."),
        }


class DependencyUpgradeHandoff(Handoff):
    """Prebuilt handoff for a library or framework version bump."""

    DEFAULT_TITLE = "Dependency Upgrade Handoff"

    def default_sections(self) -> dict[str, str]:
        # Upgrade structure centered on breaking changes and compatibility verification.
        return {
            "Target Versions": _section_guidance("State which dependencies are moving from which versions to which targets.", "Output package names, old versions, new versions, lockfile changes, transitive dependencies, and platform constraints.", "Include whether the upgrade is security-driven, compatibility-driven, or feature-driven."),
            "Upgrade Motivation": _section_guidance("Explain why the dependency upgrade is needed now.", "Output CVEs, deprecations, provider requirements, bug fixes, ecosystem constraints, or feature needs.", "Tie the motivation to concrete risk or value rather than generic freshness."),
            "Breaking Changes": _section_guidance("Summarize upstream API or behavior changes that affect this codebase.", "Output removed APIs, changed defaults, migration-guide requirements, runtime behavior shifts, and known incompatibilities.", "Separate confirmed impacts from upstream changes that were reviewed but do not apply."),
            "Code Adjustments Made": _section_guidance("Describe changes applied to accommodate the upgrade.", "Output modified files, replaced APIs, config updates, compatibility shims, and changed tests.", "Explain any non-obvious adaptation choices so future upgrades can follow the pattern."),
            "Config & Build Changes": _section_guidance("Record changes to build tooling, packaging, type checking, CI, or runtime configuration.", "Output lockfile updates, environment requirements, compiler or interpreter constraints, and changed scripts.", "Call out anything developers need to update locally."),
            "Compatibility Verification": _section_guidance("Describe how the upgraded dependency was validated.", "Output commands run, test suites, type checks, manual smoke tests, integration checks, and runtime environments.", "Mention whether verification covered the dependency's most important behavior in this SDK."),
            "Runtime Behavior Changes": _section_guidance("Capture behavior that may change even if tests pass.", "Output changed error messages, timing, serialization, defaults, warnings, retries, or provider responses.", "State how callers should adapt if the change is visible."),
            "Remaining Deprecations": _section_guidance("List deprecated usages still present after the upgrade.", "Output locations, warnings, upstream deadlines, and the work required to remove them.", "Distinguish harmless warnings from future-breaking issues."),
            "Rollback": _section_guidance("Explain how to return to the previous dependency state if needed.", "Output package pins, lockfile restoration, config reversions, and compatibility caveats.", "Include any data or artifact changes that make rollback harder."),
            "Follow-up Monitoring": _section_guidance("Describe what to watch after merge or release.", "Output logs, warnings, CI failures, user reports, performance metrics, or provider errors that could reveal upgrade regressions.", "Identify the timeframe where latent dependency issues are most likely to appear."),
        }


class IncidentResponseHandoff(Handoff):
    """Prebuilt handoff for an on-call incident or outage."""

    DEFAULT_TITLE = "Incident Response Handoff"

    def default_sections(self) -> dict[str, str]:
        # Timeline-oriented structure for handing off an active incident.
        return {
            "Impact & Severity": _section_guidance("Describe what is affected, who is affected, and how severe the incident is.", "Output affected services, users, regions, data, SLIs, error rates, customer symptoms, and severity classification.", "Make clear what is confirmed versus estimated."),
            "Detection & Alerts": _section_guidance("Explain how the incident was detected.", "Output alerts, dashboards, customer reports, logs, traces, or manual observations that surfaced the problem.", "Include alert names and thresholds when they matter for future tuning."),
            "Timeline": _section_guidance("Record key events from detection to the current moment in chronological order.", "Output timestamps, actions taken, decisions made, mitigation attempts, escalations, and state changes.", "Use enough detail that an incoming responder can reconstruct what happened without reading the full incident channel."),
            "Current Mitigation": _section_guidance("Describe what is currently limiting impact.", "Output deployed fixes, feature flags, rollbacks, traffic shifts, manual workarounds, or customer guidance in effect.", "State whether the mitigation is temporary, partial, or fully stabilizing."),
            "Root-Cause Status": _section_guidance("Summarize the current understanding of why the incident happened.", "Output confirmed root cause, leading hypotheses, supporting evidence, and evidence that ruled out alternatives.", "Label the status as confirmed, suspected, or unknown."),
            "Systems & Owners": _section_guidance("Identify the systems, teams, vendors, and on-call owners involved.", "Output service boundaries, escalation contacts, handoff recipients, and any external dependencies.", "Include ownership uncertainty if it is slowing response."),
            "Action Items": _section_guidance("List outstanding tasks to fully resolve or stabilize the incident.", "Output each action with owner, status, priority, dependencies, and expected effect.", "Separate immediate incident response from post-incident hardening."),
            "Comms Status": _section_guidance("Record what has been communicated and what still needs communication.", "Output internal updates, customer-facing messages, status page changes, support guidance, and next update cadence.", "Keep facts and speculation separate to avoid inconsistent messaging."),
            "Verification & Recovery": _section_guidance("Define how responders will know the incident is resolved.", "Output recovery metrics, smoke tests, customer confirmation, backlog drain checks, and monitoring windows.", "State what must remain stable before closing the incident."),
            "Post-Incident Follow-up": _section_guidance("Capture follow-up work for prevention, observability, documentation, or process.", "Output concrete remediation items, owners when known, and whether a postmortem is required.", "Do not let long-term work obscure the immediate recovery state."),
        }


class ArchitectureDecisionHandoff(Handoff):
    """Prebuilt handoff for a system design or architecture decision."""

    DEFAULT_TITLE = "Architecture Decision Handoff"

    def default_sections(self) -> dict[str, str]:
        # ADR-style structure recording the decision and its consequences.
        return {
            "Problem & Context": _section_guidance("Describe the architectural decision to be made and the forces shaping it.", "Output current constraints, goals, scale assumptions, ownership boundaries, and why the decision matters now.", "Include enough system context for someone outside the discussion to evaluate the trade-offs."),
            "Requirements & Constraints": _section_guidance("List the non-negotiable requirements and important preferences.", "Output functional needs, reliability targets, security rules, operational constraints, migration limits, and developer-experience concerns.", "Mark which constraints are hard requirements versus weighted preferences."),
            "Options Considered": _section_guidance("Summarize the viable approaches that were evaluated.", "Output each option with a short design sketch, dependencies, benefits, costs, and reasons it remained viable or was rejected.", "Avoid strawman options unless they were seriously considered by the team."),
            "Evaluation Evidence": _section_guidance("Record the evidence used to compare options.", "Output prototypes, benchmarks, prior incidents, production data, team experience, external references, or cost estimates.", "Label evidence quality so the next architect knows where confidence is weak."),
            "Decision & Rationale": _section_guidance("State the chosen approach and why it was selected.", "Output the decision in direct language, then tie it to requirements, constraints, and evidence.", "Make the rationale strong enough that future readers understand why alternatives lost."),
            "Consequences & Trade-offs": _section_guidance("Explain what the decision enables and what it costs.", "Output operational impact, complexity, performance, security, maintainability, staffing, and future-option consequences.", "Be explicit about negative consequences the team accepts."),
            "Implementation Plan": _section_guidance("Describe how the decision should be executed.", "Output phases, code areas, dependencies, migration steps, validation points, and owners if known.", "Include sequencing constraints that affect rollout safety."),
            "Open Risks": _section_guidance("Identify uncertainties or risks the decision still carries.", "Output risk likelihood, impact, mitigations, and signals that would show the decision needs revisiting.", "Do not hide unresolved concerns behind the final decision."),
            "Review & Reversal Criteria": _section_guidance("Define when the decision should be reviewed or reversed.", "Output metrics, dates, adoption thresholds, failure triggers, and alternatives to revisit.", "This should help future teams avoid treating the decision as permanent when assumptions change."),
            "Next Steps": _section_guidance("List concrete actions needed to act on the decision.", "Output immediate implementation tasks, communication needs, documentation updates, and validation work.", "Order the steps so another agent can continue without re-planning from scratch."),
        }


class CodebaseOnboardingHandoff(Handoff):
    """Prebuilt handoff for understanding an unfamiliar codebase."""

    DEFAULT_TITLE = "Codebase Onboarding Handoff"

    def default_sections(self) -> dict[str, str]:
        # Map-oriented structure for transferring a mental model of a codebase.
        return {
            "Goal": _section_guidance("State what understanding the codebase exploration aimed to build.", "Output the task, feature area, question, or onboarding objective that drove the reading.", "This should help the next reader decide whether the map is comprehensive enough for their purpose."),
            "Repository Layout": _section_guidance("Describe the top-level project structure and where important categories of code live.", "Output directories, package boundaries, generated assets, docs, tests, scripts, and build or deployment files.", "Call out layout surprises that differ from common conventions."),
            "System Map": _section_guidance("Explain the high-level architecture and major modules.", "Output the main subsystems, their responsibilities, and how they communicate.", "Keep the map conceptual but grounded in real file paths and class or function names."),
            "Key Components & Responsibilities": _section_guidance("Detail the most important components discovered during onboarding.", "Output each component's role, primary APIs, state ownership, dependencies, and extension points.", "Include only components relevant enough that a future engineer would likely edit or depend on them."),
            "Entry Points & Data Flow": _section_guidance("Describe where execution starts and how data moves through the system.", "Output CLI, web, worker, SDK, test, or scheduled entry points and the call/data path from input to output.", "Mention synchronous versus asynchronous boundaries when they matter."),
            "Configuration & Environment": _section_guidance("Record configuration files, environment variables, external services, and local setup assumptions.", "Output where config is read, defaults, required secrets, test doubles, and environment-specific behavior.", "Flag anything that can make local behavior differ from CI or production."),
            "Conventions & Gotchas": _section_guidance("Capture local patterns, idioms, naming rules, and traps specific to this codebase.", "Output conventions that future edits should follow and pitfalls that caused confusion during exploration.", "Prefer concrete examples over broad advice."),
            "Testing & Verification Map": _section_guidance("Explain how the codebase is tested and verified.", "Output test directories, frameworks, important fixtures, fast versus slow checks, and common commands.", "Mention broken or flaky checks if they affect confidence."),
            "Useful Files & Commands": _section_guidance("List the files and commands most useful for continuing work.", "Output paths, scripts, search queries, setup commands, and docs that saved time.", "Keep this curated so it remains actionable rather than becoming a full file index."),
            "Open Questions": _section_guidance("List parts of the codebase still not understood.", "Output each question with where to look next and why it matters.", "Mark questions that block current work differently from questions that are just future learning."),
        }


class CICDPipelineHandoff(Handoff):
    """Prebuilt handoff for build, test, or deploy pipeline work."""

    DEFAULT_TITLE = "CI/CD Pipeline Handoff"

    def default_sections(self) -> dict[str, str]:
        # Stage-status structure for handing off pipeline configuration work.
        return {
            "Pipeline Goal": _section_guidance("State what the pipeline is meant to build, test, package, publish, or deploy.", "Output the target branches, artifacts, environments, quality gates, and user or release workflow it supports.", "Include whether the work is creating a pipeline, fixing one, or improving an existing path."),
            "Current Pipeline Topology": _section_guidance("Describe the structure of the pipeline as it exists now.", "Output jobs, stages, dependencies, triggers, runners, matrices, caches, artifacts, and approval gates.", "Use the actual CI/CD platform terminology and file paths where possible."),
            "Stages & Status": _section_guidance("Record each important stage and whether it is passing, failing, flaky, skipped, or incomplete.", "Output status, last observed evidence, failure symptoms, and dependencies for every stage relevant to the handoff.", "Make the current operational state obvious to someone resuming the work."),
            "Build/Deploy Config": _section_guidance("Explain where the pipeline configuration lives and how it is structured.", "Output workflow files, scripts, reusable actions, deploy manifests, package settings, and generated config.", "Highlight config that is shared across jobs or environments because changes there have broader impact."),
            "Secrets & Environments": _section_guidance("Document required credentials, environment variables, permissions, and target environments.", "Output secret names, scopes, environment names, protected resources, and any missing or rotated credentials.", "Do not include secret values; describe how they are referenced and validated."),
            "Artifacts & Outputs": _section_guidance("Describe what the pipeline produces and where outputs go.", "Output build artifacts, containers, reports, coverage, release notes, deployments, notifications, and retention rules.", "Mention consumers of these outputs so breaking changes are visible."),
            "Failing/Flaky Stages": _section_guidance("Detail stages that are broken or unreliable.", "Output exact errors, logs, reproduction conditions, suspected causes, and workarounds.", "Separate deterministic failures from intermittent ones so the next engineer can triage correctly."),
            "Changes Applied": _section_guidance("Summarize pipeline modifications already made.", "Output changed files, job or script updates, dependency changes, and why each change was made.", "Include whether each change has been validated in CI or only reasoned about locally."),
            "Validation & Rollback": _section_guidance("Explain how the pipeline changes were or should be verified and reversed.", "Output test runs, dry runs, manual approvals, deployment smoke checks, and rollback steps.", "State any risk of breaking release or deploy paths."),
            "Next Steps": _section_guidance("List what to fix, add, or verify next.", "Output ordered tasks with blockers, required access, and expected confirmation signals.", "Prioritize steps that restore trust in the pipeline before optional enhancements."),
        }


class IntegrationHandoff(Handoff):
    """Prebuilt handoff for a third-party API or service integration."""

    DEFAULT_TITLE = "Integration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Contract-and-failure-mode structure for an external integration.
        return {
            "Integration Goal": _section_guidance("State what external system is being integrated and why.", "Output the business or product capability, target users, provider or service name, and success criteria.", "Clarify whether the handoff concerns design, implementation, debugging, or rollout."),
            "External Contract": _section_guidance("Describe the third-party API, protocol, webhook, SDK, or data feed and the behavior this code depends on.", "Output endpoints, methods, payloads, event shapes, rate limits, ordering guarantees, and provider-specific quirks.", "Include links or version references when they were part of the investigation."),
            "Auth & Credentials": _section_guidance("Explain how authentication works and where credentials are configured.", "Output auth flow, token scopes, secret names, rotation concerns, tenancy boundaries, and local or CI setup needs.", "Never include secret values; focus on safe operational knowledge."),
            "Implemented Surface": _section_guidance("List which parts of the integration are built and working.", "Output supported operations, files changed, public interfaces, provider adapters, parsing logic, and successful scenarios.", "Separate production-ready surface from prototypes or partial support."),
            "Data Mapping": _section_guidance("Explain how external data maps into internal models and back.", "Output field mappings, transformations, default handling, validation, serialization, and lossy conversions.", "Call out ambiguous or provider-specific fields that may require future changes."),
            "Error Handling & Retries": _section_guidance("Describe how failures are detected, represented, retried, or surfaced to callers.", "Output timeout handling, rate-limit behavior, provider errors, retry policy, fallback behavior, and observability.", "Mention failure modes that are currently unhandled."),
            "Edge Cases & Failure Modes": _section_guidance("Record unusual integration behavior under errors, limits, malformed data, duplicate events, and partial outages.", "Output concrete cases already observed or reasoned through and how the code should respond.", "Prioritize cases likely to occur in production."),
            "Local & Test Setup": _section_guidance("Document how to exercise the integration locally or in tests.", "Output fake services, fixtures, sandbox accounts, required env vars, commands, and manual setup steps.", "Include limitations of mocks versus real provider behavior."),
            "Verification Status": _section_guidance("Summarize what has actually been verified.", "Output tests run, sandbox calls, mocked scenarios, contract checks, and any expected failures.", "Make clear which behavior still depends on live provider validation."),
            "Untested Paths": _section_guidance("List integration behavior not yet verified.", "Output missing scenarios, blocked provider access, edge cases, and the most useful next checks.", "Rank gaps by production risk so the next engineer can focus quickly."),
        }


class SecurityRemediationHandoff(Handoff):
    """Prebuilt handoff for fixing security vulnerabilities."""

    DEFAULT_TITLE = "Security Remediation Handoff"

    def default_sections(self) -> dict[str, str]:
        # Remediation structure pairing each vulnerability with its fix and residual risk.
        return {
            "Vulnerabilities": _section_guidance("Describe the security issues being addressed.", "Output identifiers, affected components, vulnerable flows, data exposed, and whether findings are confirmed or suspected.", "Avoid including exploit instructions beyond what is necessary for safe remediation."),
            "Severity & Exploitability": _section_guidance("Explain how serious each issue is and how readily it can be exploited.", "Output impact, prerequisites, attacker capabilities, affected users or tenants, CVSS or internal severity, and evidence.", "Separate theoretical exposure from demonstrated exploitability."),
            "Threat Model": _section_guidance("Record the attacker model and trust boundaries relevant to the remediation.", "Output entry points, privileged operations, authentication assumptions, data boundaries, and external systems involved.", "This should help the next engineer avoid fixing only a symptom."),
            "Affected Surface": _section_guidance("List the code, configuration, dependencies, infrastructure, and workflows touched by the vulnerability.", "Output file paths, public APIs, secrets, permissions, data stores, and deployment environments.", "Call out any surface not fully inspected."),
            "Fixes Applied": _section_guidance("Describe the remediations made for each vulnerability.", "Output changed files, validation, escaping, permissions, dependency upgrades, configuration changes, and defense-in-depth additions.", "Map every fix back to the vulnerability or threat it addresses."),
            "Verification": _section_guidance("Explain how each fix was confirmed effective.", "Output tests, manual reproduction attempts, scanners, code review checks, configuration audits, and negative cases.", "State what proof is strongest and what remains unverified."),
            "Regression & Abuse Tests": _section_guidance("Document tests that prevent the issue from returning or being bypassed.", "Output test names, malicious inputs, authorization scenarios, dependency checks, and expected denials.", "If tests could not be added, give the reason and the best future test."),
            "Operational Rollout": _section_guidance("Describe how the remediation should be deployed safely.", "Output rollout order, secret rotation, cache invalidation, customer impact, monitoring, and rollback considerations.", "Include emergency actions if the vulnerability is actively exploitable."),
            "Residual Risk": _section_guidance("Identify risk that remains after the fixes.", "Output accepted risk, compensating controls, assumptions, and areas needing deeper audit.", "Be explicit about why residual risk is acceptable or what decision is still needed."),
            "Remaining Items": _section_guidance("List vulnerabilities or hardening tasks not yet remediated.", "Output concrete follow-ups, owners or priority when known, and dependencies.", "Separate must-fix security work from broader hardening."),
        }


class ReleaseHandoff(Handoff):
    """Prebuilt handoff for cutting a release or deployment."""

    DEFAULT_TITLE = "Release Handoff"

    def default_sections(self) -> dict[str, str]:
        # Checklist-oriented structure for handing off a release in progress.
        return {
            "Release Scope": _section_guidance("State what is included in the release and what is explicitly excluded.", "Output features, fixes, migrations, dependencies, docs, flags, and linked issues or PRs.", "Make scope boundaries clear enough for release notes and go/no-go review."),
            "Release Readiness": _section_guidance("Summarize whether the release is ready to ship.", "Output blocker status, approvals, open risks, unresolved incidents, dependency status, and decision owner.", "Use direct language so the next operator knows whether to proceed or pause."),
            "Changelog": _section_guidance("Describe user-facing and developer-facing changes since the last release.", "Output grouped changes, breaking changes, migrations, deprecations, and noteworthy internal changes.", "Keep wording accurate enough to become release-note source material."),
            "Versioning & Artifacts": _section_guidance("Document version numbers, tags, builds, packages, images, or other release artifacts.", "Output artifact locations, checksums if relevant, build provenance, branch or commit SHAs, and publication targets.", "Call out any artifact that still needs to be produced or promoted."),
            "Pre-Deploy Checklist": _section_guidance("List conditions that must hold before deployment begins.", "Output tests, approvals, migrations, feature flag states, monitoring readiness, capacity checks, and communication prep.", "Mark each item done, pending, or blocked where possible."),
            "Deploy Steps": _section_guidance("Provide the ordered procedure to ship the release.", "Output commands, UI steps, environment order, approvals, timing, and expected intermediate states.", "Include enough operational detail for a qualified teammate to run the release without guessing."),
            "Verification & Smoke": _section_guidance("Describe checks confirming the release is healthy after deploy.", "Output automated checks, manual smoke paths, dashboards, logs, customer-visible flows, and expected results.", "Separate immediate smoke checks from longer monitoring windows."),
            "Communications": _section_guidance("Record release communication needs and status.", "Output internal announcements, customer messages, status page updates, support notes, and documentation updates.", "State what has already been sent and what remains pending."),
            "Rollback Plan": _section_guidance("Explain how to revert or mitigate if problems appear.", "Output rollback commands, artifact versions, feature flags, data migration constraints, and decision thresholds.", "Be explicit about irreversible steps or compensating actions."),
            "Post-Release Follow-up": _section_guidance("List follow-up work after the release ships.", "Output monitoring tasks, cleanup, docs, retrospective items, issue triage, and ownership.", "Distinguish release-critical follow-up from normal backlog work."),
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
