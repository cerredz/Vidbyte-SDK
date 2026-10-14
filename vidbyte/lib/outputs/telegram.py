"""FILE: vidbyte/lib/outputs/telegram.py

PURPOSE: Defines TelegramOutput, which sends each finished agent reply to one Telegram chat, or one forum topic in it, as a bot's rich Markdown message.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one sendRichMessage OutputRequest and hands it to OutputHttp; the bot token sits in the URL path.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow the Bot API sendRichMessage reference.
KNOWN EDGE CASES: Every < shows as ＜ and every ![ as !［, so no HTML tag, button, or media block opens, and code containing < will not run when copied; an @username or a tg://user?id= link still notifies that user.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://core.telegram.org/bots/api
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_rendering.py
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.lib.constants.outputs import (
    TELEGRAM_API_URL,
    TELEGRAM_MEDIA_PREFIX,
    TELEGRAM_MEDIA_REPLACEMENT,
    TELEGRAM_RICH_METHOD,
    TELEGRAM_RICH_TEXT_MAX_CHARS,
    TELEGRAM_TAG_PREFIX,
    TELEGRAM_TAG_REPLACEMENT,
)
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
    """Sends each reply to one Telegram chat, or one forum topic in it, as a rich Markdown bot message."""

    destination = OutputDestination.TELEGRAM

    def __init__(self, *, chat_id: int | str, topic_id: int | None = None, bot_token: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        # A chat is a numeric id or an @channel name, never a bool.
        if isinstance(chat_id, int) and not isinstance(chat_id, bool):
            self._chat_id: int | str = chat_id
        elif isinstance(chat_id, str):
            self._chat_id = OutputArguments.text(chat_id, parameter="chat_id")
        else:
            raise ConfigurationError(f"chat_id must be an int or a non-blank string, got {chat_id!r}.", details={"parameter": "chat_id"})
        self._topic_id = None if topic_id is None else OutputArguments.number(topic_id, parameter="topic_id")
        self._bot_token = OutputArguments.credential(self.destination, bot_token, parameter="bot_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Send the title and body as one rich Markdown Telegram message, in the forum topic when one is set."""
        # @intent telegram-rich-text-carries-no-html-or-media
        # The reply is sent as rich Markdown on purpose. Every "<"
        # becomes "＜", so no HTML tag, and so no tg-button, reaches
        # the chat. Every "![" becomes "!［", so no media block opens
        # and model output cannot make the bot post a file. Personal
        # mentions, tg://user?id= links included, still notify.
        text = OutputText.chat_text(content).replace(TELEGRAM_TAG_PREFIX, TELEGRAM_TAG_REPLACEMENT).replace(TELEGRAM_MEDIA_PREFIX, TELEGRAM_MEDIA_REPLACEMENT)
        body: dict[str, object] = {"chat_id": self._chat_id, "rich_message": {"markdown": OutputText.truncate(text, TELEGRAM_RICH_TEXT_MAX_CHARS)}}
        # A forum topic is chosen by its thread id.
        if self._topic_id is not None:
            body["message_thread_id"] = self._topic_id
        request = OutputRequest(f"{TELEGRAM_API_URL}/bot{self._bot_token}/{TELEGRAM_RICH_METHOD}", {}, body)
        return await OutputHttp.post(self.destination, request)


__all__ = ["TelegramOutput"]
