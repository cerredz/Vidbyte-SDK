from __future__ import annotations

import unittest

from vidbyte.providers import tool_spec_to_provider_schema
from vidbyte.tools import vidbyte_tool


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


if __name__ == "__main__":
    unittest.main()

