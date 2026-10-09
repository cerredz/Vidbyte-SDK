"""FILE: scripts/review_agents/review_data.py

PURPOSE: Defines the validated records and enums the review-agents workflow's steps pass to each other.
ROLE IN CODEBASE: Every step writes these records to JSON and the next step reads them back, so each record validates itself on creation and a bad value fails where it enters, not three jobs later.
ARCHITECTURE NOTE: These records stay here rather than in vidbyte/lib/dataclasses/ and vidbyte/lib/enums/ because the workflow tools run without the SDK installed and must never ship in the wheel; scripts/run_ci.py keeps its PipelineConfig in scripts/ for the same reason.
COMMON MODIFICATION PATTERNS: Add a field with its __post_init__ check and its from_json reader together, and keep every enum value a plain lowercase string the JSON can carry.
KNOWN EDGE CASES: A summary-only review becomes one comment with no path or line; TaskResult allows a commit only for a changed task.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py.
"""

from __future__ import annotations

import enum
import re
from dataclasses import asdict, dataclass
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")
_TASK_ID = re.compile(r"^[0-9]{2}-[a-z][a-z0-9-]*-[a-z0-9]+$")
_AGENT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


class Scope(enum.StrEnum):
    """How much of a review one run of an agent covers."""

    COMMENT = "comment"
    REVIEW = "review"


class TaskStatus(enum.StrEnum):
    """The outcome of one task, as the report shows it."""

    CHANGED = "changed"
    NO_CHANGE = "no_change"
    BLOCKED = "blocked"
    FAILED = "failed"


class BiteVerdict(enum.StrEnum):
    """Whether a guard's check fails on the code the reviewer commented on."""

    VERIFIED = "verified"
    NOT_CAUGHT = "not_caught"
    ALWAYS_FAILS = "always_fails"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ReviewComment:
    """One comment the reviewer left, with the code context GitHub recorded for it."""

    id: int
    body: str
    path: str | None
    line: int | None
    url: str
    diff_hunk: str
    parent_body: str | None

    def __post_init__(self) -> None:
        _require(self.id > 0, f"ReviewComment.id must be positive, got {self.id!r}")
        _require(bool(self.body.strip()), f"ReviewComment {self.id} has an empty body")
        _require(self.line is None or self.line > 0, f"ReviewComment.line is {self.line!r}")

    @property
    def location(self) -> str:
        if self.path is None:
            return "review summary"
        return f"{self.path}:{self.line}" if self.line else self.path


@dataclass(frozen=True, slots=True)
class Review:
    """A submitted review and the pull request it belongs to."""

    repository: str
    pull_number: int
    review_id: int
    reviewed_sha: str
    head_ref: str
    base_ref: str
    summary: str
    comments: tuple[ReviewComment, ...]

    def __post_init__(self) -> None:
        _require(self.repository.count("/") == 1, f"Review.repository is {self.repository!r}")
        _require(self.pull_number > 0, f"Review.pull_number is {self.pull_number!r}")
        _require(self.review_id > 0, f"Review.review_id is {self.review_id!r}")
        _require(bool(_SHA.match(self.reviewed_sha)), f"Review.reviewed_sha is {self.reviewed_sha!r}")
        _require(bool(self.head_ref and self.base_ref), "Review needs both branch names")
        ids = [comment.id for comment in self.comments]
        _require(len(ids) == len(set(ids)), "Review.comments repeats a comment id")

    def comment(self, comment_id: int) -> ReviewComment:
        return next(comment for comment in self.comments if comment.id == comment_id)


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """One review agent: a prompt file plus the scope its frontmatter declares."""

    name: str
    order: int
    scope: Scope
    guard: bool
    prompt_path: str
    body: str

    def __post_init__(self) -> None:
        _require(bool(_AGENT_NAME.match(self.name)), f"AgentSpec.name is {self.name!r}")
        _require(0 <= self.order <= 99, f"AgentSpec.order is {self.order!r}")
        _require(isinstance(self.scope, Scope), f"AgentSpec.scope is {self.scope!r}")
        _require(bool(self.body.strip()), f"Agent {self.name} has an empty prompt")


@dataclass(frozen=True, slots=True)
class AgentTask:
    """One run of one agent over one unit of the review: a matrix leg."""

    id: str
    agent: str
    unit: str
    title: str
    comment_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        _require(bool(_TASK_ID.match(self.id)), f"AgentTask.id is {self.id!r}")
        _require(bool(self.comment_ids), f"AgentTask {self.id} covers no comments")


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    """Everything later jobs need: the review and the ordered tasks."""

    review: Review
    tasks: tuple[AgentTask, ...]

    def __post_init__(self) -> None:
        ids = [task.id for task in self.tasks]
        _require(len(ids) == len(set(ids)), "ReviewPlan.tasks repeats a task id")

    def task(self, task_id: str) -> AgentTask:
        return next(task for task in self.tasks if task.id == task_id)


@dataclass(frozen=True, slots=True)
class AgentReport:
    """The structured output an agent returns at the end of its run."""

    status: TaskStatus
    commit_title: str
    summary: str
    check_command: str

    def __post_init__(self) -> None:
        _require(self.status in {TaskStatus.CHANGED, TaskStatus.NO_CHANGE, TaskStatus.BLOCKED}, f"An agent cannot report status {self.status!r}")
        _require(bool(self.summary.strip()), "AgentReport.summary is empty")


@dataclass(frozen=True, slots=True)
class TaskResult:
    """What one task did, as the finalize step recorded it for the report."""

    task_id: str
    status: TaskStatus
    summary: str
    commit_sha: str | None
    bite: BiteVerdict
    detail: str

    def __post_init__(self) -> None:
        _require(self.commit_sha is None or bool(_SHA.match(self.commit_sha)), f"TaskResult.commit_sha is {self.commit_sha!r}")
        _require((self.status is TaskStatus.CHANGED) == (self.commit_sha is not None), "Only a changed task has a commit")


def to_json(record: Any) -> dict[str, Any]:
    """Turn a record into JSON-ready data; enums become their string values."""
    return asdict(record)


def review_from_json(data: dict[str, Any]) -> Review:
    comments = tuple(ReviewComment(**comment) for comment in data["comments"])
    return Review(**{**data, "comments": comments})


def plan_from_json(data: dict[str, Any]) -> ReviewPlan:
    tasks = tuple(AgentTask(**{**task, "comment_ids": tuple(task["comment_ids"])}) for task in data["tasks"])
    return ReviewPlan(review=review_from_json(data["review"]), tasks=tasks)


def report_from_json(data: dict[str, Any]) -> AgentReport:
    return AgentReport(
        status=TaskStatus(data["status"]),
        commit_title=str(data.get("commit_title", "")),
        summary=str(data["summary"]),
        check_command=str(data.get("check_command", "")),
    )


def result_from_json(data: dict[str, Any]) -> TaskResult:
    return TaskResult(
        task_id=data["task_id"],
        status=TaskStatus(data["status"]),
        summary=data["summary"],
        commit_sha=data["commit_sha"],
        bite=BiteVerdict(data["bite"]),
        detail=data["detail"],
    )
