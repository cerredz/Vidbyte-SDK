"""FILE: tests/test_thinking_block_replay_prefix.py

PURPOSE:
    Proves that every thinking block an agent sends back to Anthropic keeps the
    prefix it was signed with: the same top-level system prompt, the same tools,
    and the same messages before it. On Claude Fable 5.1, Opus 5.5, Sonnet 5.5
    and Haiku 5.5, a changed prefix fails the request with HTTP 400 ("Invalid
    signature in thinking block. The block is bound to a different
    conversation.") on accounts created on or after 2026-08-31.
ROLE IN CODEBASE:
    Regression tests for the request the runtime builds each loop iteration
    (vidbyte/agents/runtime.py _build_iteration_call_options) as the Anthropic
    adapter sends it.
ARCHITECTURE NOTE:
    Only HttpTransport.request is scripted. Each scripted reply carries a
    thinking block with a unique signature, so the test can find the request
    that produced every replayed block and compare the two prefixes, exactly as
    https://platform.claude.com/docs/en/build-with-claude/preserved-thinking
    defines the check.
WHAT NOT TO DO:
    Do not relax the comparison to "close enough": the API compares the prefix
    exactly. Do not reach the network or read keys from the environment.
TESTS:
    python -m pytest tests/test_thinking_block_replay_prefix.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from vidbyte import Agent, tool
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.http import HttpResponse, HttpTransport

SETTINGS = dict(provider="anthropic", model_name="claude-haiku-5-5", api_keys=["sk-ant-api03-fake"], model_mode=TextModelMode.DIRECT)


@tool
def double(x: int) -> int:
    """Double a number."""
    return x * 2


class ThinkingTransport:
    """Answers like a thinking Claude model: every reply opens with a thinking block whose signature names the request."""

    def __init__(self, tool_rounds: int) -> None:
        self.tool_rounds = tool_rounds
        self.bodies: list[dict[str, Any]] = []

    async def request(self, *_: Any, json_body: Any = None, **__: Any) -> HttpResponse:
        # Calls the first tool until the run has the scripted number of tool results, then answers.
        body = json.loads(json.dumps(json_body))
        self.bodies.append(body)
        thinking = {"type": "thinking", "thinking": "", "signature": f"request-{len(self.bodies) - 1}"}
        results = sum(1 for turn in body["messages"] if isinstance(turn.get("content"), list) and any(block.get("type") == "tool_result" for block in turn["content"]))
        if body.get("tools") and results < self.tool_rounds:
            name = body["tools"][0]["name"]
            arguments = {"message": "Help with this."} if name != "double" else {"x": 2}
            content = [thinking, {"type": "tool_use", "id": f"toolu_{len(self.bodies)}", "name": name, "input": arguments}]
            stop = "tool_use"
        else:
            content, stop = [thinking, {"type": "text", "text": "Done."}], "end_turn"
        reply = {"id": f"msg_{len(self.bodies)}", "type": "message", "role": "assistant", "model": body["model"], "content": content, "stop_reason": stop, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return HttpResponse(status_code=200, body=json.dumps(reply), headers={"content-type": "application/json"})

    def replayed_blocks(self) -> Iterator[tuple[int, int, int, int]]:
        # Yields (later request, message index, block index, producing request) for every thinking block sent back.
        for later, body in enumerate(self.bodies):
            for message_index, turn in enumerate(body["messages"]):
                for block_index, block in enumerate(turn.get("content") if isinstance(turn.get("content"), list) else ()):
                    if isinstance(block, Mapping) and block.get("type") in ("thinking", "redacted_thinking"):
                        yield later, message_index, block_index, int(str(block["signature"]).rsplit("-", 1)[-1])

    def prefix_changes(self) -> list[str]:
        # Names every part of a replayed block's prefix that differs from the request that produced the block.
        changes = []
        for later, message_index, block_index, producer in self.replayed_blocks():
            sent, signed = self.bodies[later], self.bodies[producer]
            where = f"request {later} messages.{message_index}.content.{block_index} (signed in request {producer})"
            for part, now, then in (("system", sent.get("system"), signed.get("system")), ("tools", sent.get("tools"), signed.get("tools")), ("messages before the block", sent["messages"][:message_index], signed["messages"][:message_index])):
                if now != then:
                    changes.append(f"{where}: {part} changed")
        return changes


def _run(monkeypatch: pytest.MonkeyPatch, agent: Agent, tool_rounds: int) -> ThinkingTransport:
    # Runs the agent once against the scripted thinking model.
    transport = ThinkingTransport(tool_rounds)
    monkeypatch.setattr(HttpTransport, "request", transport.request)
    asyncio.run(agent.arun("Do the task."))
    return transport


def test_plain_multi_iteration_run_replays_thinking_with_an_unchanged_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] Two tool rounds, three model calls: blocks from calls 1 and 2 are replayed later.
    transport = _run(monkeypatch, Agent(name="parent", system_prompt="Lead.", max_iterations=4, tools=[double], **SETTINGS), tool_rounds=2)
    assert len(list(transport.replayed_blocks())) >= 3
    assert transport.prefix_changes() == []


def test_sub_agent_tool_run_replays_thinking_with_an_unchanged_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] The live failure: the parent's second call after a helper.as_tool() call.
    helper = Agent(name="helper", system_prompt="Help.", max_iterations=2, agent_metadata=AgentMetadata(name="helper", description="Helps.", use_cases="help"), **SETTINGS)
    transport = _run(monkeypatch, Agent(name="parent", system_prompt="Lead.", max_iterations=4, tools=[helper.as_tool()], **SETTINGS), tool_rounds=1)
    parent_requests = [index for index, body in enumerate(transport.bodies) if "Lead." in str(body.get("system"))]
    assert len(parent_requests) == 2
    assert [later for later, *_ in transport.replayed_blocks()] == [parent_requests[1]]
    assert transport.prefix_changes() == []


def test_sub_agent_thinking_never_reaches_the_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] A helper's blocks were signed in the helper's conversation, so the parent must never send them.
    helper = Agent(name="helper", system_prompt="Help.", max_iterations=2, agent_metadata=AgentMetadata(name="helper", description="Helps.", use_cases="help"), **SETTINGS)
    transport = _run(monkeypatch, Agent(name="parent", system_prompt="Lead.", max_iterations=4, tools=[helper.as_tool()], **SETTINGS), tool_rounds=1)
    helper_requests = {index for index, body in enumerate(transport.bodies) if "Help." in str(body.get("system"))}
    assert helper_requests
    assert [producer for later, _, _, producer in transport.replayed_blocks() if later not in helper_requests and producer in helper_requests] == []
