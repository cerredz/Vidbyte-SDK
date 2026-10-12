"""FILE: vidbyte/lib/outputs/linear.py

PURPOSE: Defines LinearIssueOutput, which creates one Linear issue per finished agent reply.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one GraphQL issueCreate OutputRequest and hands it to OutputHttp; the receipt links the created issue.
COMMON MODIFICATION PATTERNS: Change LINEAR_ISSUE_CREATE_MUTATION in vidbyte/lib/constants/outputs.py only with Linear's schema open.
KNOWN EDGE CASES: Linear can answer 200 with errors[] and no issue, which becomes FAILED invalid_response; the key takes no Bearer prefix.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://linear.app/developers/graphql
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    LINEAR_GRAPHQL_URL,
    LINEAR_ISSUE_CREATE_MUTATION,
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
    """Creates one Linear issue per reply in a fixed team."""

    destination = OutputDestination.LINEAR_ISSUE

    def __init__(self, *, team_id: str, api_key: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._team_id = OutputArguments.identifier(team_id, parameter="team_id")
        self._api_key = OutputArguments.credential(self.destination, api_key, parameter="api_key")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one issue with a one-line title and the markdown body."""
        # @intent linear-success-needs-the-issue-link
        # Linear reports some failures as 200 with errors[], so only a
        # response that carries the new issue's URL counts as sent.
        issue = {"teamId": self._team_id, "title": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "description": content.body}
        body = {"query": LINEAR_ISSUE_CREATE_MUTATION, "variables": {"input": issue}}
        request = OutputRequest(LINEAR_GRAPHQL_URL, {"authorization": self._api_key}, body, link_path=("data", "issueCreate", "issue", "url"))
        return await OutputHttp.post(self.destination, request)


__all__ = ["LinearIssueOutput"]
