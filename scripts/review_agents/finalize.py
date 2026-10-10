"""FILE: scripts/review_agents/finalize.py

PURPOSE: Turns what one review agent left in the working tree into one pushed commit, or into nothing.
ROLE IN CODEBASE: run.py's finalize step calls TaskFinalizer after every agent run. Agents only edit files; this step decides whether their edit reaches the pull request: the full gate has to pass, and an agent that adds a guard has to prove the guard would have caught the comment it was written for.
ARCHITECTURE NOTE: The gate is `python scripts/run_ci.py`, the SDK's canonical local gate. Commits are written by the workflow with review trailers that later steps read, never by the agent, and pushes replay once on top of anything pushed meanwhile.
COMMON MODIFICATION PATTERNS: Add a refusal as one early return in finalize() with its reason; keep RESTORED_PATHS in step with the paths claude-code-action restores from the base branch. merging.py's MergeFinalizer reuses these helpers for the merge agent, so a helper's signature change reaches it too.
KNOWN EDGE CASES: An agent that moved the branch off its start commit fails; GITHUB_TOKEN may not push workflow files, so those edits are refused up front; push errors have their credentials masked before they reach the report.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py runs finalize against temporary git repositories and a local bare remote.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from review_agents.gitops import TRAILER_AGENT, TRAILER_COMMENTS, TRAILER_REVIEW, TRAILER_UNIT, CommandRunner, Git
from review_agents.review_data import AgentReport, AgentSpec, AgentTask, BiteVerdict, ReviewPlan, TaskResult, TaskStatus

GATE = ("python", "scripts/run_ci.py")
# Paths claude-code-action swaps for their base-branch versions before Claude starts, plus
# the folder it parks the pull request's own copies in. They must never be committed back.
RESTORED_PATHS = (".claude", ".claude-pr", ".claude.json", ".mcp.json", ".gitmodules", ".ripgreprc", ".husky", "CLAUDE.md", "CLAUDE.local.md")
# GITHUB_TOKEN may not push workflow files, so such edits are refused up front.
PROTECTED_PREFIX = ".github/workflows/"
COMMIT_TITLE = re.compile(r"^(feat|fix|docs|ci|build|chore|test|refactor|perf|style)(\([\w./-]+\))?!?: \S.{0,99}$")
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
IDENTITY = ("-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}")
CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@")


@dataclass(frozen=True, slots=True)
class FinalizeRequest:
    """One finished agent run and everything needed to land or reject its edit."""

    plan: ReviewPlan
    task: AgentTask
    agent: AgentSpec
    report: AgentReport | None
    agent_succeeded: bool
    start_sha: str
    push_remote: str
    gate: tuple[str, ...] | str = GATE
    gate_timeout: int = 2400
    check_timeout: int = 900

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", self.start_sha):
            raise ValueError(f"FinalizeRequest.start_sha is {self.start_sha!r}")
        if not self.push_remote:
            raise ValueError("FinalizeRequest.push_remote is empty")
        if self.task.agent != self.agent.name:
            raise ValueError(f"Task {self.task.id} does not belong to agent {self.agent.name}")


class TaskFinalizer:
    """Gate, commit, bite-check, and push one agent's change."""

    def __init__(self, git: Git, commands: CommandRunner) -> None:
        self._git = git
        self._commands = commands

    def finalize(self, request: FinalizeRequest) -> TaskResult:
        task, report = request.task, request.report
        # An agent that crashed or returned no result gets nothing pushed, whatever it edited.
        if not request.agent_succeeded or report is None:
            return self._failed(task, report, "The agent run failed or returned no result.")
        # Fold anything the agent committed back into the index, on top of the start commit.
        if moved := self._fold_into_index(request.start_sha):
            return self._failed(task, report, moved)
        # Put back the config the action restored from the base branch, so it is not committed.
        self._restore_config(request.start_sha)
        changed = self._staged_paths()
        # Nothing staged means the agent decided, or found, that no edit was needed.
        if not changed:
            return self._unchanged(task, report)
        # Refuse edits this token cannot push, rather than failing at the very end.
        if protected := self._protected(changed):
            return self._failed(task, report, f"Edits to {protected} cannot be pushed here.")
        # The full gate decides; a red gate means the change never reaches the pull request.
        gate = self._commands.run(request.gate, self._git.root, request.gate_timeout)
        if gate.returncode != 0:
            return self._failed(task, report, f"The gate failed:\n\n{gate.tail}")
        # The workflow, not the agent, writes the commit and the trailers later runs rely on.
        commit = self._commit(self._message(request))
        # A guard has to fail on the reviewed code, or it would not have caught this comment.
        bite, evidence = self._bite(request, commit)
        if bite in {BiteVerdict.NOT_CAUGHT, BiteVerdict.ALWAYS_FAILS}:
            return self._failed(task, report, evidence, bite)
        # Push, replaying the commit once on top of anything pushed meanwhile.
        pushed, note = self._push(request, replay=True)
        if pushed is None:
            return self._failed(task, report, note, bite)
        return TaskResult(task_id=task.id, status=TaskStatus.CHANGED, summary=report.summary, commit_sha=pushed, bite=bite, detail="\n\n".join(filter(None, (evidence, note))))

    def _fold_into_index(self, start_sha: str) -> str:
        if self._git.output("rev-parse", "HEAD") != start_sha:
            ancestry = self._git.run("merge-base", "--is-ancestor", start_sha, "HEAD", check=False)
            if ancestry.returncode != 0:
                return "The agent moved the branch off the commit it started from."
            self._git.run("reset", "-q", "--soft", start_sha)
        self._git.run("add", "-A")
        return ""

    def _restore_config(self, source: str) -> None:
        # `source` is the commit or tree whose copy of each restored path the result keeps.
        for path in RESTORED_PATHS:
            self._git.run("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path)
            if self._git.output("ls-tree", "--name-only", source, "--", path):
                self._git.run("checkout", source, "--", path)
            self._git.run("clean", "-fdxq", "--", path)

    def _staged_paths(self, against: str = "HEAD") -> tuple[str, ...]:
        names = self._git.output("diff", "--cached", "--name-only", against)
        return tuple(name for name in names.splitlines() if name)

    def _protected(self, paths: tuple[str, ...]) -> list[str]:
        return [path for path in paths if path.startswith(PROTECTED_PREFIX)]

    def _message(self, request: FinalizeRequest) -> str:
        # The trailers are how later runs and the report find this review's commits.
        report = request.report
        assert report is not None
        task, review = request.task, request.plan.review
        title = report.commit_title.strip()
        if not COMMIT_TITLE.match(title):
            title = f"fix(review): {task.agent} for {task.unit} of review {review.review_id}"
        trailers = (f"{TRAILER_REVIEW}: {review.review_id}", f"{TRAILER_AGENT}: {task.agent}", f"{TRAILER_UNIT}: {task.unit}", f"{TRAILER_COMMENTS}: {', '.join(map(str, task.comment_ids))}", CO_AUTHOR)
        return f"{title}\n\n{report.summary.strip()}\n\n" + "\n".join(trailers) + "\n"

    def _commit(self, message: str) -> str:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(message)
        self._git.run(*IDENTITY, "commit", "-q", "-F", handle.name)
        Path(handle.name).unlink()
        return self._git.output("rev-parse", "HEAD")

    def _bite(self, request: FinalizeRequest, commit: str) -> tuple[BiteVerdict, str]:
        report, root = request.report, self._git.root
        if not request.agent.guard or report is None:
            return BiteVerdict.NOT_APPLICABLE, ""
        command = report.check_command.strip()
        if not command:
            return BiteVerdict.INCONCLUSIVE, "The agent gave no check command to verify."
        # The check has to pass on the branch as it now stands.
        current = self._commands.run(command, root, request.check_timeout)
        if current.returncode != 0:
            return BiteVerdict.ALWAYS_FAILS, f"`{command}` fails on the fixed branch:\n\n{current.tail}"
        # Find the earlier commits in this review that fixed these same comments.
        review = request.plan.review
        fixes = [earlier.sha for earlier in self._git.review_commits(f"origin/{review.base_ref}", review.review_id) if earlier.agent != request.agent.name and set(earlier.comment_ids) & set(request.task.comment_ids)]
        if not fixes:
            return BiteVerdict.INCONCLUSIVE, "No earlier commit in this review fixed these comments."
        # Undo those fixes in place, keeping the guard, and see whether the check notices.
        reverted = self._git.run("revert", "--no-commit", *reversed(fixes), check=False)
        try:
            if reverted.returncode != 0:
                return BiteVerdict.INCONCLUSIVE, "Reverting the fix conflicted with later changes."
            before = self._commands.run(command, root, request.check_timeout)
            if before.returncode == 0:
                return BiteVerdict.NOT_CAUGHT, f"`{command}` still passes with the fix reverted."
            return BiteVerdict.VERIFIED, f"`{command}` fails with the fix reverted, as it should."
        finally:
            self._git.run("reset", "-q", "--hard", commit)
            self._git.run("revert", "--quit", check=False)
            self._git.run("clean", "-fdq")

    def _push(self, request: FinalizeRequest, replay: bool) -> tuple[str | None, str]:
        remote, branch = request.push_remote, request.plan.review.head_ref
        target = f"HEAD:refs/heads/{branch}"
        first = self._git.run("push", "-q", remote, target, check=False)
        if first.returncode == 0:
            return self._git.output("rev-parse", "HEAD"), ""
        if not replay:
            failure = first.stderr.strip().replace(remote, "<remote>")
            return None, "The push was rejected: " + _CREDENTIALS.sub(r"\1***@", failure)
        # Someone pushed in the meantime: replay this one commit on top of theirs, once.
        fetched = self._git.run("fetch", "-q", remote, branch, check=False)
        rebased = self._git.run("rebase", "-q", "FETCH_HEAD", check=False) if fetched.returncode == 0 else fetched
        second = self._git.run("push", "-q", remote, target, check=False) if rebased.returncode == 0 else rebased
        if second.returncode != 0:
            self._git.run("rebase", "--abort", check=False)
            failure = f"{first.stderr.strip()}\n{second.stderr.strip()}".replace(remote, "<remote>")
            return None, "The push was rejected: " + _CREDENTIALS.sub(r"\1***@", failure)
        return self._git.output("rev-parse", "HEAD"), "Rebased onto newer commits before pushing."

    def _unchanged(self, task: AgentTask, report: AgentReport) -> TaskResult:
        status = report.status if report.status is TaskStatus.BLOCKED else TaskStatus.NO_CHANGE
        detail = "The agent reported a change but left no edits." if report.status is TaskStatus.CHANGED else ""
        return TaskResult(task.id, status, report.summary, None, BiteVerdict.NOT_APPLICABLE, detail)

    def _failed(self, task: AgentTask, report: AgentReport | None, detail: str, bite: BiteVerdict = BiteVerdict.NOT_APPLICABLE) -> TaskResult:
        summary = report.summary if report else ""
        return TaskResult(task.id, TaskStatus.FAILED, summary, None, bite, detail)
