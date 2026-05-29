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
from urllib.parse import urlencode

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

    async def _json_post(self, url: str, headers: dict[str, str], body: dict) -> tuple[int, dict]:
        # POSTs JSON body to url, decodes response JSON, and returns (status, parsed_dict).
        response = await self._transport.request(
            method="POST",
            url=url,
            headers=headers,
            json_body=body,
            timeout_seconds=self._timeout,
        )
        return response.status_code, json.loads(response.body or "{}")

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
        return response.status_code, json.loads(response.body or "{}")

    async def _json_delete(self, url: str, headers: dict[str, str]) -> tuple[int, dict]:
        # DELETEs url and decodes the response JSON, returning (status, parsed_dict).
        response = await self._transport.request(
            method="DELETE",
            url=url,
            headers=headers,
            timeout_seconds=self._timeout,
        )
        body = response.body or "{}"
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return response.status_code, parsed

    def _error_output(self, status: int, body: dict) -> str:
        # Formats an HTTP error dict into a human-readable error string.
        return json.dumps({"error": True, "status": status, "body": body})

    def _success_output(self, data: dict | list | str) -> str:
        # Serializes a successful response payload to a JSON string.
        return json.dumps(data, default=str)
