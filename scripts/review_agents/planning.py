"""FILE: scripts/review_agents/planning.py

PURPOSE: Turns a review into the ordered list of agent tasks the workflow's matrix job runs.
ROLE IN CODEBASE: run.py's plan step calls PlanBuilder; every later job reads the resulting ReviewPlan, so the task list is fixed before any agent starts.
ARCHITECTURE NOTE: No model takes part in planning. A `merge` agent runs once, first, and only when git reports conflicts with the base branch; a `review` agent runs once and owns every comment; a `comment` agent runs once per comment; deciding which comments depend on each other is the resolver's own first step, inside its single run.
COMMON MODIFICATION PATTERNS: A new scope adds a Scope member in review_data.py and one branch in _units(); agent order always comes from the prompt file's number.
KNOWN EDGE CASES: A round with no comments and no conflicts plans no tasks; a merge task owns no comments; MAX_TASKS stops a runaway review from queueing more jobs than anyone can read the report of.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py.
"""

from __future__ import annotations

from review_agents.review_data import AgentSpec, AgentTask, Review, ReviewPlan, Scope

MAX_TASKS = 100


class PlanBuilder:
    """Expands every agent over the units its scope names, keeping agent order."""

    def build(self, review: Review, agents: tuple[AgentSpec, ...], conflicts: tuple[str, ...]) -> ReviewPlan:
        tasks: list[AgentTask] = []
        # Agents run in the order their file numbers give, whatever order they were loaded in.
        for agent in sorted(agents, key=lambda spec: spec.order):
            # Each scope is a different way of slicing the same round into runs.
            tasks.extend(AgentTask(id=f"{agent.order:02d}-{agent.name}-{unit}", agent=agent.name, unit=unit, title=f"{agent.name} · {unit}: {label}"[:100], comment_ids=members, scope=agent.scope) for unit, label, members in self._units(agent, review, conflicts))
        # A runaway review would otherwise queue more jobs than anyone could read the report of.
        if len(tasks) > MAX_TASKS:
            raise ValueError(f"{len(tasks)} tasks exceeds the limit of {MAX_TASKS}")
        return ReviewPlan(review=review, tasks=tuple(tasks), conflicts=conflicts)

    def _units(self, agent: AgentSpec, review: Review, conflicts: tuple[str, ...]) -> list[tuple[str, str, tuple[int, ...]]]:
        if agent.scope is Scope.MERGE:
            return [("merge", f"{len(conflicts)} file(s) conflict with {review.base_ref}", ())] if conflicts else []
        if agent.scope is Scope.COMMENT:
            return [(f"c{number}", comment.location, (comment.id,)) for number, comment in enumerate(review.comments, 1)]
        return [("review", "whole review", tuple(comment.id for comment in review.comments))] if review.comments else []
