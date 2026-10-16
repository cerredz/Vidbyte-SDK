"""Context Protocol Header

Description:
    Tests for the Reflexion runtime context-window algorithm.
Purpose:
    Validates automatic retry/reflection behavior, prompt overrides,
    public context-window preset wiring, and that a run which failed over
    reflects and retries on the fallback model.
"""

from __future__ import annotations

import dataclasses
import unittest

from pydantic import BaseModel

from vidbyte import ContextWindow, ReflexionAlgorithm
from vidbyte.agents.algorithms import ReflexionRuntimeAlgorithm
from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents import AgentFallback, AgentRuntime, FallbackModel
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.middleware import MiddlewareDecision, MiddlewareTransform
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.dataclasses.strategies import AgentResult as StrategyResult
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.tools import ToolCallContext, ToolCallState, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    response = runner.responses.pop(0)
    if isinstance(response, BaseException):
        raise response
    return response


def outage() -> ProviderRequestError:
    # The fallback-eligible error a provider that is down raises.
    return ProviderRequestError("provider is down", provider="openai", status_code=503)


class ScriptedChain(AgentFallback):
    """A primary-first chain whose backup models are scripted runners, so no real runner is built."""

    def __init__(self, *backups: FakeRunner) -> None:
        super().__init__([FallbackModel(provider="openai", model=f"model-{index}") for index in range(len(backups) + 1)])
        self.backups = backups

    def build_runner(self, index: int) -> object:
        return self.backups[index - 1]


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return dict(getattr(response, "metadata", {}))


class Ticket(BaseModel):
    title: str
    urgency: int


SECRET = "SECRETMARK api-token-123"


class RedactSecretMiddleware(AgentMiddleware):
    """A caller's redaction middleware: the model is shown [REDACTED] instead of a result holding the secret."""

    def __init__(self) -> None:
        self.redactions = 0

    async def after_tool_call(self, ctx):
        result = ctx.tool_result
        if result is not None and "SECRETMARK" in str(result.output):
            self.redactions += 1
            return MiddlewareDecision.continue_(transform=MiddlewareTransform(model_visible_tool_result=dataclasses.replace(result, output="[REDACTED]")))
        return MiddlewareDecision.continue_()


class ReflexionAlgorithmTests(unittest.IsolatedAsyncioTestCase):
    def test_context_window_preset_exposes_single_reflexion_algorithm(self) -> None:
        algorithm = ContextWindow.preset.reflexion

        self.assertEqual(algorithm.name, "reflexion")
        self.assertIsInstance(algorithm.reflexion, ReflexionAlgorithm)
        self.assertFalse(hasattr(ContextWindow.preset, "reflexion_last_attempt"))

    def test_agent_runtime_context_algorithm_dispatcher_detects_reflexion(self) -> None:
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.reflexion,
        )
        dispatcher = AgentRuntimeContextAlgorithms(runtime)

        self.assertEqual(dispatcher.detect_algorithm(), "reflexion")
        self.assertTrue(dispatcher.is_algorithm("reflexion"))
        self.assertIsInstance(dispatcher.return_algorithm(), ReflexionRuntimeAlgorithm)

    def test_reflexion_algorithm_allows_stage_prompt_overrides(self) -> None:
        algorithm = ReflexionAlgorithm(
            agent_system_prompt="AGENT {system_prompt} {reflections} {previous_attempt}",
            reflect_system_prompt="REFLECT SYSTEM",
            reflect_prompt="REFLECT {task} {failed_attempt} {reflections}",
        )

        self.assertEqual(algorithm.reflection_system_prompt(), "REFLECT SYSTEM")
        self.assertIn("REFLECT task", algorithm.render_reflection_prompt(
            task="task",
            failed_attempt="failed",
            reflections=("memory",),
        ))

    def test_reflexion_algorithm_refuses_a_template_with_an_unknown_placeholder(self) -> None:
        # [Hidden Failure] An example JSON object is an unknown {name} to str.format, so it is refused before any paid trial.
        for field_name in ("agent_system_prompt", "reflect_prompt"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValueError) as ctx:
                    ReflexionAlgorithm(**{field_name: 'Retry. {reflections} Reply as JSON like {"answer": "..."}'})
                self.assertIn(field_name, str(ctx.exception))
                self.assertIn('"answer"', str(ctx.exception))

    def test_reflexion_algorithm_renders_escaped_braces_literally(self) -> None:
        # [Edge Case] Escaped braces construct and reach the model as a literal JSON example.
        algorithm = ReflexionAlgorithm(
            agent_system_prompt='AGENT {system_prompt} {reflections} Reply as JSON like {{"answer": "..."}}',
            reflect_prompt='REFLECT {failed_attempt} Reply as JSON like {{"lesson": "..."}}',
        )

        context = algorithm.context_for_trial(BaseAgentContext(system_prompt="Base."), task="task", reflections=("memory",), failed_attempts=("failed",))
        self.assertTrue(context.system_prompt.startswith("AGENT Base."))
        self.assertTrue(context.system_prompt.endswith('Reply as JSON like {"answer": "..."}'))
        self.assertEqual(
            algorithm.render_reflection_prompt(task="task", failed_attempt="failed", reflections=()),
            'REFLECT failed Reply as JSON like {"lesson": "..."}',
        )

    async def test_runtime_reflects_after_failed_trial_and_retries_with_memory(self) -> None:
        @tool
        def lookup() -> str:
            """Look up information."""
            return "not enough"

        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("Use the lookup result before finishing."),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "fixed"}'}]}),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.reflexion,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertEqual(result.output, "fixed")
        self.assertEqual(len(runner.calls), 3)
        self.assertIn("Failed attempt:", runner.calls[1]["prompt"])
        self.assertIn("Use the lookup result before finishing.", runner.calls[2]["kwargs"]["system"])
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 2)
        self.assertEqual(result.metadata["reflexion"]["reflection_count"], 1)

    async def _run_with_failover(self, primary: FakeRunner, chain: ScriptedChain) -> StrategyResult:
        # A one-iteration Reflexion run whose primary model is down and whose chain holds the scripted backups.
        @tool
        def lookup() -> str:
            """Look up information."""
            return "not enough"

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            algorithm=ContextWindow.preset.reflexion,
            fallback=chain,
        )
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        handle = RunnerHandle(runner=primary, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata)
        return await runtime.arun("task", handle=handle, context=context)

    async def test_reflection_and_next_trial_stay_on_the_fallback_model(self) -> None:
        primary = FakeRunner([outage() for _ in range(5)])
        backup = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("Use the lookup result before finishing."),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "fixed"}'}]}),
            ]
        )

        result = await self._run_with_failover(primary, ScriptedChain(backup))

        self.assertEqual(result.output, "fixed")
        # Only the first trial's first call reaches the dead primary; the reflection and the retry go to the backup.
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(backup.calls), 3)
        self.assertIn("Failed attempt:", backup.calls[1]["prompt"])
        self.assertIn("Use the lookup result before finishing.", backup.calls[2]["kwargs"]["system"])
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 2)
        # The final trial never switched itself, yet the result still reports the run's failover.
        self.assertEqual(result.metadata["fallback"]["final_model"], "openai/model-1")

    async def test_later_trial_resumes_the_fallback_chain_where_it_stood(self) -> None:
        primary = FakeRunner([outage() for _ in range(5)])
        backup = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("Use the lookup result before finishing."),
                outage(),
            ]
        )
        last = FakeRunner([FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "fixed"}'}]})])

        result = await self._run_with_failover(primary, ScriptedChain(backup, last))

        self.assertEqual(result.output, "fixed")
        # When the backup goes down in the second trial, the run moves on to the next model instead of retrying the backup.
        self.assertEqual((len(primary.calls), len(backup.calls), len(last.calls)), (1, 3, 1))
        self.assertEqual(
            [(attempt["from"], attempt["to"]) for attempt in result.metadata["fallback"]["attempts"]],
            [("openai/model-0", "openai/model-1"), ("openai/model-1", "openai/model-2")],
        )

    def test_active_handle_is_the_given_handle_until_the_run_fails_over(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.reflexion)
        handle = RunnerHandle(runner=FakeRunner([]), provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata)

        self.assertIs(runtime._active_handle(handle), handle)

    async def test_runtime_accepts_plain_text_final_answer_without_reflecting(self) -> None:
        runner = FakeRunner([FakeResponse("Paris.")])
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.reflexion,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertEqual(result.output, "Paris.")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 1)
        self.assertEqual(result.metadata["reflexion"]["reflection_count"], 0)

    async def test_runtime_keeps_validated_structured_output(self) -> None:
        # BaseAgent raises OutputSchemaViolationError when structured is None, so Reflexion must carry it through.
        runner = FakeRunner([FakeResponse('{"title": "Card declined", "urgency": 2}')])
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.reflexion,
            output_schema=Ticket,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertEqual(result.structured, Ticket(title="Card declined", urgency=2))
        self.assertEqual(result.metadata["reflexion"]["trial_count"], 1)

    def test_format_failed_attempt_includes_tool_context(self) -> None:
        algorithm = ReflexionAlgorithm()
        context_record = ToolCallContext(
            tool_name="lookup",
            state=ToolCallState.FAILED,
            result=ToolResult.error("lookup", "raw result"),
        )

        summary = algorithm.format_failed_attempt(
            StrategyResult(
                output="failed",
                strategy_name="direct_runner",
                metadata={
                    "stop_reason": "max_iterations",
                    "tool_calls": (context_record,),
                },
            )
        )

        self.assertIn("Stop reason: max_iterations", summary)
        self.assertIn("lookup", summary)

    def test_format_failed_attempt_renders_model_visible_result_not_raw_output(self) -> None:
        algorithm = ReflexionAlgorithm()
        raw = ToolResult.success("read_secret", SECRET)
        redacted = ToolCallContext(
            tool_name="read_secret",
            state=ToolCallState.SUCCEEDED,
            result=raw,
            model_visible_result=dataclasses.replace(raw, output="[REDACTED]"),
        )
        unprotected = ToolCallContext(tool_name="lookup", state=ToolCallState.SUCCEEDED, result=ToolResult.success("lookup", "plain value"))

        summary = algorithm.format_failed_attempt(
            StrategyResult(
                output="failed",
                strategy_name="direct_runner",
                metadata={"stop_reason": "max_iterations", "tool_calls": (redacted, unprotected)},
            )
        )

        # The redacted call shows the model's view; a call the model saw raw still shows its raw output.
        self.assertIn("- read_secret (succeeded): [REDACTED]", summary)
        self.assertNotIn("SECRETMARK", summary)
        self.assertIn("- lookup (succeeded): plain value", summary)

    async def test_runtime_never_sends_a_redacted_tool_result_to_reflection_or_next_trial(self) -> None:
        @tool
        def read_secret() -> str:
            """Read a credentials file."""
            return SECRET

        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "read_secret", "arguments": "{}"}]}),
                FakeResponse("Do not read credentials again."),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "fixed"}'}]}),
            ]
        )
        middleware = RedactSecretMiddleware()
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([read_secret]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            middleware=(middleware,),
            algorithm=ContextWindow.preset.reflexion,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        # The run took the failed-trial, reflection, retry path and the middleware really hid a secret-bearing result.
        self.assertEqual(result.output, "fixed")
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(middleware.redactions, 1)
        reflection_call, retry_call = runner.calls[1], runner.calls[2]
        self.assertIn("Failed attempt:", reflection_call["prompt"])
        self.assertIn("[REDACTED]", reflection_call["prompt"])
        self.assertIn("[REDACTED]", retry_call["kwargs"]["system"])
        # No string bound for the model, prompt or any request keyword such as system or messages, carries the secret.
        for index, call in enumerate(runner.calls):
            with self.subTest(model_call=index):
                self.assertNotIn("SECRETMARK", repr(call))


if __name__ == "__main__":
    unittest.main()

