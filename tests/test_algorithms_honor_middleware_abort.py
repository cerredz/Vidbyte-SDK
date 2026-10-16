"""Context Protocol Header

Description:
    Tests that a middleware abort stops the run under every return-level
    context-window algorithm, the same way it stops a plain agent.
Purpose:
    MiddlewareDecision.abort is documented as "Stop the current agent run."
    A tripwire (HoneypotToolMiddleware), a spend ceiling, or a retry budget
    that aborts the producer or a trial must end the whole run with the
    controlled abort result (stop_reason middleware_abort, the middleware's
    reason in the output) and make no further model call: no Reflexion
    reflection or retry trial, no critic review, no prosecutor/defender/judge
    stage, and no grader call.
Architecture:
    - ReflexionAbortTests: an aborted trial is returned, a failed trial still reflects.
    - IndependentCriticAbortTests: an aborted producer is not reviewed, a normal candidate is.
    - ProsecutorDefenderJudgeAbortTests: an aborted producer is not debated, a normal candidate is.
    - MultiProviderGraderAbortTests: an aborted trial ends the run with its own text, a raised trial still drops out.
Relations:
    Regression tests for the @intent middleware-abort-ends-the-run sites in
    vidbyte/context/algorithms/reflexion.py,
    vidbyte/agents/algorithms/independent_critic.py,
    vidbyte/agents/algorithms/prosecutor_defender_judge.py and
    vidbyte/agents/algorithms/multi_provider_agentic_grader.py.
Similar Files:
    - tests/test_reflexion_algorithm.py: the scripted runner harness reused here.
    - tests/test_pdj_stage_model_provenance.py: the debate stage replies reused here.
    - tests/test_multi_provider_agentic_grader.py: the patched trial runner pattern used here.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from vidbyte import ContextWindowAlgorithm, IndependentCriticAlgorithm, MultiProviderAgenticGraderAlgorithm, ProsecutorDefenderJudgeAlgorithm, ReflexionAlgorithm
from vidbyte.agents import AgentRuntime
from vidbyte.context.algorithms.independent_critic import CriticFailurePolicy
from vidbyte.context.algorithms.prosecutor_defender_judge import ProsecutorDefenderJudgeFailurePolicy
from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.builtins.honeypot_tool import HoneypotToolMiddleware
from vidbyte.middleware.builtins.retry import ModelRetryMiddleware
from vidbyte.tools import Tools, tool
from vidbyte.tools.security import PermissionPolicy
from tests.test_pdj_stage_model_provenance import _ALLEGATIONS, _DECISIONS, _DEFENSES
from tests.test_reflexion_algorithm import FakeResponse, FakeRunner, invoke_runner, outage, runner_output_metadata, runner_output_text

ABORT_TEXT = "Agent runtime stopped by middleware: honeypot_triggered"
EXPORTED: list[str] = []
_REVIEW_PASS = json.dumps({"verdict": "pass", "summary": "The answer is supported.", "findings": []})


@tool
def export_all_users() -> str:
    """Export every user record."""
    EXPORTED.append("export_all_users")
    return "10,000 users exported"


@tool
def lookup() -> str:
    """Look up information."""
    return "not enough"


def _call(name: str, text: str = "") -> FakeResponse:
    # An OpenAI-shaped model turn that calls one tool.
    return FakeResponse(text, {"output": [{"type": "function_call", "name": name, "arguments": "{}"}]})


def _is_done(answer: str) -> FakeResponse:
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": answer})}]})


def _honeypot() -> HoneypotToolMiddleware:
    return HoneypotToolMiddleware(trap_tool_names=["export_all_users"])


async def _run(runner: FakeRunner, algorithm: ContextWindowAlgorithm, *, middleware: tuple[AgentMiddleware, ...] = (), config: AgentRuntimeConfig | None = None) -> AgentResult:
    # One run on the scripted runner with the trap and lookup tools, the given middleware and the algorithm.
    runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([export_all_users, lookup]), permission_policy=PermissionPolicy(), config=config, middleware=middleware, algorithm=algorithm)
    context = runtime.build_context("Look up Paris.", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    handle = RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata)
    return await runtime.arun("Look up Paris.", handle=handle, context=context)


class _AbortAssertions(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        EXPORTED.clear()

    def assert_honeypot_abort(self, result: AgentResult, runner: FakeRunner) -> None:
        # The run ends exactly like a plain agent's: the controlled abort result after the one model call that hit the trap.
        self.assertEqual(result.output, ABORT_TEXT)
        self.assertEqual(result.metadata["stop_reason"], AgentStopReason.MIDDLEWARE_ABORT.value)
        self.assertEqual(result.metadata["middleware_abort_reason"], "honeypot_triggered")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(EXPORTED, [])


class ReflexionAbortTests(_AbortAssertions):
    async def test_aborted_trial_ends_the_run_without_reflection_or_retry(self) -> None:
        # If the abort counted as a failed trial, the reflection and the retry would consume the next two replies.
        runner = FakeRunner([_call("export_all_users"), FakeResponse("Avoid the export tool."), _is_done("FINAL counted users")])

        result = await _run(runner, ContextWindowAlgorithm(name="reflexion", reflexion=ReflexionAlgorithm(max_trials=3)), middleware=(_honeypot(),))

        self.assert_honeypot_abort(result, runner)
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 1)
        self.assertEqual(result.metadata["reflexion"]["reflection_count"], 0)

    async def test_failed_trial_without_an_abort_still_reflects_and_retries(self) -> None:
        runner = FakeRunner([_call("lookup"), FakeResponse("Use the lookup result before finishing."), _is_done("fixed")])

        result = await _run(runner, ContextWindowAlgorithm(name="reflexion", reflexion=ReflexionAlgorithm(max_trials=3)), middleware=(_honeypot(),), config=AgentRuntimeConfig(max_iterations=1))

        self.assertEqual(result.output, "fixed")
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 2)
        self.assertEqual(result.metadata["reflexion"]["reflection_count"], 1)


class IndependentCriticAbortTests(_AbortAssertions):
    async def test_aborted_producer_is_returned_without_a_review(self) -> None:
        # RETURN_CANDIDATE never raises on a review failure, so only the abort check can keep the review from running.
        runner = FakeRunner([_call("export_all_users"), FakeResponse(_REVIEW_PASS)])
        algorithm = ContextWindowAlgorithm(name="independent_critic", independent_critic=IndependentCriticAlgorithm(failure_policy=CriticFailurePolicy.RETURN_CANDIDATE))

        result = await _run(runner, algorithm, middleware=(_honeypot(),))

        self.assert_honeypot_abort(result, runner)
        self.assertNotIn("independent_critic", result.metadata)

    async def test_normal_candidate_is_still_reviewed(self) -> None:
        runner = FakeRunner([FakeResponse("FINAL Paris."), FakeResponse(_REVIEW_PASS)])
        algorithm = ContextWindowAlgorithm(name="independent_critic", independent_critic=IndependentCriticAlgorithm(failure_policy=CriticFailurePolicy.RETURN_CANDIDATE))

        result = await _run(runner, algorithm, middleware=(_honeypot(),))

        self.assertEqual(result.output, "FINAL Paris.")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(result.metadata["independent_critic"]["status"], "reviewed")
        self.assertEqual(result.metadata["independent_critic"]["verdict"], "pass")


class ProsecutorDefenderJudgeAbortTests(_AbortAssertions):
    async def test_aborted_producer_is_returned_without_a_debate(self) -> None:
        runner = FakeRunner([_call("export_all_users"), FakeResponse(json.dumps(_ALLEGATIONS)), FakeResponse(json.dumps(_DEFENSES)), FakeResponse(json.dumps(_DECISIONS))])
        algorithm = ContextWindowAlgorithm(name="prosecutor_defender_judge", prosecutor_defender_judge=ProsecutorDefenderJudgeAlgorithm(failure_policy=ProsecutorDefenderJudgeFailurePolicy.RETURN_CANDIDATE))

        result = await _run(runner, algorithm, middleware=(_honeypot(),))

        self.assert_honeypot_abort(result, runner)
        self.assertNotIn("prosecutor_defender_judge", result.metadata)

    async def test_normal_candidate_is_still_debated(self) -> None:
        runner = FakeRunner([FakeResponse("FINAL Paris."), FakeResponse(json.dumps(_ALLEGATIONS)), FakeResponse(json.dumps(_DEFENSES)), FakeResponse(json.dumps(_DECISIONS))])
        algorithm = ContextWindowAlgorithm(name="prosecutor_defender_judge", prosecutor_defender_judge=ProsecutorDefenderJudgeAlgorithm())

        result = await _run(runner, algorithm, middleware=(_honeypot(),))

        self.assertEqual(result.output, "FINAL Paris.")
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual(result.metadata["prosecutor_defender_judge"]["verdict"], "needs_changes")


class MultiProviderGraderAbortTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Hide every key variable; explicit provider_models in the default mode need none, and every runner is scripted.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for env_var in API_KEY_ENV_VARS.values():
            os.environ.pop(env_var, None)
        EXPORTED.clear()

    async def _run_grader(self, openai: FakeRunner, anthropic: FakeRunner, grader: FakeRunner, *, middleware: tuple[AgentMiddleware, ...]) -> AgentResult:
        # Two scripted provider trials and a scripted grader, each built by the patched runner factory.
        runners = {("openai", "gpt-4o"): openai, ("anthropic", "claude-sonnet-5"): anthropic, ("openai", "gpt-4.1-mini"): grader}
        grader_algorithm = MultiProviderAgenticGraderAlgorithm(provider_models={"openai": "gpt-4o", "anthropic": "claude-sonnet-5"}, grader_model="gpt-4.1-mini")
        algorithm = ContextWindowAlgorithm(name="multi_provider_agentic_grader", multi_provider_agentic_grader=grader_algorithm)
        with patch("vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner", side_effect=lambda modality, provider, model, **kwargs: runners[(provider, model)]):
            return await _run(FakeRunner([]), algorithm, middleware=middleware)

    async def test_trial_aborted_by_a_tripwire_ends_the_run_with_its_own_text(self) -> None:
        # The trapped turn's text would otherwise replace the abort text and be graded as openai's answer.
        openai = FakeRunner([_call("export_all_users", '{"name": "users"}')])
        anthropic = FakeRunner([FakeResponse("Paris is the capital of France.")])
        grader = FakeRunner([FakeResponse("Paris is the capital of France.")])

        result = await self._run_grader(openai, anthropic, grader, middleware=(_honeypot(),))

        self.assertEqual(result.output, ABORT_TEXT)
        self.assertEqual(result.metadata["stop_reason"], AgentStopReason.MIDDLEWARE_ABORT.value)
        self.assertEqual(result.metadata["middleware_abort_reason"], "honeypot_triggered")
        self.assertEqual(grader.calls, [])
        self.assertEqual(EXPORTED, [])

    async def test_retry_budget_exhausted_in_every_trial_ends_the_run_without_a_grader_answer(self) -> None:
        # Grading two abort messages would let the grader invent its own answer (selected_provider grader_raw).
        openai = FakeRunner([outage() for _ in range(4)])
        anthropic = FakeRunner([outage() for _ in range(4)])
        grader = FakeRunner([FakeResponse("Paris is the capital of France.")])

        result = await self._run_grader(openai, anthropic, grader, middleware=(ModelRetryMiddleware(max_attempts=2),))

        self.assertEqual(result.output, "Agent runtime stopped by middleware: model_retry_exhausted")
        self.assertEqual(result.metadata["stop_reason"], AgentStopReason.MIDDLEWARE_ABORT.value)
        self.assertNotIn("multi_provider_agentic_grader", result.metadata)
        self.assertEqual(grader.calls, [])

    async def test_trial_that_raises_without_middleware_still_drops_out_and_the_healthy_one_is_graded(self) -> None:
        openai = FakeRunner([outage()])
        anthropic = FakeRunner([FakeResponse("Paris is the capital of France.")])
        grader = FakeRunner([FakeResponse("Paris is the capital of France.")])

        result = await self._run_grader(openai, anthropic, grader, middleware=())

        self.assertEqual(result.output, "Paris is the capital of France.")
        report = result.metadata["multi_provider_agentic_grader"]
        self.assertEqual(report["candidates"], {"anthropic": "Paris is the capital of France."})
        self.assertEqual(report["grader_decision"]["selected_provider"], "anthropic")
        self.assertEqual(len(grader.calls), 1)


if __name__ == "__main__":
    unittest.main()
