"""FILE: scripts/review_agents/planning.py

PURPOSE: Turns a review into the ordered list of agent tasks the workflow's matrix job runs.
ROLE IN CODEBASE: run.py's plan step calls PlanBuilder; every later job reads the resulting ReviewPlan, so the task list is fixed before any agent starts.
ARCHITECTURE NOTE: No model takes part in planning. A `review` agent runs once and owns every comment, and a `comment` agent runs once per comment; deciding which comments depend on each other is the resolver's own first step, inside its single run.
COMMON MODIFICATION PATTERNS: A new scope adds a Scope member in review_data.py and one branch in _units(); agent order always comes from the prompt file's number.
KNOWN EDGE CASES: A review with no comments plans no tasks; MAX_TASKS stops a runaway review from queueing more jobs than anyone can read the report of.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py.
"""

from __future__ import annotations

from review_agents.review_data import AgentSpec, AgentTask, Review, ReviewPlan, Scope

MAX_TASKS = 100


class PlanBuilder:
    """Expands every agent over the units its scope names, keeping agent order."""

    def build(self, review: Review, agents: tuple[AgentSpec, ...]) -> ReviewPlan:
        tasks: list[AgentTask] = []
        # Agents run in the order their file numbers give, whatever order they were loaded in.
        for agent in sorted(agents, key=lambda spec: spec.order):
            # Each scope is a different way of slicing the same comments into runs.
            tasks.extend(AgentTask(id=f"{agent.order:02d}-{agent.name}-{unit}", agent=agent.name, unit=unit, title=f"{agent.name} · {unit}: {label}"[:100], comment_ids=members) for unit, label, members in self._units(agent, review) if members)
        # A runaway review would otherwise queue more jobs than anyone could read the report of.
        if len(tasks) > MAX_TASKS:
            raise ValueError(f"{len(tasks)} tasks exceeds the limit of {MAX_TASKS}")
        return ReviewPlan(review=review, tasks=tuple(tasks))

    def _units(self, agent: AgentSpec, review: Review) -> list[tuple[str, str, tuple[int, ...]]]:
        if agent.scope is Scope.COMMENT:
            return [(f"c{number}", comment.location, (comment.id,)) for number, comment in enumerate(review.comments, 1)]
        return [("review", "whole review", tuple(comment.id for comment in review.comments))]
