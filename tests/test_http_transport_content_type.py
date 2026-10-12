"""FILE: tests/test_http_transport_content_type.py

PURPOSE: Verifies that every JSON request built by HttpTransport and SyncHttpTransport carries exactly one content-type header, keeps a caller's own value, and that ExaClient succeeds against a server that rejects a doubled header.
ROLE IN CODEBASE: Pins the transport's header rule. Exa answered every research search with HTTP 400 while the SDK sent "Content-Type" and "content-type" side by side.
ARCHITECTURE NOTE: httpx.MockTransport stands in for the network on the async path, and a captured urllib Request stands in on the sync paths; the transport and client code run unmodified.
COMMON MODIFICATION PATTERNS: Add a case here when a new JSON send site is added to vidbyte/lib/http/transport.py.
KNOWN EDGE CASES: urllib folds header-name case on its own, so the sync cases check the caller's value survives rather than the line count alone.
RELATED DOCS: docs/design/single-content-type-header.md.
TESTS: python -m pytest tests/test_http_transport_content_type.py and python scripts/test-single-content-type-header.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import httpx

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpTransport, SyncHttpTransport, _json_request_headers
from vidbyte.tools.builtins.operations import ExaClient

_REAL_ASYNC_CLIENT = httpx.AsyncClient
_URL = "https://provider.test/v1/search"


def _content_type_lines(request: httpx.Request) -> list[str]:
    # Returns every content-type line exactly as httpx would put it on the wire.
    return [value.decode() for name, value in request.headers.raw if name.lower() == b"content-type"]


class _RecordingServer:
    """Answers each request and keeps it, optionally rejecting any request without exactly one content-type."""

    def __init__(self, *, strict: bool = False, payload: dict | None = None) -> None:
        self.strict = strict
        self.payload = payload or {"ok": True}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        # Records the request and mimics Exa's 400 for a doubled or missing content-type.
        self.requests.append(request)
        if self.strict and len(_content_type_lines(request)) != 1:
            return httpx.Response(400, json={"error": "invalid content-type"})
        return httpx.Response(200, json=self.payload)

    def client_factory(self, *args, **kwargs) -> httpx.AsyncClient:
        # Builds the real AsyncClient wired to this in-memory server.
        return _REAL_ASYNC_CLIENT(*args, transport=httpx.MockTransport(self.handle), **kwargs)


def _send_async(server: _RecordingServer, headers: dict[str, str], json_body: dict | None, method: str = "POST") -> int:
    # Sends one request through HttpTransport against the recording server and returns the status.
    with patch("vidbyte.lib.http.transport.httpx.AsyncClient", server.client_factory):
        response = asyncio.run(HttpTransport().request(method=method, url=_URL, headers=headers, json_body=json_body, max_response_bytes=1_000_000))
    return response.status_code


class AsyncTransportContentTypeTests(unittest.TestCase):
    def test_caller_title_case_content_type_is_sent_once(self) -> None:
        # [Hidden Failure] "Content-Type" from the caller used to be joined by a second lowercase line.
        server = _RecordingServer(strict=True)
        status = _send_async(server, {"x-api-key": "k", "Content-Type": "application/json"}, {"query": "q"})
        self.assertEqual(status, 200)
        self.assertEqual(_content_type_lines(server.requests[0]), ["application/json"])

    def test_caller_lowercase_content_type_is_sent_once(self) -> None:
        # [Edge Case] The transport's own spelling from the caller still yields one line.
        server = _RecordingServer(strict=True)
        _send_async(server, {"content-type": "application/json"}, {"query": "q"})
        self.assertEqual(_content_type_lines(server.requests[0]), ["application/json"])

    def test_custom_content_type_is_kept_not_replaced(self) -> None:
        # [Silent Failure] A caller's own media type must reach the server untouched and alone.
        server = _RecordingServer(strict=True)
        _send_async(server, {"CONTENT-TYPE": "application/vnd.api+json"}, {"query": "q"})
        self.assertEqual(_content_type_lines(server.requests[0]), ["application/vnd.api+json"])

    def test_default_added_when_caller_sends_none(self) -> None:
        # [Hidden Assumption] A JSON body with no caller header still gets application/json, once.
        server = _RecordingServer(strict=True)
        _send_async(server, {"x-api-key": "k"}, {"query": "q"})
        self.assertEqual(_content_type_lines(server.requests[0]), ["application/json"])
        self.assertEqual(json.loads(server.requests[0].content), {"query": "q"})

    def test_no_content_type_without_json_body(self) -> None:
        # [Edge Case] A bodiless GET carries no content-type at all.
        server = _RecordingServer()
        _send_async(server, {"x-api-key": "k"}, None, method="GET")
        self.assertEqual(_content_type_lines(server.requests[0]), [])


class HeaderHelperTests(unittest.TestCase):
    def test_helper_does_not_mutate_caller_headers(self) -> None:
        # [Hidden Assumption] The caller's mapping is reused across retries, so it must stay unchanged.
        caller = {"Content-Type": "application/json", "x-api-key": "k"}
        snapshot = dict(caller)
        built = _json_request_headers(caller)
        self.assertEqual(caller, snapshot)
        self.assertIsNot(built, caller)
        self.assertEqual([name for name in built if name.lower() == "content-type"], ["Content-Type"])


class SyncTransportContentTypeTests(unittest.TestCase):
    def _captured_request(self, call) -> object:
        # Runs one sync send with urlopen replaced, returning the urllib Request it built.
        captured = []

        def refuse(request, timeout=None):
            captured.append(request)
            raise URLError("offline test")

        with patch("vidbyte.lib.http.transport.urlopen", refuse):
            try:
                result = call()
                if hasattr(result, "__next__"):
                    next(result)
            except ProviderRequestError:
                pass
        return captured[0]

    def test_sync_paths_use_the_same_helper(self) -> None:
        # [Silent Failure] urllib let a default "content-type" overwrite the caller's custom value.
        transport = SyncHttpTransport()
        headers = {"CONTENT-TYPE": "application/vnd.api+json"}
        calls = {
            "request": lambda: transport.request(method="POST", url=_URL, headers=headers, json_body={"q": 1}),
            "request_bytes": lambda: transport.request_bytes(method="POST", url=_URL, headers=headers, json_body={"q": 1}),
            "stream_request": lambda: transport.stream_request(method="POST", url=_URL, headers=headers, json_body={"q": 1}),
        }
        for label, call in calls.items():
            with self.subTest(path=label):
                request = self._captured_request(call)
                values = [value for name, value in request.header_items() if name.lower() == "content-type"]
                self.assertEqual(values, ["application/vnd.api+json"])


class ExaClientStrictServerTests(unittest.TestCase):
    def test_exa_search_succeeds_against_a_strict_server(self) -> None:
        # [Hidden Failure] The exact ExaClient call that returned 400 in production must now succeed.
        server = _RecordingServer(strict=True, payload={"results": [{"url": "https://a.test/1", "title": "A", "highlights": ["first fact"]}, {"url": "https://a.test/2", "title": "B", "highlights": ["second fact"]}]})
        client = ExaClient("test-key", max_results=20, include_highlights=True)
        with patch("vidbyte.lib.http.transport.httpx.AsyncClient", server.client_factory):
            payload = asyncio.run(client.search("mongodb elemMatch projection", num_results=20, search_type="auto"))
        self.assertEqual([hit.url for hit in payload.hits], ["https://a.test/1", "https://a.test/2"])
        self.assertEqual(_content_type_lines(server.requests[0]), ["application/json"])
        self.assertEqual(json.loads(server.requests[0].content)["type"], "auto")


if __name__ == "__main__":
    unittest.main()
