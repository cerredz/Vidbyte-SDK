"""FILE: vidbyte/lib/outputs/slack.py

PURPOSE: Defines SlackOutput, which posts each finished agent reply to one Slack channel through an incoming webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the webhook URL is the credential. A reply of up to 12,000 characters goes as a markdown block, a longer one as escaped plain text.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow Slack's incoming-webhook reference.
KNOWN EDGE CASES: Slack answers errors with plain-text tokens such as no_service, which become http_<status>:<token> codes.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    OUTPUT_TITLE_MAX_CHARS,
    SLACK_BROADCAST_PREFIX,
    SLACK_BROADCAST_REPLACEMENT,
    SLACK_MARKDOWN_MAX_CHARS,
    SLACK_TEXT_MAX_CHARS,
    SLACK_USER_MENTION_PREFIX,
    SLACK_USER_MENTION_REPLACEMENT,
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


class SlackOutput(BaseOutput):
    """Posts each reply to one Slack channel through an incoming webhook."""

    destination = OutputDestination.SLACK

    def __init__(self, *, webhook_url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the reply as a Markdown block under its one-line title, or, above 12,000 characters, as escaped plain text."""
        chat = OutputText.chat_text(content)
        # @intent slack-markdown-cannot-ping
        # Slack does not say whether a markdown block parses mentions,
        # so "<!" and "<@" become the fullwidth "＜!" and "＜@", which
        # keep the length and cannot ping. The notification text is
        # the one-line title, cut first and then escaped.
        if len(chat) <= SLACK_MARKDOWN_MAX_CHARS:
            markdown = chat.replace(SLACK_BROADCAST_PREFIX, SLACK_BROADCAST_REPLACEMENT).replace(SLACK_USER_MENTION_PREFIX, SLACK_USER_MENTION_REPLACEMENT)
            title = SlackOutput._escape(OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS))
            body: dict[str, object] = {"text": title, "blocks": [{"type": "markdown", "text": markdown}]}
        # @intent slack-text-cannot-ping-the-channel
        # A longer reply is plain text. Escaping &, <, and > stops
        # <!channel> and <!here> from pinging everyone. It runs after
        # the cut, so no &amp; is cut in half.
        else:
            body = {"text": SlackOutput._escape(OutputText.truncate(chat, SLACK_TEXT_MAX_CHARS))}
        request = OutputRequest(self._webhook_url, {"content-type": "application/json"}, body)
        return await OutputHttp.post(self.destination, request)

    @staticmethod
    def _escape(text: str) -> str:
        # Slack's three control characters, as its formatting guide says.
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = ["SlackOutput"]
