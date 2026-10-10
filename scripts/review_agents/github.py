"""FILE: scripts/review_agents/github.py

PURPOSE: Reads one submitted pull-request review and its comments from GitHub through the gh CLI.
ROLE IN CODEBASE: run.py's collect step calls ReviewFetcher, so the workflow decides which comments exist by asking the API, never a model, and no comment can be skipped because an agent missed it.
ARCHITECTURE NOTE: GitHubReader is a Protocol, so tests pass a fake reader and never touch the network; GhCli is the only class that shells out to gh.
COMMON MODIFICATION PATTERNS: Read a new comment field in _comment() and add it to ReviewComment in review_data.py in the same change.
KNOWN EDGE CASES: Outdated comments lose `line` and keep `original_line`; a review with no inline comments turns its summary into one comment; the @claude trigger is removed from the summary.
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


class ReviewFetcher:
    """Builds a validated Review from the pull request, the review, and its comments."""

    def __init__(self, reader: GitHubReader) -> None:
        self._reader = reader

    def fetch(self, repository: str, pull_number: int, review_id: int) -> Review:
        # The pull request supplies the branches; the review supplies the reviewed commit.
        base = f"repos/{repository}/pulls/{pull_number}"
        pull = self._reader.get(base)
        review = self._reader.get(f"{base}/reviews/{review_id}")
        # The pull request's comment list carries line numbers and reply links, which the
        # per-review endpoint omits, so read it whole and keep this review's comments.
        every_comment = self._reader.list(f"{base}/comments")
        raw_comments = [raw for raw in every_comment if raw.get("pull_request_review_id") == review_id]
        # A reply only makes sense next to the comment it answers.
        parents = {int(raw["id"]): raw["body"] for raw in every_comment}
        summary = TRIGGER.sub("", review.get("body") or "").strip()
        comments = tuple(self._comment(raw, parents) for raw in raw_comments)
        # A review with no inline comments is a request written in the summary itself.
        if not comments and summary:
            comments = (self._summary_comment(review, summary),)
        return Review(repository=repository, pull_number=pull_number, review_id=review_id, reviewed_sha=review["commit_id"], head_ref=pull["head"]["ref"], base_ref=pull["base"]["ref"], summary=summary, comments=comments)

    def _comment(self, raw: dict[str, Any], parents: dict[int, str]) -> ReviewComment:
        # Outdated comments lose `line`; `original_line` still points at what was reviewed.
        line = raw.get("line") or raw.get("original_line")
        return ReviewComment(id=int(raw["id"]), body=raw["body"], path=raw.get("path"), line=int(line) if line else None, url=raw.get("html_url", ""), diff_hunk=raw.get("diff_hunk") or "", parent_body=parents.get(raw.get("in_reply_to_id") or 0))

    def _summary_comment(self, review: dict[str, Any], summary: str) -> ReviewComment:
        return ReviewComment(id=int(review["id"]), body=summary, path=None, line=None, url=review.get("html_url", ""), diff_hunk="", parent_body=None)
