"""FILE: scripts/review_agents/report.py

PURPOSE: Renders the one pull-request comment that tells the reviewer what every review agent did.
ROLE IN CODEBASE: run.py's report step writes this comment's body, and the workflow's report job posts it with gh and fails the run when any task failed.
ARCHITECTURE NOTE: Every planned task appears, including tasks that never reported, so an agent that silently did not run shows up as a failure instead of disappearing from the summary. Only a round in which every task succeeded ends with github.py's ROUND_MARKER, so the next @claude review picks up again every comment of a round that failed.
COMMON MODIFICATION PATTERNS: A new TaskStatus or BiteVerdict needs its label in _STATUS or _BITE; keep the table one row per comment and one column per comment-handling agent; a merge task gets its own line above the table, because it owns no comments.
KNOWN EDGE CASES: Summaries and details are cut to SUMMARY_LIMIT and the whole body to BODY_LIMIT, under GitHub's comment size limit, and the marker is added after the cut so it always survives; pipes in comment text are escaped for the table.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py.
"""

from __future__ import annotations

from review_agents.github import ROUND_MARKER
from review_agents.prompting import Markdown
from review_agents.review_data import AgentTask, BiteVerdict, ReviewComment, ReviewPlan, Scope, TaskResult, TaskStatus

SUMMARY_LIMIT = 4000
BODY_LIMIT = 60000
NO_RESULT_DETAIL = "The job ended without a result. Open the workflow run for its log."
_STATUS = {
    TaskStatus.CHANGED: "✅ changed",
    TaskStatus.NO_CHANGE: "➖ no change",
    TaskStatus.BLOCKED: "⚠️ blocked",
    TaskStatus.FAILED: "❌ failed",
}
_BITE = {
    BiteVerdict.VERIFIED: "guard verified",
    BiteVerdict.INCONCLUSIVE: "guard not verified",
    BiteVerdict.NOT_CAUGHT: "guard rejected: it misses the original problem",
    BiteVerdict.ALWAYS_FAILS: "guard rejected: it fails on the fixed code",
    BiteVerdict.NOT_APPLICABLE: "",
}


class ReportWriter:
    """Builds the summary table and the per-task details from the plan and the results."""

    def render(self, plan: ReviewPlan, agent_names: tuple[str, ...], results: dict[str, TaskResult]) -> tuple[str, bool]:
        review = plan.review
        marker = "\n" + ROUND_MARKER.format(through=review.through) + "\n"
        # The headline: which review closed the round, on which commit, and how much it covered.
        lines = ["## Claude review agents", "", f"Review {review.review_id} on commit `{review.reviewed_sha[:12]}`: {len(review.comments)} comment(s) {self._window(plan)}."]
        if not plan.tasks:
            lines += ["", "There are no new comments for the agents to act on."]
            return "\n".join(lines) + "\n" + marker, True
        # The merge with the base branch, when one ran, comes first, as it did in the run.
        lines += [self._merge_line(plan, task, results.get(task.id)) for task in plan.tasks if task.scope is Scope.MERGE]
        # One row per comment and one column per comment-handling agent, in run order.
        if review.comments:
            lines += ["", "| Comment | " + " | ".join(agent_names) + " |"]
            lines.append("|---|" + "---|" * len(agent_names))
            for comment in review.comments:
                cells = [self._cell(plan, results, name, comment) for name in agent_names]
                lines.append(f"| {self._comment_cell(comment)} | " + " | ".join(cells) + " |")
        # Each task's own account, folded away so the table stays readable.
        lines += [self._details(task, results.get(task.id), review.repository) for task in plan.tasks]
        ok = all(task.id in results and results[task.id].status is not TaskStatus.FAILED for task in plan.tasks)
        # Only a clean round moves the start of the next one past these comments.
        body = ("\n".join(lines) + "\n")[:BODY_LIMIT]
        return (body + marker if ok else body), ok

    def _window(self, plan: ReviewPlan) -> str:
        review = plan.review
        return f"left since the round that ended {review.since}" if review.since else "left since the pull request opened"

    def _merge_line(self, plan: ReviewPlan, task: AgentTask, result: TaskResult | None) -> str:
        status = _STATUS[result.status] if result else "❌ did not report"
        commit = f" `{result.commit_sha[:7]}`" if result and result.commit_sha else ""
        return f"\nMerge of `{plan.review.base_ref}`, {len(plan.conflicts)} conflicted file(s): {status}{commit}"

    def _cell(self, plan: ReviewPlan, results: dict[str, TaskResult], agent: str, comment: ReviewComment) -> str:
        task = next((t for t in plan.tasks if t.agent == agent and comment.id in t.comment_ids), None)
        if task is None:
            return ""
        result = results.get(task.id)
        if result is None:
            return "❌ did not report"
        parts = [_STATUS[result.status]]
        if result.commit_sha:
            parts.append(f"`{result.commit_sha[:7]}`")
        if _BITE[result.bite]:
            parts.append(_BITE[result.bite])
        return " · ".join(parts)

    def _comment_cell(self, comment: ReviewComment) -> str:
        text = Markdown.first_line(comment.body, 60).replace("|", "\\|")
        where = f"[`{comment.location}`]({comment.url})" if comment.url else f"`{comment.location}`"
        return f"{where} {text}"

    def _details(self, task: AgentTask, result: TaskResult | None, repository: str) -> str:
        if result is None:
            return f"\n<details><summary>{task.title}: did not report</summary>\n\n{NO_RESULT_DETAIL}\n</details>"
        commit = f"\n\nCommit: https://github.com/{repository}/commit/{result.commit_sha}" if result.commit_sha else ""
        summary = result.summary.strip()[:SUMMARY_LIMIT] or "The agent gave no summary."
        detail = f"\n\n{result.detail.strip()[:SUMMARY_LIMIT]}" if result.detail.strip() else ""
        status = _STATUS[result.status]
        return f"\n<details><summary>{task.title}: {status}</summary>\n\n{summary}{detail}{commit}\n</details>"
