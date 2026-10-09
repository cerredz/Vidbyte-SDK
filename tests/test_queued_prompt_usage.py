"""FILE: tests/test_queued_prompt_usage.py

PURPOSE: Regression tests that queued prompts drained after the primary run keep every run's usage on the agent's tracker.
ROLE IN CODEBASE: Guards BaseAgent._drain_queued_prompts, whose drained generate_reply calls reset the usage tracker and once left get_usage() reporting only the last drained run.
ARCHITECTURE NOTE: Offline scripted runner whose text responses report a priced model's token usage; each test compares recorded model calls with runner invocations.
COMMON MODIFICATION PATTERNS: Add a case here when the drain gains a new exit path that could drop a run's usage.
KNOWN EDGE CASES: A drained run that fails before its model call records nothing, so only the runs before it are counted.
RELATED DOCS: docs/design/queued-drain-keeps-usage.md.
TESTS: python -m pytest tests/test_queued_prompt_usage.py.
"""

from __future__ import annotations

import unittest
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.usage_ledger import usage_ledger_scope

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


if __name__ == "__main__":
    unittest.main()
