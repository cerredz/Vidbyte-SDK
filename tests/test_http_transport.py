"""Context Protocol Header

Description:
    Regression tests for outbound HTTP request framing.
Purpose:
    Proves JSON requests contain exactly one content-type header regardless of
    the casing used by provider adapters.
Architecture:
    - _record_json_request: Runs the public async transport against httpx's
      in-memory mock transport and returns the emitted content-type headers.
Relations:
    Protects vidbyte.lib.http.transport from provider-wide HTTP 400 regressions.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx
import pytest

from vidbyte.lib.http import HttpTransport


async def _record_json_request(monkeypatch: pytest.MonkeyPatch, headers: Mapping[str, str]) -> list[tuple[bytes, bytes]]:
    recorded: list[tuple[bytes, bytes]] = []
    async_client = httpx.AsyncClient

    async def handle(request: httpx.Request) -> httpx.Response:
        recorded.extend((name.lower(), value) for name, value in request.headers.raw if name.lower() == b"content-type")
        return httpx.Response(200, json={})

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return async_client(transport=httpx.MockTransport(handle), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    await HttpTransport().request(method="POST", url="https://provider.test/search", headers=headers, json_body={"query": "test"})
    return recorded


@pytest.mark.asyncio
async def test_json_request_preserves_one_mixed_case_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    content_types = await _record_json_request(monkeypatch, {"Content-Type": "application/problem+json"})

    assert content_types == [(b"content-type", b"application/problem+json")]


@pytest.mark.asyncio
async def test_json_request_adds_one_default_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    content_types = await _record_json_request(monkeypatch, {})

    assert content_types == [(b"content-type", b"application/json")]
