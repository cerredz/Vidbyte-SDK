"""FILE: vidbyte/lib/outputs/slack.py

PURPOSE: Defines SlackOutput, which posts each finished agent reply to one Slack channel through an incoming webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the webhook URL is the credential.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow Slack's incoming-webhook reference.
KNOWN EDGE CASES: Slack answers errors with plain-text tokens such as no_service, which become http_<status>:<token> codes.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import SLACK_TEXT_MAX_CHARS
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
        """Post the title and body as one plain-text Slack message."""
        # @intent slack-text-cannot-ping-the-channel
        # Escaping &, <, and > stops <!channel> and <!here> from pinging
        # everyone. It runs after the cut, so no &amp; is cut in half.
        text = OutputText.truncate(OutputText.chat_text(content), SLACK_TEXT_MAX_CHARS)
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        request = OutputRequest(self._webhook_url, {"content-type": "application/json"}, {"text": escaped})
        return await OutputHttp.post(self.destination, request)


__all__ = ["SlackOutput"]
