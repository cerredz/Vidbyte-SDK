from __future__ import annotations

import unittest

from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools import ToolRegistry, ToolsClient, vidbyte_tool


class ToolRegistryCustomInputTests(unittest.TestCase):
    def test_duplicate_names_raise(self) -> None:
        @vidbyte_tool(name="same")
        def first() -> str:
            return "first"

        @vidbyte_tool(name="same")
        def second() -> str:
            return "second"

        registry = ToolRegistry([first])

        with self.assertRaises(ToolRegistrationError):
            registry.register(second)

    def test_replace_allows_explicit_override(self) -> None:
        @vidbyte_tool(name="same")
        def first() -> str:
            return "first"

        @vidbyte_tool(name="same")
        def second() -> str:
            return "second"

        registry = ToolRegistry([first])
        registry.register(second, replace=True)

        self.assertIs(registry.get("same"), second)

    def test_refused_batch_registers_nothing(self) -> None:
        # @intent refused-batch-registers-nothing
        # A duplicate late in a batch refuses the whole batch, so the tools client's registry and
        # catalog stay in step and a corrected retry is not blocked by half-registered tools.
        @vidbyte_tool(name="search")
        def search() -> str:
            return "search"

        @vidbyte_tool(name="fetch")
        def fetch() -> str:
            return "fetch"

        @vidbyte_tool(name="search")
        def search_v2() -> str:
            return "search v2"

        registry = ToolRegistry()
        with self.assertRaises(ToolRegistrationError):
            registry.register_many([search, fetch, search_v2])
        self.assertEqual(registry.names(), ())
        registry.register_many([search, fetch])
        self.assertEqual(registry.names(), ("search", "fetch"))

        client = ToolsClient()
        with self.assertRaises(ToolRegistrationError):
            client.with_tools([search, fetch, search_v2])
        self.assertEqual(client.registry.names(), client.catalog.names())
        client.with_tools([search, fetch])
        self.assertEqual(client.registry.names(), ("search", "fetch"))

    def test_invalid_registration_input_raises(self) -> None:
        registry = ToolRegistry()

        with self.assertRaises(TypeError):
            registry.register(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

