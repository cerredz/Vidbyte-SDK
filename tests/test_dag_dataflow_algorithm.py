"""Context Protocol Header

Description:
    Tests for the DAG Dataflow runtime context-window algorithm.
Purpose:
    Validates preset wiring, config validation, DAG parsing, topological ordering,
    cycle detection, and runtime behavior using fake runners.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.algorithms import DAGDataflowRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms.dag_dataflow import DAGDataflowAlgorithm
from vidbyte.context.window import ContextWindow
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return dict(getattr(response, "metadata", {}))


class DAGDataflowAlgorithmConfigTests(unittest.TestCase):
    def test_context_window_preset_exposes_dag_dataflow_algorithm(self) -> None:
        # [Hidden Assumption] preset name and type correct.
        algorithm = ContextWindow.preset.dag_dataflow

        self.assertEqual(algorithm.name, "dag_dataflow")
        self.assertIsInstance(algorithm.dag_dataflow, DAGDataflowAlgorithm)

    def test_resolve_algorithm_accepts_dag_dataflow_string(self) -> None:
        # [Hidden Assumption] string resolution works.
        algorithm = ContextWindow.resolve_algorithm("dag_dataflow")

        self.assertEqual(algorithm.name, "dag_dataflow")

    def test_dag_dataflow_algorithm_raises_on_zero_max_nodes(self) -> None:
        # [Edge Case] max_nodes=0 is invalid.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(max_nodes=0)

    def test_dag_dataflow_algorithm_raises_on_zero_max_parallel(self) -> None:
        # [Edge Case] max_parallel=0 is invalid.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(max_parallel=0)

    def test_dag_dataflow_algorithm_raises_on_zero_max_plan_chars(self) -> None:
        # [Edge Case] max_plan_chars=0 is invalid.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(max_plan_chars=0)

    def test_dag_dataflow_algorithm_raises_on_zero_max_node_output_chars(self) -> None:
        # [Edge Case] max_node_output_chars=0 is invalid.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(max_node_output_chars=0)

    def test_dag_dataflow_algorithm_rejects_empty_planner_prompt(self) -> None:
        # [Edge Case] empty string override should raise.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(planner_system_prompt="")

    def test_dag_dataflow_algorithm_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] metadata keys must be strings.
        with self.assertRaises(ConfigurationError):
            DAGDataflowAlgorithm(metadata={1: "value"})  # type: ignore[arg-type]

    def test_dag_dataflow_algorithm_parse_dag_plan_valid_json(self) -> None:
        # [Hidden Assumption] valid JSON array parsed correctly.
        algorithm = DAGDataflowAlgorithm()
        nodes = algorithm.parse_dag_plan('[{"id":"A","description":"Step A","dependencies":[]}]')

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["id"], "A")

    def test_dag_dataflow_algorithm_parse_dag_plan_strips_markdown_fences(self) -> None:
        # [Hidden Failure] fences must be stripped before JSON parse.
        algorithm = DAGDataflowAlgorithm()
        plan_with_fences = '```json\n[{"id":"A","description":"Step A","dependencies":[]}]\n```'
        nodes = algorithm.parse_dag_plan(plan_with_fences)

        self.assertEqual(len(nodes), 1)

    def test_dag_dataflow_algorithm_parse_dag_plan_invalid_json_raises(self) -> None:
        # [Edge Case] invalid JSON must raise AgentExecutionError.
        algorithm = DAGDataflowAlgorithm()
        with self.assertRaises(AgentExecutionError):
            algorithm.parse_dag_plan("not json at all")

    def test_dag_dataflow_algorithm_parse_dag_plan_non_array_raises(self) -> None:
        # [Edge Case] JSON object (not array) must raise AgentExecutionError.
        algorithm = DAGDataflowAlgorithm()
        with self.assertRaises(AgentExecutionError):
            algorithm.parse_dag_plan('{"id": "A"}')

    def test_dag_dataflow_algorithm_truncates_to_max_nodes(self) -> None:
        # [Silent Failure] plan with more nodes than max_nodes must be truncated.
        algorithm = DAGDataflowAlgorithm(max_nodes=2)
        plan = '[{"id":"A","description":"A","dependencies":[]},{"id":"B","description":"B","dependencies":[]},{"id":"C","description":"C","dependencies":[]}]'
        nodes = algorithm.parse_dag_plan(plan)

        self.assertEqual(len(nodes), 2)

    def test_dag_dataflow_algorithm_truncates_node_output(self) -> None:
        # [Silent Failure] node output exceeding limit must be truncated.
        algorithm = DAGDataflowAlgorithm(max_node_output_chars=10)
        truncated = algorithm.truncate_node_output("A" * 20)

        self.assertIn("truncated", truncated)


class DAGDataflowTopologicalTests(unittest.TestCase):
    def _make_algorithm(self) -> DAGDataflowAlgorithm:
        return DAGDataflowAlgorithm()

    def _make_adapter(self) -> DAGDataflowRuntimeAlgorithm:
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        return DAGDataflowRuntimeAlgorithm(runtime, self._make_algorithm())

    def test_topological_levels_linear_chain(self) -> None:
        # [Hidden Assumption] A→B→C must produce three separate levels.
        adapter = self._make_adapter()
        nodes = [
            {"id": "A", "description": "step A", "dependencies": []},
            {"id": "B", "description": "step B", "dependencies": ["A"]},
            {"id": "C", "description": "step C", "dependencies": ["B"]},
        ]
        levels = adapter._topological_levels(nodes)

        self.assertEqual(len(levels), 3)
        self.assertEqual([n["id"] for n in levels[0]], ["A"])
        self.assertEqual([n["id"] for n in levels[1]], ["B"])
        self.assertEqual([n["id"] for n in levels[2]], ["C"])

    def test_topological_levels_parallel_roots(self) -> None:
        # [Hidden Failure] A and B with no deps must be at level 0 together.
        adapter = self._make_adapter()
        nodes = [
            {"id": "A", "description": "step A", "dependencies": []},
            {"id": "B", "description": "step B", "dependencies": []},
            {"id": "C", "description": "step C", "dependencies": ["A", "B"]},
        ]
        levels = adapter._topological_levels(nodes)

        self.assertEqual(len(levels), 2)
        level_0_ids = {n["id"] for n in levels[0]}
        self.assertIn("A", level_0_ids)
        self.assertIn("B", level_0_ids)

    def test_cycle_detection_raises_on_cycle(self) -> None:
        # [Edge Case] A→B→A cycle must raise AgentExecutionError.
        adapter = self._make_adapter()
        nodes = [
            {"id": "A", "description": "step A", "dependencies": ["B"]},
            {"id": "B", "description": "step B", "dependencies": ["A"]},
        ]
        with self.assertRaises(AgentExecutionError):
            adapter._validate_no_cycles(nodes)

    def test_cycle_detection_passes_for_valid_dag(self) -> None:
        # [Hidden Assumption] valid acyclic graph must not raise.
        adapter = self._make_adapter()
        nodes = [
            {"id": "A", "description": "step A", "dependencies": []},
            {"id": "B", "description": "step B", "dependencies": ["A"]},
        ]
        adapter._validate_no_cycles(nodes)


class DAGDataflowDispatcherTests(unittest.TestCase):
    def test_dispatcher_detects_dag_dataflow_algorithm(self) -> None:
        # [Hidden Assumption] dispatcher must detect the preset.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.dag_dataflow,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "dag_dataflow")

    def test_dispatcher_returns_dag_dataflow_runtime_algorithm(self) -> None:
        # [Hidden Failure] return_algorithm must return the correct adapter type.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.dag_dataflow,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertIsInstance(dispatcher.return_algorithm(), DAGDataflowRuntimeAlgorithm)


class DAGDataflowRuntimeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_dag_dataflow_runtime_executes_nodes_and_synthesizes(self) -> None:
        # [Hidden Assumption] full pipeline: plan → execute → synthesize.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="dag_dataflow", dag_dataflow=DAGDataflowAlgorithm()),
        )
        runner = FakeRunner([
            # Planner response
            FakeResponse('[{"id":"A","description":"Step A","dependencies":[]},{"id":"B","description":"Step B","dependencies":["A"]}]'),
            # Node A execution (isDone)
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "output of A"}', "call_id": "c1"}]}),
            # Node B execution (isDone)
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "output of B"}', "call_id": "c2"}]}),
            # Synthesizer response
            FakeResponse("Final synthesized answer."),
        ])
        context = runtime.build_context("my task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "my task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "Final synthesized answer.")
        self.assertIn("dag_dataflow", result.metadata)
        self.assertEqual(result.metadata["dag_dataflow"]["node_count"], 2)

    async def test_dag_dataflow_runtime_raises_on_cycle_in_plan(self) -> None:
        # [Edge Case] plan with cycle must raise AgentExecutionError.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="dag_dataflow", dag_dataflow=DAGDataflowAlgorithm()),
        )
        runner = FakeRunner([
            FakeResponse('[{"id":"A","description":"Step A","dependencies":["B"]},{"id":"B","description":"Step B","dependencies":["A"]}]'),
        ])
        context = runtime.build_context("my task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        with self.assertRaises(AgentExecutionError):
            await runtime.arun(
                "my task",
                runner=runner,
                context=context,
                provider="openai",
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
            )


if __name__ == "__main__":
    unittest.main()
