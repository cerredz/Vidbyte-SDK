"""FILE: tests/features/agent_output_connectors/test_output_connectors_webhook_options.py

PURPOSE: Prove the generic webhook's follow-up options: fixed headers (lowercased, validated, never shown), a custom payload that replaces the envelope, and Standard Webhooks signing whose signature covers exactly the bytes on the wire and survives a 429 retry unchanged; plus the HttpTransport content= option that carries those bytes verbatim.
ROLE IN CODEBASE: Contract and security tests of vidbyte/lib/outputs/webhook.py (WebhookOutput headers=, payload=, secret=), OutputArguments.headers and signing_key in vidbyte/lib/outputs/base.py, and vidbyte/lib/http/transport.py HttpTransport.request(content=).
ARCHITECTURE NOTE: The wire-bytes tests keep the real _send_once over httpx.MockTransport (httpx_destination), because only there are the bytes httpx sends visible; the retry and header-precedence tests script _send_once (fake_http). Signatures are recomputed with the standard library from what was recorded, never frozen.
FUNCTION INVENTORY: test_webhook_sends_fixed_headers_* and test_webhook_header_values_never_* (AC-10, INV-3, FR-13); test_invalid_webhook_headers_* (AC-10, EC-15, EC-16, INV-11); test_webhook_payload_* (AC-11, EC-18, EC-19, FR-14); test_signed_webhook_* and test_each_signed_send_* (AC-12, AC-13, INV-8, EC-17, FR-15); test_invalid_webhook_secret_* and test_webhook_secret_of_* (AC-14, D-5); test_transport_* (AC-15, FR-16).
COMMON MODIFICATION PATTERNS: Add a bad header or secret as one table row naming the text that must not appear in the error.
WHAT NOT TO DO IN THIS FILE: 1. Do not freeze time or uuid; read webhook-id and webhook-timestamp from the recorded request. 2. Do not verify a signature against json.dumps of the parsed body; verify against the recorded bytes.
KNOWN EDGE CASES: httpx adds content-length to a bytes body but no content-type, so a duplicated or missing content-type shows on the wire. The timestamp is checked against a before/after bracket, not a tolerance. A value JSON cannot encode fails inside WebhookOutput on the signed path and inside the transport (here, the fake) on the unsigned path; both become unexpected:TypeError.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.1 INV-3, INV-8, INV-11; §6.2 AC-10 to AC-15; §6.3 EC-15 to EC-19; §8.1 D-3 to D-5; §9.2 webhook rows)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_webhook_options.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone

import httpx
import pytest

from tests.features.agent_output_connectors.factories import (
    SLACK_URL,
    WEBHOOK_URL,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.http.transport import HttpTransport

TITLE = "Checkout total ignores coupons"
BODY = "Applying SAVE10 leaves the total unchanged."
ENVELOPE = {"agent": "checkout-scout", "title": TITLE, "body": BODY, "structured": None}
SIGNING_KEY_TEXT = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
SIGNING_HEADERS = ("content-type", "webhook-id", "webhook-timestamp", "webhook-signature")


def _names(word: str, message: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


def _expected_signature(secret: str, msg_id: str, timestamp: str, body: bytes) -> str:
    # Standard Webhooks: base64 HMAC-SHA256 of "{id}.{timestamp}." plus the raw body, keyed by the decoded secret.
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def _key_text(size: int) -> str:
    return base64.b64encode(bytes(range(size))).decode()


async def _send(output_api, connector):
    return await connector.send(build_reply(BODY, sender="checkout-scout"), output_api.OutputContent(TITLE, BODY))


# --- headers= --------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_sends_fixed_headers_lowercased_and_keeps_the_envelope(output_api, fake_http) -> None:
    # AC-10 / FR-13: names are lowercased for the transport; the default envelope is unchanged.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, headers={"Authorization": "Bearer S3CREThdr", "X-Team": "a"})

    receipt = await _send(output_api, connector)

    [send] = fake_http.sends
    assert send["headers"] == {"authorization": "Bearer S3CREThdr", "x-team": "a"}
    assert send["json_body"] == ENVELOPE
    assert receipt_rows([receipt]) == [("webhook", "sent", None, None)]
    assert repr(connector) == "WebhookOutput(credential='***')"


@pytest.mark.asyncio
async def test_webhook_header_values_never_reach_a_rendered_surface_when_the_receiver_echoes_them(output_api, fake_http) -> None:
    # INV-3 / T-1: a header value is a secret like the URL; the error, its details, and the receipts stay clean.
    fake_http.answer("hook.eu1.make.com", (401, "bad key Bearer S3CREThdr"))
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, headers={"Authorization": "Bearer S3CREThdr"})
    reply = build_reply(BODY)

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((connector,), reply, reply.metadata)

    err = info.value
    assert receipt_rows(err.receipts) == [("webhook", "failed", None, "http_401")]
    for surface in (repr(connector), str(connector), repr(err.receipts), str(err), repr(err), repr(err.details), repr(reply.metadata)):
        assert "S3CRET" not in surface


# (headers value, words the error must name, texts the error must not contain)
INVALID_HEADERS = [
    pytest.param({"X Team": "a"}, ["headers"], ["X Team"], id="name-with-space"),
    pytest.param({"Authorization: Bearer S3CRET": ""}, ["headers"], ["S3CRET", "Bearer"], id="name-with-colon"),
    pytest.param({"": "a"}, ["headers"], [], id="empty-name"),
    pytest.param({7: "a"}, ["headers"], [], id="non-text-name"),
    pytest.param({"x-team": "a\r\nInjected: S3CRET"}, ["headers", "x-team"], ["S3CRET", "Injected"], id="crlf-value"),
    pytest.param({"x-team": "a\nS3CRET"}, ["headers", "x-team"], ["S3CRET"], id="lf-value"),
    pytest.param({"x-team": "a\rS3CRET"}, ["headers", "x-team"], ["S3CRET"], id="cr-value"),
    pytest.param({"x-team": "a\x00S3CRET"}, ["headers", "x-team"], ["S3CRET"], id="nul-value"),
    pytest.param({"x-team": 7}, ["headers", "x-team"], [], id="non-text-value"),
    pytest.param({"Authorization": "S3CRETa", "authorization": "S3CRETb"}, ["headers", "authorization"], ["S3CRET"], id="EC-15-duplicate-after-lowercasing"),
    pytest.param(["Authorization: Bearer S3CRET"], ["headers", "list"], ["S3CRET"], id="list-not-mapping"),
    pytest.param("Authorization: Bearer S3CRET", ["headers", "str"], ["S3CRET"], id="string-not-mapping"),
]


@pytest.mark.parametrize(("headers", "named", "hidden"), INVALID_HEADERS)
def test_invalid_webhook_headers_are_refused_naming_only_safe_parts(output_api, fake_http, headers, named, hidden) -> None:
    # AC-10 / EC-15 / EC-16 / INV-11 / R-18: a valid name may be named, an invalid one only by position, a value never.
    with pytest.raises(ConfigurationError) as info:
        output_api.WebhookOutput(url=WEBHOOK_URL, headers=headers)

    message = str(info.value)
    assert all(_names(word, message.lower()) for word in named), message
    assert [text for text in hidden if text.lower() in message.lower()] == []
    assert fake_http.sends == []


# --- payload= --------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_payload_replaces_the_envelope_and_receives_the_reply_and_content(output_api, fake_http) -> None:
    # AC-11 / FR-14: the callable's mapping is the whole JSON body.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    seen = []

    def payload(reply, content):
        seen.append((reply.sender, content.title))
        return {"text": content.title}

    receipt = await _send(output_api, output_api.WebhookOutput(url=WEBHOOK_URL, payload=payload))

    [send] = fake_http.sends
    assert send["json_body"] == {"text": TITLE}
    assert seen == [("checkout-scout", TITLE)]
    assert receipt_rows([receipt]) == [("webhook", "sent", None, None)]


def _raises(reply, content):
    raise ValueError("payload bug")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        pytest.param(_raises, "unexpected:ValueError", id="payload-raises"),
        pytest.param(lambda reply, content: ["not", "a", "mapping"], "unexpected:TypeError", id="payload-returns-a-list"),
        pytest.param(lambda reply, content: None, "unexpected:TypeError", id="payload-returns-none"),
    ],
)
async def test_webhook_payload_that_raises_or_returns_a_non_mapping_fails_only_that_output(output_api, fake_http, payload, error_code) -> None:
    # EC-18 / INV-15: the dispatcher maps the exception; the other output is still delivered.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    outputs = (output_api.WebhookOutput(url=WEBHOOK_URL, payload=payload), output_api.SlackOutput(webhook_url=SLACK_URL))
    reply = build_reply(BODY)

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("webhook", "failed", None, error_code), ("slack", "sent", None, None)]
    assert [send["url"] for send in fake_http.sends] == [SLACK_URL]


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", [None, SIGNING_KEY_TEXT], ids=["unsigned", "signed"])
async def test_webhook_payload_with_a_value_json_cannot_encode_is_failed_unexpected_type_error(output_api, fake_http, secret) -> None:
    # EC-19: json.dumps raises TypeError in the connector (signed) or the transport (unsigned); either way one FAILED receipt.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    found_at = datetime(2026, 10, 14, tzinfo=timezone.utc)
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, payload=lambda reply, content: {"found_at": found_at}, secret=secret)
    reply = build_reply(BODY)

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((connector,), reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("webhook", "failed", None, "unexpected:TypeError")]


# --- secret= ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_webhook_puts_exact_bytes_on_the_wire_with_a_verifiable_signature(output_api, httpx_destination) -> None:
    # AC-12 / INV-8 / D-3 / D-4: the signature verifies over the bytes httpx actually sent, with one JSON content-type.
    httpx_destination.routes["hook.eu1.make.com"] = httpx.Response(200, text="Accepted")
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, headers={"X-Team": "a"}, secret=SIGNING_KEY_TEXT)
    before = int(time.time())

    receipt = await _send(output_api, connector)

    after = int(time.time())
    [request] = httpx_destination
    wire = request.content
    msg_id, timestamp = request.headers["webhook-id"], request.headers["webhook-timestamp"]
    assert request.method == "POST"
    assert json.loads(wire) == ENVELOPE
    assert request.headers.get_list("content-type") == ["application/json"]
    assert re.fullmatch(r"msg_[0-9a-f]{32}", msg_id), msg_id
    assert re.fullmatch(r"[0-9]+", timestamp) and before <= int(timestamp) <= after, timestamp
    assert request.headers["webhook-signature"] == _expected_signature(SIGNING_KEY_TEXT, msg_id, timestamp, wire)
    assert request.headers["x-team"] == "a"
    assert receipt_rows([receipt]) == [("webhook", "sent", None, None)]


@pytest.mark.asyncio
async def test_signed_webhook_retry_after_429_repeats_the_same_bytes_and_signing_headers(output_api, fake_http) -> None:
    # AC-13 / INV-8 / FR-16: the body goes to the transport as content= bytes, so a retry cannot re-serialize or re-sign it.
    fake_http.answer("hook.eu1.make.com", (429, ""), (200, "Accepted"))
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, secret=SIGNING_KEY_TEXT)

    receipt = await _send(output_api, connector)

    first, second = fake_http.sends
    assert first["json_body"] is None and second["json_body"] is None
    assert isinstance(first["content"], bytes)
    assert first["content"] == second["content"]
    assert {name: first["headers"][name] for name in SIGNING_HEADERS} == {name: second["headers"][name] for name in SIGNING_HEADERS}
    assert first["headers"]["webhook-signature"] == _expected_signature(SIGNING_KEY_TEXT, first["headers"]["webhook-id"], first["headers"]["webhook-timestamp"], first["content"])
    assert receipt_rows([receipt]) == [("webhook", "sent", None, None)]


@pytest.mark.asyncio
async def test_each_signed_send_gets_a_new_webhook_id(output_api, fake_http) -> None:
    # INV-8 / D-4: receivers dedupe on webhook-id, so two replies must never share one.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"), repeat=True)
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, secret=SIGNING_KEY_TEXT)

    await _send(output_api, connector)
    await _send(output_api, connector)

    first, second = fake_http.sends
    assert first["headers"]["webhook-id"] != second["headers"]["webhook-id"]
    for send in (first, second):
        assert send["headers"]["webhook-signature"] == _expected_signature(SIGNING_KEY_TEXT, send["headers"]["webhook-id"], send["headers"]["webhook-timestamp"], send["content"])


@pytest.mark.asyncio
async def test_signing_headers_replace_the_callers_content_type_and_signature_headers(output_api, fake_http) -> None:
    # EC-17 / D-4: the SDK's signing headers are set after headers=, so a caller's value cannot forge or break them.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    headers = {"Content-Type": "text/plain", "Webhook-Signature": "v1,forged", "Webhook-Id": "msg_forged", "X-Team": "a"}
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, headers=headers, secret=SIGNING_KEY_TEXT)

    await _send(output_api, connector)

    [send] = fake_http.sends
    sent = send["headers"]
    assert sent["content-type"] == "application/json"
    assert sent["webhook-id"] != "msg_forged" and re.fullmatch(r"msg_[0-9a-f]{32}", sent["webhook-id"])
    assert sent["webhook-signature"] == _expected_signature(SIGNING_KEY_TEXT, sent["webhook-id"], sent["webhook-timestamp"], send["content"])
    assert sent["x-team"] == "a"


INVALID_SECRETS = [
    pytest.param("", id="blank"),
    pytest.param("   ", id="whitespace"),
    pytest.param("whsec_", id="prefix-only"),
    pytest.param("whsec_S3CRET!!", id="not-base64"),
    pytest.param("whsec_AA==", id="one-byte"),
    pytest.param("whsec_" + _key_text(23), id="23-bytes"),
    pytest.param("whsec_" + _key_text(65), id="65-bytes"),
    pytest.param(_key_text(23), id="23-bytes-without-prefix"),
    pytest.param(12345, id="int"),
    pytest.param(SIGNING_KEY_TEXT.encode(), id="bytes"),
]


@pytest.mark.parametrize("secret", INVALID_SECRETS)
def test_invalid_webhook_secret_is_refused_naming_secret_without_echoing_it(output_api, secret) -> None:
    # AC-14 / D-5 / INV-11: the Standard Webhooks key is 24-64 bytes of base64; the error never shows the value.
    with pytest.raises(ConfigurationError) as info:
        output_api.WebhookOutput(url=WEBHOOK_URL, secret=secret)

    message = str(info.value)
    assert _names("secret", message), message
    value = secret.decode() if isinstance(secret, bytes) else str(secret)
    secret_part = value.strip().removeprefix("whsec_")
    assert secret_part == "" or secret_part not in message
    assert "S3CRET" not in message


@pytest.mark.parametrize("secret", [SIGNING_KEY_TEXT, "whsec_" + _key_text(64), _key_text(24)], ids=["spec-example-24-bytes", "64-bytes", "24-bytes-without-prefix"])
def test_webhook_secret_of_24_to_64_bytes_is_accepted_with_or_without_the_prefix(output_api, secret) -> None:
    # AC-14 boundary / D-5: both ends of the Standard Webhooks size range are valid keys.
    connector = output_api.WebhookOutput(url=WEBHOOK_URL, secret=secret)

    assert repr(connector) == "WebhookOutput(credential='***')"


@pytest.mark.parametrize("payload", [{"text": "x"}, "x"], ids=["mapping", "string"])
def test_webhook_payload_must_be_callable(output_api, payload) -> None:
    # §9.2(b) payload row: optional_callable refuses anything that is not None or callable.
    with pytest.raises(ConfigurationError) as info:
        output_api.WebhookOutput(url=WEBHOOK_URL, payload=payload)

    assert _names("payload", str(info.value)), str(info.value)


# --- HttpTransport content= --------------------------------------------------


@pytest.mark.asyncio
async def test_transport_sends_content_bytes_verbatim_without_adding_a_content_type(httpx_destination) -> None:
    # AC-15 / FR-16 / D-3: the canonical helper carries caller bytes as they are.
    httpx_destination.routes["receiver.example.net"] = httpx.Response(200, text="ok")

    response = await HttpTransport().request(method="POST", url="https://receiver.example.net/in", headers={}, content=b'{"a":1}')

    [request] = httpx_destination
    assert request.content == b'{"a":1}'
    assert "content-type" not in request.headers
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_transport_refuses_json_body_and_content_together_before_any_request(httpx_destination) -> None:
    # AC-15 / D-3: two bodies is a caller bug; nothing may be sent.
    httpx_destination.routes["receiver.example.net"] = httpx.Response(200, text="ok")

    with pytest.raises(ProviderRequestError):
        await HttpTransport().request(method="POST", url="https://receiver.example.net/in", headers={}, json_body={"a": 1}, content=b'{"a":1}')

    assert list(httpx_destination) == []
