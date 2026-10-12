"""FILE: vidbyte/lib/outputs/webhook.py

PURPOSE: Defines WebhookOutput, which posts each finished agent reply as JSON to any https receiver (Make, n8n, Pipedream, Zapier, Power Automate).
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the receiver URL is the credential and the request is unsigned.
COMMON MODIFICATION PATTERNS: Add a payload key here only when every receiver can ignore it; receivers parse the JSON themselves.
KNOWN EDGE CASES: A structured mapping is sent as-is, so a value JSON cannot encode fails that send as unexpected:TypeError.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp


class WebhookOutput(BaseOutput):
    """Posts each reply as one JSON document to a webhook receiver."""

    destination = OutputDestination.WEBHOOK

    def __init__(self, *, url: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._url = OutputArguments.https_url(OutputArguments.credential(self.destination, url, parameter="url"), parameter="url")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the agent name, title, body, and structured output as one JSON document."""
        # @intent webhook-payload-is-plain-json
        # Receivers get the full title and body plus the agent's
        # structured output in JSON form; nothing is cut or signed.
        body = {"agent": reply.sender, "title": content.title, "body": content.body, "structured": WebhookOutput._structured_json(reply.structured)}
        return await OutputHttp.post(self.destination, OutputRequest(self._url, {}, body))

    @staticmethod
    def _structured_json(structured: object) -> object:
        # A pydantic model becomes its JSON form; a JSON value passes
        # through as-is; anything else is dropped.
        if isinstance(structured, BaseModel):
            return structured.model_dump(mode="json")
        if isinstance(structured, (dict, list, str, int, float, bool)):
            return structured
        return None


__all__ = ["WebhookOutput"]
