"""Context Protocol Header

Description:
    Converts Vidbyte tool specs to model-provider tool formats.
Purpose:
    Keeps provider schema formatting separate from tool execution contracts so
    OpenAI, Anthropic, Grok, and Gemini adapters can share one SDK utility.
Architecture:
    - ToolsFormatter: Static provider conversion and parse helpers.
Relations:
    Related to vidbyte.lib.dataclasses.tools and future provider clients.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolSpec


class ToolsFormatter:
    """Formats SDK tool specs and provider tool calls."""

    @staticmethod
    def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into an OpenAI-compatible function tool."""
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": ToolsFormatter._parameters_schema(spec.parameters),
            },
        }

    @staticmethod
    def to_anthropic_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into an Anthropic Claude tool declaration."""
        return {
            "name": spec.name,
            "description": spec.description,
            "input_schema": ToolsFormatter._parameters_schema(spec.parameters),
        }

    @staticmethod
    def to_grok_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into a Grok/xAI OpenAI-compatible tool."""
        return ToolsFormatter.to_openai_tool(spec)

    @staticmethod
    def to_gemini_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into a Gemini function declaration."""
        return {
            "function_declarations": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": ToolsFormatter._parameters_schema(spec.parameters),
                }
            ]
        }

    @staticmethod
    def parse_openai_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse an OpenAI-compatible tool call into a ToolCall."""
        function = raw_call.get("function", raw_call)
        if not isinstance(function, Mapping):
            raise ValueError("OpenAI tool call must include a function object")
        name = str(function.get("name", ""))
        return ToolCall(name, ToolsFormatter._parse_arguments(function.get("arguments", {})))

    @staticmethod
    def parse_anthropic_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse an Anthropic tool_use block into a ToolCall."""
        name = str(raw_call.get("name", ""))
        raw_input = raw_call.get("input", {})
        if not isinstance(raw_input, Mapping):
            raise ValueError("Anthropic tool input must be an object")
        return ToolCall(name, dict(raw_input))

    @staticmethod
    def parse_grok_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse a Grok/xAI OpenAI-compatible tool call into a ToolCall."""
        return ToolsFormatter.parse_openai_tool_call(raw_call)

    @staticmethod
    def parse_gemini_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse a Gemini function call into a ToolCall."""
        function_call = raw_call.get("functionCall") or raw_call.get("function_call") or raw_call
        if not isinstance(function_call, Mapping):
            raise ValueError("Gemini tool call must include a function call object")
        args = function_call.get("args", {})
        if not isinstance(args, Mapping):
            raise ValueError("Gemini function call args must be an object")
        return ToolCall(str(function_call.get("name", "")), dict(args))

    @staticmethod
    def _parameters_schema(parameters: tuple[ToolParameter, ...]) -> dict[str, Any]:
        """Build a JSON Schema object for provider function parameters."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in parameters:
            properties[parameter.name] = {
                "type": ToolsFormatter._json_type(parameter.type),
                "description": parameter.description,
            }
            if parameter.required:
                required.append(parameter.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @staticmethod
    def _json_type(raw_type: str) -> str:
        """Normalize SDK parameter type names into JSON Schema primitive types."""
        lowered = raw_type.lower()
        aliases = {
            "bool": "boolean",
            "dict": "object",
            "float": "number",
            "int": "integer",
            "list": "array",
            "str": "string",
        }
        return aliases.get(lowered, lowered if lowered else "string")

    @staticmethod
    def _parse_arguments(raw_arguments: object) -> dict[str, Any]:
        """Parse provider argument payloads into a plain dictionary."""
        if isinstance(raw_arguments, Mapping):
            return dict(raw_arguments)
        if isinstance(raw_arguments, str):
            if not raw_arguments.strip():
                return {}
            parsed = json.loads(raw_arguments)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        raise ValueError("Tool call arguments must decode to an object")
