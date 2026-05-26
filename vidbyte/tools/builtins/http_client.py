"""Context Protocol Header

Description:
    Implements HTTP client tools (GET, POST, PUT, DELETE) using HttpTransport.
Purpose:
    Provides agents with the ability to make HTTP requests and receive responses.
Architecture:
    - Function-based tools using @tool decorator.
    - Uses the existing HttpTransport from vidbyte.lib.http.transport.
Relations:
    Related to vidbyte.lib.http.transport and vidbyte.tools.builtins.
"""

from __future__ import annotations

import json

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

MAX_BODY_CHARS = 100000


def _truncate(body: str) -> str:
    if len(body) > MAX_BODY_CHARS:
        return body[:MAX_BODY_CHARS] + "\n...[truncated at 100K chars]"
    return body


@tool(permission=ToolPermission.READ)
async def http_get(url: str, headers: dict[str, str] | None = None) -> str:
    """Make an HTTP GET request and return the response body."""
    transport = HttpTransport()
    response = transport.request(method="GET", url=url, headers=headers or {})
    return f"Status: {response.status_code}\n\n{_truncate(response.body)}"


@tool(permission=ToolPermission.WRITE)
async def http_post(url: str, body: str | None = None, headers: dict[str, str] | None = None) -> str:
    """Make an HTTP POST request and return the response."""
    transport = HttpTransport()
    hdrs = dict(headers or {})
    json_body = None
    if body:
        try:
            json_body = json.loads(body)
        except json.JSONDecodeError:
            hdrs.setdefault("Content-Type", "text/plain")
            json_body = {"raw_body": body}
    response = transport.request(method="POST", url=url, headers=hdrs, json_body=json_body)
    return f"Status: {response.status_code}\n\n{_truncate(response.body)}"


@tool(permission=ToolPermission.WRITE)
async def http_put(url: str, body: str, headers: dict[str, str] | None = None) -> str:
    """Make an HTTP PUT request."""
    transport = HttpTransport()
    hdrs = dict(headers or {})
    json_body = None
    try:
        json_body = json.loads(body)
    except json.JSONDecodeError:
        hdrs.setdefault("Content-Type", "text/plain")
        json_body = {"raw_body": body}
    response = transport.request(method="PUT", url=url, headers=hdrs, json_body=json_body)
    return f"Status: {response.status_code}\n\n{_truncate(response.body)}"


@tool(permission=ToolPermission.WRITE)
async def http_delete(url: str, headers: dict[str, str] | None = None) -> str:
    """Make an HTTP DELETE request."""
    transport = HttpTransport()
    response = transport.request(method="DELETE", url=url, headers=headers or {})
    return f"Status: {response.status_code}\n\n{_truncate(response.body)}"
