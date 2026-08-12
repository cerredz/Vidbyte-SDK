"""Gemini's tool wire format is an OpenAPI subset, not full JSON Schema or OpenAI roles."""

from __future__ import annotations

import json
import unittest

from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolResult, ToolSpec
from vidbyte.lib.tools import ToolsFormatter


def _spec_with_schema(schema: dict) -> ToolSpec:
    return ToolSpec(name="submitThing", description="Submit a thing.", input_schema=schema)


class GeminiToolSchemaTests(unittest.TestCase):
    """`parameters` must contain only keywords Gemini's Schema type accepts."""

    def test_additional_properties_is_dropped(self) -> None:
        # Every spec-declared tool goes through _parameters_schema, which stamps
        # additionalProperties: False. Gemini rejects the whole request over it.
        spec = ToolSpec(
            name="isDone",
            description="Signal completion.",
            parameters=(ToolParameter(name="done", type="bool", description="d", required=True),),
        )
        blob = json.dumps(ToolsFormatter.to_gemini_tool(spec))
        self.assertNotIn("additionalProperties", blob)

    def test_defs_and_refs_are_inlined(self) -> None:
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}},
            "$defs": {"Item": {"type": "object", "properties": {"name": {"type": "string"}}}},
        }
        parameters = ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]
        blob = json.dumps(parameters)
        self.assertNotIn("$defs", blob)
        self.assertNotIn("$ref", blob)
        self.assertEqual(parameters["properties"]["items"]["items"]["properties"]["name"]["type"], "string")

    def test_supported_keywords_survive(self) -> None:
        schema = {
            "type": "object",
            "description": "d",
            "properties": {"n": {"type": "integer", "minimum": 1, "enum": [1, 2]}},
            "required": ["n"],
        }
        parameters = ToolsFormatter.to_gemini_tool(_spec_with_schema(schema))["function_declarations"][0]["parameters"]
        self.assertEqual(parameters["required"], ["n"])
        self.assertEqual(parameters["properties"]["n"]["minimum"], 1)
        self.assertEqual(parameters["properties"]["n"]["enum"], [1, 2])

    def test_recursive_ref_terminates(self) -> None:
        schema = {
            "type": "object",
            "properties": {"child": {"$ref": "#/$defs/Node"}},
            "$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}}},
        }
        blob = json.dumps(ToolsFormatter.to_gemini_tool(_spec_with_schema(schema)))
        self.assertNotIn("$ref", blob)


class GeminiToolResultRoleTests(unittest.TestCase):
    """generateContent accepts only 'user' and 'model' turns."""

    def test_tool_result_uses_a_user_turn(self) -> None:
        call = ToolCall("submitThing", {})
        message = ToolsFormatter.format_tool_result(call, ToolResult.success("submitThing", "ok"), "gemini")
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["parts"][0]["functionResponse"]["name"], "submitThing")

    def test_tool_error_result_uses_a_user_turn(self) -> None:
        call = ToolCall("submitThing", {})
        message = ToolsFormatter.format_tool_result(call, ToolResult.failure("submitThing", "boom"), "gemini")
        self.assertEqual(message["role"], "user")


if __name__ == "__main__":
    unittest.main()
