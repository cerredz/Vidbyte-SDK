"""FILE: scripts/review_agents/sweep.py

PURPOSE: Starts the review agents for @claude reviews that GitHub sent no workflow event for, because their pull request conflicts with its base branch.
ROLE IN CODEBASE: run.py's sweep step calls ReviewSweeper once per repository; .github/workflows/claude-review-sweep.yml runs that step every few minutes from this public repository, whose Actions minutes are free, over every repository its CLAUDE_REVIEW_SWEEP_REPOSITORIES variable lists.
ARCHITECTURE NOTE: GitHub runs no pull_request_review workflow while a pull request conflicts, and this sweeper fills exactly that gap. It looks only at conflicting pull requests, so it never races the event a mergeable one gets, and it starts each review at most once, recognizing every earlier run, whether an event or a sweep started it, by the run name claude-review-agents.yml gives it. Which reviews count reuses github.py's trust and round rules, so the sweep and the run agree on what is new.
COMMON MODIFICATION PATTERNS: Read a new pull-request field by adding it to QUERY and to _due(); keep RUN_NAME identical to the `run-name` in every repository's claude-review-agents.yml.
KNOWN EDGE CASES: GitHub reports `UNKNOWN` mergeability until it has computed it, so a pull request that just started conflicting is picked up on the next sweep; forks are skipped because the workflow cannot push to them; only the latest 100 runs are read, so a long-failed review may be started once more.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py drives ReviewSweeper with a fake GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from review_agents.github import TRIGGER, is_trusted, last_round_end

WORKFLOW = "claude-review-agents.yml"
RUN_NAME = "Claude review agents: #{pull} review {review}"
QUERY = "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { defaultBranchRef { name } pullRequests(states: OPEN, first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { number mergeable isCrossRepository reviews(last: 100) { nodes { databaseId body submittedAt authorAssociation author { __typename login } } } comments(last: 100) { nodes { body author { login } } } } } } }"


class SweepGitHub(Protocol):
    def get(self, path: str) -> dict[str, Any]: ...

    def graphql(self, query: str, variables: dict[str, str]) -> dict[str, Any]: ...

    def post(self, path: str, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class Dispatch:
    """One @claude review the sweeper started the agents for."""

    repository: str
    pull_number: int
    review_id: int

    def __post_init__(self) -> None:
        if self.repository.count("/") != 1:
            raise ValueError(f"Dispatch.repository is {self.repository!r}")
        if self.pull_number <= 0 or self.review_id <= 0:
            raise ValueError(f"Dispatch needs a positive pull request and review, got {self.pull_number!r} and {self.review_id!r}")

    @property
    def run_name(self) -> str:
        return RUN_NAME.format(pull=self.pull_number, review=self.review_id)


class ReviewSweeper:
    """Finds conflicting pull requests with an unhandled @claude review and starts the agents for each."""

    def __init__(self, github: SweepGitHub) -> None:
        self._github = github

    def sweep(self, repository: str) -> tuple[Dispatch, ...]:
        # One query reads every open pull request with its latest reviews and comments.
        owner, name = repository.split("/")
        data = self._github.graphql(QUERY, {"owner": owner, "name": name})["repository"]
        # Every run already started, by an event or an earlier sweep, is known by its name.
        started = self._started(repository)
        # Only a conflicting pull request misses its review event, so only those can be due.
        found = (self._due(repository, pull) for pull in data["pullRequests"]["nodes"])
        due = tuple(dispatch for dispatch in found if dispatch is not None and dispatch.run_name not in started)
        # Start the workflow from the default branch, where its current version lives.
        for dispatch in due:
            inputs = {"pr": str(dispatch.pull_number), "review": str(dispatch.review_id)}
            self._github.post(f"repos/{repository}/actions/workflows/{WORKFLOW}/dispatches", {"ref": data["defaultBranchRef"]["name"], "inputs": inputs})
        return due

    def _started(self, repository: str) -> set[str]:
        runs = self._github.get(f"repos/{repository}/actions/workflows/{WORKFLOW}/runs?per_page=100")["workflow_runs"]
        return {str(run.get("display_title", "")) for run in runs}

    def _due(self, repository: str, pull: dict[str, Any]) -> Dispatch | None:
        if pull["mergeable"] != "CONFLICTING" or pull["isCrossRepository"]:
            return None
        # The newest trusted @claude review after the last clean round closes the next round.
        since = last_round_end(pull["comments"]["nodes"])
        asks = [review for review in pull["reviews"]["nodes"] if TRIGGER.search(review.get("body") or "") and is_trusted(review) and (review.get("submittedAt") or "") > since]
        if not asks:
            return None
        latest = max(asks, key=lambda review: review["submittedAt"])
        return Dispatch(repository=repository, pull_number=int(pull["number"]), review_id=int(latest["databaseId"]))
