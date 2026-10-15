"""FILE: tests/test_tool_error_policy_retry_budget.py

PURPOSE: Prove that ToolErrorPolicy(max_retries_per_tool_call=N) gives every separate tool call its own N silent retries, even when two calls in one run share a call id or carry none.
ROLE IN CODEBASE: Drives BaseAgent end to end with an offline scripted runner so ToolErrorPolicyMiddleware, the runtime retry loop, and the model-visible tool results are exercised together; complements the hook-level tests in tests/test_new_middleware_builtins.py.
ARCHITECTURE NOTE: The runner is bound through tests/agent_test_support.py, so no provider or network call is made; the tool fails with kind "timeout" on the first attempt of each call and succeeds on the retry.
FUNCTION INVENTORY: test_reused_call_id_gets_a_fresh_budget_each_turn covers servers that number ids per response; test_id_less_identical_calls_each_get_a_retry covers Gemini-style calls with no id and identical arguments; test_single_call_retries_at_most_the_budget is the control that one call still runs at most N+1 times. Run this file with pytest.
COMMON MODIFICATION PATTERNS: Add a case when a new call-identity shape reaches the middleware; keep the tool deterministic and the runner scripted.
WHAT NOT TO DO IN THIS FILE: 1. Do not implement retry policy here; vidbyte/middleware/builtins/tool_error_policy.py owns it. 2. Do not call live providers.
KNOWN EDGE CASES: The retried failure is hidden from the model, so the only model-visible evidence is the final tool results.
RELATED DOCS: vidbyte/middleware/builtins/tool_error_policy.py intent retry-budget-is-per-call.
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import json
import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentLoopSettings, ToolErrorPolicy
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec

_RATE_TEXT = "EUR/CHF = 1.5"


class _FirstAttemptTimesOutRate(BaseTool):
    """Read-only rate lookup that times out on the first attempt of each call and answers on the retry."""

    def __init__(self, *, always_fail: bool = False) -> None:
        self.executions = 0
        self.always_fail = always_fail

    def spec(self) -> ToolSpec:
        return ToolSpec(name="rate", description="Return the EUR rate for a currency.", permission=ToolPermission.READ)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executions += 1
        if self.always_fail or self.executions % 2 == 1:
            return ToolResult.error("rate", "rate service timed out", metadata={"error": "timeout"})
        return ToolResult.success("rate", _RATE_TEXT)


class _ScriptedRateRunner:
    """Offline model that asks for the CHF rate on each scripted turn, then finishes, recording what it was shown."""

    def __init__(self, call_ids: list[str | None]) -> None:
        self.call_ids = list(call_ids)
        self.seen_messages: list[object] = []

    async def arun(self, prompt: str, **kwargs: object) -> object:
        # Emit one rate call per scripted turn (with the scripted id, or none), then isDone.
        self.seen_messages = list(kwargs.get("messages") or [])

        class _Resp:
            text = ""
            raw: dict = {}

        response = _Resp()
        if not self.call_ids:
            response.raw = {"output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": "done"})}]}
            return response
        call: dict[str, object] = {"type": "function_call", "name": "rate", "arguments": json.dumps({"currency": "CHF"})}
        call_id = self.call_ids.pop(0)
        if call_id is not None:
            call["call_id"] = call_id
        response.raw = {"output": [call]}
        return response


def _policy(max_retries: int) -> AgentLoopSettings:
    return AgentLoopSettings(
        max_iterations=8,
        tool_error_policy=ToolErrorPolicy(max_retries_per_tool_call=max_retries, retry_backoff_base_seconds=0, retry_backoff_cap_seconds=0),
    )


class ToolErrorPolicyRetryBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, call_ids: list[str | None], tool: _FirstAttemptTimesOutRate, max_retries: int = 1) -> tuple[object, _ScriptedRateRunner]:
        runner = _ScriptedRateRunner(call_ids)
        agent = build_test_agent(name="fx", system_prompt="Fetch rates.", runner=runner, tools=[tool], agent_loop_settings=_policy(max_retries))
        reply = await agent.arun("Check the CHF rate, then check it again.")
        return reply, runner

    async def test_reused_call_id_gets_a_fresh_budget_each_turn(self) -> None:
        # @intent retry-budget-is-per-call
        # [Silent Failure] A server that numbers ids per response sends "call_0" every turn; the second call must still be retried.
        tool = _FirstAttemptTimesOutRate()
        reply, runner = await self._run(["call_0", "call_0"], tool)

        seen = json.dumps(runner.seen_messages)
        self.assertEqual(tool.executions, 4)
        self.assertEqual(seen.count(_RATE_TEXT), 2)
        self.assertNotIn("kind=timeout", seen)
        self.assertEqual(reply.metadata["tool_call_states"], ("succeeded", "succeeded", "succeeded"))

    async def test_id_less_identical_calls_each_get_a_retry(self) -> None:
        # @intent retry-budget-is-per-call
        # [Silent Failure] Calls with no id and the same arguments share a name+args key; each separate call still gets its retry.
        tool = _FirstAttemptTimesOutRate()
        reply, runner = await self._run([None, None], tool)

        seen = json.dumps(runner.seen_messages)
        self.assertEqual(tool.executions, 4)
        self.assertEqual(seen.count(_RATE_TEXT), 2)
        self.assertNotIn("kind=timeout", seen)
        self.assertEqual(reply.metadata["tool_call_states"], ("succeeded", "succeeded", "succeeded"))

    async def test_single_call_retries_at_most_the_budget(self) -> None:
        # [Control] One failing call still runs at most max_retries_per_tool_call + 1 times, then the model sees the error.
        tool = _FirstAttemptTimesOutRate(always_fail=True)
        reply, runner = await self._run(["call_0"], tool, max_retries=2)

        self.assertEqual(tool.executions, 3)
        self.assertIn("kind=timeout", json.dumps(runner.seen_messages))
        self.assertEqual(reply.metadata["tool_call_states"], ("failed", "succeeded"))


if __name__ == "__main__":
    unittest.main()
