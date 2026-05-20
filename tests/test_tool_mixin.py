from __future__ import annotations

import unittest

from vidbyte.tools import ToolMixin, vidbyte_tool


class ToolOwner(ToolMixin):
    pass


class ToolMixinTests(unittest.TestCase):
    def test_with_tools_is_chainable_and_instance_local(self) -> None:
        @vidbyte_tool
        def alpha() -> str:
            return "alpha"

        left = ToolOwner().with_tools(alpha)
        right = ToolOwner()

        self.assertIsInstance(left, ToolOwner)
        self.assertEqual(len(left.tool_registry), 1)
        self.assertEqual(len(right.tool_registry), 0)

    def test_copy_tools_to_tool_mixin_target_is_idempotent(self) -> None:
        @vidbyte_tool
        def alpha() -> str:
            return "alpha"

        source = ToolOwner().with_tools(alpha)
        target = ToolOwner()

        source._copy_tools_to(target)
        source._copy_tools_to(target)

        self.assertEqual(len(target.tool_registry), 1)


if __name__ == "__main__":
    unittest.main()

