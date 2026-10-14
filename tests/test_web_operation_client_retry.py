"""FILE: tests/test_web_operation_client_retry.py

PURPOSE: Prove a POST web operation client with the default RetryPolicy passes the HttpTransport retry guard and reports only the attempts it made, that BraveClient sends Brave's own search_lang codes, and that TavilyClient clamps its query to Tavily's 400-character limit.
ROLE IN CODEBASE: Drives vidbyte.tools.builtins.operations.clients.ExaClient, BraveClient, TavilyClient and ExaSearchTool over the real HttpTransport with its single-attempt send faked.
ARCHITECTURE NOTE: HttpTransport._send_once and the transport sleep are patched, so no socket opens and retries do not wait.
COMMON MODIFICATION PATTERNS: Add a case when another POST client gains its own request path; keep faking only the lowest send layer.
KNOWN EDGE CASES: A 503 response is retryable and the final 200 ends the loop; statuses are consumed in send order.
RELATED DOCS: docs/design/builtin-tool-transport-and-builder-fixes.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.http import transport as transport_module
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.tools.builtins.operations.clients import BraveClient, ExaClient, TavilyClient
from vidbyte.tools.builtins.operations.search import ExaSearchTool

_EXA_BODY = '{"results": [{"url": "https://example.com", "title": "Example"}]}'


def _install_fake_send(monkeypatch: pytest.MonkeyPatch, statuses: list[int]) -> list[dict[str, Any]]:
    # Replaces the single-attempt send so no socket opens, recording each attempt made.
    sends: list[dict[str, Any]] = []

    async def fake_send(self: HttpTransport, client: object, **kwargs: Any) -> HttpResponse:
        sends.append(kwargs)
        status = statuses[len(sends) - 1]
        return HttpResponse(status_code=status, body=_EXA_BODY if status == 200 else "{}", headers={})

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)
    return sends


@pytest.mark.asyncio
async def test_default_retry_policy_post_client_reaches_transport_send(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch, [200])

    payload = await ExaClient("test-key").search("vidbyte")

    assert len(sends) == 1
    assert sends[0]["method"] == "POST"
    assert payload.attempts == 1
    assert len(payload.hits) == 1


@pytest.mark.asyncio
async def test_retried_post_bills_only_the_attempts_actually_made(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch, [503, 200])
    tool = ExaSearchTool(client=ExaClient("test-key"))
    call = ToolCall("exa_search", {"query": "vidbyte"})

    result = await tool.execute(call)

    assert result.status.value == "success"
    assert len(sends) == 2
    assert tool.attempts_used(call, result) == 2


@pytest.mark.asyncio
async def test_brave_keeps_its_own_subtag_search_lang_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch, [200, 200, 200])
    client = BraveClient("test-key")

    for language in ("zh-hans", "pt-br", "en-US"):
        await client.search("vidbyte", language=language)

    sent = [parse_qs(urlsplit(send["url"]).query)["search_lang"] for send in sends]
    assert sent == [["zh-hans"], ["pt-br"], ["en"]]


@pytest.mark.asyncio
async def test_tavily_clamps_search_query_to_its_400_character_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch, [200, 200])
    client = TavilyClient("test-key")
    long_query = "a" * 400 + "b" * 16
    exact_query = "c" * 400

    long_payload = await client.search(long_query)
    exact_payload = await client.search(exact_query)

    assert [send["json_body"]["query"] for send in sends] == ["a" * 400, exact_query]
    assert long_payload.query == long_query
    assert exact_payload.query == exact_query
