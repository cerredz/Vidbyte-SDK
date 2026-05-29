"""Context Protocol Header

Description:
    Tests for the Gossip/Epidemic Knowledge Propagation runtime algorithm.
Purpose:
    Validates preset wiring, config validation, gossip pairing logic, knowledge
    truncation, and runtime behavior using fake runners.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.algorithms import GossipRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms.gossip import GossipAlgorithm
from vidbyte.context.window import ContextWindow
from vidbyte.lib.errors import ConfigurationError
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


class GossipAlgorithmConfigTests(unittest.TestCase):
    def test_context_window_preset_exposes_gossip_algorithm(self) -> None:
        # [Hidden Assumption] preset name and type correct.
        algorithm = ContextWindow.preset.gossip

        self.assertEqual(algorithm.name, "gossip")
        self.assertIsInstance(algorithm.gossip, GossipAlgorithm)

    def test_resolve_algorithm_accepts_gossip_string(self) -> None:
        # [Hidden Assumption] string resolution works.
        algorithm = ContextWindow.resolve_algorithm("gossip")

        self.assertEqual(algorithm.name, "gossip")

    def test_gossip_algorithm_raises_on_num_agents_less_than_two(self) -> None:
        # [Edge Case] num_agents=1 is invalid (need at least 2 for gossip exchange).
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(num_agents=1)

    def test_gossip_algorithm_raises_on_zero_num_agents(self) -> None:
        # [Edge Case] num_agents=0 is invalid.
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(num_agents=0)

    def test_gossip_algorithm_raises_on_zero_gossip_rounds(self) -> None:
        # [Edge Case] gossip_rounds=0 is invalid.
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(gossip_rounds=0)

    def test_gossip_algorithm_raises_on_zero_max_knowledge_chars(self) -> None:
        # [Edge Case] max_knowledge_chars=0 is invalid.
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(max_knowledge_chars=0)

    def test_gossip_algorithm_rejects_empty_agent_prompt(self) -> None:
        # [Edge Case] empty string override should raise.
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(agent_system_prompt="")

    def test_gossip_algorithm_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] metadata keys must be strings.
        with self.assertRaises(ConfigurationError):
            GossipAlgorithm(metadata={1: "value"})  # type: ignore[arg-type]

    def test_gossip_algorithm_truncates_knowledge(self) -> None:
        # [Silent Failure] knowledge exceeding limit must be truncated with suffix.
        algorithm = GossipAlgorithm(max_knowledge_chars=10)
        truncated = algorithm.truncate_knowledge("A" * 20)

        self.assertIn("truncated", truncated)
        self.assertTrue(truncated.startswith("AAAAAAAAAA"))

    def test_gossip_algorithm_does_not_truncate_within_limit(self) -> None:
        # [Silent Failure] short knowledge must pass through unchanged.
        algorithm = GossipAlgorithm()
        knowledge = "Short knowledge."

        self.assertEqual(algorithm.truncate_knowledge(knowledge), knowledge)

    def test_gossip_algorithm_build_angle_cycles_when_more_agents_than_angles(self) -> None:
        # [Hidden Failure] angle index must cycle, not raise IndexError.
        algorithm = GossipAlgorithm(num_agents=2)
        angles = [algorithm.build_angle_for_agent(i, "task") for i in range(100)]

        self.assertEqual(len(angles), 100)
        for angle in angles:
            self.assertIsInstance(angle, str)
            self.assertIn("task", angle)

    def test_gossip_algorithm_render_merge_prompt_includes_both_stores(self) -> None:
        # [Hidden Assumption] merge prompt must include both knowledge stores.
        algorithm = GossipAlgorithm()
        prompt = algorithm.render_merge_prompt("knowledge A", "knowledge B")

        self.assertIn("knowledge A", prompt)
        self.assertIn("knowledge B", prompt)

    def test_gossip_algorithm_render_synthesis_prompt_includes_task_and_stores(self) -> None:
        # [Hidden Assumption] synthesis prompt must include task and all stores.
        algorithm = GossipAlgorithm(num_agents=2)
        prompt = algorithm.render_synthesis_prompt("the task", ["store one", "store two"])

        self.assertIn("the task", prompt)
        self.assertIn("store one", prompt)
        self.assertIn("store two", prompt)


class GossipPairingTests(unittest.TestCase):
    def _make_adapter(self) -> GossipRuntimeAlgorithm:
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        return GossipRuntimeAlgorithm(runtime, GossipAlgorithm(num_agents=4))

    def test_gossip_pairs_even_agents_produces_n_over_2_pairs(self) -> None:
        # [Hidden Assumption] 4 agents → 2 pairs per round.
        adapter = self._make_adapter()
        pairs = adapter._gossip_pairs(4, 0)

        self.assertEqual(len(pairs), 2)
        for a, b in pairs:
            self.assertNotEqual(a, b)

    def test_gossip_pairs_odd_agents_produces_floor_n_over_2_pairs(self) -> None:
        # [Edge Case] 3 agents → 1 pair per round; one agent unpaired.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        adapter = GossipRuntimeAlgorithm(runtime, GossipAlgorithm(num_agents=3))
        pairs = adapter._gossip_pairs(3, 0)

        self.assertEqual(len(pairs), 1)

    def test_gossip_pairs_uses_different_pairings_across_rounds(self) -> None:
        # [Hidden Failure] rotation scheme must produce different pairs in different rounds.
        adapter = self._make_adapter()
        pairs_round_0 = adapter._gossip_pairs(4, 0)
        pairs_round_1 = adapter._gossip_pairs(4, 1)

        self.assertNotEqual(pairs_round_0, pairs_round_1)


class GossipDispatcherTests(unittest.TestCase):
    def test_dispatcher_detects_gossip_algorithm(self) -> None:
        # [Hidden Assumption] dispatcher must detect the preset.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.gossip,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "gossip")

    def test_dispatcher_returns_gossip_runtime_algorithm(self) -> None:
        # [Hidden Failure] return_algorithm must return the correct adapter type.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.gossip,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertIsInstance(dispatcher.return_algorithm(), GossipRuntimeAlgorithm)


class GossipRuntimeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_gossip_runtime_initializes_agents_and_synthesizes(self) -> None:
        # [Hidden Assumption] full pipeline: init agents → gossip rounds → synthesize.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="gossip",
                gossip=GossipAlgorithm(num_agents=2, gossip_rounds=1),
            ),
        )
        runner = FakeRunner([
            # Agent 1 initialization
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "knowledge from agent 1"}', "call_id": "c1"}]}),
            # Agent 2 initialization
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "knowledge from agent 2"}', "call_id": "c2"}]}),
            # Gossip merge round 1
            FakeResponse("merged knowledge from agents 1 and 2"),
            # Synthesizer
            FakeResponse("final synthesized answer"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "final synthesized answer")
        self.assertIn("gossip", result.metadata)

    async def test_gossip_runtime_attaches_gossip_metadata(self) -> None:
        # [Hidden Assumption] metadata must include num_agents, gossip_rounds, knowledge_chars.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="gossip",
                gossip=GossipAlgorithm(num_agents=2, gossip_rounds=1),
            ),
        )
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "k1"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "k2"}', "call_id": "c2"}]}),
            FakeResponse("merged"),
            FakeResponse("synthesized"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        meta = result.metadata["gossip"]
        self.assertEqual(meta["num_agents"], 2)
        self.assertEqual(meta["gossip_rounds"], 1)
        self.assertIn("initial_knowledge_chars", meta)
        self.assertIn("final_knowledge_chars", meta)
        self.assertEqual(len(meta["initial_knowledge_chars"]), 2)
        self.assertEqual(len(meta["final_knowledge_chars"]), 2)

    async def test_gossip_runtime_handles_empty_agent_output(self) -> None:
        # [Edge Case] empty agent output must use fallback "(no output)", not crash.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="gossip",
                gossip=GossipAlgorithm(num_agents=2, gossip_rounds=1),
            ),
        )
        runner = FakeRunner([
            # Agent 1: empty output (no isDone, just text)
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": ""}', "call_id": "c1"}]}),
            # Agent 2: normal output
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "real knowledge"}', "call_id": "c2"}]}),
            # Merge
            FakeResponse("merged"),
            # Synthesize
            FakeResponse("synthesized"),
        ])
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertIsNotNone(result.output)


if __name__ == "__main__":
    unittest.main()
