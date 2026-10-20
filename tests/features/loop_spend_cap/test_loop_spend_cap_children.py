"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_children.py

PURPOSE: Prove a child agent's spend lands on its capped parent's meter when the child's
reply finishes, so the parent's very next check point stops the run, and that two
capped children running at the same time each enforce their own cap against their own
ledger, not a shared one.
ROLE IN CODEBASE: Behavior tests for spec INV-12, AC-7 (sub-agent tool) and AC-15,
through the real AgentTool fork path and the real BaseAgent.generate_reply ledger
scope and merge.
ARCHITECTURE NOTE: Parent and children are offline BaseAgents with scripted runners;
the merge of a child's rollup into its parent happens in production code
(generate_reply's finally). The concurrent case uses a barrier runner: each child's
model call waits until its sibling's model call has started, so the two child runs
truly overlap without any sleep or clock.
FUNCTION INVENTORY: test_a_sub_agent_tool_that_spends_past_the_cap_stops_the_next_tool;
test_concurrent_capped_children_each_keep_their_own_cap_and_the_parent_stops_on_their_total.
COMMON MODIFICATION PATTERNS: A new way to run a child (bulk work, swarm, fork tool) adds
one case that puts the child between two parent check points and asserts the parent's
next check stops the run.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock the ledger merge or the ledger scope.
2. Do not run two replies on one agent object at once; that shared-tracker case is the
accepted limitation EC-35 and is not tested as fixed. 3. Do not hard-code dollars.
KNOWN EDGE CASES: as_tool() runs a fork of the wrapped agent, so the child here is an
OfflineTestAgent, whose fork keeps the scripted runner. A child counts toward its parent
only after its reply returns (INV-12).
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-6, INV-12, AC-7, AC-15;
tests/features/sdk_model_usage/test_nested_usage_bill.py (the merge it relies on).
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_children.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from tests.agent_test_support import OfflineTestAgent
from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    MAX_SPEND,
    REACHED_TEXT,
    LookupTool,
    ScriptedRunner,
    call_response,
    capped_settings,
    priced_agent,
    reference_cost,
    text_response,
    usage,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class BarrierRunner(ScriptedRunner):
    """A scripted runner whose call returns only once every runner sharing its barrier has been called."""

    def __init__(self, barrier: dict[str, Any], *responses: object) -> None:
        super().__init__(*responses)
        self.barrier = barrier

    async def arun(self, prompt: str, **options: Any) -> object:
        self.barrier["arrived"] += 1
        if self.barrier["arrived"] >= self.barrier["parties"]:
            self.barrier["event"].set()
        await self.barrier["event"].wait()
        return await super().arun(prompt, **options)


class FanOutTool(BaseTool):
    """Runs two separate child agents concurrently and returns both answers."""

    def __init__(self, *children: BaseAgent) -> None:
        self.children = children
        self.replies: list[Any] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(name="fan_out", description="Asks two helpers at once.")

    async def execute(self, call: ToolCall) -> ToolResult:
        self.replies = list(
            await asyncio.gather(
                *(child.arun("Help with Paris.") for child in self.children)
            )
        )
        return ToolResult.success(
            call.tool_name, " | ".join(str(reply.content) for reply in self.replies)
        )


def test_a_sub_agent_tool_that_spends_past_the_cap_stops_the_next_tool() -> None:
    # AC-7 and AC-15: the helper's spend reaches the parent's meter when its reply returns, so CP3 stops the lookup after it.
    helper_answer = text_response("Paris is the capital.", usage=usage(1_500, 200))
    helper_runner = ScriptedRunner(helper_answer)
    helper = priced_agent(
        helper_runner,
        name="helper",
        agent_type=OfflineTestAgent,
        agent_metadata=AgentMetadata(
            name="helper", description="Answers questions.", use_cases="facts"
        ),
    )
    parent_turn = call_response(
        ("helper", {}), ("lookup", {"q": "Paris"}), usage=usage(1_000, 100)
    )
    cap = reference_cost(parent_turn, helper_answer)
    lookup = LookupTool()
    parent_runner = ScriptedRunner(parent_turn)
    parent = priced_agent(
        parent_runner, tools=[helper.as_tool(), lookup], loop=capped_settings(cap)
    )

    reply = parent.run("Find the capital of France.")

    assert (reply.content, reply.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert (helper_runner.calls, parent_runner.calls, lookup.executed) == (1, 1, [])
    bill = parent.get_usage()
    assert bill.model_call_count == 2
    assert bill.cost_usd == cap
    assert [record.cost_usd for record in bill.calls][-1] == reference_cost(
        helper_answer
    )


def test_concurrent_capped_children_each_keep_their_own_cap_and_the_parent_stops_on_their_total() -> (
    None
):
    # INV-12 and EC-14: each child spends below its own cap, the two together exceed one child's cap, and both still
    # finish; the parent, capped at their sum plus its own call, stops at the check right after the fan-out.
    child_usage = usage(1_000, 100)
    child_cost = reference_cost(text_response("", usage=child_usage))
    child_cap = child_cost * 1.5
    barrier: dict[str, Any] = {"arrived": 0, "parties": 2, "event": asyncio.Event()}
    child_runners = [
        BarrierRunner(barrier, text_response(f"helper {index} done", usage=child_usage))
        for index in (1, 2)
    ]
    children = [
        priced_agent(runner, name=f"helper-{index}", loop=capped_settings(child_cap))
        for index, runner in enumerate(child_runners, start=1)
    ]
    parent_turn = call_response(
        ("fan_out", {}), ("lookup", {"q": "Paris"}), usage=usage(1_000, 100)
    )
    parent_cap = reference_cost(
        parent_turn,
        text_response("", usage=child_usage),
        text_response("", usage=child_usage),
    )
    fan_out, lookup = FanOutTool(*children), LookupTool()
    parent = priced_agent(
        ScriptedRunner(parent_turn),
        tools=[fan_out, lookup],
        loop=capped_settings(parent_cap),
    )

    reply = parent.run("Find the capital of France.")

    assert 2 * child_cost >= child_cap > child_cost
    assert [child_reply.metadata["stop_reason"] for child_reply in fan_out.replies] == [
        "final_response",
        "final_response",
    ]
    assert [child.get_usage().model_call_count for child in children] == [1, 1]
    assert (reply.content, reply.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert lookup.executed == []
    assert parent.get_usage().model_call_count == 3
    assert parent.get_usage().cost_usd == parent_cap
