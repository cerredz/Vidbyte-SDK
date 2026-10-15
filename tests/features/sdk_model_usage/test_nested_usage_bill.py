"""FILE: tests/features/sdk_model_usage/test_nested_usage_bill.py

PURPOSE: Prove a plain top-level agent's bill holds every model call its run causes, including sub-agent tools and its continual-trace agent, each exactly once.
ROLE IN CODEBASE: Exercises the top-level ledger scope in BaseAgent.generate_reply, AgentTool's forked sub-agent run, and ContinualTraceAgent through vidbyte/lib/usage_ledger.py.
ARCHITECTURE NOTE: A scripted HttpTransport.request answers every DeepSeek chat call and counts it at the wire; agents, runtime, tools, tracing and pricing stay production code.
FUNCTION INVENTORY: test_sub_agent_tool_calls_reach_the_top_level_bill, test_continual_trace_calls_reach_the_top_level_bill, test_two_levels_of_sub_agents_bill_every_call_once.
COMMON MODIFICATION PATTERNS: A new nested-agent feature adds one case here comparing wire calls with the top-level rollup.
WHAT NOT TO DO IN THIS FILE: 1. Do not reach the network; the transport is scripted. 2. Do not hard-code tariff rates; the pricebook owns them.
KNOWN EDGE CASES: as_tool() runs a fork of the wrapped agent, so the sub-agent's own usage is read from the recorded fork.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md documents this accounting contract.
TESTS: This module and scripts/run_ci.py source gate.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

import pytest
from pydantic import BaseModel, Field

from vidbyte import Agent
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentMetadata
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.http import HttpResponse, HttpTransport

USAGE = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}


def _kw() -> dict[str, Any]:
    # Every agent here talks to DeepSeek directly with a fake key, so the scripted wire sees vendor chat calls.
    return {"provider": "deepseek", "model_name": "deepseek-v4-flash", "api_keys": ["d-mock"], "model_mode": TextModelMode.DIRECT}


class Notes(BaseModel):
    summary: str = Field(description="What happened so far.")


class _ForkRecordingAgent(Agent):
    """Records every fork, so the sub-agent run that as_tool() makes can be inspected."""

    forks: list[BaseAgent] = []

    def fork(self, settings: AgentForkSettings | None = None) -> BaseAgent:
        child = super().fork(settings)
        _ForkRecordingAgent.forks.append(child)
        return child


class _Wire:
    """Answers DeepSeek chat calls from the request alone and counts every call."""

    def __init__(self) -> None:
        self.calls = 0
        self._ids = itertools.count(1)

    async def __call__(self, *, json_body: dict[str, Any] | None = None, **_: Any) -> HttpResponse:
        # Stands in for HttpTransport.request; a callable instance is not a descriptor, so no transport argument arrives.
        self.calls += 1
        message = self._reply(json_body or {})
        body = {"id": f"c{next(self._ids)}", "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": USAGE}
        return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})

    def _reply(self, body: dict[str, Any]) -> dict[str, Any]:
        # Trace agents answer with a trace, leaf helpers answer, and any agent with an unused agent tool calls it once.
        blob = json.dumps(body)
        if "<trace_schema>" in blob:
            return {"role": "assistant", "content": json.dumps({"summary": "s"})}
        names = [tool["function"]["name"] for tool in body.get("tools", [])]
        answered = any(message.get("role") == "tool" for message in body.get("messages", []))
        for name in ("researcher", "helper"):
            if name in names and not answered:
                call = {"id": f"call_{next(self._ids)}", "type": "function", "function": {"name": name, "arguments": json.dumps({"message": "go"})}}
                return {"role": "assistant", "content": None, "tool_calls": [call]}
        return {"role": "assistant", "content": "final 42"}


def _agent(name: str, tools: list[object] | None = None, trace: bool = False) -> _ForkRecordingAgent:
    meta = AgentMetadata(name=name, description=f"The {name} agent.", use_cases=f"{name} work")
    option = TraceOption.continual(Notes, every_n_iterations=1) if trace else None
    return _ForkRecordingAgent(name=name, system_prompt=f"You are {name}.", agent_metadata=meta, tools=tools or [], max_iterations=4, trace_option=option, **_kw())


def _run(monkeypatch: pytest.MonkeyPatch, top: BaseAgent) -> _Wire:
    wire = _Wire()
    _ForkRecordingAgent.forks.clear()
    monkeypatch.setattr(HttpTransport, "request", wire)
    reply = asyncio.run(top.arun("find the answer"))
    assert "final 42" in str(reply.content)
    return wire


def test_sub_agent_tool_calls_reach_the_top_level_bill(monkeypatch: pytest.MonkeyPatch) -> None:
    # The top-level agent pays for its own two calls and the helper's one call; the helper's own usage stays its own.
    top = _agent("researcher", [_agent("helper").as_tool()])
    wire = _run(monkeypatch, top)
    rollup = top.get_usage()
    (helper_run,) = _ForkRecordingAgent.forks

    assert wire.calls == 3
    assert (rollup.model_call_count, rollup.input_tokens, rollup.unaccounted_call_count) == (3, 300, 0)
    assert helper_run.get_usage().model_call_count == 1
    assert rollup.cost_usd is not None and rollup.cost_usd > 0
    assert rollup.cost_usd == pytest.approx(sum(call.cost_usd for call in rollup.calls))
    assert rollup.cost_usd == pytest.approx(3 * helper_run.get_cost_usd())
    assert top.get_cost_usd() == pytest.approx(rollup.cost_usd)


def test_continual_trace_calls_reach_the_top_level_bill(monkeypatch: pytest.MonkeyPatch) -> None:
    # Trace-agent calls are billed by the provider, so they belong on the agent's own bill.
    top = _agent("researcher", trace=True)
    wire = _run(monkeypatch, top)
    rollup = top.get_usage()

    assert wire.calls > 1
    assert (rollup.model_call_count, rollup.input_tokens) == (wire.calls, 100 * wire.calls)


def test_two_levels_of_sub_agents_bill_every_call_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # boss -> researcher-as-tool -> helper-as-tool: each level merges its run into its parent exactly once.
    researcher = _agent("researcher", [_agent("helper").as_tool()])
    boss = Agent(name="boss", system_prompt="You are boss.", tools=[researcher.as_tool()], max_iterations=4, **_kw())
    wire = _run(monkeypatch, boss)
    rollup = boss.get_usage()
    researcher_run, helper_run = _ForkRecordingAgent.forks

    assert wire.calls == 5
    assert (rollup.model_call_count, rollup.input_tokens) == (5, 500)
    assert (researcher_run.get_usage().model_call_count, helper_run.get_usage().model_call_count) == (3, 1)
    assert rollup.cost_usd == pytest.approx(sum(call.cost_usd for call in rollup.calls))
