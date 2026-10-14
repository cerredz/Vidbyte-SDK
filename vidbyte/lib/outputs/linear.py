"""FILE: vidbyte/lib/outputs/linear.py

PURPOSE: Defines LinearIssueOutput, which creates one Linear issue per finished agent reply, or adds it as a comment on one existing issue.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one GraphQL issueCreate or commentCreate OutputRequest and hands it to OutputHttp; the receipt links the created issue or comment.
COMMON MODIFICATION PATTERNS: Change LINEAR_ISSUE_CREATE_MUTATION or LINEAR_COMMENT_CREATE_MUTATION in vidbyte/lib/constants/outputs.py only with Linear's schema open.
KNOWN EDGE CASES: Linear can answer 200 with errors[] and no issue or comment, which becomes FAILED invalid_response; the key takes no Bearer prefix; labels are label UUIDs, not names.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://linear.app/developers/graphql
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_comments.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    LINEAR_COMMENT_CREATE_MUTATION,
    LINEAR_GRAPHQL_URL,
    LINEAR_ISSUE_CREATE_MUTATION,
    LINEAR_ISSUE_REF_PATTERN,
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


class LinearIssueOutput(BaseOutput):
    """Creates one Linear issue per reply in a fixed team, or comments on one fixed issue."""

    destination = OutputDestination.LINEAR_ISSUE

    def __init__(
        self,
        *,
        team_id: str | None = None,
        labels: Sequence[str] = (),
        comment_on: str | None = None,
        api_key: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        self._team_id = None if team_id is None else OutputArguments.identifier(team_id, parameter="team_id")
        self._labels = tuple(OutputArguments.identifier(label, parameter="labels") for label in OutputArguments.texts(labels, parameter="labels"))
        self._comment_on = None if comment_on is None else OutputArguments.matching(comment_on, LINEAR_ISSUE_REF_PATTERN, parameter="comment_on")
        # A comment goes to one existing issue, so it takes no team and
        # no labels; one of the two targets is required.
        OutputArguments.exclusive({"team_id": self._team_id, "comment_on": self._comment_on}, required=True)
        OutputArguments.exclusive({"labels": self._labels, "comment_on": self._comment_on})
        self._api_key = OutputArguments.credential(self.destination, api_key, parameter="api_key")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one issue with a one-line title and the markdown body, or comment on the configured issue."""
        # @intent linear-success-needs-the-issue-link
        # Linear reports some failures as 200 with errors[], so only a
        # response that carries the new issue's or comment's URL
        # counts as sent.
        headers = {"authorization": self._api_key}
        # A comment has no title field, so it carries the chat text;
        # the issue reference is sent as given.
        if self._comment_on is not None:
            comment = {"issueId": self._comment_on, "body": OutputText.chat_text(content)}
            body = {"query": LINEAR_COMMENT_CREATE_MUTATION, "variables": {"input": comment}}
            request = OutputRequest(LINEAR_GRAPHQL_URL, headers, body, link_path=("data", "commentCreate", "comment", "url"))
            return await OutputHttp.post(self.destination, request)
        # A new issue gets its labels only when some were given.
        issue: dict[str, object] = {"teamId": self._team_id, "title": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "description": content.body}
        if self._labels:
            issue["labelIds"] = list(self._labels)
        body = {"query": LINEAR_ISSUE_CREATE_MUTATION, "variables": {"input": issue}}
        request = OutputRequest(LINEAR_GRAPHQL_URL, headers, body, link_path=("data", "issueCreate", "issue", "url"))
        return await OutputHttp.post(self.destination, request)


__all__ = ["LinearIssueOutput"]
