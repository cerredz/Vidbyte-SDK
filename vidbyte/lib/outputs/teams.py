"""FILE: vidbyte/lib/outputs/teams.py

PURPOSE: Defines TeamsOutput, which posts each finished agent reply to a Microsoft Teams channel through a Workflows webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one full-width Adaptive Card OutputRequest, a bold title block over a body block, and hands it to OutputHttp; the webhook URL carries the SAS signature.
COMMON MODIFICATION PATTERNS: Change the card here only to follow the Workflows "When a Teams webhook request is received" trigger.
KNOWN EDGE CASES: The host is never checked, because Microsoft has moved Workflows URLs between hosts; a 202 means accepted, not posted.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://learn.microsoft.com/en-us/connectors/teams/
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    OUTPUT_TITLE_MAX_CHARS,
    TEAMS_ADAPTIVE_CARD_VERSION,
    TEAMS_CARD_WIDTH,
    TEAMS_TEXT_MAX_CHARS,
    TEAMS_TITLE_SIZE,
    TEAMS_TITLE_WEIGHT,
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
    """Posts each reply to a Teams channel as one full-width Adaptive Card with a bold title."""

    destination = OutputDestination.TEAMS

    def __init__(self, *, webhook_url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post one full-width Adaptive Card: the title in bold, then the body without a repeated title."""
        # @intent teams-text-is-plain
        # TextBlocks carry no mention entities, so model-written text
        # cannot mention a person or the whole channel.
        title = {"type": "TextBlock", "text": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "weight": TEAMS_TITLE_WEIGHT, "size": TEAMS_TITLE_SIZE, "wrap": True}
        text = OutputText.truncate(TeamsOutput._body_without_title(content), TEAMS_TEXT_MAX_CHARS)
        # A body that is only the title leaves no empty block behind.
        blocks = [title, {"type": "TextBlock", "text": text, "wrap": True}] if text.strip() else [title]
        card = {"type": "AdaptiveCard", "version": TEAMS_ADAPTIVE_CARD_VERSION, "body": blocks, "msteams": {"width": TEAMS_CARD_WIDTH}}
        attachment = {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}
        request = OutputRequest(self._webhook_url, {}, {"type": "message", "attachments": [attachment]})
        return await OutputHttp.post(self.destination, request)

    @staticmethod
    def _body_without_title(content: OutputContent) -> str:
        # The default shaping opens the body with the title, so that
        # line and the blank lines after it are dropped, and the title
        # shows once. A body that does not open with the title, from a
        # render= or a direct send, is kept whole.
        if OutputText.first_line(content.body) != content.title:
            return content.body
        lines = content.body.splitlines()
        first = next(index for index, line in enumerate(lines) if line.strip())
        return "\n".join(itertools.dropwhile(lambda line: not line.strip(), lines[first + 1 :]))


__all__ = ["TeamsOutput"]
