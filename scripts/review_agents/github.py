"""FILE: scripts/review_agents/github.py

PURPOSE: Reads one round of pull-request review from GitHub through the gh CLI: every comment trusted reviewers left since the last finished round, up to the review that said @claude.
ROLE IN CODEBASE: run.py's collect step calls ReviewFetcher, so the workflow decides which comments exist by asking the API, never a model, and no comment can be skipped because an agent missed it. sweep.py uses GhCli's graphql and post calls to find and start rounds GitHub never sent an event for.
ARCHITECTURE NOTE: GitHubReader is a Protocol, so tests pass a fake reader and never touch the network; GhCli is the only class that shells out to gh. A round ends where the last clean summary comment's ROUND_MARKER says, so no state lives outside the pull request itself.
COMMON MODIFICATION PATTERNS: Read a new comment field in _comment() and add it to ReviewComment in review_data.py in the same change; widen who may start a round only through TRUSTED_ASSOCIATIONS.
KNOWN EDGE CASES: Outdated comments lose `line` and keep `original_line`; "Add single comment" makes each comment its own review, which is why a round spans reviews; a summary-only round turns the @claude summary into one comment; the @claude trigger is removed from every summary; reviews from bots and from people without write access never enter a round.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py uses a fake GitHubReader.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Protocol

from review_agents.review_data import Review, ReviewComment

TRIGGER = re.compile(r"@claude\b", re.IGNORECASE)
# The summary comment of a round that finished cleanly ends with this marker, and the next round starts after it.
ROUND_MARKER = "<!-- claude-review-agents through={through} -->"
ROUND_MARKER_PATTERN = re.compile(r"<!-- claude-review-agents through=(?P<through>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z) -->")
# Only people who can already push to the repository may hand an agent instructions.
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
BOT_LOGIN = "github-actions[bot]"


class GitHubReader(Protocol):
    def get(self, path: str) -> dict[str, Any]: ...

    def list(self, path: str) -> list[dict[str, Any]]: ...


class GhCli:
    """The real reader: `gh api`, authenticated by the GH_TOKEN the workflow sets."""

    def get(self, path: str) -> dict[str, Any]:
        result = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True, encoding="utf-8")
        data: dict[str, Any] = json.loads(result.stdout)
        return data

    def list(self, path: str) -> list[dict[str, Any]]:
        # One compact JSON object per line across every page, whatever the gh version.
        result = subprocess.run(["gh", "api", "--paginate", "--jq", ".[]", f"{path}?per_page=100"], check=True, capture_output=True, text=True, encoding="utf-8")
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def graphql(self, query: str, variables: dict[str, str]) -> dict[str, Any]:
        fields = [argument for name, value in variables.items() for argument in ("-f", f"{name}={value}")]
        result = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}", *fields], check=True, capture_output=True, text=True, encoding="utf-8")
        data: dict[str, Any] = json.loads(result.stdout)["data"]
        return data

    def post(self, path: str, payload: dict[str, Any]) -> None:
        subprocess.run(["gh", "api", "-X", "POST", path, "--input", "-"], input=json.dumps(payload), check=True, capture_output=True, text=True, encoding="utf-8")


def is_trusted(item: dict[str, Any]) -> bool:
    """Whether a review or comment comes from a person who can push here, never a bot."""
    user = item.get("user") or item.get("author") or {}
    is_bot = user.get("type") == "Bot" or user.get("__typename") == "Bot"
    association = item.get("author_association") or item.get("authorAssociation")
    return association in TRUSTED_ASSOCIATIONS and not is_bot


def last_round_end(comments: list[dict[str, Any]]) -> str:
    """The `through` time of the newest clean round, read from the workflow's own summary comments."""
    ends = []
    for comment in comments:
        author = (comment.get("user") or comment.get("author") or {}).get("login")
        found = ROUND_MARKER_PATTERN.search(comment.get("body") or "")
        if found and author in {BOT_LOGIN, "github-actions"}:
            ends.append(found.group("through"))
    return max(ends, default="")


class ReviewFetcher:
    """Builds a validated Review for one round from the pull request, its reviews, and their comments."""

    def __init__(self, reader: GitHubReader) -> None:
        self._reader = reader

    def fetch(self, repository: str, pull_number: int, review_id: int) -> Review:
        # The pull request supplies the branches; the review that said @claude closes the round.
        base = f"repos/{repository}/pulls/{pull_number}"
        pull = self._reader.get(base)
        trigger = self._reader.get(f"{base}/reviews/{review_id}")
        if not is_trusted(trigger):
            raise ValueError(f"Review {review_id} is not from someone with write access to {repository}")
        # The last round that finished cleanly left a marker in its summary comment; this round starts after it.
        since = last_round_end(self._reader.list(f"repos/{repository}/issues/{pull_number}/comments"))
        through = trigger["submitted_at"]
        # Every review a trusted person submitted after that, up to and including the trigger, is in the round.
        round_reviews = self._round_reviews(self._reader.list(f"{base}/reviews"), since, through)
        round_ids = {int(review["id"]) for review in round_reviews}
        # The pull request's comment list carries line numbers and reply links, which the
        # per-review endpoint omits, so read it whole and keep the round's comments.
        every_comment = self._reader.list(f"{base}/comments")
        # A reply only makes sense next to the comment it answers.
        parents = {int(raw["id"]): raw["body"] for raw in every_comment}
        inline = [self._comment(raw, parents) for raw in every_comment if raw.get("pull_request_review_id") in round_ids]
        # A summary written on any other review in the round is a request of its own.
        summaries = [self._summary_comment(review, text) for review in round_reviews if int(review["id"]) != review_id and (text := self._summary(review))]
        summary = self._summary(trigger)
        comments = tuple(inline + summaries)
        # A round with nothing else in it is a request written in the @claude summary itself.
        if not comments and summary and since < through:
            comments = (self._summary_comment(trigger, summary),)
        return Review(repository=repository, pull_number=pull_number, review_id=review_id, reviewed_sha=trigger["commit_id"], head_ref=pull["head"]["ref"], base_ref=pull["base"]["ref"], summary=summary, comments=comments, since=since, through=through)

    def _round_reviews(self, reviews: list[dict[str, Any]], since: str, through: str) -> list[dict[str, Any]]:
        # GitHub timestamps share one fixed format, so comparing them as text compares the times.
        return [review for review in reviews if since < (review.get("submitted_at") or "") <= through and is_trusted(review)]

    def _summary(self, review: dict[str, Any]) -> str:
        return TRIGGER.sub("", review.get("body") or "").strip()

    def _comment(self, raw: dict[str, Any], parents: dict[int, str]) -> ReviewComment:
        # Outdated comments lose `line`; `original_line` still points at what was reviewed.
        line = raw.get("line") or raw.get("original_line")
        return ReviewComment(id=int(raw["id"]), body=raw["body"], path=raw.get("path"), line=int(line) if line else None, url=raw.get("html_url", ""), diff_hunk=raw.get("diff_hunk") or "", parent_body=parents.get(raw.get("in_reply_to_id") or 0))

    def _summary_comment(self, review: dict[str, Any], summary: str) -> ReviewComment:
        return ReviewComment(id=int(review["id"]), body=summary, path=None, line=None, url=review.get("html_url", ""), diff_hunk="", parent_body=None)
