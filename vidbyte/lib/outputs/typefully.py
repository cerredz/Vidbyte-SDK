"""FILE: vidbyte/lib/outputs/typefully.py

PURPOSE: Defines TypefullyDraftOutput, which saves each finished agent reply as one Typefully draft for the chosen social platforms.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one v2 drafts OutputRequest and hands it to OutputHttp; auth is a Bearer API key.
COMMON MODIFICATION PATTERNS: Add a platform as one TypefullyPlatform member in vidbyte/lib/enums/outputs.py after checking Typefully's API reference.
KNOWN EDGE CASES: Nothing is ever published or scheduled: a person publishes the draft in Typefully; each platform gets the body as one post.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://typefully.com/docs/api
TESTS: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from vidbyte.lib.constants.outputs import (
    OUTPUT_TITLE_MAX_CHARS,
    TYPEFULLY_DRAFTS_PATH,
    TYPEFULLY_ID_PATTERN,
    TYPEFULLY_SOCIAL_SETS_URL,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination, TypefullyPlatform
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class TypefullyDraftOutput(BaseOutput):
    """Saves each reply as one Typefully draft in a fixed social set, for the chosen platforms."""

    destination = OutputDestination.TYPEFULLY_DRAFT

    def __init__(self, *, social_set_id: str | int, platforms: Sequence[TypefullyPlatform | str], api_key: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._social_set_id = OutputArguments.reference(social_set_id, TYPEFULLY_ID_PATTERN, parameter="social_set_id")
        self._platforms = OutputArguments.members(platforms, TypefullyPlatform, parameter="platforms")
        self._api_key = OutputArguments.credential(self.destination, api_key, parameter="api_key")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Save one draft titled with the reply title, with the body as one post on each chosen platform."""
        # @intent typefully-only-creates-drafts
        # No publish_at, plan_at, or share is ever sent, so the draft
        # waits for a person to publish it; an agent never posts in
        # public on its own.
        post = {"enabled": True, "posts": [{"text": content.body}]}
        draft = {"draft_title": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "platforms": {platform.value: post for platform in self._platforms}}
        request = OutputRequest(f"{TYPEFULLY_SOCIAL_SETS_URL}/{self._social_set_id}{TYPEFULLY_DRAFTS_PATH}", {"authorization": f"Bearer {self._api_key}"}, draft, link_path=("private_url",))
        return await OutputHttp.post(self.destination, request)


__all__ = ["TypefullyDraftOutput"]
