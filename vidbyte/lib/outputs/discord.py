"""FILE: vidbyte/lib/outputs/discord.py

PURPOSE: Defines DiscordOutput, which posts each finished agent reply to one Discord channel through a channel webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the webhook URL is the credential.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow Discord's Execute Webhook reference.
KNOWN EDGE CASES: Discord answers 204 with no body by default, so the receipt carries no link.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.discord.com/developers/resources/webhook
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import DISCORD_CONTENT_MAX_CHARS
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


class DiscordOutput(BaseOutput):
    """Posts each reply to one Discord channel through a channel webhook."""

    destination = OutputDestination.DISCORD

    def __init__(self, *, webhook_url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the title and body as one Discord message."""
        # @intent discord-text-cannot-ping-everyone
        # An empty allowed_mentions.parse list stops @everyone, @here,
        # and role pings in model-written text from notifying anyone.
        text = OutputText.truncate(OutputText.chat_text(content), DISCORD_CONTENT_MAX_CHARS)
        request = OutputRequest(self._webhook_url, {}, {"content": text, "allowed_mentions": {"parse": []}})
        return await OutputHttp.post(self.destination, request)


__all__ = ["DiscordOutput"]
