"""FILE: vidbyte/lib/outputs/github.py

PURPOSE: Defines GitHubIssueOutput, which opens one GitHub issue per finished agent reply, comments on one issue or pull request, or keeps one comment or one issue per key up to date.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: send chooses one of four modes; each mode builds its requests with GitHubRequests in github_api.py, reads with OutputHttp.read, and makes exactly one write.
COMMON MODIFICATION PATTERNS: Bump GITHUB_API_VERSION in vidbyte/lib/constants/outputs.py after checking the REST changelog.
KNOWN EDGE CASES: GitHub silently drops labels unless the token has push access, so with key= a new issue opens on every run; an @user in the body notifies that user; two runs with one key at once can each write.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.github.com/en/rest/issues/issues#create-an-issue; https://docs.github.com/en/rest/issues/comments
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py, test_output_connectors_comments.py, and test_output_connectors_update_in_place.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    GITHUB_FIRST_PAGE,
    GITHUB_KEY_LABEL_PREFIX,
    GITHUB_KEY_PATTERN,
    GITHUB_MARKER_PREFIX,
    GITHUB_MARKER_SUFFIX,
    GITHUB_MAX_PAGES,
    GITHUB_PAGE_SIZE,
    GITHUB_REPO_PATTERN,
    OUTPUT_ERROR_INVALID_RESPONSE,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import DeliveryStatus, OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.github_api import GitHubRequests, GitHubResponses
from vidbyte.lib.outputs.text import OutputText


class GitHubIssueOutput(BaseOutput):
    """Opens one GitHub issue per reply in a fixed owner/name repository, comments on one issue or pull request, or updates one comment or issue per key."""

    destination = OutputDestination.GITHUB_ISSUE

    def __init__(
        self,
        *,
        repo: str,
        labels: Sequence[str] = (),
        comment_on: int | None = None,
        key: str | None = None,
        token: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        self._repo = OutputArguments.matching(repo, GITHUB_REPO_PATTERN, parameter="repo")
        self._labels = OutputArguments.texts(labels, parameter="labels")
        self._comment_on = None if comment_on is None else OutputArguments.number(comment_on, parameter="comment_on")
        self._key = None if key is None else OutputArguments.matching(key, GITHUB_KEY_PATTERN, parameter="key")
        # A comment lands on an existing issue or pull request, which
        # keeps its own labels.
        OutputArguments.exclusive({"labels": self._labels, "comment_on": self._comment_on})
        self._token = OutputArguments.credential(self.destination, token, parameter="token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Open an issue, comment on the configured issue or pull request, or update the one comment or issue that belongs to the key."""
        # @intent github-issue-target-is-fixed
        # The repo, number, key, and labels come only from the
        # constructor, so model output cannot move the reply or the
        # token to another repo, issue, or key.
        # Without a number, the reply goes to an issue: a new one each
        # time, or, with a key, the one open issue labelled with it.
        if self._comment_on is None:
            if self._key is None:
                return await self._create_issue(content)
            return await self._comment_on_keyed_issue(content, self._key)
        # With a number, the reply is a comment there: a new one each
        # time, or, with a key, the one comment marked with it.
        if self._key is None:
            return await self._comment(content, self._comment_on)
        return await self._sticky_comment(content, self._comment_on, self._key)

    async def _create_issue(self, content: OutputContent) -> DeliveryReceipt:
        # @intent github-new-issue-is-one-post
        # Today's behavior: one issue with the title, the body, and the
        # configured labels.
        request = GitHubRequests.issue(self._repo, self._token, content.title, GitHubRequests.body(content.body, None), self._labels)
        return await OutputHttp.post(self.destination, request)

    async def _comment(self, content: OutputContent, number: int) -> DeliveryReceipt:
        # @intent github-comment-is-one-post
        # A comment has no title field, so it carries the chat text,
        # title first; each reply adds a new comment.
        request = GitHubRequests.comment(self._repo, self._token, number, GitHubRequests.body(OutputText.chat_text(content), None))
        return await OutputHttp.post(self.destination, request)

    async def _comment_on_keyed_issue(self, content: OutputContent, key: str) -> DeliveryReceipt:
        # @intent github-keyed-issue-reads-then-writes-once
        # One read finds the oldest open issue, not a pull request,
        # labelled with the key; then exactly one write. A failed read
        # ends the send before anything is written.
        label = GITHUB_KEY_LABEL_PREFIX + key
        read = await OutputHttp.read(self.destination, GitHubRequests.keyed_issues(self._repo, self._token, label))
        if read.failure is not None:
            return read.failure
        items = GitHubResponses.items(read.data)
        if items is None:
            return DeliveryReceipt(self.destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_INVALID_RESPONSE)
        # The first run opens the issue with the key's label added;
        # every later run comments on it.
        number = GitHubResponses.first_issue(items)
        if number is None:
            request = GitHubRequests.issue(self._repo, self._token, content.title, GitHubRequests.body(content.body, None), (*self._labels, label))
            return await OutputHttp.post(self.destination, request)
        request = GitHubRequests.comment(self._repo, self._token, number, GitHubRequests.body(OutputText.chat_text(content), None))
        return await OutputHttp.post(self.destination, request)

    async def _sticky_comment(self, content: OutputContent, number: int, key: str) -> DeliveryReceipt:
        # @intent github-sticky-comment-reads-then-writes-once
        # Pages of comments are read oldest first, at most
        # GITHUB_MAX_PAGES of them, until the comment marked with the
        # key is found; then exactly one write. A failed read ends the
        # send before anything is written, and a failed edit never
        # falls back to a new comment.
        marker = GITHUB_MARKER_PREFIX + key + GITHUB_MARKER_SUFFIX
        body = GitHubRequests.body(OutputText.chat_text(content), marker)
        for page in range(GITHUB_FIRST_PAGE, GITHUB_FIRST_PAGE + GITHUB_MAX_PAGES):
            read = await OutputHttp.read(self.destination, GitHubRequests.comments_page(self._repo, self._token, number, page))
            if read.failure is not None:
                return read.failure
            items = GitHubResponses.items(read.data)
            if items is None:
                return DeliveryReceipt(self.destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_INVALID_RESPONSE)
            # The marked comment is edited in place.
            found = GitHubResponses.marked_comment(items, marker)
            if found is not None:
                return await OutputHttp.patch(self.destination, GitHubRequests.edit(self._repo, self._token, found, body))
            # A short page is the last one.
            if len(items) < GITHUB_PAGE_SIZE:
                break
        # No marked comment yet, so the first one is posted.
        return await OutputHttp.post(self.destination, GitHubRequests.comment(self._repo, self._token, number, body))


__all__ = ["GitHubIssueOutput"]
