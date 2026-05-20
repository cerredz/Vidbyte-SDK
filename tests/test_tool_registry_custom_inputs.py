from __future__ import annotations

import unittest

from vidbyte.lib.errors import ToolRegistrationError
from vidbyte.tools import ToolRegistry, vidbyte_tool


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

    def test_invalid_registration_input_raises(self) -> None:
        registry = ToolRegistry()

        with self.assertRaises(TypeError):
            registry.register(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

