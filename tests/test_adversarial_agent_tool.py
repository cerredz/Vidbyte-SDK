"""Context Protocol Header

Description:
    Tests for the AdversarialAgentTool wrapper.
Purpose:
    Validates critique callable execution, output bounding, metadata, and
    configuration failure paths.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools import AdversarialAgentTool, ToolCall, ToolPermission


class AdversarialAgentToolTests(unittest.IsolatedAsyncioTestCase):
    def test_tool_requires_exactly_one_executor(self) -> None:
        # Verifies the tool cannot be configured without a single critique executor.
        with self.assertRaises(ConfigurationError):
            AdversarialAgentTool()

        with self.assertRaises(ConfigurationError):
            AdversarialAgentTool(agent=object(), critique=lambda args: "bad")  # type: ignore[arg-type]

    def test_tool_rejects_empty_name(self) -> None:
        # Verifies invalid tool names fail at construction time.
        with self.assertRaises(ConfigurationError):
            AdversarialAgentTool(critique=lambda args: "critique", name=" ")

    def test_tool_rejects_zero_max_output_chars(self) -> None:
        # Verifies invalid output bounds fail at construction time.
        with self.assertRaises(ConfigurationError):
            AdversarialAgentTool(critique=lambda args: "critique", max_output_chars=0)

    async def test_tool_callable_exception_returns_error_result(self) -> None:
        # Verifies callable failures become ToolResult.error instead of uncaught exceptions.
        def fail(_: object) -> str:
            raise RuntimeError("boom")

        tool = AdversarialAgentTool(critique=fail)
        result = await tool.execute(_call())

        self.assertEqual(result.status.value, "error")
        self.assertIn("boom", result.output)

    async def test_tool_bounds_callable_output(self) -> None:
        # Verifies overlong critique text is truncated within the configured bound.
        tool = AdversarialAgentTool(critique=lambda args: "x" * 100, max_output_chars=30)
        result = await tool.execute(_call())

        self.assertEqual(result.status.value, "success")
        self.assertLessEqual(len(result.output), 30)
        self.assertIn("truncated", result.output)

    async def test_tool_rejects_empty_callable_output(self) -> None:
        # Verifies blank critique output does not become a blank success.
        tool = AdversarialAgentTool(critique=lambda args: "   ")
        result = await tool.execute(_call())

        self.assertEqual(result.status.value, "error")
        self.assertIn("empty", result.metadata["error"])

    def test_tool_spec_is_safe_and_internal_metadata_is_set(self) -> None:
        # Verifies the tool declares safe permission and internal scheduling metadata.
        spec = AdversarialAgentTool(critique=lambda args: "critique").spec()

        self.assertEqual(spec.permission, ToolPermission.SAFE)
        self.assertTrue(spec.metadata["internal"])
        self.assertTrue(spec.metadata["adversarial_agent_tool"])


def _call() -> ToolCall:
    # Build a representative adversarial tool call for tests.
    return ToolCall(
        "adversarial_critique",
        {
            "task": "task",
            "trajectory": "trajectory",
            "iteration_count": 1,
            "critique_count": 0,
        },
    )


if __name__ == "__main__":
    unittest.main()

