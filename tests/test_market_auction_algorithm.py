"""Context Protocol Header

Description:
    Tests for the Market Auction runtime context-window algorithm.
Purpose:
    Validates preset wiring, config validation, bid parsing, winner selection,
    and runtime behavior using fake runners.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.algorithms import MarketAuctionRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms.market_auction import MarketAuctionAlgorithm
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


class MarketAuctionAlgorithmConfigTests(unittest.TestCase):
    def test_context_window_preset_exposes_market_auction_algorithm(self) -> None:
        # [Hidden Assumption] preset name and type correct.
        algorithm = ContextWindow.preset.market_auction

        self.assertEqual(algorithm.name, "market_auction")
        self.assertIsInstance(algorithm.market_auction, MarketAuctionAlgorithm)

    def test_resolve_algorithm_accepts_market_auction_string(self) -> None:
        # [Hidden Assumption] string resolution works.
        algorithm = ContextWindow.resolve_algorithm("market_auction")

        self.assertEqual(algorithm.name, "market_auction")

    def test_market_auction_algorithm_raises_on_zero_num_agents(self) -> None:
        # [Edge Case] num_agents=0 is invalid.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(num_agents=0)

    def test_market_auction_algorithm_raises_on_negative_num_agents(self) -> None:
        # [Edge Case] negative num_agents is invalid.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(num_agents=-1)

    def test_market_auction_algorithm_raises_on_zero_max_bid_chars(self) -> None:
        # [Edge Case] max_bid_chars=0 is invalid.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(max_bid_chars=0)

    def test_market_auction_algorithm_raises_on_roles_length_mismatch(self) -> None:
        # [Edge Case] roles tuple must have exactly num_agents entries.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(num_agents=3, roles=("A", "B"))

    def test_market_auction_algorithm_raises_on_empty_role_string(self) -> None:
        # [Edge Case] empty role string in tuple must raise.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(num_agents=2, roles=("Valid Role", ""))

    def test_market_auction_algorithm_accepts_valid_roles(self) -> None:
        # [Hidden Assumption] valid roles accepted without error.
        algorithm = MarketAuctionAlgorithm(num_agents=2, roles=("Data Analyst", "Code Reviewer"))

        self.assertEqual(algorithm.roles, ("Data Analyst", "Code Reviewer"))

    def test_market_auction_algorithm_rejects_empty_auctioneer_prompt(self) -> None:
        # [Edge Case] empty string override should raise.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(auctioneer_system_prompt="")

    def test_market_auction_algorithm_rejects_non_string_metadata_key(self) -> None:
        # [Hidden Assumption] metadata keys must be strings.
        with self.assertRaises(ConfigurationError):
            MarketAuctionAlgorithm(metadata={1: "value"})  # type: ignore[arg-type]

    def test_market_auction_algorithm_parse_bid_valid_json(self) -> None:
        # [Hidden Assumption] valid bid JSON parsed correctly.
        algorithm = MarketAuctionAlgorithm()
        bid = algorithm.parse_bid('{"can_handle": true, "confidence": 8, "approach": "Use domain expertise."}')

        self.assertTrue(bid["can_handle"])
        self.assertEqual(bid["confidence"], 8)

    def test_market_auction_algorithm_parse_bid_falls_back_on_malformed(self) -> None:
        # [Hidden Failure] malformed JSON must return safe default, not crash.
        algorithm = MarketAuctionAlgorithm()
        bid = algorithm.parse_bid("this is not json")

        self.assertFalse(bid["can_handle"])
        self.assertEqual(bid["confidence"], 0)

    def test_market_auction_algorithm_select_winner_picks_highest_confidence(self) -> None:
        # [Silent Failure] winner must be the role with the highest confidence.
        algorithm = MarketAuctionAlgorithm()
        roles = ["Role A", "Role B", "Role C"]
        bids = [
            {"can_handle": True, "confidence": 5, "approach": "approach A"},
            {"can_handle": True, "confidence": 9, "approach": "approach B"},
            {"can_handle": True, "confidence": 3, "approach": "approach C"},
        ]
        winning_role, _ = algorithm.select_winner(bids, roles)

        self.assertEqual(winning_role, "Role B")

    def test_market_auction_algorithm_select_winner_falls_back_when_no_handler(self) -> None:
        # [Edge Case] all can_handle=false → fallback to first role, no crash.
        algorithm = MarketAuctionAlgorithm()
        roles = ["Role A", "Role B"]
        bids = [
            {"can_handle": False, "confidence": 0, "approach": ""},
            {"can_handle": False, "confidence": 0, "approach": ""},
        ]
        winning_role, winning_bid = algorithm.select_winner(bids, roles)

        self.assertEqual(winning_role, "Role A")
        self.assertTrue(winning_bid.get("_fallback", False))

    def test_market_auction_algorithm_parse_roles_extracts_json_array(self) -> None:
        # [Hidden Assumption] valid JSON role array parsed correctly.
        algorithm = MarketAuctionAlgorithm(num_agents=3)
        roles = algorithm.parse_roles('["Data Analyst", "Code Reviewer", "Domain Expert"]')

        self.assertEqual(roles, ["Data Analyst", "Code Reviewer", "Domain Expert"])

    def test_market_auction_algorithm_parse_roles_returns_empty_on_failure(self) -> None:
        # [Hidden Failure] malformed JSON must return empty list, not crash.
        algorithm = MarketAuctionAlgorithm()
        roles = algorithm.parse_roles("not json")

        self.assertEqual(roles, [])


class MarketAuctionDispatcherTests(unittest.TestCase):
    def test_dispatcher_detects_market_auction_algorithm(self) -> None:
        # [Hidden Assumption] dispatcher must detect the preset.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.market_auction,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "market_auction")

    def test_dispatcher_returns_market_auction_runtime_algorithm(self) -> None:
        # [Hidden Failure] return_algorithm must return the correct adapter type.
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.market_auction,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertIsInstance(dispatcher.return_algorithm(), MarketAuctionRuntimeAlgorithm)


class MarketAuctionRuntimeBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_market_auction_uses_predefined_roles_when_provided(self) -> None:
        # [Hidden Assumption] predefined roles skip the role-generation call.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="market_auction",
                market_auction=MarketAuctionAlgorithm(
                    num_agents=2,
                    roles=("Expert A", "Expert B"),
                ),
            ),
        )
        runner = FakeRunner([
            # Bid for Expert A
            FakeResponse('{"can_handle": true, "confidence": 5, "approach": "approach A"}'),
            # Bid for Expert B
            FakeResponse('{"can_handle": true, "confidence": 9, "approach": "approach B"}'),
            # Execution by Expert B (winner)
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "Expert B result"}', "call_id": "c1"}]}),
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

        self.assertEqual(result.output, "Expert B result")
        self.assertIn("market_auction", result.metadata)
        self.assertEqual(result.metadata["market_auction"]["winning_role"], "Expert B")

    async def test_market_auction_generates_roles_dynamically(self) -> None:
        # [Hidden Assumption] dynamic role generation precedes bidding.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="market_auction",
                market_auction=MarketAuctionAlgorithm(num_agents=2),
            ),
        )
        runner = FakeRunner([
            # Auctioneer generates roles
            FakeResponse('["Data Analyst", "Code Reviewer"]'),
            # Bid for Data Analyst
            FakeResponse('{"can_handle": true, "confidence": 7, "approach": "analyze data"}'),
            # Bid for Code Reviewer
            FakeResponse('{"can_handle": true, "confidence": 4, "approach": "review code"}'),
            # Execution by Data Analyst (winner)
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "data analysis result"}', "call_id": "c1"}]}),
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

        self.assertEqual(result.metadata["market_auction"]["winning_role"], "Data Analyst")
        self.assertIn("bids", result.metadata["market_auction"])

    async def test_market_auction_attaches_auction_metadata(self) -> None:
        # [Hidden Assumption] metadata must include role_count, winning_role, bids.
        from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(
                name="market_auction",
                market_auction=MarketAuctionAlgorithm(num_agents=2, roles=("A", "B")),
            ),
        )
        runner = FakeRunner([
            FakeResponse('{"can_handle": true, "confidence": 3, "approach": "approach A"}'),
            FakeResponse('{"can_handle": true, "confidence": 8, "approach": "approach B"}'),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "c1"}]}),
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

        meta = result.metadata["market_auction"]
        self.assertEqual(meta["role_count"], 2)
        self.assertIn("winning_role", meta)
        self.assertIn("winning_confidence", meta)
        self.assertIn("bids", meta)
        self.assertEqual(len(meta["bids"]), 2)


if __name__ == "__main__":
    unittest.main()
