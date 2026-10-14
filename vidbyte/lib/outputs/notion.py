"""FILE: vidbyte/lib/outputs/notion.py

PURPOSE: Defines NotionPageOutput, which creates one Notion page per finished agent reply under a fixed parent page, or appends it to the end of one existing page.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one pages-create OutputRequest using Notion's markdown body parameter, or one update-page-markdown insert_content PATCH, and hands it to OutputHttp.
COMMON MODIFICATION PATTERNS: Bump NOTION_API_VERSION in vidbyte/lib/constants/outputs.py after checking Notion's versioning page.
KNOWN EDGE CASES: An internal integration must be shared on the parent or appended page, or Notion answers 404; mention tags are neutralized; an append answer has no page link, so its receipt has none.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developers.notion.com/reference/post-page; https://developers.notion.com/reference/update-page-markdown
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_comments.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    NOTION_API_VERSION,
    NOTION_INSERT_COMMAND,
    NOTION_MARKDOWN_PATH,
    NOTION_MENTION_PREFIX,
    NOTION_MENTION_REPLACEMENT,
    NOTION_PAGES_URL,
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


class NotionPageOutput(BaseOutput):
    """Creates one Notion page per reply under a fixed parent page, or appends each reply to one fixed page."""

    destination = OutputDestination.NOTION_PAGE

    def __init__(self, *, parent_page_id: str | None = None, append_to: str | None = None, api_key: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._parent_page_id = None if parent_page_id is None else OutputArguments.identifier(parent_page_id, parameter="parent_page_id")
        self._append_to = None if append_to is None else OutputArguments.identifier(append_to, parameter="append_to")
        # Exactly one target: a parent for new pages, or a page to
        # append to.
        OutputArguments.exclusive({"parent_page_id": self._parent_page_id, "append_to": self._append_to}, required=True)
        self._api_key = OutputArguments.credential(self.destination, api_key, parameter="api_key")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one page titled with the reply title and holding its markdown body, or append the reply to the configured page."""
        # @intent notion-markdown-cannot-mention-people
        # Notion's markdown turns <mention-user/> tags into
        # notifications, so "<mention-" is replaced before sending, in
        # a new page and in an append alike.
        headers = {"authorization": f"Bearer {self._api_key}", "notion-version": NOTION_API_VERSION}
        # An append inserts the chat text at the end of the page, since
        # it has no title field; Notion's answer carries no page link.
        if self._append_to is not None:
            text = OutputText.chat_text(content).replace(NOTION_MENTION_PREFIX, NOTION_MENTION_REPLACEMENT)
            body: dict[str, object] = {"type": NOTION_INSERT_COMMAND, NOTION_INSERT_COMMAND: {"content": text}}
            return await OutputHttp.patch(self.destination, OutputRequest(f"{NOTION_PAGES_URL}/{self._append_to}{NOTION_MARKDOWN_PATH}", headers, body))
        # A new page is titled with the one-line title and holds the
        # body as Markdown.
        title = [{"text": {"content": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS)}}]
        body = {
            "parent": {"type": "page_id", "page_id": self._parent_page_id},
            "properties": {"title": {"title": title}},
            "markdown": content.body.replace(NOTION_MENTION_PREFIX, NOTION_MENTION_REPLACEMENT),
        }
        return await OutputHttp.post(self.destination, OutputRequest(NOTION_PAGES_URL, headers, body, link_path=("url",)))


__all__ = ["NotionPageOutput"]
