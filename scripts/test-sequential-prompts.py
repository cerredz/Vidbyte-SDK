"""Verification script for the run_sequentially / arun_sequentially feature."""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure the worktree root (parent of scripts/) is on sys.path before any vidbyte import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any

from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.lib.errors import AgentExecutionError


# ---------------------------------------------------------------------------
# Minimal fakes (no external deps)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class _EchoRunner:
    """Returns the prompt text in the final_answer field."""
    def __init__(self) -> None:
        self.call_count = 0

    def run(self, prompt: str, **_: Any) -> object:
        self.call_count += 1
        return _FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone",
                         "arguments": f'{{"final_answer": "echo:{prompt}"}}'}]},
        )


class _FailOnSecondRunner:
    def __init__(self) -> None:
        self.call_count = 0

    def run(self, prompt: str, **_: Any) -> object:
        self.call_count += 1
        if self.call_count >= 2:
            raise RuntimeError("injected failure")
        return _FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone",
                         "arguments": f'{{"final_answer": "ok:{prompt}"}}'}]},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent(**kw: Any) -> BaseAgent:
    return BaseAgent(name="tester", system_prompt="Test.", **kw)


passed = 0
failed = 0


def _result(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    if ok:
        passed += 1
    else:
        failed += 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def run_tests() -> None:
    print("\nrunning sequential-prompts verification\n")

    # 1. Three prompts → three replies in order
    agent = _agent(runner=_EchoRunner())
    replies = await agent.arun_sequentially(["a", "b", "c"])
    _result(
        "arun_sequentially returns 3 replies",
        len(replies) == 3
        and "echo:a" in replies[0].content
        and "echo:b" in replies[1].content
        and "echo:c" in replies[2].content,
    )

    # 2. Empty list → []
    runner = _EchoRunner()
    agent = _agent(runner=runner)
    replies = await agent.arun_sequentially([])
    _result(
        "empty list returns []",
        replies == [] and runner.call_count == 0 and len(agent.history) == 0,
    )

    # 3. Single-element list
    agent = _agent(runner=_EchoRunner())
    replies = await agent.arun_sequentially(["only"])
    _result(
        "single prompt works",
        len(replies) == 1 and "echo:only" in replies[0].content,
    )

    # 4. History grows exactly N entries (one per prompt)
    agent = _agent(runner=_EchoRunner())
    await agent.arun_sequentially(["p1", "p2", "p3"])
    _result(
        "history accumulates N entries",
        len(agent.history) == 3,
    )

    # 5. Context accumulates: second prompt sees first reply in history
    agent = _agent(runner=_EchoRunner())
    replies = await agent.arun_sequentially(["first", "second"])
    _result(
        "history entries match reply order",
        agent.history[0].content == replies[0].content
        and agent.history[1].content == replies[1].content,
    )

    # 6. run_sequentially raises in active event loop
    agent = _agent(runner=_EchoRunner())
    caught = False
    try:
        agent.run_sequentially(["prompt"])
    except AgentExecutionError:
        caught = True
    _result("run_sequentially raises AgentExecutionError in active loop", caught)

    # 7. Stops on first failure; only N-1 replies committed to history
    runner = _FailOnSecondRunner()
    agent = _agent(runner=runner)
    caught_exc = False
    try:
        await agent.arun_sequentially(["ok", "fail", "never"])
    except AgentExecutionError:
        caught_exc = True
    _result(
        "stops on failure and propagates error",
        caught_exc and runner.call_count == 2 and len(agent.history) == 1,
    )

    # 8. Accepts AgentInput objects
    agent = _agent(runner=_EchoRunner())
    inp = AgentInput(prompt="from-input")
    replies = await agent.arun_sequentially([inp])
    _result(
        "accepts AgentInput objects",
        len(replies) == 1 and "echo:from-input" in replies[0].content,
    )

    # 9. Mixed list (str + AgentInput)
    agent = _agent(runner=_EchoRunner())
    replies = await agent.arun_sequentially(["str-prompt", AgentInput(prompt="inp-prompt")])
    _result(
        "mixed str and AgentInput list",
        len(replies) == 2
        and "echo:str-prompt" in replies[0].content
        and "echo:inp-prompt" in replies[1].content,
    )

    # 10. history is NOT reset between calls (two separate sequential batches)
    agent = _agent(runner=_EchoRunner())
    await agent.arun_sequentially(["batch1-a", "batch1-b"])
    await agent.arun_sequentially(["batch2-a"])
    _result(
        "history persists across multiple arun_sequentially calls",
        len(agent.history) == 3,
    )

    print(f"\n{passed}/{passed + failed} tests passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
