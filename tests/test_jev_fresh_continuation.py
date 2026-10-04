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
from vidbyte.lib.dataclasses.jev import JevDoneResult, JevFailedDoneQuestion
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums import JevContinuationGate, JevDoneCheck
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevDoneRegistry


class FreshAgentStub:
    """Record the clean-context input and return one deterministic reply."""

    def __init__(self, content: str = "fresh agent response", metadata: Any = None, *, fail: bool = False) -> None:
        self.history = ["old context"]
        self.inputs: list[Any] = []
        self.reply = SimpleNamespace(content=content, metadata=metadata)
        self.fail = fail

    async def arun(self, agent_input: Any) -> Any:
        self.inputs.append(agent_input)
        if self.fail:
            from vidbyte.lib.errors import VidbyteSdkError

            raise VidbyteSdkError("fresh continuation failed")
        return self.reply


class RunStateStub:
    """Expose the request, serialized state, and latest handoff expected by the continuation."""

    def __init__(self, attempts: list[tuple[JevDoneResult, ...]] | None = None) -> None:
        self.request = "Original task"
        self.rendered = '{"goal":"finish task"}'
        self.handoff_writer = SimpleNamespace(rendered='{"evidence":"partial work"}')
        self.handoff = object()
        self.attempts = attempts or [(
            JevDoneResult(
                check=JevDoneCheck.MULTI_PART,
                score=0.2,
                passed=False,
                incomplete=("README",),
                failed_questions=(JevFailedDoneQuestion(
                    name="multi_part.delivered.README",
                    question="Does the evidence show that the README was produced in full?",
                ),),
            ),
        )]
        self.checks = tuple(dict.fromkeys(result.check for attempt in self.attempts for result in attempt)) or (JevDoneCheck.MULTI_PART,)
        self.latest_results: tuple[JevDoneResult, ...] = ()
        self.check_calls = 0
        self.failed = True

    async def check(self, final_answer: str, responses: Any, calls: Any) -> tuple[object, ...]:
        self.check_calls += 1
        if not self.failed:
            self.latest_results = tuple(JevDoneResult(check=check, score=1.0) for check in self.checks)
        else:
            attempt = min(self.check_calls - 1, len(self.attempts) - 1)
            self.latest_results = self.attempts[attempt]
        return tuple(result for result in self.latest_results if not result.passed)


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
        first = agent.continuation.fresh_agent_factory()
        second = agent.continuation.fresh_agent_factory()
        self.assertEqual(first.name, "jev-fresh-continuation")
        self.assertIsNot(first, second)

    async def test_failed_check_runs_in_clean_context_and_returns_response_to_main_loop(self) -> None:
        run_state = RunStateStub()
        fresh_agent = FreshAgentStub(
            content="  fresh agent response  ",
            metadata={
                "iteration_outputs": ("first fresh step", "", "fresh agent response"),
                "tool_calls": (ToolCallContext(tool_name="lookup", iteration_count=1), "bad item"),
            },
        )
        response = JevResponse()
        continuation = JevFreshContinuation(run_state, JevContinualSettings(max_continuations=1), response, lambda: fresh_agent)  # type: ignore[arg-type]

        should_continue = await continuation.should_continue("draft", ("earlier",), ())

        self.assertTrue(should_continue)
        self.assertEqual(run_state.check_calls, 1)
        self.assertEqual(fresh_agent.history, [])
        prompt = fresh_agent.inputs[0].prompt
        self.assertIn("Original task", prompt)
        self.assertIn("finish task", prompt)
        self.assertIn("partial work", prompt)
        self.assertIn("<completion_gate_assessment>", prompt)
        self.assertIn(JevDoneRegistry.description(JevDoneCheck.MULTI_PART), prompt)
        self.assertIn("Does the evidence show that the README was produced in full?", prompt)
        self.assertNotIn("multi_part.delivered.README", prompt)
        self.assertNotIn("P(yes)", prompt)
        messages: list[dict[str, Any]] = []
        evidence = continuation.continue_(messages)
        self.assertEqual(messages, [{"role": "user", "content": "fresh agent response"}])
        self.assertEqual(response.state.continuations, 1)
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.source, "fresh")
        self.assertEqual(evidence.responses, ("first fresh step", "", "fresh agent response", "  fresh agent response  "))
        self.assertEqual(len(evidence.tool_calls), 1)
        self.assertEqual(evidence.tool_calls[0].tool_name, "lookup")

    async def test_missing_or_malformed_metadata_falls_back_to_raw_final_content(self) -> None:
        for reply in (
            SimpleNamespace(content="raw final"),
            SimpleNamespace(content="raw final", metadata={"iteration_outputs": ("step", 5), "tool_calls": object()}),
        ):
            run_state = RunStateStub()
            fresh_agent = FreshAgentStub()
            fresh_agent.reply = reply
            continuation = JevFreshContinuation(run_state, JevContinualSettings(), JevResponse(), lambda: fresh_agent)  # type: ignore[arg-type]

            self.assertTrue(await continuation.should_continue("draft", (), ()))
            evidence = continuation.continue_([])

            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.responses, ("raw final",))
            self.assertEqual(evidence.tool_calls, ())

    async def test_gate_assessment_lists_enabled_gates_and_recomputes_failed_questions(self) -> None:
        first = (
            JevDoneResult(
                check=JevDoneCheck.MULTI_PART,
                score=0.3,
                passed=False,
                incomplete=("README", "tests"),
                failed_questions=(
                    JevFailedDoneQuestion("multi_part.delivered.README", "Is the README complete?"),
                    JevFailedDoneQuestion("multi_part.delivered.tests", "Are the tests complete?"),
                ),
            ),
            JevDoneResult(
                check=JevDoneCheck.CLAIMS,
                score=1.0,
                passed=True,
            ),
        )
        second = (
            JevDoneResult(
                check=JevDoneCheck.MULTI_PART,
                score=0.7,
                passed=False,
                incomplete=("tests",),
                failed_questions=(JevFailedDoneQuestion("multi_part.delivered.tests", "Are the tests complete?"),),
            ),
            JevDoneResult(check=JevDoneCheck.CLAIMS, score=1.0, passed=True),
        )
        run_state = RunStateStub([first, second])
        agents: list[FreshAgentStub] = []

        def factory() -> FreshAgentStub:
            agent = FreshAgentStub()
            agents.append(agent)
            return agent

        continuation = JevFreshContinuation(run_state, JevContinualSettings(max_continuations=2), JevResponse(), factory)  # type: ignore[arg-type]
        self.assertTrue(await continuation.should_continue("draft", (), ()))
        first_prompt = agents[0].inputs[0].prompt
        self.assertLess(first_prompt.index("## Multi Part"), first_prompt.index("## Claims"))
        self.assertIn("Is the README complete?", first_prompt)
        self.assertIn("Are the tests complete?", first_prompt)
        continuation.continue_([])

        self.assertTrue(await continuation.should_continue("draft", (), ()))
        second_prompt = agents[1].inputs[0].prompt
        self.assertNotIn("Is the README complete?", second_prompt)
        self.assertIn("Are the tests complete?", second_prompt)
        self.assertIn("Status: passed; no questions failed.", second_prompt)
        self.assertEqual(second_prompt.count("<completion_gate_assessment>"), 1)

    async def test_gate_assessment_distinguishes_unavailable_and_deterministic_failures(self) -> None:
        # Shows gate status without inventing a Jev question for deterministic evidence gaps.
        results = (
            JevDoneResult(check=JevDoneCheck.MULTI_PART, score=None, available=False),
            JevDoneResult(check=JevDoneCheck.REQUIRED_SEQUENCE, score=None, passed=False, incomplete=("stage_2",)),
        )
        run_state = RunStateStub([results])
        fresh_agent = FreshAgentStub()
        continuation = JevFreshContinuation(run_state, JevContinualSettings(), JevResponse(), lambda: fresh_agent)  # type: ignore[arg-type]

        self.assertTrue(await continuation.should_continue("draft", (), ()))

        prompt = fresh_agent.inputs[0].prompt
        self.assertIn("Status: not evaluated.", prompt)
        self.assertIn("Status: gate failed on deterministic evidence; no Jev question failed.", prompt)
        self.assertIn("## Multi Part", prompt)
        self.assertIn("## Required Sequence", prompt)
        self.assertNotIn("stage_2", prompt)

    async def test_fresh_factory_is_per_attempt_and_cap_and_blank_output_stop_retries(self) -> None:
        agents: list[FreshAgentStub] = []

        def factory() -> FreshAgentStub:
            agent = FreshAgentStub()
            agents.append(agent)
            return agent

        run_state = RunStateStub()
        response = JevResponse()
        continuation = JevFreshContinuation(run_state, JevContinualSettings(max_continuations=2), response, factory)  # type: ignore[arg-type]
        self.assertTrue(await continuation.should_continue("draft", (), ()))
        continuation.continue_([])
        self.assertTrue(await continuation.should_continue("draft", (), ()))
        continuation.continue_([])
        self.assertFalse(await continuation.should_continue("draft", (), ()))
        self.assertEqual(len(agents), 2)
        self.assertIsNot(agents[0], agents[1])
        self.assertEqual(run_state.check_calls, 3)

        blank = FreshAgentStub(content="  ", metadata={"iteration_outputs": ("work happened",)})
        run_state = RunStateStub()
        continuation = JevFreshContinuation(run_state, JevContinualSettings(), JevResponse(), lambda: blank)  # type: ignore[arg-type]
        self.assertFalse(await continuation.should_continue("draft", (), ()))
        self.assertIsNone(continuation.continue_([]))

    async def test_sdk_failure_leaves_answer_in_place_and_fresh_inherits_budget_extension(self) -> None:
        from vidbyte.lib.dataclasses.jev import JevDoneResult

        run_state = RunStateStub()
        response = JevResponse()
        broken = FreshAgentStub(fail=True)
        continuation = JevFreshContinuation(run_state, JevContinualSettings(), response, lambda: broken)  # type: ignore[arg-type]
        self.assertFalse(await continuation.should_continue("draft", (), ()))
        self.assertIsNone(continuation.continue_([]))
        self.assertEqual(response.state.continuations, 0)

        continuation.failed = (JevDoneResult(check=JevDoneCheck.FAITHFUL_SCOPE, score=None),)
        self.assertEqual(continuation.budget_extension(), (
            continuation.continual.faithful_scope_extra_iterations,
            continuation.continual.faithful_scope_extra_tokens,
            continuation.continual.faithful_scope_extra_tool_calls,
        ))


if __name__ == "__main__":
    unittest.main()
