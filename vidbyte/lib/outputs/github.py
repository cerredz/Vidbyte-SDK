"""FILE: vidbyte/lib/outputs/github.py

PURPOSE: Defines GitHubIssueOutput, which opens one GitHub issue per finished agent reply.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one REST OutputRequest and hands it to OutputHttp; the receipt links the created issue's html_url.
COMMON MODIFICATION PATTERNS: Bump GITHUB_API_VERSION in vidbyte/lib/constants/outputs.py after checking the REST changelog.
KNOWN EDGE CASES: GitHub silently drops labels unless the token has push access; an @user in the body notifies that user.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.github.com/en/rest/issues/issues#create-an-issue
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    GITHUB_API_URL,
    GITHUB_API_VERSION,
    GITHUB_BODY_MAX_CHARS,
    GITHUB_REPO_PATTERN,
    OUTPUT_TITLE_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class GitHubIssueOutput(BaseOutput):
    """Opens one GitHub issue per reply in a fixed owner/name repository."""

    destination = OutputDestination.GITHUB_ISSUE

    def __init__(self, *, repo: str, labels: Sequence[str] = (), token: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._repo = OutputArguments.matching(repo, GITHUB_REPO_PATTERN, parameter="repo")
        self._labels = OutputArguments.texts(labels, parameter="labels")
        self._token = OutputArguments.credential(self.destination, token, parameter="token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Open one issue with a one-line title, the body, and the configured labels."""
        # @intent github-issue-target-is-fixed
        # The repo and labels come only from the constructor, so model
        # output cannot move the issue or the token to another repo.
        title = OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS)
        body = OutputText.truncate(content.body, GITHUB_BODY_MAX_CHARS)
        headers = {"authorization": f"Bearer {self._token}", "accept": "application/vnd.github+json", "x-github-api-version": GITHUB_API_VERSION}
        request = OutputRequest(f"{GITHUB_API_URL}/repos/{self._repo}/issues", headers, {"title": title, "body": body, "labels": list(self._labels)}, link_path=("html_url",))
        return await OutputHttp.post(self.destination, request)


__all__ = ["GitHubIssueOutput"]
