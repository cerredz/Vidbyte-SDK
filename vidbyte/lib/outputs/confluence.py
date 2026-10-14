"""FILE: vidbyte/lib/outputs/confluence.py

PURPOSE: Defines ConfluencePageOutput, which creates one Confluence Cloud page per finished agent reply in a fixed space.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one REST v2 OutputRequest whose body OutputAdf turns into ADF, and hands it to OutputHttp; auth is Basic email:token.
COMMON MODIFICATION PATTERNS: Keep the body in Atlassian Document Format, sent as a JSON string, as Jira's description is built.
KNOWN EDGE CASES: Confluence returns a site-relative webui path, so the receipt link is built from the site; a title already used in the space is refused; scoped tokens are unsupported.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/#api-pages-post
TESTS: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    CONFLUENCE_BODY_MAX_CHARS,
    CONFLUENCE_ID_PATTERN,
    CONFLUENCE_PAGE_STATUS,
    CONFLUENCE_PAGES_PATH,
    CONFLUENCE_REPRESENTATION,
    CONFLUENCE_WEB_PREFIX,
    JIRA_SITE_PATTERN,
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


class ConfluencePageOutput(BaseOutput):
    """Creates one Confluence page per reply in a fixed space, under a fixed parent page when one is given."""

    destination = OutputDestination.CONFLUENCE_PAGE

    def __init__(
        self,
        *,
        site: str,
        space_id: str | int,
        email: str,
        parent_id: str | int | None = None,
        api_token: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        # @intent confluence-site-is-a-bare-atlassian-host
        # The site is checked as a bare *.atlassian.net host, so the
        # Basic credentials can never be sent to another server.
        self._site = OutputArguments.matching(site, JIRA_SITE_PATTERN, parameter="site")
        self._space_id = OutputArguments.reference(space_id, CONFLUENCE_ID_PATTERN, parameter="space_id")
        self._parent_id = None if parent_id is None else OutputArguments.reference(parent_id, CONFLUENCE_ID_PATTERN, parameter="parent_id")
        self._email = OutputArguments.address(email, parameter="email")
        self._api_token = OutputArguments.credential(self.destination, api_token, parameter="api_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one published page titled with the reply title, holding the body as rich text."""
        headers = {"authorization": "Basic " + base64.b64encode(f"{self._email}:{self._api_token}".encode()).decode()}
        # The body keeps its headings, lists, and code blocks as ADF,
        # which Confluence takes as a JSON string.
        document = OutputAdf.document(OutputText.truncate(content.body, CONFLUENCE_BODY_MAX_CHARS))
        page: dict[str, object] = {
            "spaceId": self._space_id,
            "status": CONFLUENCE_PAGE_STATUS,
            "title": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS),
            "body": {"representation": CONFLUENCE_REPRESENTATION, "value": json.dumps(document)},
        }
        # Without a parent, the page lands at the top of the space.
        if self._parent_id is not None:
            page["parentId"] = self._parent_id
        # @intent confluence-page-link-is-built-from-the-site
        # Confluence returns only a site-relative webui path, so the
        # link is built from the checked site; a 2xx without it is
        # FAILED.
        request = OutputRequest(f"https://{self._site}{CONFLUENCE_PAGES_PATH}", headers, page, link_path=("_links", "webui"), link_prefix=f"https://{self._site}{CONFLUENCE_WEB_PREFIX}")
        return await OutputHttp.post(self.destination, request)


__all__ = ["ConfluencePageOutput"]
