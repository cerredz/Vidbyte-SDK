from __future__ import annotations

import unittest

from vidbyte.agents import AgentRegistry, BaseAgent
from vidbyte.lib.errors import AgentRegistryError
from vidbyte.tools import ToolSpec


class FakeTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(name="calculator", description="Math")


class AgentRegistryTests(unittest.TestCase):
    def test_lookup_and_filtering(self) -> None:
        registry = AgentRegistry()
        worker = BaseAgent(
            name="worker",
            system_prompt="Work.",
            tools=[FakeTool()],
            capabilities=["math"],
            metadata={"role": "worker"},
        )
        evaluator = BaseAgent(
            name="judge",
            system_prompt="Judge.",
            metadata={"role": "evaluator"},
        )
        registry.register(worker)
        registry.register(evaluator)

        self.assertIs(registry.get("worker"), worker)
        self.assertEqual(registry.find(metadata={"role": "worker"}), (worker,))
        self.assertEqual(registry.find(capability="math"), (worker,))
        self.assertEqual(registry.find(tool_name="calculator"), (worker,))
        self.assertEqual(len(registry.cards()), 2)

    def test_plain_function_tool_keeps_its_catalog_name(self) -> None:
        # @intent plain-function-tool-keeps-catalog-name
        def lookup_order(order_id: str) -> str:
            return order_id

        def cancel_order(order_id: str) -> str:
            return order_id

        registry = AgentRegistry()
        worker = BaseAgent(name="worker", system_prompt="Work.", tools=[lookup_order])
        registry.register(worker)

        self.assertEqual(worker.tools.names(), ("lookup_order",))
        self.assertEqual(worker.card().tool_names, ("lookup_order",))
        self.assertEqual(registry.find(tool_name="lookup_order"), (worker,))
        self.assertEqual(worker.export_state().tool_names, ("lookup_order",))
        same = BaseAgent.restore(worker.export_state(), tools=[lookup_order])
        self.assertNotIn("__resume_tool_mismatch__", same.metadata)
        swapped = BaseAgent.restore(worker.export_state(), tools=[cancel_order])
        self.assertEqual(
            swapped.metadata["__resume_tool_mismatch__"],
            {"expected": ["lookup_order"], "got": ["cancel_order"]},
        )

    def test_duplicate_and_missing_errors(self) -> None:
        registry = AgentRegistry()
        agent = BaseAgent(name="worker", system_prompt="Work.")
        registry.register(agent)
        with self.assertRaises(AgentRegistryError):
            registry.register(agent)
        with self.assertRaises(AgentRegistryError):
            registry.get("missing")


if __name__ == "__main__":
    unittest.main()
