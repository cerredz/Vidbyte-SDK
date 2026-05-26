"""Context Protocol Header

Description:
    Converts between SDK data types and MCP JSON-RPC protocol representations.
Purpose:
    Keeps JSON serialization and MCP schema logic centralized so server and
    handler modules stay focused on their own responsibilities.
Architecture:
    - tool_spec_to_mcp_tool: SDK ToolSpec -> MCP tools/list entry dict.
    - mcp_result_response / mcp_error_response: JSON-RPC 2.0 response builders.
    - tool_result_to_mcp_content: SDK ToolResult -> MCP content array.
Relations:
    Used by vidbyte.mcp_server.server and vidbyte.mcp_server.handlers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.tools.types import ToolParameter, ToolResult, ToolSpec


def tool_spec_to_mcp_tool(spec: ToolSpec) -> dict[str, Any]:
    """Convert a single SDK ToolSpec into an MCP tools/list entry dict."""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required: list[str] = []
    for param in spec.parameters:
        prop: dict[str, Any] = {}
        if param.type:
            prop["type"] = param.type
        if param.description:
            prop["description"] = param.description
        input_schema["properties"][param.name] = prop
        if param.required:
            required.append(param.name)
    if required:
        input_schema["required"] = required
    return {
        "name": spec.name,
        "description": spec.description,
        "inputSchema": input_schema,
    }


def tool_result_to_mcp_content(result: ToolResult) -> list[dict[str, Any]]:
    """Convert an SDK ToolResult into an MCP content array."""
    return [{"type": "text", "text": result.output}]


def mcp_result_response(request_id: int | str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def mcp_error_response(request_id: int | str, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def mcp_tool_error_result(request_id: int | str, error_text: str) -> dict[str, Any]:
    """Build a tools/call response with isError flag for runtime failures."""
    return mcp_result_response(
        request_id,
        {"content": [{"type": "text", "text": error_text}], "isError": True},
    )


def mcp_tool_success_result(request_id: int | str, content: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a tools/call success response."""
    return mcp_result_response(request_id, {"content": content})


def parameters_from_input_schema(
    parameters: tuple[ToolParameter, ...],
) -> dict[str, dict[str, Any]]:
    """Extract supported keyword arguments from ToolParameter definitions
    for invoking an SDK tool via tool_spec_to_mcp_tool inputSchema.
    """
    params: dict[str, dict[str, Any]] = {}
    for param in parameters:
        params[param.name] = param
    return params
