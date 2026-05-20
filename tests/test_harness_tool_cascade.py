from __future__ import annotations

import unittest

from vidbyte.harnesses import BaseHarness
from vidbyte.strategies import ReActStrategy
from vidbyte.tools import vidbyte_tool


class HarnessToolCascadeTests(unittest.IsolatedAsyncioTestCase):
    async def test_harness_tools_cascade_to_attached_strategy(self) -> None:
        @vidbyte_tool
        async def fetch_user_metrics(user_id: int) -> str:
            """Fetches user metrics."""
            return f"metrics:{user_id}"

        strategy = ReActStrategy()
        harness = BaseHarness().with_strategy(strategy).with_tools([fetch_user_metrics])

        result = await harness.arun(
            "use the tool",
            model_output='Action: fetch_user_metrics\nAction Input: {"user_id": 42}',
        )

        self.assertIn("metrics:42", result.output)
        self.assertIsNotNone(strategy.tool_registry.get("fetch_user_metrics"))

    async def test_harness_cascade_does_not_duplicate_on_repeated_runs(self) -> None:
        @vidbyte_tool
        def ping() -> str:
            return "pong"

        strategy = ReActStrategy()
        harness = BaseHarness().with_strategy(strategy).with_tools([ping])

        await harness.arun("first")
        await harness.arun("second")

        self.assertEqual(len(strategy.tool_registry), 1)


if __name__ == "__main__":
    unittest.main()

