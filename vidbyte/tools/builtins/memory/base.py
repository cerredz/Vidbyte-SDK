"""Context Protocol Header

Description:
    Shared base class for all memory provider tools.
Purpose:
    Provides HttpTransport wiring and JSON request helpers so provider-specific
    tools only need to build URLs, headers, and bodies.
Architecture:
    - BaseMemoryTool: Extends BaseTool with _json_post, _json_get, _json_delete helpers.
Relations:
    Extended by supermemory, mem0, zep, cognee, and letta tool modules.
"""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult


class BaseMemoryTool(BaseTool):
    """Abstract base for all memory provider tools; wires HttpTransport and JSON helpers."""

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 30.0) -> None:
        # Validates the API key and stores transport config for all subclasses.
        if not api_key or not api_key.strip():
            raise ValueError("api_key cannot be empty")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = HttpTransport()

    def _auth_headers(self, scheme: str = "Bearer") -> dict[str, str]:
        # Returns the Authorization header using the configured scheme and key.
        return {"authorization": f"{scheme} {self._api_key}"}

    def _ok(self, status: int) -> bool:
        # Returns True when the HTTP status code indicates success (2xx).
        return 200 <= status < 300

    @staticmethod
    def _path_id(value: object) -> str:
        # @intent ids-stay-inside-their-path-segment
        # An id the model chose is encoded as one path segment, so slashes or dots cannot send the request elsewhere.
        text = str(value)
        if text in ("", ".", ".."):
            raise ValueError(f"id {text!r} cannot be used as a URL path segment")
        return quote(text, safe="")

    async def _json_post(self, url: str, headers: dict[str, str], body: dict) -> tuple[int, dict]:
        # POSTs JSON body to url, decodes response JSON, and returns (status, parsed_dict).
        response = await self._transport.request(
            method="POST",
            url=url,
            headers=headers,
            json_body=body,
            timeout_seconds=self._timeout,
        )
        return response.status_code, self._decode_body(response.body, keep_raw=not self._ok(response.status_code))

    async def _json_get(self, url: str, headers: dict[str, str], params: dict | None = None) -> tuple[int, dict]:
        # GETs url with optional query params, decodes response JSON, returns (status, parsed_dict).
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
        response = await self._transport.request(
            method="GET",
            url=url,
            headers=headers,
            timeout_seconds=self._timeout,
        )
        return response.status_code, self._decode_body(response.body, keep_raw=not self._ok(response.status_code))

    async def _json_delete(self, url: str, headers: dict[str, str]) -> tuple[int, dict]:
        # DELETEs url and decodes the response JSON, returning (status, parsed_dict).
        response = await self._transport.request(
            method="DELETE",
            url=url,
            headers=headers,
            timeout_seconds=self._timeout,
        )
        return response.status_code, self._decode_body(response.body, keep_raw=True)

    @staticmethod
    def _decode_body(body: str, *, keep_raw: bool) -> dict:
        # @intent memory-tools-report-status-for-non-json-bodies
        # A gateway error page is not JSON, so keep its text and let the tool report the HTTP status.
        # POST and GET keep raw text only for error statuses, so a non-JSON success body still fails.
        text = body or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if not keep_raw:
                raise
            return {"raw": text}

    def _error_output(self, status: int, body: dict) -> str:
        # Formats an HTTP error dict into a human-readable error string.
        return json.dumps({"error": True, "status": status, "body": body})

    def _success_output(self, data: dict | list | str) -> str:
        # Serializes a successful response payload to a JSON string.
        return json.dumps(data, default=str)
