"""FILE: scripts/review_agents/gitops.py

PURPOSE: Wraps the git and shell commands the review-agents workflow runs, so finalize reads as steps rather than plumbing.
ROLE IN CODEBASE: finalize.py and merging.py commit, revert, and push through Git; run.py reads earlier review commits through their trailers and previews the merge with the base branch to plan the merge agent; CommandRunner runs the gate and each guard's check.
ARCHITECTURE NOTE: The trailer names here are the contract between finalize, which writes them, and every later step, which finds this review's commits by them.
COMMON MODIFICATION PATTERNS: Add a trailer as a TRAILER_ constant and read it in review_commits(); keep every subprocess call argument-list based except a guard's own check command.
KNOWN EDGE CASES: A guard's check command is a shell string the agent wrote, so it alone runs with shell=True; output is decoded as UTF-8 with replacement so a stray byte never crashes a job; merge_preview needs git 2.38 or later for `merge-tree --write-tree`.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py drives these wrappers against temporary git repositories.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TRAILER_REVIEW = "Claude-Review"
TRAILER_AGENT = "Claude-Review-Agent"
TRAILER_UNIT = "Claude-Review-Unit"
TRAILER_COMMENTS = "Claude-Review-Comments"
OUTPUT_TAIL_LINES = 40


@dataclass(frozen=True, slots=True)
class ReviewCommit:
    """A commit this workflow pushed, identified by the trailers finalize writes."""

    sha: str
    subject: str
    review_id: int
    agent: str
    unit: str
    comment_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MergePreview:
    """What merging the base branch would produce, worked out without touching the working tree."""

    tree: str
    conflicts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """A finished command: its exit status and the end of what it printed."""

    returncode: int
    tail: str


class Git:
    """Runs git in one checkout and fails loudly with git's own message."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["git", *arguments], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        if check and result.returncode != 0:
            raise RuntimeError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
        return result

    def output(self, *arguments: str) -> str:
        return self.run(*arguments).stdout.strip()

    def review_commits(self, since: str, review_id: int) -> tuple[ReviewCommit, ...]:
        # Unit and record separators keep commit bodies from being mistaken for fields.
        log = self.output("log", "--reverse", "--format=%H%x1f%s%x1f%B%x1e", f"{since}..HEAD")
        commits = []
        for record in filter(None, (chunk.strip() for chunk in log.split("\x1e"))):
            sha, subject, body = record.split("\x1f", 2)
            trailers = dict(re.findall(r"^(Claude-Review[\w-]*): (.+)$", body, re.MULTILINE))
            if trailers.get(TRAILER_REVIEW) != str(review_id):
                continue
            comment_ids = tuple(int(value) for value in re.findall(r"\d+", trailers.get(TRAILER_COMMENTS, "")))
            commits.append(ReviewCommit(sha=sha, subject=subject, review_id=review_id, agent=trailers.get(TRAILER_AGENT, ""), unit=trailers.get(TRAILER_UNIT, ""), comment_ids=comment_ids))
        return tuple(commits)


    def merge_preview(self, base: str, head: str) -> MergePreview:
        # merge-tree prints the merged tree, then each conflicted path, and exits 1 on conflicts.
        result = self.run("merge-tree", "--write-tree", "--name-only", "--no-messages", base, head, check=False)
        if result.returncode not in {0, 1}:
            raise RuntimeError(f"git merge-tree {base} {head} failed: {result.stderr.strip()}")
        tree, *paths = result.stdout.splitlines()
        return MergePreview(tree=tree.strip(), conflicts=tuple(dict.fromkeys(path for path in paths if path)))


class CommandRunner:
    """Runs a gate or a check, streams its output to the job log, and keeps the tail."""

    def run(self, command: str | tuple[str, ...], cwd: Path, timeout: int) -> CommandOutcome:
        try:
            result = subprocess.run(command, cwd=cwd, shell=isinstance(command, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return CommandOutcome(124, f"Timed out after {timeout} seconds.")
        sys.stdout.write(result.stdout)
        sys.stdout.flush()
        tail = "\n".join(result.stdout.splitlines()[-OUTPUT_TAIL_LINES:])
        return CommandOutcome(result.returncode, tail)
