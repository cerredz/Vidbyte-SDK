"""FILE: scripts/review_agents/merging.py

PURPOSE: Turns the merge agent's settled conflicts into one pushed merge commit of the base branch, or into nothing.
ROLE IN CODEBASE: run.py's finalize step uses MergeFinalizer instead of TaskFinalizer for a task whose scope is `merge`. The workflow starts `git merge --no-commit` before the agent runs; this step checks the agent left no conflict markers, gates the result, and records the merge with both branches as parents so the pull request stops conflicting.
ARCHITECTURE NOTE: MergeFinalizer subclasses TaskFinalizer and reuses its fold, restore, gate, and push helpers; only the checks a merge needs and the two-parent commit are its own. git's merge-tree preview, not the agent, says which files conflicted and what the clean merge holds, so the agent cannot hide a conflict or slip an unrelated edit into a workflow file.
COMMON MODIFICATION PATTERNS: Add a refusal as one early return in finalize() with its reason, as finalize.py does.
KNOWN EDGE CASES: A merge is never replayed onto newer commits, because rebasing would flatten it, so a push race fails and the next @claude review merges again; a conflict inside config that claude-code-action swaps for its base-branch copy needs a person; pushing a merge that brings in base-branch workflow changes needs CLAUDE_REVIEW_PUSH_TOKEN with Workflows write, because GITHUB_TOKEN may not change workflow files.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py runs MergeFinalizer against temporary git repositories and a local bare remote.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from review_agents.finalize import IDENTITY, RESTORED_PATHS, FinalizeRequest, TaskFinalizer
from review_agents.review_data import BiteVerdict, TaskResult, TaskStatus

CONFLICT_MARKER = re.compile(r"^(<{7}|>{7})( |$)", re.MULTILINE)
WORKFLOW_PUSH_HINT = "GITHUB_TOKEN may not push workflow files, and this merge brings in the base branch's workflow changes. Add a CLAUDE_REVIEW_PUSH_TOKEN secret with Contents and Workflows write access."


class MergeFinalizer(TaskFinalizer):
    """Gate, commit, and push the merge of the base branch that the merge agent settled."""

    def finalize(self, request: FinalizeRequest) -> TaskResult:
        task, report, review = request.task, request.report, request.plan.review
        # An agent that crashed or returned no result gets nothing pushed, whatever it settled.
        if not request.agent_succeeded or report is None:
            return self._failed(task, report, "The agent run failed or returned no result.")
        # Work out the clean merge again, so git, not the agent, says which files conflicted.
        base_sha = self._git.output("rev-parse", f"origin/{review.base_ref}")
        preview = self._git.merge_preview(base_sha, request.start_sha)
        # Config the action swaps for its base-branch copy cannot be settled by the agent.
        if config := self._config_conflicts(preview.conflicts):
            return self._failed(task, report, f"{', '.join(config)} conflicted and must be merged by hand.")
        # A file that still holds conflict markers was not settled.
        if unsettled := self._unsettled(preview.conflicts):
            return self._failed(task, report, f"Conflict markers remain in {', '.join(unsettled)}.")
        # Fold anything the agent committed back into the index, on top of the start commit.
        if moved := self._fold_into_index(request.start_sha):
            return self._failed(task, report, moved)
        # Put back the config the action swapped in, as the clean merge holds it.
        self._restore_config(preview.tree)
        # Nothing staged means someone already merged the base branch in.
        if not self._staged_paths():
            return self._unchanged(task, report)
        # Workflow files may change only as the base branch changed them, never by the agent's hand.
        if protected := self._protected(self._staged_paths(preview.tree)):
            return self._failed(task, report, f"Edits to {protected} cannot be pushed here.")
        # The full gate decides; a red gate means the merge never reaches the pull request.
        gate = self._commands.run(request.gate, self._git.root, request.gate_timeout)
        if gate.returncode != 0:
            return self._failed(task, report, f"The gate failed:\n\n{gate.tail}")
        # Record the merge with both branches as parents, so the base branch's history stays whole.
        self._merge_commit(self._message(request), base_sha)
        # Push once, without replaying: replaying a merge onto newer commits would flatten it.
        pushed, note = self._push(request, replay=False)
        if pushed is None:
            hint = f"\n\n{WORKFLOW_PUSH_HINT}" if "workflow" in note else ""
            return self._failed(task, report, note + hint)
        return TaskResult(task_id=task.id, status=TaskStatus.CHANGED, summary=report.summary, commit_sha=pushed, bite=BiteVerdict.NOT_APPLICABLE, detail=note)

    def _config_conflicts(self, paths: tuple[str, ...]) -> list[str]:
        return [path for path in paths if any(path == root or path.startswith(f"{root}/") for root in RESTORED_PATHS)]

    def _unsettled(self, paths: tuple[str, ...]) -> list[str]:
        files = ((path, self._git.root / path) for path in paths)
        return [path for path, file in files if file.is_file() and CONFLICT_MARKER.search(file.read_text(encoding="utf-8", errors="replace"))]

    def _merge_commit(self, message: str, base_sha: str) -> str:
        # Forget git's own merge state, which a commit the agent made may already have cleared.
        self._git.run("merge", "--quit", check=False)
        tree = self._git.output("write-tree")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(message)
        commit = self._git.output(*IDENTITY, "commit-tree", tree, "-p", "HEAD", "-p", base_sha, "-F", handle.name)
        Path(handle.name).unlink()
        self._git.run("reset", "-q", "--soft", commit)
        return commit
