"""Verification script for agent behavior facade.

Runs every test case from Section 10 of docs/design/agent-behavior.md.
Prints PASS/FAIL per test case and exits non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput
from vidbyte.context.handoff.base import Handoff
from vidbyte.evals import Behavior, ContainsGrader, EvalCase, EvalRunner, EvalSuite, PredicateGrader, RunProbe
from vidbyte.evals.behavior.efficiency import EfficiencyBehavior
from vidbyte.evals.behavior.tool import ToolBehavior
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult, ToolStatus


def make_call(name: str, state: ToolCallState = ToolCallState.SUCCEEDED, args: dict[str, Any] | None = None, result_output: str | None = "ok") -> ToolCallContext:
    # Builds a ToolCallContext with the given name, state, args, and optional result output.
    result = None
    if result_output is not None:
        result = ToolResult(tool_name=name, status=ToolStatus.SUCCESS, output=result_output)
    return ToolCallContext(tool_name=name, arguments=dict(args or {}), state=state, result=result)


def make_reply(content: str = "reply", metadata: dict[str, Any] | None = None) -> AgentMessage:
    # Builds an AgentMessage with the given content and metadata.
    return AgentMessage(sender="agent", recipient="orchestrator", content=content, metadata=metadata or {})


def behavior_from_probe(probe: RunProbe) -> Behavior:
    # Builds a Behavior facade backed by a pre-built probe (bypasses agent lookup).
    b = Behavior.__new__(Behavior)
    b._agent = None
    b._probe = probe
    b._tool = ToolBehavior.__new__(ToolBehavior)
    b._tool._behavior = b
    from vidbyte.evals.behavior.tool_arguments import ToolArgumentBehavior
    from vidbyte.evals.behavior.stop import StopBehavior
    from vidbyte.evals.behavior.handoff import HandoffBehavior
    b._tool_args = ToolArgumentBehavior.__new__(ToolArgumentBehavior)
    b._tool_args._behavior = b
    b._stop = StopBehavior.__new__(StopBehavior)
    b._stop._behavior = b
    b._handoff = HandoffBehavior.__new__(HandoffBehavior)
    b._handoff._behavior = b
    b._efficiency = EfficiencyBehavior.__new__(EfficiencyBehavior)
    b._efficiency._behavior = b
    return b


class StubAgent:
    """Minimal stub mimicking BaseAgent post-run fields for RunProbe tests."""

    def __init__(self, reply: AgentMessage | None = None, handoff: Handoff | None = None, handoffs: list | None = None, trace: dict | None = None) -> None:
        self.last_reply = reply
        self.last_handoff = handoff
        self.handoffs = handoffs or []
        self.last_trace = trace


class MockAgent(BaseAgent):
    """BaseAgent subclass returning scripted replies with tool call metadata."""

    def __init__(self, reply_metadata: dict[str, Any] | None = None) -> None:
        super().__init__(name="mock", system_prompt="test", runner=object())
        self._reply_metadata = reply_metadata or {}

    def fork(self, **kwargs: Any) -> MockAgent:
        return self

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Simulates the cache invalidation that BaseAgent.generate_reply performs.
        self._behavior_view = None
        reply = AgentMessage(sender="mock", recipient="orchestrator", content="processed", metadata=dict(self._reply_metadata))
        self.last_reply = reply
        return reply


class TestRunner:
    """Collects and runs test cases, printing PASS/FAIL and a summary."""

    def __init__(self) -> None:
        self._results: list[tuple[str, bool, str]] = []

    def run(self, name: str, test_fn: Any) -> None:
        try:
            test_fn()
            self._results.append((name, True, ""))
            print(f"PASS: {name}")
        except AssertionError as exc:
            self._results.append((name, False, str(exc)))
            print(f"FAIL: {name} - {exc}")
        except Exception as exc:
            self._results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL: {name} - {type(exc).__name__}: {exc}")

    async def run_async(self, name: str, test_fn: Any) -> None:
        try:
            await test_fn()
            self._results.append((name, True, ""))
            print(f"PASS: {name}")
        except AssertionError as exc:
            self._results.append((name, False, str(exc)))
            print(f"FAIL: {name} - {exc}")
        except Exception as exc:
            self._results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL: {name} - {type(exc).__name__}: {exc}")

    def summary(self) -> int:
        passed = sum(1 for _, ok, _ in self._results if ok)
        total = len(self._results)
        print(f"\n{passed}/{total} tests passed")
        return 0 if passed == total else 1


# --- RunProbe tests ---

def test_probe_from_agent_populated() -> None:
    # [Hidden Assumption] from_agent with populated last_reply extracts all metadata fields.
    calls = (make_call("search"), make_call("read", state=ToolCallState.FAILED))
    reply = make_reply(metadata={"tool_calls": calls, "stop_reason": "max_iterations", "iteration_count": 5, "tokens_used": 1000, "tool_call_count": 2})
    probe = RunProbe.from_agent(StubAgent(reply=reply))
    assert probe.tool_calls == calls
    assert probe.stop_reason == "max_iterations"
    assert probe.iteration_count == 5
    assert probe.tokens_used == 1000
    assert probe.tool_call_count == 2

def test_probe_from_agent_no_reply() -> None:
    # [Edge Case] from_agent with last_reply=None returns all-empty/zero probe.
    probe = RunProbe.from_agent(StubAgent(reply=None))
    assert probe.tool_calls == ()
    assert probe.stop_reason == "final_response"
    assert probe.iteration_count == 0
    assert probe.tokens_used is None

def test_probe_missing_tool_calls_key() -> None:
    # [Edge Case] metadata lacks tool_calls returns empty tuple.
    probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"stop_reason": "final_response"})))
    assert probe.tool_calls == ()

def test_probe_missing_stop_reason_defaults() -> None:
    # [Silent Failure] metadata lacks stop_reason defaults to "final_response".
    probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"tool_calls": ()})))
    assert probe.stop_reason == "final_response"

def test_probe_reads_handoff_and_handoffs_independently() -> None:
    # [Hidden Assumption] from_agent reads last_handoff and handoffs independently.
    h1, h2 = Handoff(sections={"a": "b"}), Handoff(sections={"c": "d"})
    probe = RunProbe.from_agent(StubAgent(reply=make_reply(), handoff=h1, handoffs=[h2]))
    assert probe.handoff is h1
    assert probe.handoffs == (h2,)

def test_probe_from_reply_no_agent() -> None:
    # [Edge Case] from_reply without agent returns handoff=None and handoffs=().
    probe = RunProbe.from_reply(make_reply(metadata={"tool_calls": ()}))
    assert probe.handoff is None
    assert probe.handoffs == ()

def test_probe_states_derived_from_calls() -> None:
    # [Silent Failure] tool_call_states derived from tool_calls when not in metadata.
    calls = (make_call("a", state=ToolCallState.SUCCEEDED), make_call("b", state=ToolCallState.FAILED))
    probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"tool_calls": calls})))
    assert probe.tool_call_states == ("succeeded", "failed")


# --- ToolBehavior Category A (presence) ---

def test_called_tool_true_false() -> None:
    # [Edge Case] called_tool returns True when called, False when not.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
    assert b.tool.called_tool("search") is True
    assert b.tool.called_tool("write") is False

def test_not_called_tool_negation() -> None:
    # [Silent Failure] not_called_tool is the exact negation of called_tool.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"),)))
    assert b.tool.not_called_tool("search") is False
    assert b.tool.not_called_tool("write") is True

def test_called_all_tools_present_and_missing() -> None:
    # [Edge Case] called_all_tools True when all present, False when one missing.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
    assert b.tool.called_all_tools(["search", "read"]) is True
    assert b.tool.called_all_tools(["search", "write"]) is False

def test_called_all_tools_empty_vacuous() -> None:
    # [Edge Case] called_all_tools([]) returns True (vacuous).
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"),)))
    assert b.tool.called_all_tools([]) is True

def test_called_any_tool_match_and_no_match() -> None:
    # [Edge Case] called_any_tool True with one match, False with no matches.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
    assert b.tool.called_any_tool(["search", "write"]) is True
    assert b.tool.called_any_tool(["write", "exec"]) is False

def test_called_no_tools_true_and_false() -> None:
    # [Edge Case] called_no_tools True when empty, False when calls exist.
    assert behavior_from_probe(RunProbe(tool_calls=())).tool.called_no_tools() is True
    assert behavior_from_probe(RunProbe(tool_calls=(make_call("search"),))).tool.called_no_tools() is False

def test_called_only_tools_in_set_and_extra() -> None:
    # [Silent Failure] called_only_tools True when all in set, False when extra outside.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
    assert b.tool.called_only_tools(["search", "read"]) is True
    assert b.tool.called_only_tools(["search"]) is False

def test_called_only_tools_empty_with_calls() -> None:
    # [Edge Case] called_only_tools([]) with non-empty calls returns False.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"),)))
    assert b.tool.called_only_tools([]) is False

def test_called_tools_in_order_valid_and_invalid() -> None:
    # [Silent Failure] called_tools_in_order True for valid subsequence, False when wrong order.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("a"), make_call("b"), make_call("c"))))
    assert b.tool.called_tools_in_order(["a", "c"]) is True
    assert b.tool.called_tools_in_order(["c", "a"]) is False

def test_called_tools_in_order_empty_vacuous() -> None:
    # [Edge Case] called_tools_in_order([]) returns True (vacuous).
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("a"),)))
    assert b.tool.called_tools_in_order([]) is True

def test_tool_call_count_multiple() -> None:
    # [Silent Failure] tool_call_count returns correct count for multiple calls to same tool.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("search"), make_call("read"))))
    assert b.tool.tool_call_count("search") == 2
    assert b.tool.tool_call_count("read") == 1
    assert b.tool.tool_call_count("write") == 0

def test_called_tool_names_ordered_unique() -> None:
    # [Silent Failure] called_tool_names returns ordered unique names preserving first-occurrence.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("b"), make_call("a"), make_call("b"))))
    assert b.tool.called_tool_names() == ("b", "a")


# --- ToolBehavior Category B (outcome/state) ---

def test_tool_succeeded_state_check() -> None:
    # [Hidden Assumption] tool_succeeded True only when state is SUCCEEDED.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("s", state=ToolCallState.SUCCEEDED), make_call("f", state=ToolCallState.FAILED))))
    assert b.tool.tool_succeeded("s") is True
    assert b.tool.tool_succeeded("f") is False

def test_tool_failed_state_check() -> None:
    # [Hidden Assumption] tool_failed True only when state is FAILED.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("s", state=ToolCallState.SUCCEEDED), make_call("f", state=ToolCallState.FAILED))))
    assert b.tool.tool_failed("f") is True
    assert b.tool.tool_failed("s") is False

def test_tool_denied_state_check() -> None:
    # [Hidden Assumption] tool_denied True only when state is DENIED.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("d", state=ToolCallState.DENIED), make_call("s", state=ToolCallState.SUCCEEDED))))
    assert b.tool.tool_denied("d") is True
    assert b.tool.tool_denied("s") is False

def test_all_tool_calls_succeeded_mixed() -> None:
    # [Silent Failure] all_tool_calls_succeeded False when any call failed.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("a", state=ToolCallState.SUCCEEDED), make_call("b", state=ToolCallState.FAILED))))
    assert b.tool.all_tool_calls_succeeded() is False

def test_all_tool_calls_succeeded_vacuous() -> None:
    # [Edge Case] all_tool_calls_succeeded True when zero calls (vacuous).
    b = behavior_from_probe(RunProbe(tool_calls=()))
    assert b.tool.all_tool_calls_succeeded() is True

def test_tool_returned_containing_finds_substring() -> None:
    # [Hidden Assumption] tool_returned_containing finds substring in result output.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output="hello world"),)))
    assert b.tool.tool_returned_containing("search", "hello") is True
    assert b.tool.tool_returned_containing("search", "goodbye") is False

def test_tool_returned_containing_skips_none_result() -> None:
    # [Hidden Failure] tool_returned_containing skips calls with .result is None.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output=None),)))
    assert b.tool.tool_returned_containing("search", "anything") is False

def test_tool_returned_matching_regex() -> None:
    # [Edge Case] tool_returned_matching applies regex to result output.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output="id: 123-45"),)))
    assert b.tool.tool_returned_matching("search", r"\d{3}-\d{2}") is True
    assert b.tool.tool_returned_matching("search", r"\d{5}") is False


# --- ToolArgumentBehavior Category C ---

def test_tool_called_with_subset() -> None:
    # [Silent Failure] tool_called_with True when args are a subset of call arguments.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python", "limit": 10}),)))
    assert b.tool_args.tool_called_with("search", query="python") is True
    assert b.tool_args.tool_called_with("search", query="python", limit=10) is True
    assert b.tool_args.tool_called_with("search", query="java") is False

def test_tool_called_with_empty_kwargs() -> None:
    # [Edge Case] tool_called_with empty kwargs True if the tool was called at all.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
    assert b.tool_args.tool_called_with("search") is True
    assert b.tool_args.tool_called_with("write") is False

def test_tool_called_with_exact_match() -> None:
    # [Silent Failure] tool_called_with_exact True only on exact argument dict match.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python", "limit": 10}),)))
    assert b.tool_args.tool_called_with_exact("search", {"query": "python", "limit": 10}) is True
    assert b.tool_args.tool_called_with_exact("search", {"query": "python"}) is False

def test_tool_never_called_with_negation() -> None:
    # [Silent Failure] tool_never_called_with is the negation of tool_called_with.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
    assert b.tool_args.tool_never_called_with("search", query="java") is True
    assert b.tool_args.tool_never_called_with("search", query="python") is False

def test_tool_called_with_matching_predicate() -> None:
    # [Hidden Assumption] tool_called_with_matching calls the predicate on the arg value.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python tutorial"}),)))
    assert b.tool_args.tool_called_with_matching("search", "query", lambda q: "python" in q) is True
    assert b.tool_args.tool_called_with_matching("search", "query", lambda q: "java" in q) is False

def test_tool_called_with_matching_skips_missing_arg() -> None:
    # [Hidden Failure] tool_called_with_matching skips calls where arg_name is absent.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
    assert b.tool_args.tool_called_with_matching("search", "limit", lambda v: True) is False


# --- StopBehavior Category D ---

def test_stopped_on_exact_match() -> None:
    # [Edge Case] stopped_on True for exact reason match.
    b = behavior_from_probe(RunProbe(stop_reason="max_iterations"))
    assert b.stop.stopped_on("max_iterations") is True
    assert b.stop.stopped_on("final_response") is False

def test_stopped_normally_only_final_response() -> None:
    # [Silent Failure] stopped_normally True only for "final_response".
    assert behavior_from_probe(RunProbe(stop_reason="final_response")).stop.stopped_normally() is True
    assert behavior_from_probe(RunProbe(stop_reason="max_iterations")).stop.stopped_normally() is False

def test_did_not_hit_max_iterations() -> None:
    # [Hidden Assumption] did_not_hit_max_iterations False when stop_reason is max_iterations.
    assert behavior_from_probe(RunProbe(stop_reason="max_iterations")).stop.did_not_hit_max_iterations() is False
    assert behavior_from_probe(RunProbe(stop_reason="final_response")).stop.did_not_hit_max_iterations() is True

def test_did_not_hit_max_tool_calls() -> None:
    # [Hidden Assumption] did_not_hit_max_tool_calls False when stop_reason is max_tool_calls.
    assert behavior_from_probe(RunProbe(stop_reason="max_tool_calls")).stop.did_not_hit_max_tool_calls() is False

def test_did_not_hit_max_tokens() -> None:
    # [Hidden Assumption] did_not_hit_max_tokens False when stop_reason is max_tokens.
    assert behavior_from_probe(RunProbe(stop_reason="max_tokens")).stop.did_not_hit_max_tokens() is False

def test_iteration_count_raw() -> None:
    # [Edge Case] iteration_count returns the raw int from probe.
    assert behavior_from_probe(RunProbe(iteration_count=7)).stop.iteration_count() == 7

def test_total_tool_calls_raw() -> None:
    # [Edge Case] total_tool_calls returns the raw count from probe.
    assert behavior_from_probe(RunProbe(tool_call_count=3)).stop.total_tool_calls() == 3

def test_tokens_used_none() -> None:
    # [Edge Case] tokens_used returns None when not reported.
    assert behavior_from_probe(RunProbe(tokens_used=None)).stop.tokens_used() is None

def test_did_not_exceed_tokens_none() -> None:
    # [Silent Failure] did_not_exceed_tokens True when tokens_used is None.
    assert behavior_from_probe(RunProbe(tokens_used=None)).stop.did_not_exceed_tokens(1000) is True

def test_did_not_exceed_tokens_exceeds() -> None:
    # [Silent Failure] did_not_exceed_tokens False when tokens exceed limit.
    b = behavior_from_probe(RunProbe(tokens_used=2000))
    assert b.stop.did_not_exceed_tokens(1000) is False
    assert b.stop.did_not_exceed_tokens(3000) is True


# --- HandoffBehavior Category E ---

def test_handoff_occurred_true() -> None:
    # [Edge Case] handoff_occurred True when last_handoff is set.
    assert behavior_from_probe(RunProbe(handoff=Handoff(sections={"a": "b"}))).handoff.handoff_occurred() is True

def test_handoff_occurred_false() -> None:
    # [Edge Case] handoff_occurred False when last_handoff is None.
    assert behavior_from_probe(RunProbe(handoff=None)).handoff.handoff_occurred() is False

def test_handoff_is_filled_true() -> None:
    # [Silent Failure] handoff_is_filled True only when is_filled is True.
    h = Handoff(sections={"a": "b"}).fill({"a": "content"})
    assert behavior_from_probe(RunProbe(handoff=h)).handoff.handoff_is_filled() is True

def test_handoff_is_filled_false() -> None:
    # [Silent Failure] handoff_is_filled False when handoff is not filled.
    assert behavior_from_probe(RunProbe(handoff=Handoff(sections={"a": "b"}))).handoff.handoff_is_filled() is False

def test_handoff_count() -> None:
    # [Hidden Assumption] handoff_count returns len(handoffs) list.
    h1, h2 = Handoff(sections={"a": "b"}), Handoff(sections={"c": "d"})
    assert behavior_from_probe(RunProbe(handoff=h1, handoffs=(h1, h2))).handoff.handoff_count() == 2

def test_handoff_has_section_true_false() -> None:
    # [Edge Case] handoff_has_section True for existing, False for missing.
    b = behavior_from_probe(RunProbe(handoff=Handoff(sections={"summary": "text", "details": "more"})))
    assert b.handoff.handoff_has_section("summary") is True
    assert b.handoff.handoff_has_section("missing") is False

def test_handoff_section_contains_finds_substring() -> None:
    # [Silent Failure] handoff_section_contains finds substring in the named section.
    b = behavior_from_probe(RunProbe(handoff=Handoff(sections={"summary": "The agent searched for data."})))
    assert b.handoff.handoff_section_contains("summary", "searched") is True
    assert b.handoff.handoff_section_contains("summary", "failed") is False

def test_handoff_section_contains_missing_section() -> None:
    # [Hidden Failure] handoff_section_contains returns False when section doesn't exist.
    b = behavior_from_probe(RunProbe(handoff=Handoff(sections={"summary": "text"})))
    assert b.handoff.handoff_section_contains("missing", "text") is False

def test_handoff_all_predicates_none() -> None:
    # [Edge Case] All handoff predicates return False/0 when handoff is None.
    b = behavior_from_probe(RunProbe(handoff=None))
    assert b.handoff.handoff_occurred() is False
    assert b.handoff.handoff_is_filled() is False
    assert b.handoff.handoff_count() == 0
    assert b.handoff.handoff_has_section("a") is False
    assert b.handoff.handoff_section_contains("a", "b") is False


# --- EfficiencyBehavior Category G ---

def test_efficiency_max_tool_repetitions() -> None:
    # [Edge Case] max_tool_repetitions handles below, equal, and above threshold.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("search"), make_call("read"))))
    assert b.efficiency.max_tool_repetitions("search", 2) is True
    assert b.efficiency.max_tool_repetitions("search", 1) is False
    assert b.efficiency.max_tool_repetitions("write", 0) is True

def test_efficiency_max_any_tool_repetitions() -> None:
    # [Silent Failure] max_any_tool_repetitions uses the most repeated tool name.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("search"), make_call("read"))))
    assert b.efficiency.max_any_tool_repetitions(2) is True
    assert b.efficiency.max_any_tool_repetitions(1) is False

def test_efficiency_completed_within_iterations() -> None:
    # [Edge Case] completed_within_iterations uses an inclusive boundary.
    b = behavior_from_probe(RunProbe(iteration_count=4))
    assert b.efficiency.completed_within_iterations(4) is True
    assert b.efficiency.completed_within_iterations(3) is False

def test_efficiency_completed_within_tool_calls() -> None:
    # [Edge Case] completed_within_tool_calls uses an inclusive boundary.
    b = behavior_from_probe(RunProbe(tool_call_count=3))
    assert b.efficiency.completed_within_tool_calls(3) is True
    assert b.efficiency.completed_within_tool_calls(2) is False

def test_efficiency_tool_calls_between() -> None:
    # [Silent Failure] tool_calls_between uses inclusive lower and upper bounds.
    b = behavior_from_probe(RunProbe(tool_call_count=3))
    assert b.efficiency.tool_calls_between(3, 3) is True
    assert b.efficiency.tool_calls_between(1, 5) is True
    assert b.efficiency.tool_calls_between(4, 5) is False
    assert b.efficiency.tool_calls_between(0, 2) is False

def test_efficiency_no_duplicate_tool_args() -> None:
    # [Hidden Assumption] duplicate args are scoped to the named tool only.
    calls = (make_call("search", args={"q": "x"}), make_call("read", args={"q": "x"}), make_call("search", args={"q": "x"}))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.no_duplicate_tool_args("search") is False
    assert b.efficiency.no_duplicate_tool_args("read") is True

def test_efficiency_no_duplicate_tool_calls() -> None:
    # [Silent Failure] duplicate tool calls require both same tool name and same arguments.
    duplicate = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}))))
    unique = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"q": "x"}), make_call("search", args={"q": "y"}))))
    assert duplicate.efficiency.no_duplicate_tool_calls() is False
    assert unique.efficiency.no_duplicate_tool_calls() is True

def test_efficiency_duplicate_tool_arg_count() -> None:
    # [Silent Failure] duplicate_tool_arg_count counts duplicate occurrences after the first.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.duplicate_tool_arg_count("search") == 2

def test_efficiency_duplicate_tool_call_count() -> None:
    # [Silent Failure] duplicate_tool_call_count counts duplicate exact calls after the first.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}), make_call("read", args={"q": "x"}))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.duplicate_tool_call_count() == 1

def test_efficiency_unique_tool_call_count() -> None:
    # [Silent Failure] unique_tool_call_count does not inflate repeated exact calls.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}), make_call("search", args={"q": "y"}))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.unique_tool_call_count() == 2

def test_efficiency_unique_tool_ratio_at_least_empty() -> None:
    # [Edge Case] zero tool calls are treated as a unique ratio of 1.0.
    b = behavior_from_probe(RunProbe(tool_calls=(), tool_call_count=0))
    assert b.efficiency.unique_tool_ratio_at_least(1.0) is True
    assert b.efficiency.unique_tool_ratio_at_least(1.1) is False

def test_efficiency_unique_tool_ratio_at_least_mixed() -> None:
    # [Silent Failure] unique_tool_ratio_at_least uses exact unique calls over total calls.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}), make_call("read", args={"path": "a"}))
    b = behavior_from_probe(RunProbe(tool_calls=calls, tool_call_count=3))
    assert b.efficiency.unique_tool_ratio_at_least(2 / 3) is True
    assert b.efficiency.unique_tool_ratio_at_least(0.75) is False

def test_efficiency_no_consecutive_identical_calls() -> None:
    # [Hidden Assumption] no_consecutive_identical_calls only checks adjacent exact repeats.
    adjacent = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}))))
    non_adjacent = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"q": "x"}), make_call("read"), make_call("search", args={"q": "x"}))))
    assert adjacent.efficiency.no_consecutive_identical_calls() is False
    assert non_adjacent.efficiency.no_consecutive_identical_calls() is True

def test_efficiency_no_consecutive_same_tool() -> None:
    # [Hidden Assumption] no_consecutive_same_tool ignores arguments.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"q": "x"}), make_call("search", args={"q": "y"}))))
    assert b.efficiency.no_consecutive_same_tool() is False

def test_efficiency_consecutive_identical_call_count() -> None:
    # [Silent Failure] consecutive_identical_call_count ignores non-adjacent repeats.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}), make_call("read"), make_call("search", args={"q": "x"}))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.consecutive_identical_call_count() == 1

def test_efficiency_consecutive_same_tool_count() -> None:
    # [Silent Failure] consecutive_same_tool_count counts adjacent same-tool pairs.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "y"}), make_call("search", args={"q": "z"}), make_call("read"))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.consecutive_same_tool_count() == 2

def test_efficiency_max_consecutive_tool_calls() -> None:
    # [Silent Failure] max_consecutive_tool_calls uses the longest run for one tool.
    calls = (make_call("search"), make_call("search"), make_call("read"), make_call("search"))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.max_consecutive_tool_calls("search", 2) is True
    assert b.efficiency.max_consecutive_tool_calls("search", 1) is False

def test_efficiency_max_any_consecutive_tool_repetitions() -> None:
    # [Silent Failure] max_any_consecutive_tool_repetitions uses the longest run across all tools.
    calls = (make_call("search"), make_call("read"), make_call("read"), make_call("read"))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.max_any_consecutive_tool_repetitions(3) is True
    assert b.efficiency.max_any_consecutive_tool_repetitions(2) is False

def test_efficiency_repeated_tool_names_ordered() -> None:
    # [Silent Failure] repeated_tool_names preserves first-occurrence order.
    calls = (make_call("b"), make_call("a"), make_call("b"), make_call("a"), make_call("c"))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.repeated_tool_names() == ("b", "a")

def test_efficiency_no_repeated_tool_results_global_and_scoped() -> None:
    # [Hidden Assumption] no_repeated_tool_results can be global or scoped to one tool.
    calls = (make_call("search", result_output="same"), make_call("read", result_output="same"))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.no_repeated_tool_results() is False
    assert b.efficiency.no_repeated_tool_results("search") is True

def test_efficiency_repeated_tool_result_count() -> None:
    # [Hidden Failure] repeated_tool_result_count skips None results and counts repeats after first.
    calls = (make_call("search", result_output="same"), make_call("search", result_output=None), make_call("read", result_output="same"), make_call("write", result_output="same"))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.repeated_tool_result_count() == 2

def test_efficiency_max_result_repetitions() -> None:
    # [Edge Case] max_result_repetitions uses an inclusive frequency threshold.
    calls = (make_call("search", result_output="same"), make_call("read", result_output="same"))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.max_result_repetitions(2) is True
    assert b.efficiency.max_result_repetitions(1) is False

def test_efficiency_failed_tool_calls_at_most() -> None:
    # [Edge Case] failed_tool_calls_at_most uses an inclusive FAILED-call threshold.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("a", state=ToolCallState.FAILED),)))
    assert b.efficiency.failed_tool_calls_at_most(1) is True
    assert b.efficiency.failed_tool_calls_at_most(0) is False

def test_efficiency_denied_tool_calls_at_most() -> None:
    # [Edge Case] denied_tool_calls_at_most uses an inclusive DENIED-call threshold.
    b = behavior_from_probe(RunProbe(tool_calls=(make_call("a", state=ToolCallState.DENIED),)))
    assert b.efficiency.denied_tool_calls_at_most(1) is True
    assert b.efficiency.denied_tool_calls_at_most(0) is False

def test_efficiency_unsuccessful_tool_calls_at_most() -> None:
    # [Hidden Assumption] unsuccessful_tool_calls_at_most counts FAILED and DENIED only.
    calls = (make_call("a", state=ToolCallState.FAILED), make_call("b", state=ToolCallState.DENIED), make_call("c", state=ToolCallState.SUCCEEDED))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.unsuccessful_tool_calls_at_most(2) is True
    assert b.efficiency.unsuccessful_tool_calls_at_most(1) is False

def test_efficiency_successful_tool_call_ratio_at_least_empty() -> None:
    # [Edge Case] zero calls are treated as a successful-call ratio of 1.0.
    b = behavior_from_probe(RunProbe(tool_calls=(), tool_call_count=0))
    assert b.efficiency.successful_tool_call_ratio_at_least(1.0) is True
    assert b.efficiency.successful_tool_call_ratio_at_least(1.1) is False

def test_efficiency_successful_tool_call_ratio_at_least_mixed() -> None:
    # [Silent Failure] successful_tool_call_ratio_at_least uses succeeded count over total count.
    calls = (make_call("a", state=ToolCallState.SUCCEEDED), make_call("b", state=ToolCallState.FAILED))
    b = behavior_from_probe(RunProbe(tool_calls=calls, tool_call_count=2))
    assert b.efficiency.successful_tool_call_ratio_at_least(0.5) is True
    assert b.efficiency.successful_tool_call_ratio_at_least(0.75) is False

def test_efficiency_no_failed_tool_retries() -> None:
    # [Hidden Assumption] no_failed_tool_retries is scoped to unsuccessful exact attempts.
    calls = (make_call("search", state=ToolCallState.FAILED, args={"q": "x"}), make_call("search", state=ToolCallState.DENIED, args={"q": "x"}), make_call("read", state=ToolCallState.FAILED, args={"q": "x"}))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.no_failed_tool_retries("search") is False
    assert b.efficiency.no_failed_tool_retries("read") is True

def test_efficiency_failed_tool_retry_count() -> None:
    # [Silent Failure] failed_tool_retry_count counts repeated unsuccessful exact attempts after first.
    calls = (make_call("search", state=ToolCallState.FAILED, args={"q": "x"}), make_call("search", state=ToolCallState.DENIED, args={"q": "x"}), make_call("search", state=ToolCallState.FAILED, args={"q": "x"}))
    assert behavior_from_probe(RunProbe(tool_calls=calls)).efficiency.failed_tool_retry_count("search") == 2

def test_efficiency_did_not_stop_on_budget() -> None:
    # [Hidden Assumption] did_not_stop_on_budget rejects all budget stop reasons.
    assert behavior_from_probe(RunProbe(stop_reason="final_response")).efficiency.did_not_stop_on_budget() is True
    assert behavior_from_probe(RunProbe(stop_reason="max_iterations")).efficiency.did_not_stop_on_budget() is False
    assert behavior_from_probe(RunProbe(stop_reason="max_tool_calls")).efficiency.did_not_stop_on_budget() is False
    assert behavior_from_probe(RunProbe(stop_reason="max_tokens")).efficiency.did_not_stop_on_budget() is False

def test_efficiency_stopped_normally_within_iterations() -> None:
    # [Hidden Failure] stopped_normally_within_iterations requires normal stop and iteration bound.
    assert behavior_from_probe(RunProbe(stop_reason="final_response", iteration_count=2)).efficiency.stopped_normally_within_iterations(2) is True
    assert behavior_from_probe(RunProbe(stop_reason="max_iterations", iteration_count=2)).efficiency.stopped_normally_within_iterations(2) is False
    assert behavior_from_probe(RunProbe(stop_reason="final_response", iteration_count=3)).efficiency.stopped_normally_within_iterations(2) is False

def test_efficiency_stopped_normally_within_tool_calls() -> None:
    # [Hidden Failure] stopped_normally_within_tool_calls requires normal stop and tool-call bound.
    assert behavior_from_probe(RunProbe(stop_reason="final_response", tool_call_count=2)).efficiency.stopped_normally_within_tool_calls(2) is True
    assert behavior_from_probe(RunProbe(stop_reason="max_tool_calls", tool_call_count=2)).efficiency.stopped_normally_within_tool_calls(2) is False
    assert behavior_from_probe(RunProbe(stop_reason="final_response", tool_call_count=3)).efficiency.stopped_normally_within_tool_calls(2) is False

def test_efficiency_tokens_per_tool_call() -> None:
    # [Edge Case] tokens_per_tool_call divides normally and returns None when unavailable.
    assert behavior_from_probe(RunProbe(tokens_used=100, tool_call_count=4)).efficiency.tokens_per_tool_call() == 25.0
    assert behavior_from_probe(RunProbe(tokens_used=None, tool_call_count=4)).efficiency.tokens_per_tool_call() is None
    assert behavior_from_probe(RunProbe(tokens_used=100, tool_call_count=0)).efficiency.tokens_per_tool_call() is None

def test_efficiency_tokens_per_tool_call_at_most() -> None:
    # [Silent Failure] tokens_per_tool_call_at_most passes unknown usage and fails known over-limit usage.
    assert behavior_from_probe(RunProbe(tokens_used=None, tool_call_count=4)).efficiency.tokens_per_tool_call_at_most(1) is True
    assert behavior_from_probe(RunProbe(tokens_used=100, tool_call_count=4)).efficiency.tokens_per_tool_call_at_most(25) is True
    assert behavior_from_probe(RunProbe(tokens_used=100, tool_call_count=4)).efficiency.tokens_per_tool_call_at_most(24) is False

def test_efficiency_tokens_per_iteration() -> None:
    # [Edge Case] tokens_per_iteration divides normally and returns None when unavailable.
    assert behavior_from_probe(RunProbe(tokens_used=100, iteration_count=4)).efficiency.tokens_per_iteration() == 25.0
    assert behavior_from_probe(RunProbe(tokens_used=None, iteration_count=4)).efficiency.tokens_per_iteration() is None
    assert behavior_from_probe(RunProbe(tokens_used=100, iteration_count=0)).efficiency.tokens_per_iteration() is None

def test_efficiency_tokens_per_iteration_at_most() -> None:
    # [Silent Failure] tokens_per_iteration_at_most passes unknown usage and fails known over-limit usage.
    assert behavior_from_probe(RunProbe(tokens_used=None, iteration_count=4)).efficiency.tokens_per_iteration_at_most(1) is True
    assert behavior_from_probe(RunProbe(tokens_used=100, iteration_count=4)).efficiency.tokens_per_iteration_at_most(25) is True
    assert behavior_from_probe(RunProbe(tokens_used=100, iteration_count=4)).efficiency.tokens_per_iteration_at_most(24) is False

def test_efficiency_handles_nested_unhashable_args() -> None:
    # [Hidden Failure] duplicate detection handles nested list and dict argument values.
    args = {"query": {"terms": ["a", "b"]}}
    calls = (make_call("search", args=args), make_call("search", args=args))
    b = behavior_from_probe(RunProbe(tool_calls=calls))
    assert b.efficiency.duplicate_tool_call_count() == 1
    assert b.efficiency.no_duplicate_tool_args("search") is False


# --- Behavior Facade tests ---

def test_agent_behavior_returns_behavior() -> None:
    # [Edge Case] agent.behavior returns a Behavior instance.
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    assert isinstance(agent.behavior, Behavior)

def test_agent_behavior_efficiency_returns_efficiency_behavior() -> None:
    # [Edge Case] agent.behavior.efficiency returns an EfficiencyBehavior instance.
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    assert isinstance(agent.behavior.efficiency, EfficiencyBehavior)

def test_behavior_from_probe_helper_initializes_efficiency() -> None:
    # [Hidden Assumption] behavior_from_probe wires the efficiency category for isolated tests.
    b = behavior_from_probe(RunProbe(tool_calls=()))
    assert b.efficiency.no_duplicate_tool_calls() is True

def test_agent_behavior_cached() -> None:
    # [Silent Failure] agent.behavior returns the same instance on repeated access.
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    assert agent.behavior is agent.behavior

def test_agent_behavior_tool_returns_tool_behavior() -> None:
    # [Edge Case] agent.behavior.tool returns a ToolBehavior.
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    assert isinstance(agent.behavior.tool, ToolBehavior)

def test_behavior_probe_built_lazily() -> None:
    # [Hidden Assumption] probe is not built in __init__ but on first access.
    b = Behavior(BaseAgent(name="t", system_prompt="t", runner=object()))
    assert b._probe is None
    _ = b.probe
    assert b._probe is not None

def test_behavior_probe_cached() -> None:
    # [Silent Failure] probe is cached (built once, returned on subsequent access).
    b = Behavior(BaseAgent(name="t", system_prompt="t", runner=object()))
    assert b.probe is b.probe


# --- PredicateGrader tests ---

def test_predicate_grader_agrade_with_probe_true() -> None:
    # [Edge Case] agrade_with_probe returns passed result when predicate returns True.
    grader = PredicateGrader(lambda p: len(p.tool_calls) > 0)
    probe = RunProbe(tool_calls=(make_call("search"),))
    result = asyncio.run(grader.agrade_with_probe(EvalCase(prompt="t"), "actual", probe))
    assert result.passed is True
    assert result.score == 1.0

def test_predicate_grader_agrade_with_probe_false() -> None:
    # [Edge Case] agrade_with_probe returns failed result when predicate returns False.
    grader = PredicateGrader(lambda p: len(p.tool_calls) > 0)
    result = asyncio.run(grader.agrade_with_probe(EvalCase(prompt="t"), "actual", RunProbe(tool_calls=())))
    assert result.passed is False
    assert result.score == 0.0

def test_predicate_grader_agrade_with_probe_error() -> None:
    # [Hidden Failure] agrade_with_probe returns failed result with error when predicate raises.
    def _bad(p: RunProbe) -> bool:
        raise ValueError("boom")
    grader = PredicateGrader(_bad)
    result = asyncio.run(grader.agrade_with_probe(EvalCase(prompt="t"), "actual", RunProbe()))
    assert result.passed is False
    assert "boom" in result.reason

def test_predicate_grader_agrade_fallback() -> None:
    # [Hidden Assumption] agrade (fallback) returns a descriptive failed result.
    grader = PredicateGrader(lambda p: True)
    result = asyncio.run(grader.agrade(EvalCase(prompt="t"), "actual"))
    assert result.passed is False
    assert "RunProbe" in result.reason


# --- Integration tests ---

async def test_integration_behavior_after_run() -> None:
    # [Silent Failure] End-to-end: run agent, access behavior, verify reflects tool calls.
    calls = (make_call("search", state=ToolCallState.SUCCEEDED),)
    agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
    await agent.arun("find X")
    assert agent.behavior.tool.called_tool("search") is True
    assert agent.behavior.stop.stopped_normally() is True

async def test_integration_efficiency_after_run() -> None:
    # [Silent Failure] End-to-end: efficiency behavior reflects repeated tool calls from the latest run.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}))
    agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 2, "iteration_count": 1})
    await agent.arun("find X")
    assert agent.behavior.efficiency.no_duplicate_tool_calls() is False
    assert agent.behavior.efficiency.duplicate_tool_call_count() == 1

async def test_integration_eval_runner_with_predicate_grader() -> None:
    # [Hidden Assumption] EvalRunner + PredicateGrader: verify passed reflects predicate.
    calls = (make_call("search", state=ToolCallState.SUCCEEDED),)
    agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
    suite = EvalSuite("s", [EvalCase(prompt="t", grader=PredicateGrader(lambda p: p.tool_call_count > 0))])
    runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
    result = await runner.arun(suite)
    assert len(result.results) == 1
    assert result.results[0].grader_result.passed is True

async def test_integration_eval_runner_with_efficiency_predicate() -> None:
    # [Hidden Assumption] EvalRunner still passes probes that can express efficiency predicates.
    calls = (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"}))
    agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 2, "iteration_count": 1})
    suite = EvalSuite("s", [EvalCase(prompt="t", grader=PredicateGrader(lambda p: len({str(dict(c.arguments)) for c in p.tool_calls}) == 1))])
    runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
    result = await runner.arun(suite)
    assert result.results[0].grader_result.passed is True

async def test_integration_eval_runner_standard_grader_unchanged() -> None:
    # [Hidden Failure] EvalRunner + ContainsGrader: standard agrade path unchanged.
    agent = MockAgent(reply_metadata={"tool_calls": ()})
    suite = EvalSuite("s", [EvalCase(prompt="t", expected="processed", grader=ContainsGrader())])
    runner = EvalRunner(agent, default_grader=ContainsGrader())
    result = await runner.arun(suite)
    assert result.results[0].grader_result.passed is True

async def test_integration_cache_invalidation() -> None:
    # [Silent Failure] Cache invalidation: run twice, verify behavior reflects second run.
    agent = MockAgent(reply_metadata={"tool_calls": (make_call("search"),), "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
    await agent.arun("first")
    assert agent.behavior.tool.called_tool("search") is True
    agent._reply_metadata = {"tool_calls": (make_call("write"),), "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1}
    await agent.arun("second")
    assert agent.behavior.tool.called_tool("search") is False
    assert agent.behavior.tool.called_tool("write") is True

async def test_integration_efficiency_cache_invalidation() -> None:
    # [Silent Failure] Cache invalidation: efficiency predicates reflect the second run.
    agent = MockAgent(reply_metadata={"tool_calls": (make_call("search", args={"q": "x"}), make_call("search", args={"q": "x"})), "stop_reason": "final_response", "tool_call_count": 2, "iteration_count": 1})
    await agent.arun("first")
    assert agent.behavior.efficiency.no_duplicate_tool_calls() is False
    agent._reply_metadata = {"tool_calls": (make_call("search", args={"q": "x"}), make_call("search", args={"q": "y"})), "stop_reason": "final_response", "tool_call_count": 2, "iteration_count": 1}
    await agent.arun("second")
    assert agent.behavior.efficiency.no_duplicate_tool_calls() is True


# --- Main ---

def main() -> int:
    tr = TestRunner()
    # RunProbe
    tr.run("probe_from_agent_populated [Hidden Assumption]", test_probe_from_agent_populated)
    tr.run("probe_from_agent_no_reply [Edge Case]", test_probe_from_agent_no_reply)
    tr.run("probe_missing_tool_calls_key [Edge Case]", test_probe_missing_tool_calls_key)
    tr.run("probe_missing_stop_reason_defaults [Silent Failure]", test_probe_missing_stop_reason_defaults)
    tr.run("probe_reads_handoff_and_handoffs [Hidden Assumption]", test_probe_reads_handoff_and_handoffs_independently)
    tr.run("probe_from_reply_no_agent [Edge Case]", test_probe_from_reply_no_agent)
    tr.run("probe_states_derived_from_calls [Silent Failure]", test_probe_states_derived_from_calls)
    # ToolBehavior A
    tr.run("called_tool_true_false [Edge Case]", test_called_tool_true_false)
    tr.run("not_called_tool_negation [Silent Failure]", test_not_called_tool_negation)
    tr.run("called_all_tools_present_missing [Edge Case]", test_called_all_tools_present_and_missing)
    tr.run("called_all_tools_empty_vacuous [Edge Case]", test_called_all_tools_empty_vacuous)
    tr.run("called_any_tool_match [Edge Case]", test_called_any_tool_match_and_no_match)
    tr.run("called_no_tools_true_false [Edge Case]", test_called_no_tools_true_and_false)
    tr.run("called_only_tools_in_set_extra [Silent Failure]", test_called_only_tools_in_set_and_extra)
    tr.run("called_only_tools_empty_with_calls [Edge Case]", test_called_only_tools_empty_with_calls)
    tr.run("called_tools_in_order [Silent Failure]", test_called_tools_in_order_valid_and_invalid)
    tr.run("called_tools_in_order_empty [Edge Case]", test_called_tools_in_order_empty_vacuous)
    tr.run("tool_call_count_multiple [Silent Failure]", test_tool_call_count_multiple)
    tr.run("called_tool_names_ordered_unique [Silent Failure]", test_called_tool_names_ordered_unique)
    # ToolBehavior B
    tr.run("tool_succeeded_state [Hidden Assumption]", test_tool_succeeded_state_check)
    tr.run("tool_failed_state [Hidden Assumption]", test_tool_failed_state_check)
    tr.run("tool_denied_state [Hidden Assumption]", test_tool_denied_state_check)
    tr.run("all_tool_calls_succeeded_mixed [Silent Failure]", test_all_tool_calls_succeeded_mixed)
    tr.run("all_tool_calls_succeeded_vacuous [Edge Case]", test_all_tool_calls_succeeded_vacuous)
    tr.run("tool_returned_containing [Hidden Assumption]", test_tool_returned_containing_finds_substring)
    tr.run("tool_returned_containing_skips_none [Hidden Failure]", test_tool_returned_containing_skips_none_result)
    tr.run("tool_returned_matching_regex [Edge Case]", test_tool_returned_matching_regex)
    # ToolArgumentBehavior C
    tr.run("tool_called_with_subset [Silent Failure]", test_tool_called_with_subset)
    tr.run("tool_called_with_empty_kwargs [Edge Case]", test_tool_called_with_empty_kwargs)
    tr.run("tool_called_with_exact [Silent Failure]", test_tool_called_with_exact_match)
    tr.run("tool_never_called_with [Silent Failure]", test_tool_never_called_with_negation)
    tr.run("tool_called_with_matching [Hidden Assumption]", test_tool_called_with_matching_predicate)
    tr.run("tool_called_with_matching_skips_missing [Hidden Failure]", test_tool_called_with_matching_skips_missing_arg)
    # StopBehavior D
    tr.run("stopped_on_exact [Edge Case]", test_stopped_on_exact_match)
    tr.run("stopped_normally [Silent Failure]", test_stopped_normally_only_final_response)
    tr.run("did_not_hit_max_iterations [Hidden Assumption]", test_did_not_hit_max_iterations)
    tr.run("did_not_hit_max_tool_calls [Hidden Assumption]", test_did_not_hit_max_tool_calls)
    tr.run("did_not_hit_max_tokens [Hidden Assumption]", test_did_not_hit_max_tokens)
    tr.run("iteration_count_raw [Edge Case]", test_iteration_count_raw)
    tr.run("total_tool_calls_raw [Edge Case]", test_total_tool_calls_raw)
    tr.run("tokens_used_none [Edge Case]", test_tokens_used_none)
    tr.run("did_not_exceed_tokens_none [Silent Failure]", test_did_not_exceed_tokens_none)
    tr.run("did_not_exceed_tokens_exceeds [Silent Failure]", test_did_not_exceed_tokens_exceeds)
    # HandoffBehavior E
    tr.run("handoff_occurred_true [Edge Case]", test_handoff_occurred_true)
    tr.run("handoff_occurred_false [Edge Case]", test_handoff_occurred_false)
    tr.run("handoff_is_filled_true [Silent Failure]", test_handoff_is_filled_true)
    tr.run("handoff_is_filled_false [Silent Failure]", test_handoff_is_filled_false)
    tr.run("handoff_count [Hidden Assumption]", test_handoff_count)
    tr.run("handoff_has_section [Edge Case]", test_handoff_has_section_true_false)
    tr.run("handoff_section_contains [Silent Failure]", test_handoff_section_contains_finds_substring)
    tr.run("handoff_section_contains_missing [Hidden Failure]", test_handoff_section_contains_missing_section)
    tr.run("handoff_all_predicates_none [Edge Case]", test_handoff_all_predicates_none)
    # EfficiencyBehavior G
    tr.run("efficiency_max_tool_repetitions [Edge Case]", test_efficiency_max_tool_repetitions)
    tr.run("efficiency_max_any_tool_repetitions [Silent Failure]", test_efficiency_max_any_tool_repetitions)
    tr.run("efficiency_completed_within_iterations [Edge Case]", test_efficiency_completed_within_iterations)
    tr.run("efficiency_completed_within_tool_calls [Edge Case]", test_efficiency_completed_within_tool_calls)
    tr.run("efficiency_tool_calls_between [Silent Failure]", test_efficiency_tool_calls_between)
    tr.run("efficiency_no_duplicate_tool_args [Hidden Assumption]", test_efficiency_no_duplicate_tool_args)
    tr.run("efficiency_no_duplicate_tool_calls [Silent Failure]", test_efficiency_no_duplicate_tool_calls)
    tr.run("efficiency_duplicate_tool_arg_count [Silent Failure]", test_efficiency_duplicate_tool_arg_count)
    tr.run("efficiency_duplicate_tool_call_count [Silent Failure]", test_efficiency_duplicate_tool_call_count)
    tr.run("efficiency_unique_tool_call_count [Silent Failure]", test_efficiency_unique_tool_call_count)
    tr.run("efficiency_unique_tool_ratio_empty [Edge Case]", test_efficiency_unique_tool_ratio_at_least_empty)
    tr.run("efficiency_unique_tool_ratio_mixed [Silent Failure]", test_efficiency_unique_tool_ratio_at_least_mixed)
    tr.run("efficiency_no_consecutive_identical_calls [Hidden Assumption]", test_efficiency_no_consecutive_identical_calls)
    tr.run("efficiency_no_consecutive_same_tool [Hidden Assumption]", test_efficiency_no_consecutive_same_tool)
    tr.run("efficiency_consecutive_identical_call_count [Silent Failure]", test_efficiency_consecutive_identical_call_count)
    tr.run("efficiency_consecutive_same_tool_count [Silent Failure]", test_efficiency_consecutive_same_tool_count)
    tr.run("efficiency_max_consecutive_tool_calls [Silent Failure]", test_efficiency_max_consecutive_tool_calls)
    tr.run("efficiency_max_any_consecutive_tool_repetitions [Silent Failure]", test_efficiency_max_any_consecutive_tool_repetitions)
    tr.run("efficiency_repeated_tool_names_ordered [Silent Failure]", test_efficiency_repeated_tool_names_ordered)
    tr.run("efficiency_no_repeated_tool_results [Hidden Assumption]", test_efficiency_no_repeated_tool_results_global_and_scoped)
    tr.run("efficiency_repeated_tool_result_count [Hidden Failure]", test_efficiency_repeated_tool_result_count)
    tr.run("efficiency_max_result_repetitions [Edge Case]", test_efficiency_max_result_repetitions)
    tr.run("efficiency_failed_tool_calls_at_most [Edge Case]", test_efficiency_failed_tool_calls_at_most)
    tr.run("efficiency_denied_tool_calls_at_most [Edge Case]", test_efficiency_denied_tool_calls_at_most)
    tr.run("efficiency_unsuccessful_tool_calls_at_most [Hidden Assumption]", test_efficiency_unsuccessful_tool_calls_at_most)
    tr.run("efficiency_successful_ratio_empty [Edge Case]", test_efficiency_successful_tool_call_ratio_at_least_empty)
    tr.run("efficiency_successful_ratio_mixed [Silent Failure]", test_efficiency_successful_tool_call_ratio_at_least_mixed)
    tr.run("efficiency_no_failed_tool_retries [Hidden Assumption]", test_efficiency_no_failed_tool_retries)
    tr.run("efficiency_failed_tool_retry_count [Silent Failure]", test_efficiency_failed_tool_retry_count)
    tr.run("efficiency_did_not_stop_on_budget [Hidden Assumption]", test_efficiency_did_not_stop_on_budget)
    tr.run("efficiency_stopped_normally_within_iterations [Hidden Failure]", test_efficiency_stopped_normally_within_iterations)
    tr.run("efficiency_stopped_normally_within_tool_calls [Hidden Failure]", test_efficiency_stopped_normally_within_tool_calls)
    tr.run("efficiency_tokens_per_tool_call [Edge Case]", test_efficiency_tokens_per_tool_call)
    tr.run("efficiency_tokens_per_tool_call_at_most [Silent Failure]", test_efficiency_tokens_per_tool_call_at_most)
    tr.run("efficiency_tokens_per_iteration [Edge Case]", test_efficiency_tokens_per_iteration)
    tr.run("efficiency_tokens_per_iteration_at_most [Silent Failure]", test_efficiency_tokens_per_iteration_at_most)
    tr.run("efficiency_handles_nested_unhashable_args [Hidden Failure]", test_efficiency_handles_nested_unhashable_args)
    # Behavior Facade
    tr.run("agent_behavior_returns_behavior [Edge Case]", test_agent_behavior_returns_behavior)
    tr.run("agent_behavior_efficiency_returns_efficiency [Edge Case]", test_agent_behavior_efficiency_returns_efficiency_behavior)
    tr.run("behavior_from_probe_initializes_efficiency [Hidden Assumption]", test_behavior_from_probe_helper_initializes_efficiency)
    tr.run("agent_behavior_cached [Silent Failure]", test_agent_behavior_cached)
    tr.run("agent_behavior_tool_returns_tb [Edge Case]", test_agent_behavior_tool_returns_tool_behavior)
    tr.run("behavior_probe_built_lazily [Hidden Assumption]", test_behavior_probe_built_lazily)
    tr.run("behavior_probe_cached [Silent Failure]", test_behavior_probe_cached)
    # PredicateGrader
    tr.run("predicate_grader_true [Edge Case]", test_predicate_grader_agrade_with_probe_true)
    tr.run("predicate_grader_false [Edge Case]", test_predicate_grader_agrade_with_probe_false)
    tr.run("predicate_grader_error [Hidden Failure]", test_predicate_grader_agrade_with_probe_error)
    tr.run("predicate_grader_fallback [Hidden Assumption]", test_predicate_grader_agrade_fallback)

    # Async integration tests
    asyncio.run(tr.run_async("integration_behavior_after_run [Silent Failure]", test_integration_behavior_after_run))
    asyncio.run(tr.run_async("integration_efficiency_after_run [Silent Failure]", test_integration_efficiency_after_run))
    asyncio.run(tr.run_async("integration_eval_runner_predicate [Hidden Assumption]", test_integration_eval_runner_with_predicate_grader))
    asyncio.run(tr.run_async("integration_eval_runner_efficiency_predicate [Hidden Assumption]", test_integration_eval_runner_with_efficiency_predicate))
    asyncio.run(tr.run_async("integration_eval_runner_standard [Hidden Failure]", test_integration_eval_runner_standard_grader_unchanged))
    asyncio.run(tr.run_async("integration_cache_invalidation [Silent Failure]", test_integration_cache_invalidation))
    asyncio.run(tr.run_async("integration_efficiency_cache_invalidation [Silent Failure]", test_integration_efficiency_cache_invalidation))

    return tr.summary()


if __name__ == "__main__":
    sys.exit(main())
