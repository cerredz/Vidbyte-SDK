from __future__ import annotations

import unittest

from vidbyte import Tools, tool, vidbyte_tool
from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools import ToolRegistry


class ToolsCatalogTests(unittest.TestCase):
    def test_tool_decorator_alias_matches_vidbyte_tool(self) -> None:
        @tool
        def alpha(value: int) -> int:
            """Alpha tool."""
            return value

        @vidbyte_tool
        def beta(value: int) -> int:
            """Beta tool."""
            return value

        self.assertEqual(alpha.spec().name, "alpha")
        self.assertEqual(beta.spec().name, "beta")

    def test_catalog_describes_specs_and_names(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return topic

        catalog = Tools([lookup])

        self.assertEqual(catalog.names(), ("lookup",))
        self.assertEqual(catalog[0].name, "lookup")
        self.assertIn("Look up a topic", catalog.describe())
        self.assertEqual(catalog.specs()[0].name, "lookup")

    def test_catalog_rejects_duplicate_names(self) -> None:
        @tool(name="same")
        def first() -> str:
            return "first"

        @tool(name="same")
        def second() -> str:
            return "second"

        with self.assertRaises(ToolRegistrationError):
            Tools([first, second])

    def test_catalog_formats_provider_schemas(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return topic

        catalog = Tools([lookup])

        openai_schema = catalog.provider_schemas("openai")[0]
        anthropic_schema = catalog.provider_schemas("anthropic")[0]
        gemini_schema = catalog.provider_schemas("gemini")[0]

        self.assertEqual(openai_schema["function"]["name"], "lookup")
        self.assertEqual(anthropic_schema["name"], "lookup")
        self.assertEqual(gemini_schema["function_declarations"][0]["name"], "lookup")

    def test_tool_registry_compatibility(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return topic

        registry = ToolRegistry()
        registry.register(lookup)

        self.assertEqual(registry.get("lookup").name, "lookup")
        self.assertIn("Look up a topic", registry.specs_as_prompt_str())


if __name__ == "__main__":
    unittest.main()
