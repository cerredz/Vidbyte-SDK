"""FILE: tests/test_queued_prompt_usage.py

PURPOSE: Regression tests that queued prompts drained after the primary run keep every run's usage on the agent's tracker, and that a failed or cancelled run leaves the queue empty.
ROLE IN CODEBASE: Guards BaseAgent._drain_queued_prompts, whose drained generate_reply calls reset the usage tracker and once left get_usage() reporting only the last drained run, and BaseAgent._close_failed_reply, which once left queued prompts for the next unrelated run.
ARCHITECTURE NOTE: Offline scripted runners; the usage tests report a priced model's token usage, the cleanup tests drive the real run_prompts_sequentially tool through function-call responses.
COMMON MODIFICATION PATTERNS: Add a case here when the drain gains a new exit path that could drop a run's usage or leave prompts queued.
KNOWN EDGE CASES: A drained run that fails before its model call records nothing, so only the runs before it are counted. A cancellation during the automatic handoff, after the primary run succeeded, must also clear the queue.
RELATED DOCS: docs/design/queued-drain-keeps-usage.md, docs/design/queued-prompts-cleared-on-failure.md, docs/design/queued-prompts-cleared-on-handoff-cancel.md.
TESTS: python -m pytest tests/test_queued_prompt_usage.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Callable
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.agents.pricing import UsageTracker
from vidbyte.context.handoff import MinimalHandoff
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.usage_ledger import usage_ledger_scope
from vidbyte.tools.builtins.run_prompts_sequentially import RunPromptsSequentiallyTool

_PRICED_MODEL = "gpt-5.4-mini"


class ScriptedRunner:
    """Returns one priced text response per call and fails on the call numbers it is told to."""

    def __init__(self, *, fail_on: tuple[int, ...] = ()) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model=_PRICED_MODEL, text="done", raw={}, usage={"input_tokens": 100, "output_tokens": 20})
        self.fail_on = fail_on
        self.calls = 0

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("scripted model failure")
        return self.response


def _single_run_cost() -> float:
    tracker = UsageTracker()
    tracker.record_call(ScriptedRunner().response)
    cost = tracker.rollup().cost_usd
    assert cost is not None
    return cost


class QueuedPromptUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_covers_primary_and_every_drained_run(self) -> None:
        runner = ScriptedRunner()
        agent = build_test_agent(runner=runner, name="queued", system_prompt="Answer briefly.")
        agent.enqueue_prompts(["first follow-up", "second follow-up"])
        reply = await agent.arun("primary")
        usage = agent.get_usage()
        self.assertEqual(reply.metadata["queued_prompt_runs"], 2)
        self.assertEqual(runner.calls, 3)
        self.assertEqual(usage.model_call_count, 3)
        self.assertEqual((usage.input_tokens, usage.output_tokens), (300, 60))
        self.assertEqual([record.call_index for record in usage.calls], [1, 2, 3])
        self.assertTrue(usage.cost_complete)
        self.assertAlmostEqual(agent.get_cost_usd(), 3 * _single_run_cost())

    async def test_failed_drained_run_keeps_earlier_usage(self) -> None:
        runner = ScriptedRunner(fail_on=(3,))
        agent = build_test_agent(runner=runner, name="queued", system_prompt="Answer briefly.")
        agent.enqueue_prompts(["first follow-up", "failing follow-up"])
        reply = await agent.arun("primary")
        self.assertIn("queued_prompt_error", reply.metadata)
        self.assertEqual(agent.get_usage().model_call_count, 2)

    async def test_parent_ledger_receives_every_drained_run(self) -> None:
        runner = ScriptedRunner()
        agent = build_test_agent(runner=runner, name="queued", system_prompt="Answer briefly.")
        agent.enqueue_prompts(["first follow-up", "second follow-up"])
        parent = UsageTracker()
        with usage_ledger_scope(parent):
            await agent.arun("primary")
        self.assertEqual(parent.rollup().model_call_count, 3)
        self.assertEqual(agent.get_usage().model_call_count, 3)


_FOLLOWUPS = ["FOLLOWUP-1 email the CFO", "FOLLOWUP-2 post to #general"]


class _FunctionCallResponse:
    """Minimal runner response carrying one model function call."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.text = ""
        self.raw = {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments)}]}


def _queue_followups(prompt: str) -> _FunctionCallResponse:
    return _FunctionCallResponse("run_prompts_sequentially", {"prompts": _FOLLOWUPS})


def _finish(prompt: str) -> _FunctionCallResponse:
    return _FunctionCallResponse("isDone", {"final_answer": "done"})


def _fail(prompt: str) -> _FunctionCallResponse:
    raise RuntimeError("HTTP 400 from the model provider")


class StepRunner:
    """Async runner that plays one scripted step per model call, then finishes every later call."""

    def __init__(self, steps: list[Callable[[str], Any]]) -> None:
        self.steps = list(steps)
        self.prompts: list[str] = []
        self.hang = asyncio.Event()

    async def arun(self, prompt: str, **_: object) -> _FunctionCallResponse:
        self.prompts.append(prompt)
        step = self.steps.pop(0) if self.steps else _finish
        if step is None:
            # Simulates a model call still in flight when the caller's timeout cancels the run.
            await self.hang.wait()
        return step(prompt)


class QueuedPromptFailureCleanupTests(unittest.IsolatedAsyncioTestCase):
    # @intent failed-run-leaves-no-queued-prompts
    # Prompts queued by a run that fails or is cancelled must not run after the next unrelated request.

    def _agent(self, runner: StepRunner) -> Any:
        return build_test_agent(runner=runner, name="queued", system_prompt="Answer briefly.", tools=[RunPromptsSequentiallyTool()])

    async def _assert_next_run_is_clean(self, agent: Any, runner: StepRunner) -> None:
        calls_before = len(runner.prompts)
        reply = await agent.arun("hello")
        self.assertNotIn("queued_prompt_runs", reply.metadata)
        self.assertEqual(len(runner.prompts) - calls_before, 1)
        self.assertEqual(agent._queued_prompts, [])

    async def test_failed_primary_run_clears_queue(self) -> None:
        runner = StepRunner([_queue_followups, _fail])
        agent = self._agent(runner)
        with self.assertRaises(AgentExecutionError):
            await agent.arun("plan the launch")
        self.assertEqual(agent._queued_prompts, [])
        await self._assert_next_run_is_clean(agent, runner)

    async def test_cancelled_primary_run_clears_queue(self) -> None:
        runner = StepRunner([_queue_followups, None])
        agent = self._agent(runner)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(agent.arun("plan the launch"), timeout=0.2)
        self.assertEqual(agent._queued_prompts, [])
        await self._assert_next_run_is_clean(agent, runner)

    async def test_cancelled_drained_run_clears_queue(self) -> None:
        runner = StepRunner([_queue_followups, _finish, None])
        agent = self._agent(runner)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(agent.arun("plan the launch"), timeout=0.2)
        self.assertEqual(agent._queued_prompts, [])
        await self._assert_next_run_is_clean(agent, runner)

    async def test_failed_drained_run_still_reports_error_on_primary_reply(self) -> None:
        runner = StepRunner([_queue_followups, _finish, _fail])
        agent = self._agent(runner)
        reply = await agent.arun("plan the launch")
        self.assertIn("queued_prompt_error", reply.metadata)
        self.assertEqual(agent._queued_prompts, [])
        await self._assert_next_run_is_clean(agent, runner)

    async def test_cancelled_auto_handoff_clears_queue(self) -> None:
        # The primary run succeeds, then the caller's timeout cancels the automatic handoff before the drain starts.
        runner = StepRunner([_queue_followups, _finish, None])
        agent = build_test_agent(
            runner=runner, name="queued", system_prompt="Answer briefly.", tools=[RunPromptsSequentiallyTool()], handoff=MinimalHandoff()
        )
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(agent.arun("ship v3"), timeout=0.2)
        self.assertEqual(agent._queued_prompts, [])
        calls_before = len(runner.prompts)
        reply = await agent.arun("hello")
        self.assertNotIn("queued_prompt_runs", reply.metadata)
        # A drained follow-up would reach the model as its own task prompt; only "hello" and its handoff may.
        self.assertEqual(runner.prompts[calls_before], "hello")
        self.assertFalse(any(prompt.startswith("FOLLOWUP") for prompt in runner.prompts[calls_before:]))
        self.assertEqual(agent._queued_prompts, [])


if __name__ == "__main__":
    unittest.main()
