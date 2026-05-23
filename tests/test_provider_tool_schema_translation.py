from __future__ import annotations

import unittest

from vidbyte.providers import tool_spec_to_provider_schema
from vidbyte.tools import ToolsFormatter, tool, vidbyte_tool


class ProviderToolSchemaTranslationTests(unittest.TestCase):
    def test_openai_and_xai_schema_shape(self) -> None:
        @vidbyte_tool
        def fetch_user_metrics(user_id: int) -> str:
            """Fetches user metrics."""
            return str(user_id)

        schema = tool_spec_to_provider_schema(fetch_user_metrics.spec(), "openai")

        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "fetch_user_metrics")
        self.assertIn("user_id", schema["function"]["parameters"]["properties"])

    def test_anthropic_schema_shape(self) -> None:
        @vidbyte_tool
        def clear_cache(cache_key: str) -> str:
            """Clears a cache key."""
            return cache_key

        schema = tool_spec_to_provider_schema(clear_cache.spec(), "anthropic")

        self.assertEqual(schema["name"], "clear_cache")
        self.assertIn("cache_key", schema["input_schema"]["properties"])

    def test_gemini_schema_shape(self) -> None:
        @vidbyte_tool
        def clear_cache(cache_key: str) -> str:
            """Clears a cache key."""
            return cache_key

        schema = tool_spec_to_provider_schema(clear_cache.spec(), "gemini")

        self.assertEqual(schema["name"], "clear_cache")
        self.assertIn("cache_key", schema["parameters"]["properties"])

    def test_parse_provider_tool_call_payloads(self) -> None:
        openai_calls = ToolsFormatter.parse_tool_calls(
            {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "sdk"}', "call_id": "call-1"}]},
            "openai",
        )
        chat_calls = ToolsFormatter.parse_tool_calls(
            {"choices": [{"message": {"tool_calls": [{"id": "call-2", "function": {"name": "lookup", "arguments": '{"topic": "chat"}'}}]}}]},
            "openai",
        )
        anthropic_calls = ToolsFormatter.parse_tool_calls(
            {"content": [{"type": "tool_use", "id": "call-3", "name": "lookup", "input": {"topic": "claude"}}]},
            "anthropic",
        )
        gemini_calls = ToolsFormatter.parse_tool_calls(
            {"candidates": [{"content": {"parts": [{"functionCall": {"name": "lookup", "args": {"topic": "gemini"}}}]}}]},
            "gemini",
        )

        self.assertEqual(openai_calls[0].tool_name, "lookup")
        self.assertEqual(chat_calls[0].call_id, "call-2")
        self.assertEqual(anthropic_calls[0].arguments["topic"], "claude")
        self.assertEqual(gemini_calls[0].arguments["topic"], "gemini")

    def test_tool_alias_schema_shape(self) -> None:
        @tool
        def fetch_user_metrics(user_id: int) -> str:
            """Fetches user metrics."""
            return str(user_id)

        schema = tool_spec_to_provider_schema(fetch_user_metrics.spec(), "xai")

        self.assertEqual(schema["function"]["name"], "fetch_user_metrics")


if __name__ == "__main__":
    unittest.main()

