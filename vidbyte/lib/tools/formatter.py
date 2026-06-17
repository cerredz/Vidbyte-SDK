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
from collections.abc import Iterable, Mapping
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolResult, ToolSpec


class ToolsFormatter:
    """Formats SDK tool specs and provider tool calls."""

    @staticmethod
    def provider_from_model(provider_or_model: str | None) -> str:
        """Return a provider family from a provider name or model-ish string."""
        if not provider_or_model:
            return "openai"
        value = provider_or_model.lower()
        if "anthropic" in value or "claude" in value:
            return "anthropic"
        if "gemini" in value or "google" in value:
            return "gemini"
        if "grok" in value or "xai" in value:
            return "xai"
        return "openai"

    @staticmethod
    def format_tools(tools: object, provider_or_model: str) -> tuple[dict[str, Any], ...]:
        """Format a tool catalog or iterable of specs for a provider family."""
        specs_method = getattr(tools, "specs", None)
        if callable(specs_method):
            specs = tuple(specs_method())
        else:
            specs = tuple(tools) if isinstance(tools, Iterable) else ()
        provider = ToolsFormatter.provider_from_model(provider_or_model)
        formatted: list[dict[str, Any]] = []
        for spec in specs:
            if not isinstance(spec, ToolSpec):
                spec_method = getattr(spec, "spec", None)
                spec = spec_method() if callable(spec_method) else spec
            if not isinstance(spec, ToolSpec):
                continue
            if provider == "anthropic":
                formatted.append(ToolsFormatter.to_anthropic_tool(spec))
            elif provider == "gemini":
                formatted.append(ToolsFormatter.to_gemini_tool(spec))
            else:
                formatted.append(ToolsFormatter.to_openai_tool(spec))
        return tuple(formatted)

    @staticmethod
    def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into an OpenAI-compatible function tool."""
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": ToolsFormatter._schema_for_spec(spec),
            },
        }

    @staticmethod
    def to_anthropic_tool(spec: ToolSpec) -> dict[str, Any]:
        """Convert a ToolSpec into an Anthropic Claude tool declaration."""
        return {
            "name": spec.name,
            "description": spec.description,
            "input_schema": ToolsFormatter._schema_for_spec(spec),
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
                    "parameters": ToolsFormatter._schema_for_spec(spec),
                }
            ]
        }

    @staticmethod
    def parse_tool_calls(raw: object, provider_or_model: str) -> tuple[ToolCall, ...]:
        """Parse provider-native tool calls from a raw model response."""
        raw_payload = getattr(raw, "raw", raw)
        if not isinstance(raw_payload, Mapping):
            return ()
        provider = ToolsFormatter.provider_from_model(provider_or_model)
        if provider == "anthropic":
            return ToolsFormatter._parse_anthropic_tool_calls(raw_payload)
        if provider == "gemini":
            return ToolsFormatter._parse_gemini_tool_calls(raw_payload)
        return ToolsFormatter._parse_openai_tool_calls(raw_payload)

    @staticmethod
    def format_assistant_tool_calls(raw: object, provider_or_model: str) -> Mapping[str, Any] | None:
        """Extract the assistant/model turn from a tool-call response so it can precede tool results."""
        raw_payload = getattr(raw, "raw", raw)
        if not isinstance(raw_payload, Mapping):
            return None
        provider = ToolsFormatter.provider_from_model(provider_or_model)
        if provider == "anthropic":
            return ToolsFormatter._assistant_turn_anthropic(raw_payload)
        if provider == "gemini":
            return ToolsFormatter._assistant_turn_gemini(raw_payload)
        return ToolsFormatter._assistant_turn_openai(raw_payload)

    @staticmethod
    def _assistant_turn_openai(raw_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return the assistant message from an OpenAI chat-completions payload, or None for Responses API."""
        if isinstance(raw_payload.get("output"), list):
            return None
        choices = raw_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
        if isinstance(message, Mapping) and isinstance(message.get("tool_calls"), list):
            return dict(message)
        return None

    @staticmethod
    def _assistant_turn_anthropic(raw_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return an assistant message wrapping the full content list from an Anthropic payload."""
        content = raw_payload.get("content")
        if not isinstance(content, list) or not content:
            return None
        has_tool_use = any(isinstance(item, Mapping) and item.get("type") == "tool_use" for item in content)
        if not has_tool_use:
            return None
        return {"role": "assistant", "content": list(content)}

    @staticmethod
    def _assistant_turn_gemini(raw_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return the model content from a Gemini candidates payload."""
        candidates = raw_payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return None
        content = candidates[0].get("content") if isinstance(candidates[0], Mapping) else None
        if not isinstance(content, Mapping):
            return None
        parts = content.get("parts")
        if not isinstance(parts, list):
            return None
        has_function_call = any(
            isinstance(p, Mapping) and ("functionCall" in p or "function_call" in p) for p in parts
        )
        if not has_function_call:
            return None
        return dict(content)

    @staticmethod
    def format_tool_result(
        call: ToolCall,
        result: ToolResult,
        provider_or_model: str,
    ) -> Mapping[str, Any]:
        """Format a local tool result for a follow-up provider request."""
        provider = ToolsFormatter.provider_from_model(provider_or_model)
        call_id = call.call_id or call.tool_name
        if provider == "anthropic":
            return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": result.output}]}
        if provider == "gemini":
            return {
                "role": "function",
                "parts": [
                    {
                        "functionResponse": {
                            "name": call.tool_name,
                            "response": {"output": result.output, "status": result.status.value},
                        }
                    }
                ],
            }
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "name": call.tool_name,
            "content": result.output,
        }

    @staticmethod
    def parse_openai_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse an OpenAI-compatible tool call into a ToolCall."""
        function = raw_call.get("function", raw_call)
        if not isinstance(function, Mapping):
            raise ValueError("OpenAI tool call must include a function object")
        name = str(function.get("name", ""))
        return ToolCall(
            name,
            ToolsFormatter._parse_arguments(function.get("arguments", {})),
            call_id=str(raw_call.get("id") or raw_call.get("call_id") or "") or None,
        )

    @staticmethod
    def parse_anthropic_tool_call(raw_call: Mapping[str, Any]) -> ToolCall:
        """Parse an Anthropic tool_use block into a ToolCall."""
        name = str(raw_call.get("name", ""))
        raw_input = raw_call.get("input", {})
        if not isinstance(raw_input, Mapping):
            raise ValueError("Anthropic tool input must be an object")
        return ToolCall(
            name,
            dict(raw_input),
            call_id=str(raw_call.get("id") or "") or None,
        )

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
        return ToolCall(
            str(function_call.get("name", "")),
            dict(args),
            call_id=str(raw_call.get("id") or "") or None,
        )

    @staticmethod
    def _schema_for_spec(spec: ToolSpec) -> dict[str, Any]:
        """Return the best available JSON Schema for a tool spec."""
        if isinstance(spec.input_schema, Mapping):
            return dict(spec.input_schema)
        return ToolsFormatter._parameters_schema(spec.parameters)

    @staticmethod
    def _parse_openai_tool_calls(raw_payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
        """Parse OpenAI Responses or chat-completions tool call payloads."""
        calls: list[ToolCall] = []
        output = raw_payload.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, Mapping) and item.get("type") in {"function_call", "tool_call"}:
                    calls.append(
                        ToolCall(
                            str(item.get("name", "")),
                            ToolsFormatter._parse_arguments(item.get("arguments", {})),
                            call_id=str(item.get("call_id") or item.get("id") or "") or None,
                            metadata={"provider_shape": "openai_responses"},
                        )
                    )
        choices = raw_payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                message = choice.get("message") if isinstance(choice, Mapping) else None
                tool_calls = message.get("tool_calls") if isinstance(message, Mapping) else None
                if isinstance(tool_calls, list):
                    for raw_call in tool_calls:
                        if isinstance(raw_call, Mapping):
                            calls.append(ToolsFormatter.parse_openai_tool_call(raw_call))
        return tuple(call for call in calls if call.tool_name)

    @staticmethod
    def _parse_anthropic_tool_calls(raw_payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
        """Parse Anthropic tool_use content blocks."""
        content = raw_payload.get("content")
        if not isinstance(content, list):
            return ()
        calls = [
            ToolsFormatter.parse_anthropic_tool_call(item)
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "tool_use"
        ]
        return tuple(call for call in calls if call.tool_name)

    @staticmethod
    def _parse_gemini_tool_calls(raw_payload: Mapping[str, Any]) -> tuple[ToolCall, ...]:
        """Parse Gemini function call parts."""
        calls: list[ToolCall] = []
        candidates = raw_payload.get("candidates")
        if not isinstance(candidates, list):
            return ()
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, Mapping) else None
            parts = content.get("parts") if isinstance(content, Mapping) else None
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, Mapping) and ("functionCall" in part or "function_call" in part):
                    calls.append(ToolsFormatter.parse_gemini_tool_call(part))
        return tuple(call for call in calls if call.tool_name)

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
