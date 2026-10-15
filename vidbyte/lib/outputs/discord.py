"""FILE: vidbyte/lib/outputs/discord.py

PURPOSE: Defines DiscordOutput, which posts each finished agent reply to one Discord channel, or as a new forum post, through a channel webhook.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the webhook URL is the credential.
COMMON MODIFICATION PATTERNS: Change the message body here only to follow Discord's Execute Webhook reference.
KNOWN EDGE CASES: Discord answers 204 with no body by default, so the receipt carries no link; it rejects thread_name on a channel that is not a forum, so forum=True is opt-in.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.discord.com/developers/resources/webhook
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_rendering.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    DISCORD_CONTENT_MAX_CHARS,
    DISCORD_SNOWFLAKE_PATTERN,
    DISCORD_THREAD_NAME_MAX_CHARS,
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


class DiscordOutput(BaseOutput):
    """Posts each reply to one Discord channel, or as a new forum post, through a channel webhook."""

    destination = OutputDestination.DISCORD

    def __init__(self, *, webhook_url: str | None = None, forum: bool = False, forum_tags: Sequence[str] = (), render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._forum = OutputArguments.flag(forum, parameter="forum")
        self._forum_tags = tuple(OutputArguments.matching(tag, DISCORD_SNOWFLAKE_PATTERN, parameter="forum_tags") for tag in OutputArguments.texts(forum_tags, parameter="forum_tags"))
        # Tags exist only on forum posts, so tags without forum=True
        # would be dropped by Discord without a word.
        if self._forum_tags and not self._forum:
            raise ConfigurationError("forum_tags needs forum=True.", details={"parameter": "forum_tags"})
        self._webhook_url = OutputArguments.https_url(OutputArguments.credential(self.destination, webhook_url, parameter="webhook_url"), parameter="webhook_url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the title and body as one Discord message, or as a new forum post named after the title."""
        # @intent discord-text-cannot-ping-everyone
        # An empty allowed_mentions.parse list stops @everyone, @here,
        # and role pings in model-written text from notifying anyone,
        # in a channel message and in a forum post alike.
        text = OutputText.truncate(OutputText.chat_text(content), DISCORD_CONTENT_MAX_CHARS)
        body: dict[str, object] = {"content": text, "allowed_mentions": {"parse": []}}
        # A forum post needs a one-line thread name, and carries the
        # forum's tags when they were given.
        if self._forum:
            body["thread_name"] = OutputText.single_line(content.title, DISCORD_THREAD_NAME_MAX_CHARS)
        if self._forum_tags:
            body["applied_tags"] = list(self._forum_tags)
        return await OutputHttp.post(self.destination, OutputRequest(self._webhook_url, {}, body))


__all__ = ["DiscordOutput"]
