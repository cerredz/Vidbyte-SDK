"""FILE: vidbyte/lib/outputs/teams.py

PURPOSE: Defines TeamsOutput, which posts each finished agent reply to a Microsoft Teams channel through a Workflows webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one Adaptive Card OutputRequest and hands it to OutputHttp; the webhook URL carries the SAS signature.
COMMON MODIFICATION PATTERNS: Change the card here only to follow the Workflows "When a Teams webhook request is received" trigger.
KNOWN EDGE CASES: The host is never checked, because Microsoft has moved Workflows URLs between hosts; a 202 means accepted, not posted.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://learn.microsoft.com/en-us/connectors/teams/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    TEAMS_ADAPTIVE_CARD_VERSION,
    TEAMS_TEXT_MAX_CHARS,
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


class TeamsOutput(BaseOutput):
    """Posts each reply to a Teams channel as one Adaptive Card text block."""

    destination = OutputDestination.TEAMS

    def __init__(self, *, webhook_url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the title and body as one Adaptive Card with a single text block."""
        # @intent teams-text-is-plain
        # A TextBlock renders the text as plain text, so model-written
        # markup cannot mention a person or the whole channel.
        text = OutputText.truncate(OutputText.chat_text(content), TEAMS_TEXT_MAX_CHARS)
        card = {"type": "AdaptiveCard", "version": TEAMS_ADAPTIVE_CARD_VERSION, "body": [{"type": "TextBlock", "text": text, "wrap": True}]}
        attachment = {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}
        request = OutputRequest(self._webhook_url, {}, {"type": "message", "attachments": [attachment]})
        return await OutputHttp.post(self.destination, request)


__all__ = ["TeamsOutput"]
