"""Context Protocol Header

Description:
    Full unit and integration test coverage for the agent behavior facade.
Purpose:
    Validates RunProbe, ToolBehavior, ToolArgumentBehavior, StopBehavior,
    HandoffBehavior, Behavior facade, PredicateGrader, and EvalRunner integration.
Architecture:
    - MockAgent: BaseAgent subclass returning scripted replies with tool call metadata.
    - StubAgent: Minimal stub for RunProbe tests without full agent construction.
    - AgentBehaviorTests: IsolatedAsyncioTestCase covering all categories.
Relations:
    Validates code in vidbyte/evals/behavior/ and runs under scripts/test-agent-behavior.py.
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput
from vidbyte.context.handoff.base import Handoff
from vidbyte.evals import Behavior, ContainsGrader, EvalCase, EvalRunner, EvalSuite, PredicateGrader, RunProbe
from vidbyte.evals.behavior.output import OutputBehavior
from vidbyte.evals.behavior.tool import ToolBehavior
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult, ToolStatus
from pydantic import BaseModel


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
    b._output = OutputBehavior.__new__(OutputBehavior)
    b._output._behavior = b
    return b


class StructuredPayload(BaseModel):
    """Pydantic payload used to verify model_dump structured traversal."""

    answer: str
    items: list[dict[str, Any]]


class StubAgent:
    """Minimal stub mimicking BaseAgent post-run fields for RunProbe tests."""

    def __init__(self, reply: AgentMessage | None = None, handoff: Handoff | None = None, handoffs: list | None = None, trace: dict | None = None) -> None:
        self.last_reply = reply
        self.last_handoff = handoff
        self.handoffs = handoffs or []
        self.last_trace = trace


class MockAgent(BaseAgent):
    """BaseAgent subclass returning scripted replies with tool call metadata."""

    def __init__(self, reply_metadata: dict[str, Any] | None = None, reply_content: str = "processed") -> None:
        super().__init__(name="mock", system_prompt="test", runner=object())
        self._reply_metadata = reply_metadata or {}
        self._reply_content = reply_content

    def fork(self, **kwargs: Any) -> MockAgent:
        return self

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        self._behavior_view = None
        reply = AgentMessage(sender="mock", recipient="orchestrator", content=self._reply_content, metadata=dict(self._reply_metadata))
        self.last_reply = reply
        return reply


class AgentBehaviorTests(unittest.IsolatedAsyncioTestCase):
    """Main test suite validating all behavior predicate categories and integration."""

    # --- RunProbe ---

    def test_probe_from_agent_populated(self) -> None:
        # [Hidden Assumption] from_agent with populated last_reply extracts all metadata fields.
        calls = (make_call("search"), make_call("read", state=ToolCallState.FAILED))
        reply = make_reply(metadata={"tool_calls": calls, "stop_reason": "max_iterations", "iteration_count": 5, "tokens_used": 1000, "tool_call_count": 2})
        probe = RunProbe.from_agent(StubAgent(reply=reply))
        self.assertEqual(probe.tool_calls, calls)
        self.assertEqual(probe.stop_reason, "max_iterations")
        self.assertEqual(probe.iteration_count, 5)
        self.assertEqual(probe.tokens_used, 1000)

    def test_probe_from_agent_no_reply(self) -> None:
        # [Edge Case] from_agent with last_reply=None returns all-empty/zero probe.
        probe = RunProbe.from_agent(StubAgent(reply=None))
        self.assertEqual(probe.tool_calls, ())
        self.assertEqual(probe.stop_reason, "final_response")
        self.assertIsNone(probe.tokens_used)

    def test_probe_missing_tool_calls_key(self) -> None:
        # [Edge Case] metadata lacks tool_calls returns empty tuple.
        probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"stop_reason": "final_response"})))
        self.assertEqual(probe.tool_calls, ())

    def test_probe_missing_stop_reason_defaults(self) -> None:
        # [Silent Failure] metadata lacks stop_reason defaults to "final_response".
        probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"tool_calls": ()})))
        self.assertEqual(probe.stop_reason, "final_response")

    def test_probe_reads_handoff_and_handoffs(self) -> None:
        # [Hidden Assumption] from_agent reads last_handoff and handoffs independently.
        h1, h2 = Handoff(sections={"a": "b"}), Handoff(sections={"c": "d"})
        probe = RunProbe.from_agent(StubAgent(reply=make_reply(), handoff=h1, handoffs=[h2]))
        self.assertIs(probe.handoff, h1)
        self.assertEqual(probe.handoffs, (h2,))

    def test_probe_from_reply_no_agent(self) -> None:
        # [Edge Case] from_reply without agent returns handoff=None and handoffs=().
        probe = RunProbe.from_reply(make_reply(metadata={"tool_calls": ()}))
        self.assertIsNone(probe.handoff)
        self.assertEqual(probe.handoffs, ())

    def test_probe_states_derived_from_calls(self) -> None:
        # [Silent Failure] tool_call_states derived from tool_calls when not in metadata.
        calls = (make_call("a", state=ToolCallState.SUCCEEDED), make_call("b", state=ToolCallState.FAILED))
        probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"tool_calls": calls})))
        self.assertEqual(probe.tool_call_states, ("succeeded", "failed"))

    def test_probe_from_agent_structured(self) -> None:
        # [Hidden Assumption] from_agent copies metadata["structured"] into probe.structured.
        structured = {"answer": "yes"}
        probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"structured": structured})))
        self.assertIs(probe.structured, structured)

    def test_probe_from_reply_structured(self) -> None:
        # [Hidden Assumption] from_reply copies metadata["structured"] without an agent.
        structured = {"answer": "yes"}
        probe = RunProbe.from_reply(make_reply(metadata={"structured": structured}))
        self.assertIs(probe.structured, structured)

    def test_probe_missing_structured_defaults_none(self) -> None:
        # [Edge Case] missing structured metadata leaves probe.structured as None.
        probe = RunProbe.from_reply(make_reply())
        self.assertIsNone(probe.structured)

    # --- ToolBehavior Category A ---

    def test_called_tool(self) -> None:
        # [Edge Case] called_tool returns True when called, False when not.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
        self.assertTrue(b.tool.called_tool("search"))
        self.assertFalse(b.tool.called_tool("write"))

    def test_not_called_tool(self) -> None:
        # [Silent Failure] not_called_tool is the exact negation of called_tool.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"),)))
        self.assertFalse(b.tool.not_called_tool("search"))
        self.assertTrue(b.tool.not_called_tool("write"))

    def test_called_all_tools(self) -> None:
        # [Edge Case] called_all_tools True when all present, False when one missing.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
        self.assertTrue(b.tool.called_all_tools(["search", "read"]))
        self.assertFalse(b.tool.called_all_tools(["search", "write"]))
        self.assertTrue(b.tool.called_all_tools([]))

    def test_called_any_tool(self) -> None:
        # [Edge Case] called_any_tool True with one match, False with no matches.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
        self.assertTrue(b.tool.called_any_tool(["search", "write"]))
        self.assertFalse(b.tool.called_any_tool(["write", "exec"]))

    def test_called_no_tools(self) -> None:
        # [Edge Case] called_no_tools True when empty, False when calls exist.
        self.assertTrue(behavior_from_probe(RunProbe(tool_calls=())).tool.called_no_tools())
        self.assertFalse(behavior_from_probe(RunProbe(tool_calls=(make_call("search"),))).tool.called_no_tools())

    def test_called_only_tools(self) -> None:
        # [Silent Failure] called_only_tools True when all in set, False when extra outside.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("read"))))
        self.assertTrue(b.tool.called_only_tools(["search", "read"]))
        self.assertFalse(b.tool.called_only_tools(["search"]))
        self.assertFalse(b.tool.called_only_tools([]))

    def test_called_tools_in_order(self) -> None:
        # [Silent Failure] called_tools_in_order True for valid subsequence, False when wrong order.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("a"), make_call("b"), make_call("c"))))
        self.assertTrue(b.tool.called_tools_in_order(["a", "c"]))
        self.assertFalse(b.tool.called_tools_in_order(["c", "a"]))
        self.assertTrue(b.tool.called_tools_in_order([]))

    def test_tool_call_count(self) -> None:
        # [Silent Failure] tool_call_count returns correct count for multiple calls to same tool.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search"), make_call("search"), make_call("read"))))
        self.assertEqual(b.tool.tool_call_count("search"), 2)
        self.assertEqual(b.tool.tool_call_count("read"), 1)
        self.assertEqual(b.tool.tool_call_count("write"), 0)

    def test_called_tool_names_ordered_unique(self) -> None:
        # [Silent Failure] called_tool_names returns ordered unique names preserving first-occurrence.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("b"), make_call("a"), make_call("b"))))
        self.assertEqual(b.tool.called_tool_names(), ("b", "a"))

    # --- ToolBehavior Category B ---

    def test_tool_succeeded(self) -> None:
        # [Hidden Assumption] tool_succeeded True only when state is SUCCEEDED.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("s", state=ToolCallState.SUCCEEDED), make_call("f", state=ToolCallState.FAILED))))
        self.assertTrue(b.tool.tool_succeeded("s"))
        self.assertFalse(b.tool.tool_succeeded("f"))

    def test_tool_failed(self) -> None:
        # [Hidden Assumption] tool_failed True only when state is FAILED.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("s", state=ToolCallState.SUCCEEDED), make_call("f", state=ToolCallState.FAILED))))
        self.assertTrue(b.tool.tool_failed("f"))
        self.assertFalse(b.tool.tool_failed("s"))

    def test_tool_denied(self) -> None:
        # [Hidden Assumption] tool_denied True only when state is DENIED.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("d", state=ToolCallState.DENIED), make_call("s", state=ToolCallState.SUCCEEDED))))
        self.assertTrue(b.tool.tool_denied("d"))
        self.assertFalse(b.tool.tool_denied("s"))

    def test_all_tool_calls_succeeded(self) -> None:
        # [Silent Failure] all_tool_calls_succeeded False when any failed; True when zero calls.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("a", state=ToolCallState.SUCCEEDED), make_call("b", state=ToolCallState.FAILED))))
        self.assertFalse(b.tool.all_tool_calls_succeeded())
        self.assertTrue(behavior_from_probe(RunProbe(tool_calls=())).tool.all_tool_calls_succeeded())

    def test_tool_returned_containing(self) -> None:
        # [Hidden Assumption] tool_returned_containing finds substring; skips None result.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output="hello world"),)))
        self.assertTrue(b.tool.tool_returned_containing("search", "hello"))
        self.assertFalse(b.tool.tool_returned_containing("search", "goodbye"))
        b2 = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output=None),)))
        self.assertFalse(b2.tool.tool_returned_containing("search", "anything"))

    def test_tool_returned_matching(self) -> None:
        # [Edge Case] tool_returned_matching applies regex to result output.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", result_output="id: 123-45"),)))
        self.assertTrue(b.tool.tool_returned_matching("search", r"\d{3}-\d{2}"))
        self.assertFalse(b.tool.tool_returned_matching("search", r"\d{5}"))

    # --- ToolArgumentBehavior Category C ---

    def test_tool_called_with_subset(self) -> None:
        # [Silent Failure] tool_called_with True when args are a subset of call arguments.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python", "limit": 10}),)))
        self.assertTrue(b.tool_args.tool_called_with("search", query="python"))
        self.assertTrue(b.tool_args.tool_called_with("search", query="python", limit=10))
        self.assertFalse(b.tool_args.tool_called_with("search", query="java"))

    def test_tool_called_with_empty_kwargs(self) -> None:
        # [Edge Case] tool_called_with empty kwargs True if the tool was called at all.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
        self.assertTrue(b.tool_args.tool_called_with("search"))
        self.assertFalse(b.tool_args.tool_called_with("write"))

    def test_tool_called_with_exact(self) -> None:
        # [Silent Failure] tool_called_with_exact True only on exact argument dict match.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python", "limit": 10}),)))
        self.assertTrue(b.tool_args.tool_called_with_exact("search", {"query": "python", "limit": 10}))
        self.assertFalse(b.tool_args.tool_called_with_exact("search", {"query": "python"}))

    def test_tool_never_called_with(self) -> None:
        # [Silent Failure] tool_never_called_with is the negation of tool_called_with.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
        self.assertTrue(b.tool_args.tool_never_called_with("search", query="java"))
        self.assertFalse(b.tool_args.tool_never_called_with("search", query="python"))

    def test_tool_called_with_matching(self) -> None:
        # [Hidden Assumption] tool_called_with_matching calls predicate on arg value.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python tutorial"}),)))
        self.assertTrue(b.tool_args.tool_called_with_matching("search", "query", lambda q: "python" in q))
        self.assertFalse(b.tool_args.tool_called_with_matching("search", "query", lambda q: "java" in q))

    def test_tool_called_with_matching_skips_missing(self) -> None:
        # [Hidden Failure] tool_called_with_matching skips calls where arg_name is absent.
        b = behavior_from_probe(RunProbe(tool_calls=(make_call("search", args={"query": "python"}),)))
        self.assertFalse(b.tool_args.tool_called_with_matching("search", "limit", lambda v: True))

    # --- StopBehavior Category D ---

    def test_stopped_on(self) -> None:
        # [Edge Case] stopped_on True for exact reason match.
        b = behavior_from_probe(RunProbe(stop_reason="max_iterations"))
        self.assertTrue(b.stop.stopped_on("max_iterations"))
        self.assertFalse(b.stop.stopped_on("final_response"))

    def test_stopped_normally(self) -> None:
        # [Silent Failure] stopped_normally True only for "final_response".
        self.assertTrue(behavior_from_probe(RunProbe(stop_reason="final_response")).stop.stopped_normally())
        self.assertFalse(behavior_from_probe(RunProbe(stop_reason="max_iterations")).stop.stopped_normally())

    def test_did_not_hit_budgets(self) -> None:
        # [Hidden Assumption] budget checks return False when the corresponding stop reason is hit.
        self.assertFalse(behavior_from_probe(RunProbe(stop_reason="max_iterations")).stop.did_not_hit_max_iterations())
        self.assertFalse(behavior_from_probe(RunProbe(stop_reason="max_tool_calls")).stop.did_not_hit_max_tool_calls())
        self.assertFalse(behavior_from_probe(RunProbe(stop_reason="max_tokens")).stop.did_not_hit_max_tokens())

    def test_stop_raw_values(self) -> None:
        # [Edge Case] iteration_count, total_tool_calls, tokens_used return raw values.
        b = behavior_from_probe(RunProbe(iteration_count=7, tool_call_count=3, tokens_used=None))
        self.assertEqual(b.stop.iteration_count(), 7)
        self.assertEqual(b.stop.total_tool_calls(), 3)
        self.assertIsNone(b.stop.tokens_used())

    def test_did_not_exceed_tokens(self) -> None:
        # [Silent Failure] did_not_exceed_tokens True when None, False when exceeded.
        self.assertTrue(behavior_from_probe(RunProbe(tokens_used=None)).stop.did_not_exceed_tokens(1000))
        b = behavior_from_probe(RunProbe(tokens_used=2000))
        self.assertFalse(b.stop.did_not_exceed_tokens(1000))
        self.assertTrue(b.stop.did_not_exceed_tokens(3000))

    # --- HandoffBehavior Category E ---

    def test_handoff_occurred(self) -> None:
        # [Edge Case] handoff_occurred True when set, False when None.
        self.assertTrue(behavior_from_probe(RunProbe(handoff=Handoff(sections={"a": "b"}))).handoff.handoff_occurred())
        self.assertFalse(behavior_from_probe(RunProbe(handoff=None)).handoff.handoff_occurred())

    def test_handoff_is_filled(self) -> None:
        # [Silent Failure] handoff_is_filled True only when is_filled is True.
        h = Handoff(sections={"a": "b"}).fill({"a": "content"})
        self.assertTrue(behavior_from_probe(RunProbe(handoff=h)).handoff.handoff_is_filled())
        self.assertFalse(behavior_from_probe(RunProbe(handoff=Handoff(sections={"a": "b"}))).handoff.handoff_is_filled())

    def test_handoff_count(self) -> None:
        # [Hidden Assumption] handoff_count returns len(handoffs) list.
        h1, h2 = Handoff(sections={"a": "b"}), Handoff(sections={"c": "d"})
        self.assertEqual(behavior_from_probe(RunProbe(handoff=h1, handoffs=(h1, h2))).handoff.handoff_count(), 2)

    def test_handoff_sections(self) -> None:
        # [Edge Case / Hidden Failure] handoff_has_section and handoff_section_contains.
        b = behavior_from_probe(RunProbe(handoff=Handoff(sections={"summary": "The agent searched for data."})))
        self.assertTrue(b.handoff.handoff_has_section("summary"))
        self.assertFalse(b.handoff.handoff_has_section("missing"))
        self.assertTrue(b.handoff.handoff_section_contains("summary", "searched"))
        self.assertFalse(b.handoff.handoff_section_contains("missing", "text"))

    def test_handoff_all_predicates_none(self) -> None:
        # [Edge Case] All handoff predicates return False/0 when handoff is None.
        b = behavior_from_probe(RunProbe(handoff=None))
        self.assertFalse(b.handoff.handoff_occurred())
        self.assertFalse(b.handoff.handoff_is_filled())
        self.assertEqual(b.handoff.handoff_count(), 0)

    # --- OutputBehavior Category F ---

    def test_output_empty_and_not_empty(self) -> None:
        # [Edge Case / Silent Failure] is_empty and is_not_empty handle empty and whitespace output.
        self.assertTrue(behavior_from_probe(RunProbe(output="")).output.is_empty())
        self.assertTrue(behavior_from_probe(RunProbe(output="   ")).output.is_empty(strip=True))
        self.assertFalse(behavior_from_probe(RunProbe(output="   ")).output.is_empty(strip=False))
        self.assertTrue(behavior_from_probe(RunProbe(output="text")).output.is_not_empty())

    def test_output_length_bounds(self) -> None:
        # [Edge Case / Silent Failure] length uses inclusive character bounds.
        self.assertTrue(behavior_from_probe(RunProbe(output="")).output.length(at_least=0, at_most=0))
        self.assertTrue(behavior_from_probe(RunProbe(output="abcd")).output.length(at_least=2, at_most=4))
        self.assertFalse(behavior_from_probe(RunProbe(output="abcde")).output.length(at_least=2, at_most=4))

    def test_output_line_count(self) -> None:
        # [Edge Case / Silent Failure] line_count uses splitlines logical lines.
        self.assertTrue(behavior_from_probe(RunProbe(output="")).output.line_count(at_least=0, at_most=0))
        self.assertTrue(behavior_from_probe(RunProbe(output="a\nb")).output.line_count(at_least=2, at_most=2))
        self.assertFalse(behavior_from_probe(RunProbe(output="a\nb\nc")).output.line_count(at_most=2))

    def test_output_word_count(self) -> None:
        # [Silent Failure] word_count counts word tokens instead of raw whitespace splits.
        self.assertTrue(behavior_from_probe(RunProbe(output="one, two three")).output.word_count(at_least=3, at_most=3))
        self.assertFalse(behavior_from_probe(RunProbe(output="one two")).output.word_count(at_least=3))

    def test_output_is_valid_json(self) -> None:
        # [Edge Case / Hidden Failure / Silent Failure] JSON validity returns booleans without raising.
        self.assertFalse(behavior_from_probe(RunProbe(output="")).output.is_valid_json())
        self.assertFalse(behavior_from_probe(RunProbe(output="{bad")).output.is_valid_json())
        self.assertTrue(behavior_from_probe(RunProbe(output='{"a": 1}')).output.is_valid_json())
        self.assertTrue(behavior_from_probe(RunProbe(output='[1, 2]')).output.is_valid_json())

    def test_output_code_blocks(self) -> None:
        # [Edge Case / Hidden Failure / Silent Failure] code block detection handles language and unclosed fences.
        output = "Before\n```Python\nprint('x')\n```\n~~~js\nconsole.log(1)\n~~~"
        b = behavior_from_probe(RunProbe(output=output))
        self.assertTrue(b.output.contains_code_block())
        self.assertTrue(b.output.contains_code_block("python"))
        self.assertEqual(b.output.code_block_count(), 2)
        self.assertEqual(b.output.code_block_count("python"), 1)
        self.assertTrue(b.output.code_block_count("python", at_least=1, at_most=1))
        self.assertFalse(behavior_from_probe(RunProbe(output="```python\nx")).output.contains_code_block())
        self.assertTrue(behavior_from_probe(RunProbe(output="plain")).output.code_block_count(at_least=0, at_most=0))

    def test_output_urls(self) -> None:
        # [Edge Case / Silent Failure] URL detection handles http, https, and www forms.
        self.assertFalse(behavior_from_probe(RunProbe(output="no link")).output.contains_url())
        b = behavior_from_probe(RunProbe(output="See https://a.test and http://b.test plus www.c.test"))
        self.assertTrue(b.output.contains_url())
        self.assertTrue(b.output.url_count(at_least=3, at_most=3))

    def test_output_citations(self) -> None:
        # [Edge Case / Silent Failure] citation detection supports markdown, bracket, footnote, url, and any.
        self.assertFalse(behavior_from_probe(RunProbe(output="no citations")).output.contains_citation())
        output = "See [source](https://example.com), [1], and [^note]."
        b = behavior_from_probe(RunProbe(output=output))
        self.assertTrue(b.output.contains_citation("markdown"))
        self.assertTrue(b.output.contains_citation("bracket"))
        self.assertTrue(b.output.contains_citation("footnote"))
        self.assertTrue(b.output.contains_citation("url"))
        self.assertTrue(b.output.citation_count("any", at_least=4))

    def test_output_unknown_citation_style_raises(self) -> None:
        # [Hidden Failure] unknown citation style raises ValueError.
        with self.assertRaises(ValueError):
            behavior_from_probe(RunProbe(output="text")).output.contains_citation("apa")

    def test_output_refusal_and_hedging(self) -> None:
        # [Silent Failure / Edge Case] refusal and hedging phrases are detected case-insensitively.
        self.assertTrue(behavior_from_probe(RunProbe(output="I can't help with that.")).output.refused())
        self.assertTrue(behavior_from_probe(RunProbe(output="I cannot comply.")).output.refused())
        self.assertTrue(behavior_from_probe(RunProbe(output="I'm unable to do that.")).output.refused())
        self.assertFalse(behavior_from_probe(RunProbe(output="I can help with that.")).output.refused())
        self.assertTrue(behavior_from_probe(RunProbe(output="Maybe this is likely correct.")).output.contains_hedging())
        self.assertTrue(behavior_from_probe(RunProbe(output="I think it works.")).output.contains_hedging())
        self.assertFalse(behavior_from_probe(RunProbe(output="This is correct.")).output.contains_hedging())

    def test_output_prefix_suffix(self) -> None:
        # [Silent Failure / Edge Case] prefix and suffix checks handle case, stripping, and empty strings.
        b = behavior_from_probe(RunProbe(output=" Result: done. \n"))
        self.assertTrue(b.output.starts_with("result:", case_sensitive=False, strip=True))
        self.assertTrue(b.output.ends_with(".", strip=True))
        self.assertTrue(b.output.starts_with(""))
        self.assertTrue(b.output.ends_with(""))

    def test_structured_valid(self) -> None:
        # [Edge Case] structured_valid distinguishes None from empty structured objects.
        self.assertFalse(behavior_from_probe(RunProbe(structured=None)).output.structured_valid())
        self.assertTrue(behavior_from_probe(RunProbe(structured={})).output.structured_valid())

    def test_structured_field_exists(self) -> None:
        # [Silent Failure / Hidden Failure] structured_field_exists handles falsey values and missing fields.
        b = behavior_from_probe(RunProbe(structured={"answer": "", "items": [{"title": "First"}]}))
        self.assertTrue(b.output.structured_field_exists("answer"))
        self.assertTrue(b.output.structured_field_exists("items.0.title"))
        self.assertFalse(b.output.structured_field_exists("missing"))
        self.assertFalse(b.output.structured_field_exists("items.x.title"))
        self.assertFalse(b.output.structured_field_exists("items.99.title"))

    def test_structured_field_equals(self) -> None:
        # [Silent Failure] structured_field_equals compares with == and preserves falsey values.
        b = behavior_from_probe(RunProbe(structured={"count": 0, "status": "complete"}))
        self.assertTrue(b.output.structured_field_equals("count", 0))
        self.assertTrue(b.output.structured_field_equals("status", "complete"))
        self.assertFalse(b.output.structured_field_equals("missing", None))

    def test_structured_field_matches(self) -> None:
        # [Hidden Assumption / Hidden Failure] predicate is called only for existing fields and errors propagate.
        b = behavior_from_probe(RunProbe(structured={"score": 0.9}))
        self.assertTrue(b.output.structured_field_matches("score", lambda v: v > 0.8))
        self.assertFalse(b.output.structured_field_matches("missing", lambda v: True))
        with self.assertRaises(ValueError):
            b.output.structured_field_matches("score", lambda v: (_ for _ in ()).throw(ValueError("boom")))

    def test_structured_field_type_and_keys(self) -> None:
        # [Silent Failure] structured_field_type and structured_contains_keys use resolved/top-level values.
        b = behavior_from_probe(RunProbe(structured={"items": [], "a": 0, "b": False}))
        self.assertTrue(b.output.structured_field_type("items", list))
        self.assertFalse(b.output.structured_field_type("items", dict))
        self.assertTrue(b.output.structured_contains_keys(["a", "b"]))
        self.assertFalse(b.output.structured_contains_keys(["a", "c"]))

    def test_structured_pydantic_model_dump(self) -> None:
        # [Hidden Assumption] Pydantic structured objects are supported through model_dump().
        payload = StructuredPayload(answer="yes", items=[{"title": "First"}])
        b = behavior_from_probe(RunProbe(structured=payload))
        self.assertTrue(b.output.structured_field_equals("answer", "yes"))
        self.assertTrue(b.output.structured_field_exists("items.0.title"))

    # --- Behavior Facade ---

    def test_agent_behavior_returns_behavior(self) -> None:
        # [Edge Case] agent.behavior returns a Behavior instance.
        agent = BaseAgent(name="t", system_prompt="t", runner=object())
        self.assertIsInstance(agent.behavior, Behavior)

    def test_agent_behavior_output_returns_output_behavior(self) -> None:
        # [Edge Case] agent.behavior.output returns an OutputBehavior instance.
        agent = BaseAgent(name="t", system_prompt="t", runner=object())
        self.assertIsInstance(agent.behavior.output, OutputBehavior)

    def test_agent_behavior_cached(self) -> None:
        # [Silent Failure] agent.behavior returns the same instance on repeated access.
        agent = BaseAgent(name="t", system_prompt="t", runner=object())
        self.assertIs(agent.behavior, agent.behavior)
        self.assertIs(agent.behavior.output, agent.behavior.output)

    def test_behavior_probe_lazy_and_cached(self) -> None:
        # [Hidden Assumption / Silent Failure] probe built lazily and cached.
        b = Behavior(BaseAgent(name="t", system_prompt="t", runner=object()))
        self.assertIsNone(b._probe)
        first = b.probe
        self.assertIsNotNone(b._probe)
        self.assertIs(first, b.probe)
        self.assertIs(b.output._behavior.probe, b.tool._behavior.probe)

    # --- PredicateGrader ---

    async def test_predicate_grader_with_probe(self) -> None:
        # [Edge Case / Hidden Failure] PredicateGrader pass/fail/error paths.
        grader = PredicateGrader(lambda p: len(p.tool_calls) > 0)
        result = await grader.agrade_with_probe(EvalCase(prompt="t"), "actual", RunProbe(tool_calls=(make_call("search"),)))
        self.assertTrue(result.passed)
        result = await grader.agrade_with_probe(EvalCase(prompt="t"), "actual", RunProbe(tool_calls=()))
        self.assertFalse(result.passed)

    async def test_predicate_grader_error(self) -> None:
        # [Hidden Failure] PredicateGrader returns failed with error when predicate raises.
        def _bad(p: RunProbe) -> bool:
            raise ValueError("boom")
        grader = PredicateGrader(_bad)
        result = await grader.agrade_with_probe(EvalCase(prompt="t"), "actual", RunProbe())
        self.assertFalse(result.passed)
        self.assertIn("boom", result.reason)

    async def test_predicate_grader_fallback(self) -> None:
        # [Hidden Assumption] agrade fallback returns a descriptive failed result.
        grader = PredicateGrader(lambda p: True)
        result = await grader.agrade(EvalCase(prompt="t"), "actual")
        self.assertFalse(result.passed)
        self.assertIn("RunProbe", result.reason)

    # --- Integration ---

    async def test_integration_behavior_after_run(self) -> None:
        # [Silent Failure] End-to-end: run agent, access behavior, verify reflects tool calls.
        calls = (make_call("search", state=ToolCallState.SUCCEEDED),)
        agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
        await agent.arun("find X")
        self.assertTrue(agent.behavior.tool.called_tool("search"))
        self.assertTrue(agent.behavior.stop.stopped_normally())

    async def test_integration_output_structured_after_run(self) -> None:
        # [Hidden Assumption] End-to-end: structured metadata is visible through output behavior.
        agent = MockAgent(reply_metadata={"structured": {"answer": "yes"}}, reply_content='{"answer": "yes"}')
        await agent.arun("answer")
        self.assertTrue(agent.behavior.output.structured_field_equals("answer", "yes"))
        self.assertTrue(agent.behavior.output.is_valid_json())

    async def test_integration_output_code_block_after_run(self) -> None:
        # [Silent Failure] End-to-end: code block output is visible through output behavior.
        agent = MockAgent(reply_content="```python\nprint('x')\n```")
        await agent.arun("code")
        self.assertTrue(agent.behavior.output.contains_code_block("python"))

    async def test_integration_eval_runner_with_predicate(self) -> None:
        # [Hidden Assumption] EvalRunner + PredicateGrader: verify passed reflects predicate.
        calls = (make_call("search", state=ToolCallState.SUCCEEDED),)
        agent = MockAgent(reply_metadata={"tool_calls": calls, "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
        suite = EvalSuite("s", [EvalCase(prompt="t", grader=PredicateGrader(lambda p: p.tool_call_count > 0))])
        runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
        result = await runner.arun(suite)
        self.assertTrue(result.results[0].grader_result.passed)

    async def test_integration_eval_runner_with_structured_predicate(self) -> None:
        # [Hidden Failure] EvalRunner + PredicateGrader passes structured output through the probe.
        agent = MockAgent(reply_metadata={"structured": {"answer": "yes"}}, reply_content='{"answer": "yes"}')
        suite = EvalSuite("s", [EvalCase(prompt="t", grader=PredicateGrader(lambda p: p.structured is not None and p.output != ""))])
        runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
        result = await runner.arun(suite)
        self.assertTrue(result.results[0].grader_result.passed)

    async def test_integration_eval_runner_standard_grader(self) -> None:
        # [Hidden Failure] EvalRunner + ContainsGrader: standard agrade path unchanged.
        agent = MockAgent(reply_metadata={"tool_calls": ()})
        suite = EvalSuite("s", [EvalCase(prompt="t", expected="processed", grader=ContainsGrader())])
        runner = EvalRunner(agent, default_grader=ContainsGrader())
        result = await runner.arun(suite)
        self.assertTrue(result.results[0].grader_result.passed)

    async def test_integration_cache_invalidation(self) -> None:
        # [Silent Failure] Cache invalidation: run twice, verify behavior reflects second run.
        agent = MockAgent(reply_metadata={"tool_calls": (make_call("search"),), "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1})
        await agent.arun("first")
        self.assertTrue(agent.behavior.tool.called_tool("search"))
        agent._reply_metadata = {"tool_calls": (make_call("write"),), "stop_reason": "final_response", "tool_call_count": 1, "iteration_count": 1}
        agent._reply_content = "second output"
        await agent.arun("second")
        self.assertFalse(agent.behavior.tool.called_tool("search"))
        self.assertTrue(agent.behavior.tool.called_tool("write"))
        self.assertTrue(agent.behavior.output.starts_with("second"))


if __name__ == "__main__":
    unittest.main()
