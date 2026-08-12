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


class GeminiContentsOrderingTests(unittest.TestCase):
    """`contents` must place the prompt before the tool exchange it provoked."""

    def _contents(self, messages: list) -> list:
        from vidbyte.lib.config import TextModelConfig
        from vidbyte.lib.enums import ModelProvider
        from vidbyte.providers.gemini import GeminiProvider

        config = TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-3.6-flash", messages=tuple(messages))
        return GeminiProvider()._create_contents(config, "do the thing")

    def test_prompt_precedes_a_trailing_tool_exchange(self) -> None:
        contents = self._contents(
            [
                {"role": "model", "parts": [{"functionCall": {"name": "t", "args": {}}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "t", "response": {}}}]},
            ]
        )
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[0]["parts"][0]["text"], "do the thing")

    def test_prompt_appends_when_history_has_no_tool_turns(self) -> None:
        contents = self._contents([{"role": "user", "parts": [{"text": "earlier"}]}])
        self.assertEqual(contents[-1]["parts"][0]["text"], "do the thing")

    def test_prompt_follows_plain_history_but_precedes_tool_block(self) -> None:
        contents = self._contents(
            [
                {"role": "user", "parts": [{"text": "earlier"}]},
                {"role": "model", "parts": [{"functionCall": {"name": "t", "args": {}}}]},
            ]
        )
        self.assertEqual(contents[0]["parts"][0]["text"], "earlier")
        self.assertEqual(contents[1]["parts"][0]["text"], "do the thing")
        self.assertIn("functionCall", contents[2]["parts"][0])

    def test_openai_shaped_history_is_converted_to_parts(self) -> None:
        # Contract feedback and assistant turns are appended in the OpenAI {role, content}
        # shape, which Gemini cannot read.
        contents = self._contents([{"role": "assistant", "content": "prior answer"}])
        self.assertEqual(contents[0]["role"], "model")
        self.assertEqual(contents[0]["parts"][0]["text"], "prior answer")
        self.assertNotIn("content", contents[0])
