"""Verification script for the four non-linear agent runtime algorithms.

Runs every test case from the design doc section 10 testing plan.
Exits with code 0 if all pass, non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import sys
import traceback


PASS = "✓ PASS"
FAIL = "✗ FAIL"

passed = 0
failed = 0
_results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    _results.append((name, ok, detail))
    if ok:
        passed += 1
        print(f"  {PASS}  {name}")
    else:
        failed += 1
        print(f"  {FAIL}  {name}")
        if detail:
            print(f"         {detail}")


def check(name: str, condition: bool, detail: str = "") -> None:
    record(name, condition, detail)


def check_raises(name: str, exc_type: type, fn: object) -> None:
    try:
        fn()
        record(name, False, f"Expected {exc_type.__name__} but no exception raised")
    except exc_type:
        record(name, True)
    except Exception as exc:
        record(name, False, f"Wrong exception type: {type(exc).__name__}: {exc}")


async def check_async(name: str, coro: object) -> None:
    try:
        await coro
        record(name, True)
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


# ────────────────────────────────────────────────────────────────
# Imports
# ────────────────────────────────────────────────────────────────
from vidbyte.agents.algorithms import (
    BeamSearchRuntimeAlgorithm,
    DAGDataflowRuntimeAlgorithm,
    GossipRuntimeAlgorithm,
    MarketAuctionRuntimeAlgorithm,
)
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms.beam_search import BeamSearchAlgorithm
from vidbyte.context.algorithms.dag_dataflow import DAGDataflowAlgorithm
from vidbyte.context.algorithms.gossip import GossipAlgorithm
from vidbyte.context.algorithms.market_auction import MarketAuctionAlgorithm
from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
from vidbyte.context.window import ContextWindow
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
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


def make_runtime(algorithm: object | None = None) -> AgentRuntime:
    return AgentRuntime(
        agent_name="worker",
        system_prompt="Work.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        algorithm=algorithm,
    )


def build_context(runtime: AgentRuntime) -> object:
    return runtime.build_context(
        "task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=()
    )


# ────────────────────────────────────────────────────────────────
# Section 1: Preset registration and string resolution
# ────────────────────────────────────────────────────────────────
print("\n── Preset registration ──")
check("beam_search preset has correct name", ContextWindow.preset.beam_search.name == "beam_search")
check("beam_search preset contains BeamSearchAlgorithm", isinstance(ContextWindow.preset.beam_search.beam_search, BeamSearchAlgorithm))
check("dag_dataflow preset has correct name", ContextWindow.preset.dag_dataflow.name == "dag_dataflow")
check("dag_dataflow preset contains DAGDataflowAlgorithm", isinstance(ContextWindow.preset.dag_dataflow.dag_dataflow, DAGDataflowAlgorithm))
check("market_auction preset has correct name", ContextWindow.preset.market_auction.name == "market_auction")
check("market_auction preset contains MarketAuctionAlgorithm", isinstance(ContextWindow.preset.market_auction.market_auction, MarketAuctionAlgorithm))
check("gossip preset has correct name", ContextWindow.preset.gossip.name == "gossip")
check("gossip preset contains GossipAlgorithm", isinstance(ContextWindow.preset.gossip.gossip, GossipAlgorithm))
check("resolve_algorithm('beam_search') works", ContextWindow.resolve_algorithm("beam_search").name == "beam_search")
check("resolve_algorithm('dag_dataflow') works", ContextWindow.resolve_algorithm("dag_dataflow").name == "dag_dataflow")
check("resolve_algorithm('market_auction') works", ContextWindow.resolve_algorithm("market_auction").name == "market_auction")
check("resolve_algorithm('gossip') works", ContextWindow.resolve_algorithm("gossip").name == "gossip")

# ────────────────────────────────────────────────────────────────
# Section 2: Config validation
# ────────────────────────────────────────────────────────────────
print("\n── Config validation ──")
check_raises("BeamSearchAlgorithm rejects beam_width=0", ConfigurationError, lambda: BeamSearchAlgorithm(beam_width=0))
check_raises("BeamSearchAlgorithm rejects beam_width=-1", ConfigurationError, lambda: BeamSearchAlgorithm(beam_width=-1))
check_raises("BeamSearchAlgorithm rejects max_scorer_chars=0", ConfigurationError, lambda: BeamSearchAlgorithm(max_scorer_chars=0))
check_raises("BeamSearchAlgorithm rejects empty scorer_system_prompt", ConfigurationError, lambda: BeamSearchAlgorithm(scorer_system_prompt=""))
check_raises("BeamSearchAlgorithm rejects scorer_prompt missing {task}", ConfigurationError, lambda: BeamSearchAlgorithm(scorer_prompt="Candidate: {candidate}"))
check_raises("BeamSearchAlgorithm rejects scorer_prompt missing {candidate}", ConfigurationError, lambda: BeamSearchAlgorithm(scorer_prompt="Task: {task}"))
check_raises("DAGDataflowAlgorithm rejects max_nodes=0", ConfigurationError, lambda: DAGDataflowAlgorithm(max_nodes=0))
check_raises("DAGDataflowAlgorithm rejects max_parallel=0", ConfigurationError, lambda: DAGDataflowAlgorithm(max_parallel=0))
check_raises("DAGDataflowAlgorithm rejects max_plan_chars=0", ConfigurationError, lambda: DAGDataflowAlgorithm(max_plan_chars=0))
check_raises("DAGDataflowAlgorithm rejects empty planner_system_prompt", ConfigurationError, lambda: DAGDataflowAlgorithm(planner_system_prompt=""))
check_raises("MarketAuctionAlgorithm rejects num_agents=0", ConfigurationError, lambda: MarketAuctionAlgorithm(num_agents=0))
check_raises("MarketAuctionAlgorithm rejects roles length mismatch", ConfigurationError, lambda: MarketAuctionAlgorithm(num_agents=3, roles=("A", "B")))
check_raises("MarketAuctionAlgorithm rejects empty role string", ConfigurationError, lambda: MarketAuctionAlgorithm(num_agents=2, roles=("Valid", "")))
check_raises("GossipAlgorithm rejects num_agents=1", ConfigurationError, lambda: GossipAlgorithm(num_agents=1))
check_raises("GossipAlgorithm rejects gossip_rounds=0", ConfigurationError, lambda: GossipAlgorithm(gossip_rounds=0))
check_raises("GossipAlgorithm rejects max_knowledge_chars=0", ConfigurationError, lambda: GossipAlgorithm(max_knowledge_chars=0))
check_raises("GossipAlgorithm rejects empty agent_system_prompt", ConfigurationError, lambda: GossipAlgorithm(agent_system_prompt=""))
check_raises("ContextWindowAlgorithm rejects two algorithms set", ValueError, lambda: ContextWindowAlgorithm(name="x", beam_search=BeamSearchAlgorithm(), gossip=GossipAlgorithm()))

# ────────────────────────────────────────────────────────────────
# Section 3: Truncation helpers
# ────────────────────────────────────────────────────────────────
print("\n── Truncation helpers ──")
bs = BeamSearchAlgorithm(max_scorer_chars=10)
truncated = bs.truncate_candidate("A" * 20)
check("BeamSearchAlgorithm.truncate_candidate applies suffix", "truncated" in truncated)
check("BeamSearchAlgorithm.truncate_candidate preserves prefix", truncated.startswith("AAAAAAAAAA"))

gos = GossipAlgorithm(max_knowledge_chars=10)
check("GossipAlgorithm.truncate_knowledge applies suffix", "truncated" in gos.truncate_knowledge("B" * 20))

dag = DAGDataflowAlgorithm(max_node_output_chars=10)
check("DAGDataflowAlgorithm.truncate_node_output applies suffix", "truncated" in dag.truncate_node_output("C" * 20))

# ────────────────────────────────────────────────────────────────
# Section 4: Parse helpers
# ────────────────────────────────────────────────────────────────
print("\n── Parse helpers ──")
dag2 = DAGDataflowAlgorithm()
nodes = dag2.parse_dag_plan('[{"id":"A","description":"Step A","dependencies":[]}]')
check("DAGDataflowAlgorithm.parse_dag_plan parses valid JSON", len(nodes) == 1 and nodes[0]["id"] == "A")
nodes_fenced = dag2.parse_dag_plan('```json\n[{"id":"B","description":"B","dependencies":[]}]\n```')
check("DAGDataflowAlgorithm.parse_dag_plan strips markdown fences", len(nodes_fenced) == 1 and nodes_fenced[0]["id"] == "B")
check_raises("DAGDataflowAlgorithm.parse_dag_plan raises on invalid JSON", AgentExecutionError, lambda: dag2.parse_dag_plan("not json"))

ma = MarketAuctionAlgorithm()
bid = ma.parse_bid('{"can_handle": true, "confidence": 8, "approach": "plan"}')
check("MarketAuctionAlgorithm.parse_bid parses valid JSON", bid["can_handle"] is True and bid["confidence"] == 8)
fallback = ma.parse_bid("not json at all")
check("MarketAuctionAlgorithm.parse_bid returns safe default on failure", not fallback["can_handle"] and fallback["confidence"] == 0)

roles = ma.parse_roles('["Expert A", "Expert B"]')
check("MarketAuctionAlgorithm.parse_roles parses valid JSON", roles == ["Expert A", "Expert B"])
check("MarketAuctionAlgorithm.parse_roles returns empty on failure", ma.parse_roles("not json") == [])

winner_role, winner_bid = ma.select_winner(
    [{"can_handle": True, "confidence": 3}, {"can_handle": True, "confidence": 9}],
    ["Role A", "Role B"],
)
check("MarketAuctionAlgorithm.select_winner picks highest confidence", winner_role == "Role B")

all_no_handle = [{"can_handle": False, "confidence": 0}, {"can_handle": False, "confidence": 0}]
fallback_role, fallback_bid = ma.select_winner(all_no_handle, ["X", "Y"])
check("MarketAuctionAlgorithm.select_winner falls back when all can_handle=false", fallback_bid.get("_fallback") is True)

# ────────────────────────────────────────────────────────────────
# Section 5: Dispatcher wiring
# ────────────────────────────────────────────────────────────────
print("\n── Dispatcher wiring ──")
for preset_name, rt_cls in [
    ("beam_search", BeamSearchRuntimeAlgorithm),
    ("dag_dataflow", DAGDataflowRuntimeAlgorithm),
    ("market_auction", MarketAuctionRuntimeAlgorithm),
    ("gossip", GossipRuntimeAlgorithm),
]:
    rt = make_runtime(ContextWindow.resolve_algorithm(preset_name))
    dispatcher = AgentRuntimeContextAlgorithms(rt)
    check(f"dispatcher.detect_algorithm() == '{preset_name}'", dispatcher.detect_algorithm() == preset_name)
    check(f"dispatcher.return_algorithm() is {rt_cls.__name__}", isinstance(dispatcher.return_algorithm(), rt_cls))

check("dispatcher returns None with no algorithm", AgentRuntimeContextAlgorithms(make_runtime()).return_algorithm() is None)

# ────────────────────────────────────────────────────────────────
# Section 6: Gossip pairing
# ────────────────────────────────────────────────────────────────
print("\n── Gossip pairing ──")
gos_adapter = GossipRuntimeAlgorithm(make_runtime(), GossipAlgorithm(num_agents=4))
pairs_r0 = gos_adapter._gossip_pairs(4, 0)
pairs_r1 = gos_adapter._gossip_pairs(4, 1)
check("gossip_pairs produces 2 pairs for 4 agents", len(pairs_r0) == 2)
check("gossip_pairs produces different pairings across rounds", pairs_r0 != pairs_r1)

gos_odd = GossipRuntimeAlgorithm(make_runtime(), GossipAlgorithm(num_agents=3))
check("gossip_pairs produces 1 pair for 3 agents (odd)", len(gos_odd._gossip_pairs(3, 0)) == 1)

angles = [GossipAlgorithm(num_agents=2).build_angle_for_agent(i, "task") for i in range(100)]
check("GossipAlgorithm.build_angle_for_agent cycles without IndexError", len(angles) == 100)

# ────────────────────────────────────────────────────────────────
# Section 7: parse_score
# ────────────────────────────────────────────────────────────────
print("\n── BeamSearch score parsing ──")
check("_parse_score extracts integer", BeamSearchRuntimeAlgorithm._parse_score("Score: 7") == 7.0)
check("_parse_score returns 0.0 on non-numeric", BeamSearchRuntimeAlgorithm._parse_score("no numbers") == 0.0)
check("_parse_score picks first integer", BeamSearchRuntimeAlgorithm._parse_score("6 then 9") == 6.0)

# ────────────────────────────────────────────────────────────────
# Section 8: Runtime behavior (async)
# ────────────────────────────────────────────────────────────────
print("\n── Runtime behavior (async) ──")

async def run_all_async() -> None:
    # BeamSearch: winner is highest scored
    async def test_beam_winner() -> None:
        rt = make_runtime(ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm(beam_width=2)))
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "low"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "high"}', "call_id": "c2"}]}),
            FakeResponse("2"),
            FakeResponse("9"),
        ])
        ctx = build_context(rt)
        result = await rt.arun("task", runner=runner, context=ctx, provider="openai",
                               invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                               runner_output_metadata=runner_output_metadata)
        check("beam_search runtime returns highest-scored candidate", result.output == "high")
        check("beam_search runtime attaches beam_search metadata", "beam_search" in result.metadata)
        check("beam_search metadata has winner_index=1", result.metadata["beam_search"]["winner_index"] == 1)

    await check_async("beam_search: winner is highest scored", test_beam_winner())

    # DAG: plan → execute nodes → synthesize
    async def test_dag_full() -> None:
        rt = make_runtime(ContextWindowAlgorithm(name="dag_dataflow", dag_dataflow=DAGDataflowAlgorithm()))
        runner = FakeRunner([
            FakeResponse('[{"id":"A","description":"Step A","dependencies":[]},{"id":"B","description":"Step B","dependencies":["A"]}]'),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "output A"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "output B"}', "call_id": "c2"}]}),
            FakeResponse("synthesized answer"),
        ])
        ctx = build_context(rt)
        result = await rt.arun("task", runner=runner, context=ctx, provider="openai",
                               invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                               runner_output_metadata=runner_output_metadata)
        check("dag_dataflow runtime returns synthesized output", result.output == "synthesized answer")
        check("dag_dataflow runtime attaches dag_dataflow metadata", "dag_dataflow" in result.metadata)
        check("dag_dataflow metadata has node_count=2", result.metadata["dag_dataflow"]["node_count"] == 2)

    await check_async("dag_dataflow: full plan-execute-synthesize pipeline", test_dag_full())

    # DAG: cycle raises
    async def test_dag_cycle() -> None:
        rt = make_runtime(ContextWindowAlgorithm(name="dag_dataflow", dag_dataflow=DAGDataflowAlgorithm()))
        runner = FakeRunner([
            FakeResponse('[{"id":"A","description":"A","dependencies":["B"]},{"id":"B","description":"B","dependencies":["A"]}]'),
        ])
        ctx = build_context(rt)
        try:
            await rt.arun("task", runner=runner, context=ctx, provider="openai",
                          invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                          runner_output_metadata=runner_output_metadata)
            check("dag_dataflow raises on cycle", False, "Expected AgentExecutionError but no exception raised")
        except AgentExecutionError:
            check("dag_dataflow raises on cycle", True)

    await check_async("dag_dataflow: raises on cyclic DAG", test_dag_cycle())

    # Market auction: predefined roles, winner is highest confidence
    async def test_auction_winner() -> None:
        rt = make_runtime(ContextWindowAlgorithm(name="market_auction", market_auction=MarketAuctionAlgorithm(num_agents=2, roles=("Expert A", "Expert B"))))
        runner = FakeRunner([
            FakeResponse('{"can_handle": true, "confidence": 3, "approach": "approach A"}'),
            FakeResponse('{"can_handle": true, "confidence": 9, "approach": "approach B"}'),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "expert B answer"}', "call_id": "c1"}]}),
        ])
        ctx = build_context(rt)
        result = await rt.arun("task", runner=runner, context=ctx, provider="openai",
                               invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                               runner_output_metadata=runner_output_metadata)
        check("market_auction runtime selects highest-confidence winner", result.metadata["market_auction"]["winning_role"] == "Expert B")
        check("market_auction runtime attaches auction metadata", "bids" in result.metadata["market_auction"])

    await check_async("market_auction: winner is highest-confidence bidder", test_auction_winner())

    # Gossip: full pipeline
    async def test_gossip_full() -> None:
        rt = make_runtime(ContextWindowAlgorithm(name="gossip", gossip=GossipAlgorithm(num_agents=2, gossip_rounds=1)))
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "k1"}', "call_id": "c1"}]}),
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "k2"}', "call_id": "c2"}]}),
            FakeResponse("merged knowledge"),
            FakeResponse("final synthesized answer"),
        ])
        ctx = build_context(rt)
        result = await rt.arun("task", runner=runner, context=ctx, provider="openai",
                               invoke_runner=invoke_runner, runner_output_text=runner_output_text,
                               runner_output_metadata=runner_output_metadata)
        check("gossip runtime returns synthesized output", result.output == "final synthesized answer")
        check("gossip runtime attaches gossip metadata", "gossip" in result.metadata)
        check("gossip metadata has num_agents=2", result.metadata["gossip"]["num_agents"] == 2)
        check("gossip metadata has gossip_rounds=1", result.metadata["gossip"]["gossip_rounds"] == 1)

    await check_async("gossip: full init-merge-synthesize pipeline", test_gossip_full())


asyncio.run(run_all_async())

# ────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────
print(f"\n{'─' * 50}")
print(f"{passed}/{passed + failed} tests passed")
if failed > 0:
    print(f"\nFailed tests:")
    for name, ok, detail in _results:
        if not ok:
            print(f"  {FAIL}  {name}")
            if detail:
                print(f"         {detail}")

sys.exit(0 if failed == 0 else 1)
