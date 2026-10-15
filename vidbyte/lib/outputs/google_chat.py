"""FILE: vidbyte/lib/outputs/google_chat.py

PURPOSE: Defines GoogleChatOutput, which posts each finished agent reply to one Google Chat space through a space webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the key and token in the webhook URL are the credential.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow Google Chat's incoming-webhook reference.
KNOWN EDGE CASES: The text cap is the 32,000-byte limit divided by four bytes per character; the response carries no web link.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developers.google.com/workspace/chat/quickstart/webhooks
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    GOOGLE_CHAT_MENTION_PREFIX,
    GOOGLE_CHAT_MENTION_REPLACEMENT,
    GOOGLE_CHAT_TEXT_MAX_CHARS,
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


class GoogleChatOutput(BaseOutput):
    """Posts each reply to one Google Chat space through a space webhook."""

    destination = OutputDestination.GOOGLE_CHAT

    def __init__(self, *, webhook_url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the title and body as one Google Chat message."""
        # @intent google-chat-text-cannot-mention-all
        # Replacing "<users/" stops <users/all> in model-written text
        # from mentioning the whole space; the length is unchanged.
        text = OutputText.truncate(OutputText.chat_text(content), GOOGLE_CHAT_TEXT_MAX_CHARS)
        neutralized = text.replace(GOOGLE_CHAT_MENTION_PREFIX, GOOGLE_CHAT_MENTION_REPLACEMENT)
        request = OutputRequest(self._webhook_url, {"content-type": "application/json; charset=UTF-8"}, {"text": neutralized})
        return await OutputHttp.post(self.destination, request)


__all__ = ["GoogleChatOutput"]
