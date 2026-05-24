from __future__ import annotations

import unittest

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies import BaseStrategy, StrategyChain, StrategyResult


class AppendStrategy(BaseStrategy):
    def __init__(self, name: str, suffix: str) -> None:
        self.name = name
        self.suffix = suffix
        self.seen_prompts: list[str] = []

    async def arun(self, prompt: str, **_: object) -> StrategyResult:
        self.seen_prompts.append(prompt)
        return StrategyResult(
            output=f"{prompt}{self.suffix}",
            strategy_name=self.name,
            metadata={"suffix": self.suffix},
        )


class StrategyChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_chain_threads_only_output_between_strategies(self) -> None:
        first = AppendStrategy("first", "-a")
        second = AppendStrategy("second", "-b")

        result = await StrategyChain([first, second]).arun("start")

        self.assertEqual(result.output, "start-a-b")
        self.assertEqual(first.seen_prompts, ["start"])
        self.assertEqual(second.seen_prompts, ["start-a"])
        self.assertEqual(result.metadata["stage_names"], ("first", "second"))

    async def test_chain_metadata_records_stage_names_and_metadata(self) -> None:
        result = await StrategyChain(
            [
                AppendStrategy("draft", " draft"),
                AppendStrategy("polish", " polished"),
            ]
        ).arun("answer")

        self.assertEqual(result.strategy_name, "strategy_chain")
        self.assertEqual(result.metadata["stage_count"], 2)
        self.assertEqual(result.metadata["stages"][0]["metadata"], {"suffix": " draft"})
        self.assertEqual(len(result.calls), 2)

    def test_empty_chain_fails(self) -> None:
        with self.assertRaises(StrategyExecutionError):
            StrategyChain([])


if __name__ == "__main__":
    unittest.main()
