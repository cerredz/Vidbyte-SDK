"""FILE: vidbyte/lib/outputs/webhook.py

PURPOSE: Defines WebhookOutput, which posts each finished agent reply as JSON to any https receiver (Make, n8n, Pipedream, Zapier, Power Automate).
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one OutputRequest and hands it to OutputHttp; the receiver URL is the credential. Fixed headers, a custom payload, and a Standard Webhooks signature are each opt-in; without secret= the request is unsigned.
COMMON MODIFICATION PATTERNS: Add an envelope key here only when every receiver can ignore it; receivers parse the JSON themselves, and a caller who needs another shape passes payload=.
KNOWN EDGE CASES: A structured mapping is sent as-is, so a value JSON cannot encode fails that send as unexpected:TypeError, as does a payload= that returns a non-mapping.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py and test_output_connectors_webhook_options.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping
from uuid import uuid4

from pydantic import BaseModel

from vidbyte.lib.constants.outputs import (
    OUTPUT_JSON_CONTENT_TYPE,
    WEBHOOK_ID_HEADER,
    WEBHOOK_ID_PREFIX,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_SIGNATURE_VERSION,
    WEBHOOK_TIMESTAMP_HEADER,
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


class WebhookOutput(BaseOutput):
    """Posts each reply as one JSON document to a webhook receiver, optionally with fixed headers, a custom payload, and a signature."""

    destination = OutputDestination.WEBHOOK

    def __init__(
        self,
        *,
        url: str | None = None,
        headers: Mapping[str, str] | None = None,
        payload: Callable[[AgentMessage, OutputContent], Mapping[str, object]] | None = None,
        secret: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        self._url = OutputArguments.https_url(OutputArguments.credential(self.destination, url, parameter="url"), parameter="url")
        self._headers = {} if headers is None else OutputArguments.headers(headers, parameter="headers")
        self._payload = OutputArguments.optional_callable(payload, parameter="payload")
        # @intent webhook-secret-is-kept-as-key-bytes
        # The secret is decoded once into the HMAC key and kept only as
        # bytes; its errors never show it, and repr shows '***'.
        self._key = None if secret is None else OutputArguments.signing_key(secret, parameter="secret")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Post the agent name, title, body, and structured output as one JSON document, or the payload= mapping, signed when secret= is set."""
        # @intent webhook-payload-is-plain-json
        # Receivers get the full title and body plus the agent's
        # structured output in JSON form, or the caller's own mapping;
        # nothing is cut.
        body: object
        if self._payload is None:
            body = {"agent": reply.sender, "title": content.title, "body": content.body, "structured": WebhookOutput._structured_json(reply.structured)}
        else:
            body = self._payload(reply, content)
        # A payload that is not a JSON object fails only this output.
        if not isinstance(body, Mapping):
            raise TypeError(f"payload must return a mapping, got {type(body).__name__}.")
        # Without a secret, the JSON goes out as today, with the fixed
        # headers.
        if self._key is None:
            return await OutputHttp.post(self.destination, OutputRequest(self._url, dict(self._headers), body))
        # With a secret, the body is serialized once, and those exact
        # bytes are both signed and sent, so the signature matches the
        # wire.
        wire = json.dumps(body).encode("utf-8")
        request = OutputRequest(self._url, WebhookOutput._signed_headers(self._headers, self._key, wire), None, content=wire)
        return await OutputHttp.post(self.destination, request)

    @staticmethod
    def _structured_json(structured: object) -> object:
        # A pydantic model becomes its JSON form; a JSON value passes
        # through as-is; anything else is dropped.
        if isinstance(structured, BaseModel):
            return structured.model_dump(mode="json")
        if isinstance(structured, (dict, list, str, int, float, bool)):
            return structured
        return None

    @staticmethod
    def _signed_headers(headers: Mapping[str, str], key: bytes, wire: bytes) -> dict[str, str]:
        # @intent webhook-signature-covers-the-wire-bytes
        # Standard Webhooks: one id and one timestamp per send, reused
        # by the 429 retries, and a base64 HMAC-SHA256 over
        # "{id}.{timestamp}." plus the exact bytes sent. These headers
        # are set after the caller's, so they cannot be forged.
        message_id = WEBHOOK_ID_PREFIX + uuid4().hex
        timestamp = str(int(time.time()))
        digest = hmac.new(key, f"{message_id}.{timestamp}.".encode() + wire, hashlib.sha256).digest()
        signature = f"{WEBHOOK_SIGNATURE_VERSION},{base64.b64encode(digest).decode()}"
        return {**headers, "content-type": OUTPUT_JSON_CONTENT_TYPE, WEBHOOK_ID_HEADER: message_id, WEBHOOK_TIMESTAMP_HEADER: timestamp, WEBHOOK_SIGNATURE_HEADER: signature}


__all__ = ["WebhookOutput"]
