"""FILE: tests/test_jev_fresh_continuation.py

PURPOSE: Verifies JevAgent's opt-in fresh-context continuation without network calls.
ROLE IN CODEBASE: Covers gate validation, construction, the clean input context, and the response returned to the main loop.
ARCHITECTURE NOTE: Test doubles replace only the run-state and fresh-agent boundaries; the continuation and response writer are real.
COMMON MODIFICATION PATTERNS: Add cases when fresh continuation changes its trigger, context, or fail-open behavior.
KNOWN EDGE CASES: A fresh continuation requires at least one configured done check and is bounded by max_continuations.
RELATED DOCS: docs/design/jev-fresh-continuation.md and skills/jev-continuation/SKILL.md.
TESTS: python -m pytest tests/test_jev_fresh_continuation.py.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from vidbyte.agents.jev import (
    JevAgent,
    JevAgentSettings,
    JevContinualSettings,
    JevRuntimeSettings,
)
from vidbyte.agents.jev.continuation import JevFreshContinuation
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.enums import JevContinuationGate, JevDoneCheck
from vidbyte.lib.errors import ConfigurationError


class FreshAgentStub:
    """Record the clean-context input and return one deterministic reply."""

    def __init__(self) -> None:
        self.history = ["old context"]
        self.inputs: list[Any] = []

    async def arun(self, agent_input: Any) -> Any:
        self.inputs.append(agent_input)
        return SimpleNamespace(content="fresh agent response")


class RunStateStub:
    """Expose the request, serialized state, and latest handoff expected by the continuation."""

    def __init__(self) -> None:
        self.request = "Original task"
        self.rendered = '{"goal":"finish task"}'
        self.handoff_writer = SimpleNamespace(rendered='{"evidence":"partial work"}')
        self.handoff = object()

    async def check(self, final_answer: str, responses: Any, calls: Any) -> tuple[object, ...]:
        return (object(),)


class JevFreshContinuationTests(unittest.IsolatedAsyncioTestCase):
    """Pin the public gate and the fresh-context handoff behavior."""

    def test_gate_defaults_to_existing_behavior_and_fresh_requires_a_check(self) -> None:
        self.assertIs(JevContinualSettings().gate, JevContinuationGate.SAME_CONTEXT)
        self.assertIs(JevContinualSettings(gate="fresh", checks=("multi_part",)).gate, JevContinuationGate.FRESH)
        with self.assertRaises(ConfigurationError):
            JevContinualSettings(gate="fresh")

    def test_agent_builds_fresh_continuation_when_selected(self) -> None:
        settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini")
        runtime = JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,), gate="fresh"))
        agent = JevAgent(settings, runtime)
        self.assertIsInstance(agent.continuation, JevFreshContinuation)
        self.assertEqual(agent.continuation.fresh_agent.name, "jev-fresh-continuation")

    async def test_failed_check_runs_in_clean_context_and_returns_response_to_main_loop(self) -> None:
        run_state = RunStateStub()
        fresh_agent = FreshAgentStub()
        response = JevResponse()
        continuation = JevFreshContinuation(run_state, JevContinualSettings(max_continuations=1), response, fresh_agent)  # type: ignore[arg-type]

        should_continue = await continuation.should_continue("draft", ("earlier",), ())

        self.assertTrue(should_continue)
        self.assertEqual(fresh_agent.history, [])
        prompt = fresh_agent.inputs[0].prompt
        self.assertIn("Original task", prompt)
        self.assertIn("finish task", prompt)
        self.assertIn("partial work", prompt)
        messages: list[dict[str, Any]] = []
        continuation.continue_(messages)
        self.assertEqual(messages, [{"role": "user", "content": "fresh agent response"}])
        self.assertEqual(response.state.continuations, 1)


if __name__ == "__main__":
    unittest.main()
