"""FILE: tests/test_browserbase_search_request.py

PURPOSE: Prove BrowserbaseClient keeps its search request inside Browserbase's documented ranges: the query is clamped to 200 characters and numResults to 1-25.
ROLE IN CODEBASE: Drives vidbyte.tools.builtins.operations.clients.BrowserbaseClient over the real HttpTransport with its single-attempt send faked.
ARCHITECTURE NOTE: HttpTransport._send_once is patched, so no socket opens; each test reads the JSON body the client would have sent.
COMMON MODIFICATION PATTERNS: Add a case when Browserbase documents another request limit; keep faking only the lowest send layer.
KNOWN EDGE CASES: A query of exactly 200 characters is sent unchanged; SearchPayload.query keeps the caller's original query.
RELATED DOCS: vidbyte/tools/builtins/operations/clients/README.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.tools.builtins.operations.clients import BrowserbaseClient

_BODY = '{"results": [{"url": "https://example.com", "title": "Example"}]}'


def _install_fake_send(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    # Replaces the single-attempt send so no socket opens, recording each request made.
    sends: list[dict[str, Any]] = []

    async def fake_send(self: HttpTransport, client: object, **kwargs: Any) -> HttpResponse:
        sends.append(kwargs)
        return HttpResponse(status_code=200, body=_BODY, headers={})

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    return sends


@pytest.mark.asyncio
async def test_long_query_is_sent_as_its_first_200_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch)
    query = ("What are the documented rate limits and retry semantics " * 8)[:416]
    assert len(query) == 416

    payload = await BrowserbaseClient("test-key").search(query)

    assert sends[0]["json_body"]["query"] == query[:200]
    assert payload.query == query
    assert len(payload.hits) == 1


@pytest.mark.asyncio
async def test_query_at_the_limit_is_sent_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch)
    query = "q" * 200

    await BrowserbaseClient("test-key").search(query, num_results=10)

    assert sends[0]["json_body"] == {"query": query, "numResults": 10}


@pytest.mark.asyncio
async def test_num_results_is_still_clamped_to_the_documented_range(monkeypatch: pytest.MonkeyPatch) -> None:
    sends = _install_fake_send(monkeypatch)
    client = BrowserbaseClient("test-key")

    for requested in (0, 40):
        await client.search("vidbyte", num_results=requested)

    assert [send["json_body"]["numResults"] for send in sends] == [1, 25]
