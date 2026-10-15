"""FILE: tests/test_session_rule_after_tool_retry.py

PURPOSE: Verifies a Session failure rule judges a tool result only after ToolErrorPolicy has finished retrying that call.
ROLE IN CODEBASE: Exercises the SDK-owned middleware order through a real Session and BaseAgent without provider or network dependencies.
ARCHITECTURE NOTE: Uses an offline scripted runner and a tool that times out under ToolSettings.tool_timeout_seconds.
COMMON MODIFICATION PATTERNS: Add one focused case when the order of SDK-owned middleware or the retry contract changes.
KNOWN EDGE CASES: A silently retried attempt that later succeeds, a retry that also fails, and a run with no retry policy.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_rule_after_tool_retry.py.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from tests.agent_test_support import build_test_agent
from vidbyte import Failure, FailureCode, FailureDisposition, Session, rule, tool
from vidbyte.agents import AgentLoopSettings, ToolSettings
from vidbyte.agents.settings.tool_error import ToolErrorPolicy
from vidbyte.lib.dataclasses.middleware import MiddlewareHook


class _QuoteThenAnswerRunner:
    """Offline runner that asks for one quote tool call, then answers in plain text."""

    def __init__(self) -> None:
        self.requests = 0

    def run(self, _prompt: str, **_options: object) -> SimpleNamespace:
        # Script one OpenAI-style tool call on the first request and a plain answer after it, without network access.
        self.requests += 1
        if self.requests == 1:
            call = {"id": "call_quote", "type": "function", "function": {"name": "quote", "arguments": '{"sku": "A7"}'}}
            return SimpleNamespace(text="", raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]})
        text = "Quote: A7 costs $42"
        return SimpleNamespace(text=text, raw={"choices": [{"message": {"role": "assistant", "content": text}}]})


def _stop_on_timeout(context):
    # Report a tool timeout whenever the tool result the rule is shown is a timeout error.
    result = context.tool_result
    if result is not None and dict(result.metadata).get("error") == "timeout":
        return Failure(code=FailureCode.TOOL_TIMEOUT, source="quote_timeout", summary="quote service timed out")
    return None


def _rule_records(session: Session) -> list[Failure]:
    # Keep only the timeouts the Session rule itself recorded, not the runtime's own tool-timeout record.
    return [item for item in session.failures.history(code=FailureCode.TOOL_TIMEOUT) if item.source == "quote_timeout"]


class SessionRuleAfterToolRetryTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, *, hangs: int, with_policy: bool) -> tuple[object, list[str], Session]:
        # Run a Session whose quote tool hangs past its timeout on the first `hangs` attempts.
        runs: list[str] = []

        @tool
        async def quote(sku: str) -> str:
            """Get a price quote for a SKU."""
            runs.append(sku)
            if len(runs) <= hangs:
                await asyncio.sleep(5)
            return f"{sku}: $42"

        policy = ToolErrorPolicy(max_retries_per_tool_call=1, retry_backoff_base_seconds=0, retry_backoff_cap_seconds=0) if with_policy else None
        settings = AgentLoopSettings(max_iterations=5, tool_settings=ToolSettings(tool_timeout_seconds=0.05), tool_error_policy=policy)
        session = Session(build_test_agent(name="pricing", system_prompt="Quote prices.", runner=_QuoteThenAnswerRunner(), tools=[quote], agent_loop_settings=settings))
        session.failures.add_rule(rule(code=FailureCode.TOOL_TIMEOUT, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.STOP)(_stop_on_timeout))
        reply = await session.arun("Quote SKU A7.")
        return reply, runs, session

    async def test_silently_retried_timeout_does_not_trip_stop_rule(self) -> None:  # [Hidden Failure]
        # @intent session-rules-judge-the-result-after-policy-retries
        # Verify a timeout the policy retries and recovers from never reaches the STOP rule, so the run finishes normally.
        reply, runs, session = await self._run(hangs=1, with_policy=True)
        self.assertEqual(runs, ["A7", "A7"])
        self.assertNotEqual(reply.metadata.get("stop_reason"), "middleware_abort")
        self.assertNotEqual(reply.metadata.get("middleware_abort_reason"), "failure_rule")
        self.assertIn("$42", str(reply.content))
        self.assertEqual(_rule_records(session), [])

    async def test_stop_rule_still_stops_when_the_retry_also_fails(self) -> None:  # [Hidden Failure]
        # Verify the STOP rule judges the final attempt once the policy's retry budget is spent.
        reply, runs, session = await self._run(hangs=2, with_policy=True)
        self.assertEqual(runs, ["A7", "A7"])
        self.assertEqual(reply.metadata.get("stop_reason"), "middleware_abort")
        self.assertEqual(reply.metadata.get("middleware_abort_reason"), "failure_rule")
        self.assertEqual(len(_rule_records(session)), 1)

    async def test_stop_rule_stops_on_first_timeout_without_policy(self) -> None:  # [Hidden Failure]
        # Verify that without a retry policy the STOP rule stops the run on the first timeout.
        reply, runs, session = await self._run(hangs=1, with_policy=False)
        self.assertEqual(runs, ["A7"])
        self.assertEqual(reply.metadata.get("stop_reason"), "middleware_abort")
        self.assertEqual(reply.metadata.get("middleware_abort_reason"), "failure_rule")
        self.assertEqual(len(_rule_records(session)), 1)


if __name__ == "__main__":
    unittest.main()
