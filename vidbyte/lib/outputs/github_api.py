"""FILE: vidbyte/lib/outputs/github_api.py

PURPOSE: Defines GitHubRequests and GitHubResponses, which build the GitHub REST requests GitHubIssueOutput sends and read the lists it searches.
ROLE IN CODEBASE: Called by GitHubIssueOutput in github.py for its four modes: new issue, comment, sticky comment, and one issue per key.
ARCHITECTURE NOTE: Pure static functions with no state, like OutputText; the connector chooses the mode and hands each request to OutputHttp.
COMMON MODIFICATION PATTERNS: Add a request builder to GitHubRequests and a list reader to GitHubResponses; keep GitHub's paths and query names here.
KNOWN EDGE CASES: Every body quotes "<!-- vidbyte:" before it is cut, so a reply can never plant a key's marker; list reads use page numbers because response headers are not read.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.github.com/en/rest/issues/comments; https://docs.github.com/en/rest/issues/issues
TESTS: tests/features/agent_output_connectors/test_output_connectors_update_in_place.py and test_output_connectors_comments.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlencode

from vidbyte.lib.constants.outputs import (
    GITHUB_API_URL,
    GITHUB_API_VERSION,
    GITHUB_BODY_MAX_CHARS,
    GITHUB_MARKER_PREFIX,
    GITHUB_MARKER_REPLACEMENT,
    GITHUB_PAGE_SIZE,
    OUTPUT_TITLE_MAX_CHARS,
)
from vidbyte.lib.dataclasses.outputs import OutputRequest
from vidbyte.lib.outputs.text import OutputText


class GitHubRequests:
    """Builds GitHubIssueOutput's REST requests: a new issue, a comment, an edit, and the two list reads."""

    @staticmethod
    def body(text: str, marker: str | None) -> str:
        """Quote every "<!-- vidbyte:" in text, cut it to GitHub's cap, and end it with marker when one is given."""
        # @intent github-body-cannot-plant-a-marker
        # The quoting runs before the cut, because the quoted form is
        # longer, and the connector's own marker is added after it, so
        # a body never carries a marker the reply wrote.
        quoted = text.replace(GITHUB_MARKER_PREFIX, GITHUB_MARKER_REPLACEMENT)
        if marker is None:
            return OutputText.truncate(quoted, GITHUB_BODY_MAX_CHARS)
        suffix = f"\n\n{marker}"
        return OutputText.truncate(quoted, GITHUB_BODY_MAX_CHARS - len(suffix)) + suffix

    @staticmethod
    def issue(repo: str, token: str, title: str, body: str, labels: Sequence[str]) -> OutputRequest:
        """POST a new issue with a one-line title, the body, and the labels; the receipt links its html_url."""
        payload = {"title": OutputText.single_line(title, OUTPUT_TITLE_MAX_CHARS), "body": body, "labels": list(labels)}
        return OutputRequest(f"{GITHUB_API_URL}/repos/{repo}/issues", GitHubRequests._headers(token), payload, link_path=("html_url",))

    @staticmethod
    def comment(repo: str, token: str, number: int, body: str) -> OutputRequest:
        """POST a new comment on issue or pull request number; the receipt links its html_url."""
        return OutputRequest(f"{GITHUB_API_URL}/repos/{repo}/issues/{number}/comments", GitHubRequests._headers(token), {"body": body}, link_path=("html_url",))

    @staticmethod
    def edit(repo: str, token: str, comment_id: int, body: str) -> OutputRequest:
        """PATCH comment comment_id with a new body; the receipt links its html_url."""
        return OutputRequest(f"{GITHUB_API_URL}/repos/{repo}/issues/comments/{comment_id}", GitHubRequests._headers(token), {"body": body}, link_path=("html_url",))

    @staticmethod
    def comments_page(repo: str, token: str, number: int, page: int) -> OutputRequest:
        """GET one page of the comments on issue or pull request number, oldest first."""
        query = urlencode({"per_page": GITHUB_PAGE_SIZE, "page": page})
        return OutputRequest(f"{GITHUB_API_URL}/repos/{repo}/issues/{number}/comments?{query}", GitHubRequests._headers(token), None)

    @staticmethod
    def keyed_issues(repo: str, token: str, label: str) -> OutputRequest:
        """GET the open issues carrying label, oldest first; the list endpoint, never search."""
        query = urlencode({"labels": label, "state": "open", "sort": "created", "direction": "asc", "per_page": GITHUB_PAGE_SIZE})
        return OutputRequest(f"{GITHUB_API_URL}/repos/{repo}/issues?{query}", GitHubRequests._headers(token), None)

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        # GitHub's REST headers, pinned to one API version.
        return {"authorization": f"Bearer {token}", "accept": "application/vnd.github+json", "x-github-api-version": GITHUB_API_VERSION}


class GitHubResponses:
    """Reads the JSON lists GitHub returns: the objects in a list, a marked comment, and the first issue."""

    @staticmethod
    def items(data: object) -> tuple[Mapping[str, object], ...] | None:
        """The objects in a JSON list, or None when data is not a list of objects."""
        if isinstance(data, list) and all(isinstance(item, Mapping) for item in data):
            return tuple(data)
        return None

    @staticmethod
    def marked_comment(items: Sequence[Mapping[str, object]], marker: str) -> int | None:
        """The id of the first, so oldest, comment whose body contains marker, or None."""
        for item in items:
            body, comment_id = item.get("body"), item.get("id")
            if isinstance(body, str) and marker in body and isinstance(comment_id, int):
                return comment_id
        return None

    @staticmethod
    def first_issue(items: Sequence[Mapping[str, object]]) -> int | None:
        """The number of the first issue that is not a pull request, or None; GitHub marks pull requests with a pull_request key."""
        for item in items:
            number = item.get("number")
            if "pull_request" not in item and isinstance(number, int):
                return number
        return None


__all__ = ["GitHubRequests", "GitHubResponses"]
