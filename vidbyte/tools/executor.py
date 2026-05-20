from __future__ import annotations

import json
import re
from typing import Any

from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import ToolCall, ToolResult


class ToolExecutor:
    """Parse model action blocks and execute tools from a registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def parse_call(self, raw: str) -> ToolCall | None:
        tool_match = re.search(r"Action:\s*(?P<name>[^\n\r]+)", raw)
        if not tool_match:
            return None
        input_match = re.search(r"Action Input:\s*(?P<input>\{.*\})", raw, re.DOTALL)
        arguments: dict[str, Any] = {}
        if input_match:
            json_text = input_match.group("input").strip()
            try:
                arguments = json.loads(json_text)
            except json.JSONDecodeError as exc:
                return ToolCall(tool_name=tool_match.group("name").strip(), arguments={"__parse_error__": str(exc)}, raw=raw)
        return ToolCall(tool_name=tool_match.group("name").strip(), arguments=arguments, raw=raw)

    async def execute(self, raw: str) -> ToolResult:
        call = self.parse_call(raw)
        if call is None:
            return ToolResult.failure("unknown", "Could not parse tool call from model output.")
        if "__parse_error__" in call.arguments:
            return ToolResult.failure(call.tool_name, f"Invalid JSON arguments in tool call block: {call.arguments['__parse_error__']}")
        return await self.execute_call(call)

    async def execute_call(self, call: ToolCall) -> ToolResult:
        tool = self.registry.get(call.tool_name)
        if tool is None:
            available = ", ".join(tool.name for tool in self.registry.all()) or "none"
            return ToolResult.failure(call.tool_name, f"Tool '{call.tool_name}' not found. Available tools: {available}")
        validation_error = tool.validate_call(call)
        if validation_error:
            return ToolResult.failure(call.tool_name, validation_error, metadata={"error_type": "validation"})
        try:
            return await tool.execute(call)
        except Exception as exc:
            return ToolResult.failure(call.tool_name, str(exc), metadata={"error_type": exc.__class__.__name__})

