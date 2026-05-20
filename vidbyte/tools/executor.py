# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the ToolExecutor class for the Vidbyte SDK.
# Purpose: Bridges text generation output and actual Python code invocation of tools.
# Architecture & Functions:
#   - ToolExecutor (class): Manages parsing of action text, validating calls, and executing.
#   - ToolExecutor.parse_call(raw): Extracts Action/Action Input from model output strings.
#   - ToolExecutor.execute(raw): Async parsing and execution entry point.
# Codebase Relation:
#   - Orchestrates the ToolRegistry lookup and executes matches in the agent loops.
# Similar Files:
#   - None (ToolExecutor handles the execution transition boundary specifically)
# ==============================================================================

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import ToolCall, ToolResult, ToolStatus


class ToolExecutor:
    """
    Orchestrates parsing raw agent output text into structured calls,
    validating parameters, and executing the corresponding tools.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def parse_call(self, raw: str) -> Optional[ToolCall]:
        """
        Parses action details from raw text model responses.
        Looks for the format:
        Action: <tool_name>
        Action Input: {"param": "value"}
        """
        tool_match = re.search(r"Action:\s*(.+)", raw)
        input_match = re.search(r"Action Input:\s*(\{.*\})", raw, re.DOTALL)

        if not tool_match:
            return None

        tool_name = tool_match.group(1).strip()
        arguments: Dict[str, Any] = {}

        if input_match:
            try:
                # Strip potential markdown formatting if model wrapped JSON in backticks
                json_str = input_match.group(1).strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                json_str = json_str.strip()

                arguments = json.loads(json_str)
            except json.JSONDecodeError:
                pass

        return ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            raw=raw
        )

    async def execute(self, raw: str) -> ToolResult:
        """Parses a tool invocation block, validates the call, and runs the tool."""
        call = self.parse_call(raw)

        if not call:
            return ToolResult(
                tool_name="unknown",
                status=ToolStatus.ERROR,
                output=None,
                error="Could not parse tool call from model output"
            )

        tool = self.registry.get(call.tool_name)

        if not tool:
            available_names = [t.name for t in self.registry.all()]
            return ToolResult(
                tool_name=call.tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Tool '{call.tool_name}' not found in registry. "
                      f"Available tools: {available_names}"
            )

        # Run validation check
        validation_error = tool.validate_call(call)
        if validation_error:
            return ToolResult(
                tool_name=call.tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error=validation_error
            )

        try:
            return await tool.execute(call)
        except Exception as e:
            return ToolResult(
                tool_name=call.tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error=str(e)
            )
