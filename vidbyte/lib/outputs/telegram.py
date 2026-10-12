"""FILE: vidbyte/lib/outputs/telegram.py

PURPOSE: Defines TelegramOutput, which sends each finished agent reply to one Telegram chat through a bot.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one sendMessage OutputRequest and hands it to OutputHttp; the bot token sits in the URL path.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow the Bot API sendMessage reference.
KNOWN EDGE CASES: Text is sent with no parse_mode, so it stays plain; an @username in group text still notifies that user.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://core.telegram.org/bots/api
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import TELEGRAM_API_URL, TELEGRAM_TEXT_MAX_CHARS
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class TelegramOutput(BaseOutput):
    """Sends each reply to one Telegram chat as a plain-text bot message."""

    destination = OutputDestination.TELEGRAM

    def __init__(self, *, chat_id: int | str, bot_token: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        # A chat is a numeric id or an @channel name, never a bool.
        if isinstance(chat_id, int) and not isinstance(chat_id, bool):
            self._chat_id: int | str = chat_id
        elif isinstance(chat_id, str):
            self._chat_id = OutputArguments.text(chat_id, parameter="chat_id")
        else:
            raise ConfigurationError(f"chat_id must be an int or a non-blank string, got {chat_id!r}.", details={"parameter": "chat_id"})
        self._bot_token = OutputArguments.credential(self.destination, bot_token, parameter="bot_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Send the title and body as one plain-text Telegram message."""
        # @intent telegram-text-is-plain
        # No parse_mode is sent, so model-written markup is shown as
        # typed and cannot break the message or hide a link.
        text = OutputText.truncate(OutputText.chat_text(content), TELEGRAM_TEXT_MAX_CHARS)
        request = OutputRequest(f"{TELEGRAM_API_URL}/bot{self._bot_token}/sendMessage", {}, {"chat_id": self._chat_id, "text": text})
        return await OutputHttp.post(self.destination, request)


__all__ = ["TelegramOutput"]
