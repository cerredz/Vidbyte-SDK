"""Context Protocol Header

Description:
    Tests continual trace schemas, tools, wrapper agent, and runtime integration.
Purpose:
    Verifies that TraceOption.continual(...) produces bounded user-visible trace
    artifacts without changing existing agent behavior when tracing is disabled.
Architecture:
    Unittest suite using fake runners and OpenAI-shaped tool call payloads.
Relations:
    Covers vidbyte.trace, vidbyte.agents.continual_trace, BaseAgent, and AgentRuntime.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from vidbyte import BaseAgent, TraceOption, TraceSchema
from vidbyte.agents import AgentRuntime, ContinualTraceAgent
from vidbyte.context import ContextWindow
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.enums import AgentRuntimeType, Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts import Prompts
from vidbyte.trace.prebuilt import ActionTrace, DebugTrace
from vidbyte.trace.tools import UpdateTraceTool
from vidbyte.tools import ToolCall, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    """Minimal model response for tool-call runtime tests."""

    def __init__(self, text: str = "", raw: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        # Stores model text, provider payload, and optional provider metadata.
        self.text = text
        self.raw = dict(raw or {"output_text": text})
        self.metadata = dict(metadata or {})


class FakeRunner:
    """Runner that returns queued responses to main and trace agent calls."""

    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        # Stores queued responses and records every invocation.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def arun(self, message: str, **kwargs: object) -> FakeResponse:
        # Returns the next queued response or raises the next queued exception.
        self.calls.append({"message": message, "kwargs": dict(kwargs)})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    # Adapts FakeRunner to the RunnerHandle.invoke protocol.
    return await runner.arun(prompt, **kwargs)


def runner_output_text(response: object) -> str:
    # Extracts text from fake responses in the same shape BaseAgent expects.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict[str, Any]:
    # Extracts metadata from fake responses for token/runtime accounting tests.
    return dict(getattr(response, "metadata", {}))


class ResponseFactory:
    """Builds compact OpenAI Responses-shaped fake payloads for tests."""

    @staticmethod
    def call(name: str, arguments: str = "{}", call_id: str | None = None) -> FakeResponse:
        # Creates a fake function-call model response.
        payload = {"type": "function_call", "name": name, "arguments": arguments}
        if call_id:
            payload["call_id"] = call_id
        return FakeResponse("", {"output": [payload]})

    @staticmethod
    def done(answer: str = "done") -> FakeResponse:
        # Creates a fake isDone response with a final answer argument.
        return ResponseFactory.call("isDone", f'{{"final_answer": "{answer}"}}')

    @staticmethod
    def update(arguments: str) -> FakeResponse:
        # Creates a fake updateTrace response.
        return ResponseFactory.call("updateTrace", arguments)


class TraceSchemaTests(unittest.TestCase):
    def test_rejects_empty_fields(self) -> None:
        # [Edge Case] Empty schema mapping raises ValueError.
        with self.assertRaises(ValueError):
            TraceSchema(name="empty", fields={})

    def test_rejects_blank_field_name(self) -> None:
        # [Hidden Assumption] Field names are not always valid strings.
        with self.assertRaises(ValueError):
            TraceSchema(name="bad", fields={" ": "description"})

    def test_initial_artifact_contains_all_fields(self) -> None:
        # [Silent Failure] Initial artifact must not omit any schema field.
        schema = TraceSchema(name="x", fields={"goal": "Goal.", "status": "Status."})
        self.assertEqual(schema.initial_artifact(), {"goal": None, "status": None})

    def test_coerce_mapping_preserves_insertion_order(self) -> None:
        # [Silent Failure] Field order should match developer-provided order.
        schema = TraceSchema.coerce({"first": "First.", "second": "Second."})
        self.assertEqual(tuple(schema.fields), ("first", "second"))


class TraceOptionTests(unittest.TestCase):
    def test_continual_accepts_prebuilt_schema(self) -> None:
        # [Edge Case] Prebuilt ActionTrace works without wrapping.
        option = TraceOption.continual(ActionTrace)
        self.assertEqual(option.schema.name, "action_trace")

    def test_continual_accepts_mapping_schema(self) -> None:
        # [Edge Case] A one-field custom mapping schema works.
        option = TraceOption.continual({"notes": "Notes."})
        self.assertEqual(tuple(option.schema.fields), ("notes",))

    def test_rejects_zero_interval(self) -> None:
        # [Edge Case] every_n_iterations=0 raises.
        with self.assertRaises(ValueError):
            TraceOption.continual(ActionTrace, every_n_iterations=0)

    def test_rejects_negative_interval(self) -> None:
        # [Edge Case] Negative interval raises.
        with self.assertRaises(ValueError):
            TraceOption.continual(ActionTrace, every_n_iterations=-1)

    def test_rejects_zero_trace_iterations(self) -> None:
        # [Edge Case] max_trace_iterations=0 raises.
        with self.assertRaises(ValueError):
            TraceOption.continual(ActionTrace, max_trace_iterations=0)

    def test_rejects_trace_iterations_above_three(self) -> None:
        # [Hidden Assumption] Trace agent should stay within the requested 1-3 iteration budget.
        with self.assertRaises(ValueError):
            TraceOption.continual(ActionTrace, max_trace_iterations=4)


class PrebuiltTraceTests(unittest.TestCase):
    def test_action_trace_has_required_fields(self) -> None:
        # [Hidden Failure] Prebuilt schema accidentally drops key action fields.
        self.assertTrue({"goal", "actions_taken", "mistakes"}.issubset(ActionTrace.fields))

    def test_debug_trace_constructs(self) -> None:
        # [Hidden Failure] Import-time schema validation catches broken prebuilt fields.
        self.assertIn("blockers", DebugTrace.fields)


class UpdateTraceToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_complete_trace_object(self) -> None:
        # [Edge Case] Complete update replaces all schema fields.
        tool_instance = UpdateTraceTool(ActionTrace)
        result = await tool_instance.execute(ToolCall("updateTrace", {"trace": {"goal": "ship", "actions_taken": ["test"], "mistakes": [], "current_status": "done"}}))
        self.assertEqual(result.status.value, "success")
        self.assertEqual(tool_instance.current_trace()["goal"], "ship")

    async def test_partial_update_preserves_existing_values(self) -> None:
        # [Silent Failure] Missing fields should not silently reset previous values.
        tool_instance = UpdateTraceTool(ActionTrace, {"goal": "ship", "actions_taken": ["audit"]})
        await tool_instance.execute(ToolCall("updateTrace", {"trace": {"current_status": "running"}}))
        self.assertEqual(tool_instance.current_trace()["goal"], "ship")
        self.assertEqual(tool_instance.current_trace()["current_status"], "running")

    async def test_unknown_keys_are_filtered(self) -> None:
        # [Silent Failure] Unknown model-produced keys should not leak into the artifact.
        tool_instance = UpdateTraceTool(ActionTrace)
        await tool_instance.execute(ToolCall("updateTrace", {"trace": {"goal": "ship", "extra": "ignore"}}))
        self.assertNotIn("extra", tool_instance.current_trace())

    async def test_non_object_trace_returns_error_without_mutation(self) -> None:
        # [Hidden Failure] Bad tool arguments should not corrupt trace state.
        tool_instance = UpdateTraceTool(ActionTrace, {"goal": "keep"})
        result = await tool_instance.execute(ToolCall("updateTrace", {"trace": "bad"}))
        self.assertEqual(result.status.value, "error")
        self.assertEqual(tool_instance.current_trace()["goal"], "keep")

    async def test_empty_update_keeps_initial_artifact(self) -> None:
        # [Edge Case] Empty trace object keeps all schema fields present.
        tool_instance = UpdateTraceTool(ActionTrace)
        await tool_instance.execute(ToolCall("updateTrace", {"trace": {}}))
        self.assertEqual(set(tool_instance.current_trace()), set(ActionTrace.fields))


class ContinualTraceAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_wrapper_uses_prompt_catalog(self) -> None:
        # [Hidden Assumption] Prompt enum and catalog are correctly wired.
        self.assertIn("continual trace agent", Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT).lower())

    async def test_update_returns_tool_recorded_trace(self) -> None:
        # [Edge Case] Trace agent returns updated artifact when updateTrace is called.
        runner = FakeRunner([
            ResponseFactory.update('{"trace": {"goal": "ship"}}'),
            ResponseFactory.done(),
        ])
        agent = ContinualTraceAgent(runner=runner, schema=ActionTrace)
        trace = await agent.update(context_window="Goal is ship.", trace_so_far=ActionTrace.initial_artifact())
        self.assertEqual(trace["goal"], "ship")

    async def test_no_update_tool_call_preserves_previous_trace(self) -> None:
        # [Silent Failure] Ordinary text response should not be mistaken for a trace update.
        runner = FakeRunner([FakeResponse("nothing new"), ResponseFactory.done()])
        agent = ContinualTraceAgent(runner=runner, schema=ActionTrace)
        trace = await agent.update(context_window="No change.", trace_so_far={"goal": "keep"})
        self.assertEqual(trace["goal"], "keep")

    async def test_trace_agent_failure_preserves_previous_trace(self) -> None:
        # [Hidden Failure] Trace-agent runner exception is fail-open.
        runner = FakeRunner([RuntimeError("trace failed")])
        agent = ContinualTraceAgent(runner=runner, schema=ActionTrace)
        trace = await agent.update(context_window="Main context.", trace_so_far={"goal": "keep"})
        self.assertEqual(trace["goal"], "keep")
        self.assertIsNotNone(agent.last_error)


class BaseAgentTraceTests(unittest.TestCase):
    def test_agent_stores_trace_option(self) -> None:
        # [Edge Case] BaseAgent(trace=...) stores the option.
        option = TraceOption.continual(ActionTrace)
        agent = BaseAgent(name="worker", system_prompt="Work.", trace=option)
        self.assertIs(agent.trace, option)

    def test_fork_preserves_trace_option(self) -> None:
        # [Silent Failure] Forked agents must not silently lose trace config.
        option = TraceOption.continual(ActionTrace)
        child = BaseAgent(name="worker", system_prompt="Work.", trace=option).fork(name="child")
        self.assertIs(child.trace, option)

    def test_fork_can_replace_trace_option(self) -> None:
        # [Edge Case] Explicit fork override works.
        option = TraceOption.continual(ActionTrace)
        replacement = TraceOption.continual(DebugTrace)
        child = BaseAgent(name="worker", system_prompt="Work.", trace=option).fork(name="child", trace=replacement)
        self.assertIs(child.trace, replacement)

    def test_non_linear_runtime_with_trace_raises(self) -> None:
        # [Hidden Assumption] Continual tracing is linear-runtime-only in v1.
        with self.assertRaises(ConfigurationError):
            BaseAgent(name="worker", system_prompt="Work.", runtime=AgentRuntimeType.MCTS_SEARCH, trace=TraceOption.continual(ActionTrace))

    def test_non_default_algorithm_with_trace_raises(self) -> None:
        # [Hidden Assumption] Continual tracing is default-loop-only in v1.
        with self.assertRaises(ConfigurationError):
            BaseAgent(name="worker", system_prompt="Work.", algorithm=ContextWindow.preset.no_raw_tool_outputs, trace=TraceOption.continual(ActionTrace))


class PromptCatalogTests(unittest.TestCase):
    def test_continual_trace_prompt_available(self) -> None:
        # [Hidden Failure] Prompt enum, JSON descriptor, and Markdown asset stay synchronized.
        from vidbyte.prompts import continual_trace_system_prompt

        self.assertEqual(continual_trace_system_prompt, Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT))


class PublicImportTests(unittest.TestCase):
    def test_trace_public_imports(self) -> None:
        # [Hidden Failure] Root and prebuilt public import paths work.
        from vidbyte import TraceOption as RootTraceOption
        from vidbyte.trace.prebuilt import ActionTrace as ImportedActionTrace

        self.assertIs(RootTraceOption, TraceOption)
        self.assertIs(ImportedActionTrace, ActionTrace)


class AgentRuntimeContinualTraceTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, *, trace: object | None = None, tools: Tools | None = None, max_iterations: int | None = None) -> AgentRuntime:
        # Builds a direct runtime with optional trace configuration for integration tests.
        return AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=tools or Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=max_iterations),
            trace=trace,
        )

    def _context(self, runtime: AgentRuntime) -> BaseContext:
        # Builds the minimal direct runtime context used by integration tests.
        return runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

    async def _run(self, runtime: AgentRuntime, runner: FakeRunner):
        # Executes the runtime against a fake runner handle.
        return await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

    async def test_final_response_contains_trace_metadata(self) -> None:
        # [Edge Case] A one-iteration main run still gets a forced final trace update.
        runner = FakeRunner([
            ResponseFactory.done("final"),
            ResponseFactory.update('{"trace": {"goal": "finish"}}'),
            ResponseFactory.done(),
        ])
        result = await self._run(self._runtime(trace=TraceOption.continual(ActionTrace)), runner)
        self.assertEqual(result.output, "final")
        self.assertEqual(result.metadata["trace"]["goal"], "finish")
        self.assertEqual(result.metadata["trace_metadata"]["update_count"], 1)

    async def test_updates_every_n_iterations(self) -> None:
        # [Silent Failure] Off-by-one interval bugs are caught by exact trace update count.
        @tool
        def lookup() -> str:
            return "ok"

        runner = FakeRunner([
            ResponseFactory.call("lookup"),
            ResponseFactory.call("lookup"),
            ResponseFactory.update('{"trace": {"actions_taken": ["two iterations"]}}'),
            ResponseFactory.done(),
            ResponseFactory.call("lookup"),
            ResponseFactory.done("final"),
            ResponseFactory.update('{"trace": {"current_status": "done"}}'),
            ResponseFactory.done(),
        ])
        result = await self._run(self._runtime(trace=TraceOption.continual(ActionTrace, every_n_iterations=2), tools=Tools([lookup])), runner)
        self.assertEqual(result.metadata["trace_metadata"]["update_count"], 2)
        self.assertEqual(result.metadata["trace"]["current_status"], "done")

    async def test_trace_update_failure_does_not_abort_main_agent(self) -> None:
        # [Hidden Failure] Trace-agent exception preserves main result and increments error metadata.
        runner = FakeRunner([ResponseFactory.done("final"), RuntimeError("trace failed")])
        result = await self._run(self._runtime(trace=TraceOption.continual(ActionTrace)), runner)
        self.assertEqual(result.output, "final")
        self.assertEqual(result.metadata["trace_metadata"]["error_count"], 1)

    async def test_trace_agent_tool_calls_do_not_pollute_main_tool_calls(self) -> None:
        # [Silent Failure] Main tool_call_count should not include trace-agent internal tools.
        runner = FakeRunner([
            ResponseFactory.done("final"),
            ResponseFactory.update('{"trace": {"goal": "finish"}}'),
            ResponseFactory.done(),
        ])
        result = await self._run(self._runtime(trace=TraceOption.continual(ActionTrace)), runner)
        self.assertEqual(result.metadata["tool_call_count"], 1)
        self.assertEqual(result.metadata["trace_metadata"]["update_count"], 1)

    async def test_trace_artifact_accumulates_across_updates(self) -> None:
        # [Silent Failure] Later updates merge over prior trace rather than resetting it.
        @tool
        def lookup() -> str:
            return "ok"

        runner = FakeRunner([
            ResponseFactory.call("lookup"),
            ResponseFactory.update('{"trace": {"goal": "ship", "actions_taken": ["lookup"]}}'),
            ResponseFactory.done(),
            ResponseFactory.done("final"),
            ResponseFactory.update('{"trace": {"current_status": "done"}}'),
            ResponseFactory.done(),
        ])
        result = await self._run(self._runtime(trace=TraceOption.continual(ActionTrace, every_n_iterations=1), tools=Tools([lookup])), runner)
        self.assertEqual(result.metadata["trace"]["goal"], "ship")
        self.assertEqual(result.metadata["trace"]["actions_taken"], ["lookup"])
        self.assertEqual(result.metadata["trace"]["current_status"], "done")

    async def test_disabled_trace_preserves_existing_runtime_metadata_shape(self) -> None:
        # [Hidden Assumption] Existing agents without trace remain behaviorally unchanged.
        runner = FakeRunner([ResponseFactory.done("final")])
        result = await self._run(self._runtime(), runner)
        self.assertNotIn("trace", result.metadata)
        self.assertNotIn("trace_metadata", result.metadata)


if __name__ == "__main__":
    unittest.main()
