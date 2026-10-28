"""FILE: tests/test_thinking_block_stale_prefix.py

PURPOSE:
    Proves that an agent which changes its top-level system prompt or its tool
    list mid-run never sends Anthropic a thinking block signed under the old
    prefix, so the request is accepted instead of failing with HTTP 400
    ("Invalid signature in thinking block. The block is bound to a different
    conversation. The `system` prompt differs" / "The `tools` list differs").
    It also proves the guard removes only what the docs allow: the stale block
    and every thinking block before it, never a block whose prefix is intact,
    never another block of the turn, and never a removed block put back.
ROLE IN CODEBASE:
    Regression tests for vidbyte/providers/anthropic_thinking.py, which
    AnthropicProvider runs on every request body it builds. The agent cases are
    the two live failures from the billing-readiness run (2026-10-28):
    InfiniteMemoryAgent re-renders its workspace map into `system` after a
    note is written, and JevAgent adds launch_swarm to `tools` once SWARM is
    selected.
ARCHITECTURE NOTE:
    Only HttpTransport.request is scripted. Each scripted reply opens with a
    thinking block whose signature names the request that produced it, so
    stale_replays() can compare every replayed block's prefix with the prefix
    it was signed under, as
    https://platform.claude.com/docs/en/build-with-claude/preserved-thinking
    defines the check: top-level system, tools, and the messages before the
    block, ignoring cache_control markers and earlier thinking blocks.
COMMON MODIFICATION PATTERNS:
    Add a case per agent shape that edits its prefix mid-run, and assert
    stale_replays() stays empty and kept_producers() keeps the intact blocks.
WHAT NOT TO DO:
    Do not reach the network or read keys from the environment. Do not reuse a
    signature across tests: the binding record is process-wide, so each wire
    signs with its own token.
KNOWN EDGE CASES:
    A block the process never saw signed (another process, an evicted record)
    is left in place, which is the behavior before this guard.
RELATED DOCS:
    docs/design/anthropic-stale-thinking-after-prefix-change.md;
    docs/design/thinking-block-replay-prefix.md (#1204, the loop-counter case).
TESTS:
    python -m pytest tests/test_thinking_block_stale_prefix.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_jev_compute_situations import REQUEST, ScriptedJev, lookup
from tests.test_jev_compute_swarm import _PLAN_CHECK, _RECOGNIZER, SWARM_KEYS, RoundsJev, _plan, _plan_helper, _recognizer_helper
from vidbyte import Agent, InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings, tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.swarm import JevSwarmAgent
from vidbyte.agents.jev.settings import JevRunBriefSettings
from vidbyte.lib.config import DecisionModelConfig, TextModelConfig, TextModelMode
from vidbyte.lib.dataclasses.jev import JevRunBriefAppendPayload
from vidbyte.lib.enums import DecisionModelMode, JevDynamicComputeOption
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.providers.anthropic import AnthropicProvider

KEY = "sk-ant-api03-fake"
SETTINGS = dict(provider="anthropic", model_name="claude-haiku-5-5", api_keys=[KEY], model_mode=TextModelMode.DIRECT)
THINKING = ("thinking", "redacted_thinking")


@tool
def double(x: int) -> int:
    """Double a number."""
    return x * 2


def _canonical(value: Any) -> Any:
    # The part of a request the API's prefix check reads: cache_control markers and earlier thinking blocks are not part of it.
    if isinstance(value, Mapping):
        return {key: _canonical(item) for key, item in value.items() if key != "cache_control"}
    if isinstance(value, list):
        return [_canonical(item) for item in value if not (isinstance(item, Mapping) and item.get("type") in THINKING)]
    return value


class ThinkingWire:
    """Answers like a thinking Claude model: each reply opens with a thinking block signed with this wire's token and the request number."""

    def __init__(self, steps: list[tuple[str, dict[str, Any]]]) -> None:
        # Each step calls one tool, in order, once that tool is offered; after the last step the model answers in text.
        self.steps = list(steps)
        self.token = uuid.uuid4().hex
        self.bodies: list[dict[str, Any]] = []

    async def request(self, *_: Any, json_body: Any = None, **__: Any) -> HttpResponse:
        body = json.loads(json.dumps(json_body))
        self.bodies.append(body)
        thinking = {"type": "thinking", "thinking": "", "signature": f"{self.token}-{len(self.bodies) - 1}"}
        offered = {schema.get("name") for schema in body.get("tools") or ()}
        if self.steps and self.steps[0][0] in offered:
            name, arguments = self.steps.pop(0)
            content, stop = [thinking, {"type": "tool_use", "id": f"toolu_{len(self.bodies)}", "name": name, "input": arguments}], "tool_use"
        else:
            content, stop = [thinking, {"type": "text", "text": "done"}], "end_turn"
        reply = {"id": f"msg_{len(self.bodies)}", "type": "message", "role": "assistant", "model": body["model"], "content": content, "stop_reason": stop, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return HttpResponse(status_code=200, body=json.dumps(reply), headers={"content-type": "application/json"})

    def replayed(self, later: int) -> Iterator[tuple[int, int]]:
        # Yields (message index, producing request) for every thinking block one request sends back.
        for message_index, turn in enumerate(self.bodies[later]["messages"]):
            for block in turn.get("content") if isinstance(turn.get("content"), list) else ():
                if isinstance(block, Mapping) and block.get("type") in THINKING and str(block.get("signature", "")).startswith(self.token):
                    yield message_index, int(str(block["signature"]).rsplit("-", 1)[-1])

    def stale_replays(self) -> list[str]:
        # Names every replayed block whose system, tools, or earlier messages differ from the request that signed it.
        stale = []
        for later, body in enumerate(self.bodies):
            for message_index, producer in self.replayed(later):
                signed = self.bodies[producer]
                for part, now, then in (("system", body.get("system"), signed.get("system")), ("tools", body.get("tools"), signed.get("tools")), ("messages", body["messages"][:message_index], signed["messages"])):
                    if _canonical(now) != _canonical(then):
                        stale.append(f"request {later} replays the block signed in request {producer}, but its {part} changed")
        return stale

    def kept_producers(self, later: int) -> list[int]:
        return [producer for _, producer in self.replayed(later)]

    def changed(self, part: str) -> list[int]:
        # The requests whose system or tools differ from the request before them.
        return [index for index in range(1, len(self.bodies)) if _canonical(self.bodies[index].get(part)) != _canonical(self.bodies[index - 1].get(part))]


def _wire(monkeypatch: pytest.MonkeyPatch, steps: list[tuple[str, dict[str, Any]]]) -> ThinkingWire:
    wire = ThinkingWire(steps)
    monkeypatch.setattr(HttpTransport, "request", wire.request)
    return wire


def test_infinite_memory_note_that_redraws_the_system_map_sends_no_stale_thinking(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # [Hidden Failure] Live req_011CgU1LDkwCbowyutVsxhbd: the note changes the workspace map in `system`, so call 2 was a 400.
    note = {"path": "billing/prepaid.md", "text": "Prepaid billing charges before use.", "description": "Prepaid billing basics."}
    wire = _wire(monkeypatch, [("write_note", note), ("read_lines", {"path": "billing/prepaid.md"})])
    (tmp_path / "project").mkdir()
    agent = InfiniteMemoryAgent(InfiniteMemoryAgentSettings(name="analyst", system_prompt="Research briefly.", root_dir=str(tmp_path / "project"), workspace=InfiniteWorkspaceSettings(root=str(tmp_path / "memory")), **SETTINGS))
    asyncio.run(agent.arun("Note one fact, then read it back."))

    assert len(wire.bodies) == 3
    assert wire.changed("system") == [1]
    assert wire.stale_replays() == []
    # The block signed after the change still replays, and the write's tool_use stays in its turn.
    assert wire.kept_producers(2) == [1]
    assert [block.get("type") for block in wire.bodies[1]["messages"][1]["content"]] == ["tool_use"]


def test_jev_swarm_tool_added_mid_run_sends_no_stale_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] Live req_011CgU1aZQX8bjZY3oo2pH7w: launch_swarm joins `tools` after the checkpoint, so the next call was a 400.
    steps = [("lookup", {"topic": f"t{index}"}) for index in range(3)] + [("launch_swarm", _plan("users", "orders")), ("isDone", {"final_answer": "done"})]
    wire = _wire(monkeypatch, steps)
    compute = JevComputeSettings(brief=JevRunBriefSettings(every_iterations=3), dynamic_compute=tuple(JevDynamicComputeOption), swarm_agents=4)
    runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=compute)
    agent = JevAgent(JevAgentSettings(name="researcher", system_prompt="Research.", tools=(lookup,), **SETTINGS), runtime)
    assert agent.compute is not None
    payload = JevRunBriefAppendPayload.model_validate({"notes": []})
    helper_replies = [SimpleNamespace(content=f"findings for {name}") for name in ("users", "orders")]
    with (
        patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=payload))),
        patch(_RECOGNIZER, new=_recognizer_helper(ScriptedJev({key: 0.95 for key in SWARM_KEYS}, default=0.1))),
        patch(_PLAN_CHECK, new=_plan_helper(RoundsJev())),
        patch.object(JevSwarmAgent, "arun", new=AsyncMock(side_effect=helper_replies)),
    ):
        asyncio.run(agent.arun(REQUEST))

    assert "launch_swarm" in {schema["name"] for schema in wire.bodies[3]["tools"]}
    assert 3 in wire.changed("tools")
    assert wire.stale_replays() == []
    # Blocks signed once launch_swarm was offered keep replaying.
    assert 3 in wire.kept_producers(len(wire.bodies) - 1)


def test_an_unchanged_prefix_keeps_every_thinking_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] The guard removes nothing from a loop whose prefix never changes: Claude keeps all of its reasoning.
    wire = _wire(monkeypatch, [("double", {"x": 2}), ("double", {"x": 4})])
    asyncio.run(Agent(name="parent", system_prompt="Lead.", max_iterations=4, tools=[double], **SETTINGS).arun("Do the task."))

    assert len(wire.bodies) == 3
    assert wire.kept_producers(1) == [0]
    assert wire.kept_producers(2) == [0, 1]
    assert wire.stale_replays() == []


def _assistant(signature: str, tool_id: str, *, kind: str = "thinking") -> dict[str, Any]:
    block = {"type": "thinking", "thinking": "", "signature": signature} if kind == "thinking" else {"type": "redacted_thinking", "data": signature}
    return {"role": "assistant", "content": [block, {"type": "text", "text": "Checking."}, {"type": "tool_use", "id": tool_id, "name": "double", "input": {"x": 1}}]}


def _result(tool_id: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "2"}]}


class ProviderWire:
    """Scripts AnthropicProvider directly: each call returns one thinking block with the given signature and records the body sent."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.next: dict[str, Any] = {}

    async def request(self, *_: Any, json_body: Any = None, **__: Any) -> HttpResponse:
        self.bodies.append(json.loads(json.dumps(json_body)))
        reply = {"id": "msg", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [self.next, {"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
        return HttpResponse(status_code=200, body=json.dumps(reply), headers={"content-type": "application/json"})

    def call(self, block: dict[str, Any], *, system: Any, tools: list[dict[str, Any]], messages: list[dict[str, Any]], prompt: str = "Go.") -> list[str]:
        # Sends one request and returns the thinking signatures (or redacted data) it carried, in order.
        self.next = block
        config = TextModelConfig(provider="anthropic", model="claude-haiku-5-5", api_keys=[KEY], tools=tuple(tools), messages=tuple(messages))
        asyncio.run(AnthropicProvider().run_text(prompt=prompt, system=system, metadata=None, transport=self, config=config))  # type: ignore[arg-type]
        sent = self.bodies[-1]["messages"]
        return [str(block.get("signature") or block.get("data")) for turn in sent for block in (turn["content"] if isinstance(turn["content"], list) else ()) if block.get("type") in THINKING]


TOOL_A = {"name": "double", "description": "Double.", "input_schema": {"type": "object", "properties": {"x": {"type": "integer"}}}}
TOOL_B = {"name": "halve", "description": "Halve.", "input_schema": {"type": "object", "properties": {"x": {"type": "integer"}}}}


def _thinking(signature: str) -> dict[str, Any]:
    return {"type": "thinking", "thinking": "", "signature": signature}


def test_a_system_change_removes_the_stale_block_and_never_puts_it_back() -> None:
    # [Hidden Assumption] The stale block goes with its turn's other blocks left in place, and a removed block never returns.
    token = uuid.uuid4().hex
    wire = ProviderWire()
    first, second = f"{token}-1", f"{token}-2"
    # Request 1 under system S1 signs the first block.
    wire.call(_thinking(first), system="S1", tools=[TOOL_A], messages=[])
    history = [_assistant(first, "t1"), _result("t1")]
    # Request 2 under S2: the first block is stale, so it goes; its text and tool_use stay. This request signs the second block.
    assert wire.call(_thinking(second), system="S2", tools=[TOOL_A], messages=history) == []
    assert [block["type"] for block in wire.bodies[-1]["messages"][1]["content"]] == ["text", "tool_use"]
    history += [_assistant(second, "t2"), _result("t2")]
    # Request 3, still S2: the second block is intact and kept; the first stays out.
    assert wire.call(_thinking(f"{token}-3"), system="S2", tools=[TOOL_A], messages=history) == [second]
    # Request 4 back on S1: the first block's own prefix matches again, but it was removed, so it stays out; the second is now stale.
    assert wire.call(_thinking(f"{token}-4"), system="S1", tools=[TOOL_A], messages=history) == []


def test_cache_control_markers_are_not_a_prefix_change() -> None:
    # [Hidden Assumption] The API ignores cache_control in its prefix check, so adding a marker must not cost Claude its reasoning.
    token = uuid.uuid4().hex
    wire = ProviderWire()
    wire.call(_thinking(f"{token}-1"), system=[{"type": "text", "text": "S"}], tools=[TOOL_A], messages=[])
    history = [_assistant(f"{token}-1", "t1"), _result("t1")]
    marked_tool = {**TOOL_A, "cache_control": {"type": "ephemeral"}}
    assert wire.call(_thinking(f"{token}-2"), system=[{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}], tools=[marked_tool], messages=history) == [f"{token}-1"]


def test_a_tool_change_removes_redacted_thinking_and_leaves_unknown_blocks() -> None:
    # [Hidden Failure] redacted_thinking is bound like thinking; a block this process never saw signed is left as before.
    token = uuid.uuid4().hex
    wire = ProviderWire()
    wire.call({"type": "redacted_thinking", "data": f"{token}-r1"}, system="S", tools=[TOOL_A], messages=[])
    history = [_assistant(f"{token}-r1", "t1", kind="redacted"), _result("t1")]
    assert wire.call(_thinking(f"{token}-2"), system="S", tools=[TOOL_A], messages=history) == [f"{token}-r1"]
    assert wire.call(_thinking(f"{token}-3"), system="S", tools=[TOOL_A, TOOL_B], messages=history) == []
    foreign = [_assistant(f"{token}-unseen", "t9"), _result("t9")]
    assert wire.call(_thinking(f"{token}-4"), system="S", tools=[TOOL_A, TOOL_B], messages=foreign) == [f"{token}-unseen"]


def test_an_edited_earlier_message_removes_only_the_thinking_signed_after_it() -> None:
    # [Hidden Failure] Rewriting an old tool result invalidates every later thinking block; the earlier intact block keeps its reasoning.
    token = uuid.uuid4().hex
    wire = ProviderWire()
    wire.call(_thinking(f"{token}-1"), system="S", tools=[TOOL_A], messages=[])
    history = [_assistant(f"{token}-1", "t1"), _result("t1")]
    wire.call(_thinking(f"{token}-2"), system="S", tools=[TOOL_A], messages=history)
    history += [_assistant(f"{token}-2", "t2"), _result("t2")]
    assert wire.call(_thinking(f"{token}-3"), system="S", tools=[TOOL_A], messages=history) == [f"{token}-1", f"{token}-2"]
    edited = [history[0], {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "[cleared]"}]}, *history[2:]]
    assert wire.call(_thinking(f"{token}-4"), system="S", tools=[TOOL_A], messages=edited) == [f"{token}-1"]
    # The block signed while the second was gone follows the first: the kept run has no gap, so both replay.
    edited += [_assistant(f"{token}-4", "t4"), _result("t4")]
    assert wire.call(_thinking(f"{token}-5"), system="S", tools=[TOOL_A], messages=edited) == [f"{token}-1", f"{token}-4"]
