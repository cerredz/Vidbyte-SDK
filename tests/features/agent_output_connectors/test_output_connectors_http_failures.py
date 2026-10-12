"""FILE: tests/features/agent_output_connectors/test_output_connectors_http_failures.py

PURPOSE: Prove how an HTTP destination's failures become receipts: only a 429 is retried and at most twice, every other status and every network error is tried once, error codes follow the INV-11 grammar and never carry a URL, credential, or response text, redirects are not followed, and an oversized response is refused.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/delivery.py OutputHttp.post (through real connectors) on top of vidbyte.lib.http.transport.HttpTransport, plus OutputDispatcher.deliver for the mixed-failure case.
ARCHITECTURE NOTE: Most tests script HttpTransport._send_once (fake_http). The redirect and size-ceiling tests instead keep the real _send_once and give httpx an in-memory MockTransport, because follow_redirects and the streamed size check live below _send_once.
FUNCTION INVENTORY: test_slack_answer_maps_to_* (AC-6 a-d, INV-10, EC-2 to EC-5); test_success_range_* (§9.2 success range); test_mixed_failures_* (AC-7, EC-41); test_error_body_* (INV-11 token grammar); test_redirect_is_not_followed_* (AC-25, EC-35); test_response_over_the_size_ceiling_* (EC-34).
COMMON MODIFICATION PATTERNS: Add a status row to ATTEMPT_TABLE or a body row to TOKEN_TABLE; keep expected attempt counts literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not let a request leave the process; MockTransport answers every httpx request. 2. Do not assert on exception text; codes are the contract.
KNOWN EDGE CASES: A 429 body that is a valid token would produce http_429:<token>, so the 429 rows use an empty body. MockTransport is installed by replacing httpx.AsyncClient for the test, which HttpTransport looks up on each request.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-10, INV-11; §6.2 AC-6, AC-7, AC-25; §6.3 EC-34, EC-35)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_http_failures.py
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.features.agent_output_connectors.factories import (
    DISCORD_URL,
    GITHUB_TOKEN,
    SECRET_MARKER,
    SLACK_URL,
    WEBHOOK_URL,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import transport as transport_module


def _network_error(excerpt: str = "ConnectError: connection reset by peer") -> ProviderRequestError:
    return ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=excerpt)


async def _slack_receipt(output_api):
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)
    return await connector.send(build_reply("Nightly scan: no regressions."), output_api.OutputContent("Nightly scan", "Nightly scan: no regressions."))


# (scripted answers in order, expected status, expected error code, expected number of requests)
ATTEMPT_TABLE = [
    pytest.param([(429, ""), (200, "ok")], "sent", None, 2, id="429-then-200-sent-after-one-retry"),
    pytest.param([(429, ""), (429, ""), (429, "")], "failed", "http_429", 3, id="429-three-times-failed-after-two-retries"),
    pytest.param([(500, "Internal Server Error")], "failed", "http_500", 1, id="500-never-retried"),
    pytest.param([_network_error()], "failed", "network", 1, id="network-error-never-retried"),
    pytest.param([_network_error("ReadTimeout: timed out")], "failed", "network", 1, id="read-timeout-never-retried"),
    *[pytest.param([(status, "")], "failed", f"http_{status}", 1, id=f"{status}-never-retried") for status in (408, 409, 425, 502, 503, 504)],
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("answers", "status", "error_code", "requests"), ATTEMPT_TABLE)
async def test_slack_answer_maps_to_one_receipt_and_only_a_429_is_retried(output_api, fake_http, answers, status, error_code, requests) -> None:
    # AC-6 (a)-(d) / INV-10 / EC-2 to EC-5: a retry after anything but 429 could post twice.
    fake_http.answer("hooks.slack.com", *answers)

    receipt = await _slack_receipt(output_api)

    assert receipt_rows([receipt]) == [("slack", status, None, error_code)]
    assert len(fake_http.sends) == requests


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "outcome", "error_code"), [(200, "sent", None), (204, "sent", None), (299, "sent", None), (300, "failed", "http_300"), (199, "failed", "http_199")])
async def test_success_range_is_exactly_200_to_299(output_api, fake_http, status, outcome, error_code) -> None:
    # §9.2: success means any status from 200 to 299; everything else is a FAILED http_<status>.
    fake_http.answer("hooks.slack.com", (status, ""))

    receipt = await _slack_receipt(output_api)

    assert receipt_rows([receipt]) == [("slack", outcome, None, error_code)]


@pytest.mark.asyncio
async def test_mixed_failures_give_their_codes_in_configured_order_and_no_url_leaks(output_api, fake_http) -> None:
    # AC-7 / EC-41 / INV-11: the transport's error text carries the full webhook URL; no surface may repeat it.
    fake_http.answer("hook.eu1.make.com", _network_error(f"ConnectError: [Errno 111] Connection refused while posting to {WEBHOOK_URL}"))
    fake_http.answer("hooks.slack.com", (404, "channel_not_found"))
    fake_http.answer("discord.com", (400, json.dumps({"message": "Cannot send an empty message", "code": 50006})))
    outputs = (output_api.WebhookOutput(url=WEBHOOK_URL), output_api.SlackOutput(webhook_url=SLACK_URL), output_api.DiscordOutput(webhook_url=DISCORD_URL))
    reply = build_reply("Nightly scan: no regressions.")

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    err = info.value
    assert [receipt.error_code for receipt in err.receipts] == ["network", "http_404:channel_not_found", "http_400"]
    assert str(err) == "3 of 3 outputs failed: webhook (network), slack (http_404:channel_not_found), discord (http_400)"
    for surface in (repr(err.receipts), str(err), repr(err.details)):
        assert WEBHOOK_URL not in surface
        assert "hook.eu1.make.com" not in surface
        assert SECRET_MARKER not in surface


# (response body, expected error code) for a Slack 400 or 403: the token is kept only when the whole stripped body is one.
TOKEN_TABLE = [
    pytest.param(400, "no_text", "http_400:no_text", id="plain-token"),
    pytest.param(400, "  invalid_payload \n", "http_400:invalid_payload", id="token-with-surrounding-whitespace"),
    pytest.param(403, "action_prohibited", "http_403:action_prohibited", id="forbidden-token"),
    pytest.param(400, "a" + "b" * 63, "http_400:a" + "b" * 63, id="token-of-64-characters"),
    pytest.param(400, "a" + "b" * 64, "http_400", id="token-of-65-characters"),
    pytest.param(400, "Invalid Payload", "http_400", id="uppercase-and-space"),
    pytest.param(400, "1st_error", "http_400", id="starts-with-digit"),
    pytest.param(400, "no-service", "http_400", id="hyphen"),
    pytest.param(400, "invalid_token: S3CRETslack", "http_400", id="token-followed-by-echoed-secret"),
    pytest.param(400, SLACK_URL, "http_400", id="echoed-webhook-url"),
    pytest.param(400, json.dumps({"ok": False, "error": "no_text"}), "http_400", id="json-body"),
    pytest.param(400, "", "http_400", id="empty-body"),
    pytest.param(400, "no_text\nS3CRETslack", "http_400", id="token-then-second-line"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "body", "error_code"), TOKEN_TABLE)
async def test_error_body_becomes_a_token_only_when_the_whole_body_is_one_safe_token(output_api, fake_http, status, body, error_code) -> None:
    # INV-11 / T-5: Slack's documented error tokens are kept; anything else (text, JSON, echoed secrets) is dropped.
    fake_http.answer("hooks.slack.com", (status, body))

    receipt = await _slack_receipt(output_api)

    assert receipt_rows([receipt]) == [("slack", "failed", None, error_code)]
    assert SECRET_MARKER not in repr(receipt)


class _Requests(list):
    """Recorded httpx requests plus the per-host scripted responses."""

    def __init__(self) -> None:
        super().__init__()
        self.routes: dict[str, httpx.Response] = {}


@pytest.fixture
def httpx_destination(monkeypatch: pytest.MonkeyPatch) -> _Requests:
    # Gives every httpx client an in-memory transport, so the real _send_once, redirect policy, and size ceiling run offline.
    requests = _Requests()
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return requests.routes.get(request.url.host, httpx.Response(599, text="unexpected host"))

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(transport_module.httpx, "AsyncClient", client_factory)
    return requests


@pytest.mark.asyncio
async def test_redirect_is_not_followed_so_the_token_never_reaches_the_location_host(output_api, httpx_destination) -> None:
    # AC-25 / EC-35 / INV-4: a 302 is a failure after one request, and the Location host is never contacted.
    httpx_destination.routes["api.github.com"] = httpx.Response(302, headers={"location": "https://collector.example.net/steal"})
    httpx_destination.routes["collector.example.net"] = httpx.Response(200, json={"html_url": "https://collector.example.net/x"})
    connector = output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN)

    receipt = await connector.send(build_reply("Checkout total ignores coupons."), output_api.OutputContent("Checkout bug", "Checkout total ignores coupons."))

    assert receipt_rows([receipt]) == [("github_issue", "failed", None, "http_302")]
    assert [request.url.host for request in httpx_destination] == ["api.github.com"]
    assert httpx_destination[0].headers["authorization"] == f"Bearer {GITHUB_TOKEN}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("size", "status", "error_code"), [(2, "sent", None), (1_000_001, "failed", "network")], ids=["small-ok", "one-byte-over-ceiling"])
async def test_response_over_the_size_ceiling_is_refused_as_a_network_failure(output_api, httpx_destination, size, status, error_code) -> None:
    # EC-34 / T-5: a compromised endpoint cannot make the agent buffer an unbounded body.
    httpx_destination.routes["hooks.slack.com"] = httpx.Response(200, content=b"o" * size)

    receipt = await _slack_receipt(output_api)

    assert receipt_rows([receipt]) == [("slack", status, None, error_code)]
    assert len(httpx_destination) == 1
