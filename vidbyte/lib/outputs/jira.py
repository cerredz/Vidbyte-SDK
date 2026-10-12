"""FILE: vidbyte/lib/outputs/jira.py

PURPOSE: Defines JiraIssueOutput, which creates one Jira Cloud issue per finished agent reply.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one REST v3 OutputRequest with an ADF description and hands it to OutputHttp; auth is Basic email:token.
COMMON MODIFICATION PATTERNS: Keep the description in Atlassian Document Format; v3 rejects a plain-string description.
KNOWN EDGE CASES: Jira returns only the issue key, so the receipt link is built as https://<site>/browse/<key>; scoped tokens are unsupported.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

import base64
from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    JIRA_ADF_VERSION,
    JIRA_DEFAULT_ISSUE_TYPE,
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
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class JiraIssueOutput(BaseOutput):
    """Creates one Jira Cloud issue per reply in a fixed site and project."""

    destination = OutputDestination.JIRA_ISSUE

    def __init__(
        self,
        *,
        site: str,
        project: str,
        email: str,
        issue_type: str = JIRA_DEFAULT_ISSUE_TYPE,
        api_token: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        # @intent jira-site-is-a-bare-atlassian-host
        # The site is checked as a bare *.atlassian.net host, so the
        # Basic credentials can never be sent to another server.
        self._site = OutputArguments.matching(site, JIRA_SITE_PATTERN, parameter="site")
        self._project = OutputArguments.text(project, parameter="project")
        self._email = OutputArguments.address(email, parameter="email")
        self._issue_type = OutputArguments.text(issue_type, parameter="issue_type")
        self._api_token = OutputArguments.credential(self.destination, api_token, parameter="api_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one issue with a one-line summary and one paragraph per body line."""
        basic = base64.b64encode(f"{self._email}:{self._api_token}".encode()).decode()
        lines = OutputText.truncate(content.body, JIRA_TEXT_MAX_CHARS).splitlines()
        paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in lines if line.strip()]
        fields = {
            "project": {"key": self._project},
            "issuetype": {"name": self._issue_type},
            "summary": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS),
            "description": {"type": "doc", "version": JIRA_ADF_VERSION, "content": paragraphs},
        }
        # @intent jira-issue-link-is-built-from-the-key
        # Jira returns only the new issue's key, so the link is built
        # from the checked site; a 2xx with no key is FAILED.
        request = OutputRequest(f"https://{self._site}/rest/api/3/issue", {"authorization": f"Basic {basic}"}, {"fields": fields}, link_path=("key",), link_prefix=f"https://{self._site}/browse/")
        return await OutputHttp.post(self.destination, request)


__all__ = ["JiraIssueOutput"]
