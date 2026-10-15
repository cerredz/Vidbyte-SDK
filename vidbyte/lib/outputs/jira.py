"""FILE: vidbyte/lib/outputs/jira.py

PURPOSE: Defines JiraIssueOutput, which creates one Jira Cloud issue per finished agent reply, or adds it as a comment on one existing issue.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one REST v3 OutputRequest whose text OutputAdf turns into ADF blocks, and hands it to OutputHttp; auth is Basic email:token.
COMMON MODIFICATION PATTERNS: Keep the description in Atlassian Document Format; v3 rejects a plain-string description.
KNOWN EDGE CASES: Jira returns only the issue key or the comment id, so the receipt link is built from the site; scoped tokens are unsupported; issue_type is ignored in comment mode.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_comments.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    JIRA_BROWSE_PATH,
    JIRA_COMMENT_PATH,
    JIRA_DEFAULT_ISSUE_TYPE,
    JIRA_FOCUSED_COMMENT_QUERY,
    JIRA_ISSUE_KEY_PATTERN,
    JIRA_ISSUE_PATH,
    JIRA_LABEL_PATTERN,
    JIRA_SITE_PATTERN,
    JIRA_TEXT_MAX_CHARS,
    OUTPUT_TITLE_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.adf import OutputAdf
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class JiraIssueOutput(BaseOutput):
    """Creates one Jira Cloud issue per reply in a fixed site and project, or comments on one fixed issue."""

    destination = OutputDestination.JIRA_ISSUE

    def __init__(
        self,
        *,
        site: str,
        project: str | None = None,
        email: str,
        issue_type: str = JIRA_DEFAULT_ISSUE_TYPE,
        labels: Sequence[str] = (),
        comment_on: str | None = None,
        api_token: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        # @intent jira-site-is-a-bare-atlassian-host
        # The site is checked as a bare *.atlassian.net host, so the
        # Basic credentials can never be sent to another server.
        self._site = OutputArguments.matching(site, JIRA_SITE_PATTERN, parameter="site")
        self._project = None if project is None else OutputArguments.text(project, parameter="project")
        self._email = OutputArguments.address(email, parameter="email")
        self._issue_type = OutputArguments.text(issue_type, parameter="issue_type")
        self._labels = tuple(OutputArguments.matching(label, JIRA_LABEL_PATTERN, parameter="labels") for label in OutputArguments.texts(labels, parameter="labels"))
        self._comment_on = None if comment_on is None else OutputArguments.matching(comment_on, JIRA_ISSUE_KEY_PATTERN, parameter="comment_on")
        # A comment goes to one existing issue, so it takes no project
        # and no labels; one of the two targets is required.
        OutputArguments.exclusive({"project": self._project, "comment_on": self._comment_on}, required=True)
        OutputArguments.exclusive({"labels": self._labels, "comment_on": self._comment_on})
        self._api_token = OutputArguments.credential(self.destination, api_token, parameter="api_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one issue with a one-line summary and a rich-text description, or comment on the configured issue."""
        headers = {"authorization": OutputHttp.basic_authorization(self._email, self._api_token)}
        # @intent jira-comment-link-is-built-from-its-id
        # A comment has no title field, so it carries the chat text.
        # Jira returns only the comment's id, so the link is built from
        # the checked site and issue key; a 2xx with no id is FAILED.
        if self._comment_on is not None:
            document = OutputAdf.document(OutputText.truncate(OutputText.chat_text(content), JIRA_TEXT_MAX_CHARS))
            issue_link = f"https://{self._site}{JIRA_BROWSE_PATH}{self._comment_on}{JIRA_FOCUSED_COMMENT_QUERY}"
            request = OutputRequest(f"https://{self._site}{JIRA_ISSUE_PATH}/{self._comment_on}{JIRA_COMMENT_PATH}", headers, {"body": document}, link_path=("id",), link_prefix=issue_link)
            return await OutputHttp.post(self.destination, request)
        # A new issue gets the title as its summary and the body, with
        # its headings, lists, and code blocks, as its description.
        fields: dict[str, object] = {
            "project": {"key": self._project},
            "issuetype": {"name": self._issue_type},
            "summary": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS),
            "description": OutputAdf.document(OutputText.truncate(content.body, JIRA_TEXT_MAX_CHARS)),
        }
        if self._labels:
            fields["labels"] = list(self._labels)
        # @intent jira-issue-link-is-built-from-the-key
        # Jira returns only the new issue's key, so the link is built
        # from the checked site; a 2xx with no key is FAILED.
        request = OutputRequest(f"https://{self._site}{JIRA_ISSUE_PATH}", headers, {"fields": fields}, link_path=("key",), link_prefix=f"https://{self._site}{JIRA_BROWSE_PATH}")
        return await OutputHttp.post(self.destination, request)


__all__ = ["JiraIssueOutput"]
