from __future__ import annotations

import json
import unittest

from vidbyte.agents import BaseAgent
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import VerifiedMultiAgentOrchestrationStrategy


class QueueStrategy(BaseStrategy):
    def __init__(self, name: str, outputs: list[str]) -> None:
        self.name = name
        self.outputs = outputs
        self.last_context = None

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.last_context = kwargs.get("context")
        if self.outputs:
            output = self.outputs.pop(0)
        else:
            output = ""
        return StrategyResult(output=output, strategy_name=self.name)


class VmaoTests(unittest.IsolatedAsyncioTestCase):
    async def test_executes_dag_and_verifies(self) -> None:
        planner = BaseAgent(
            name="planner",
            system_prompt="Plan.",
            strategy=QueueStrategy(
                "planner",
                [
                    json.dumps(
                        [
                            {"id": "a", "question": "A?", "depends_on": []},
                            {"id": "b", "question": "B?", "depends_on": ["a"]},
                        ]
                    )
                ],
            ),
        )
        worker = BaseAgent(
            name="worker",
            system_prompt="Work.",
            strategy=QueueStrategy("worker", ["answer-a", "answer-b"]),
        )
        verifier = BaseAgent(
            name="verifier",
            system_prompt="Verify.",
            strategy=QueueStrategy(
                "verifier",
                [json.dumps({"approved": True, "score": 1.0, "gaps": [], "rationale": "ok"})],
            ),
            metadata={"role": "evaluator"},
        )
        strategy = VerifiedMultiAgentOrchestrationStrategy(
            planner=planner,
            workers=[worker],
            verifier=verifier,
            max_rounds=1,
        )

        result = await strategy.arun("task")
        self.assertIn("answer-a", result.output)
        self.assertIn("answer-b", result.output)
        self.assertEqual(result.metadata["rounds"], 1)
        self.assertEqual(verifier.strategy.last_context.strategy_metadata, {})
        self.assertEqual(tuple(tool.name for tool in verifier.strategy.last_context.tools), ())

    async def test_rejects_cycle(self) -> None:
        planner = BaseAgent(
            name="planner",
            system_prompt="Plan.",
            strategy=QueueStrategy(
                "planner",
                [
                    json.dumps(
                        [
                            {"id": "a", "question": "A?", "depends_on": ["b"]},
                            {"id": "b", "question": "B?", "depends_on": ["a"]},
                        ]
                    )
                ],
            ),
        )
        worker = BaseAgent(name="worker", system_prompt="Work.", strategy=QueueStrategy("worker", []))
        verifier = BaseAgent(name="verifier", system_prompt="Verify.", strategy=QueueStrategy("verifier", []))
        strategy = VerifiedMultiAgentOrchestrationStrategy(planner=planner, workers=[worker], verifier=verifier)

        with self.assertRaises(StrategyExecutionError):
            await strategy.arun("task")


if __name__ == "__main__":
    unittest.main()
