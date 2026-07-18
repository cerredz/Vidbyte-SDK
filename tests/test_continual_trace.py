from __future__ import annotations

import re
import unittest

from pydantic import BaseModel, Field

from tests.agent_test_support import build_test_agent
from vidbyte import Agent, AgentForkSettings, TraceOption, TraceSchema
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec
from vidbyte.trace.continual import ActionTrace, ContinualTraceAgent, ContinualTraceMiddleware
from vidbyte.trace.continual.middleware import RESULT_METADATA_KEY, _TraceRunState
from vidbyte.trace.continual.tools import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool


class _ProgressModel(BaseModel):
    """Progress trace."""

    goal: str = Field(description="The goal.")
    steps: list[str] = Field(default_factory=list, description="Ordered steps taken.")
    done: bool = Field(default=False, description="Whether the work is complete.")


def _progress_schema() -> TraceSchema:
    return TraceSchema.from_model(_ProgressModel, name="progress")


def _call(trace: object) -> ToolCall:
    return ToolCall(tool_name=UPDATE_TRACE_TOOL_NAME, arguments={"trace": trace})


# ---------------------------------------------------------------------------
# Schema / option validation
# ---------------------------------------------------------------------------
class TraceOptionTests(unittest.TestCase):
    def test_continual_from_pydantic_model(self) -> None:  # [Edge Case]
        option = TraceOption.continual(_ProgressModel)
        self.assertTrue(option.enabled)
        self.assertEqual(option.schema.fields["steps"].type, TraceFieldType.ARRAY)
        self.assertEqual(option.schema.fields["done"].type, TraceFieldType.BOOLEAN)

    def test_continual_from_mapping_defaults_to_string(self) -> None:  # [Hidden Assumption]
        option = TraceOption.continual({"summary": "A running summary."})
        self.assertEqual(option.schema.fields["summary"].type, TraceFieldType.STRING)

    def test_rejects_empty_schema_mapping(self) -> None:  # [Edge Case]
        with self.assertRaises(ValueError):
            TraceOption.continual({})

    def test_rejects_non_positive_interval(self) -> None:  # [Edge Case]
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                TraceOption.continual(_ProgressModel, every_n_iterations=bad)

    def test_rejects_out_of_range_max_iterations(self) -> None:  # [Edge Case]
        for bad in (0, 4):
            with self.assertRaises(ValueError):
                TraceOption.continual(_ProgressModel, max_trace_iterations=bad)

    def test_from_model_requires_field_description(self) -> None:  # [Hidden Assumption]
        class NoDesc(BaseModel):
            field_a: str

        with self.assertRaises(ValueError):
            TraceSchema.from_model(NoDesc)

    def test_initial_artifact_keys_all_none(self) -> None:  # [Edge Case]
        artifact = _progress_schema().initial_artifact()
        self.assertEqual(artifact, {"goal": None, "steps": None, "done": None})

    def test_single_field_schema(self) -> None:  # [Edge Case]
        schema = TraceSchema(name="solo", fields={"only": TraceField(description="d")})
        self.assertEqual(list(schema.fields), ["only"])


# ---------------------------------------------------------------------------
# UpdateTraceTool merge / type behavior
# ---------------------------------------------------------------------------
class UpdateTraceToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_appends_array_across_calls(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(_progress_schema())
        await tool.execute(_call({"steps": ["a"]}))
        await tool.execute(_call({"steps": ["b"]}))
        self.assertEqual(tool.current_trace()["steps"], ["a", "b"])

    async def test_appends_dedupes_exact_duplicate(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(_progress_schema())
        await tool.execute(_call({"steps": ["a"]}))
        await tool.execute(_call({"steps": ["a", "c"]}))
        self.assertEqual(tool.current_trace()["steps"], ["a", "c"])

    async def test_deep_merges_object_field(self) -> None:  # [Silent Failure]
        schema = TraceSchema(name="o", fields={"meta": TraceField(description="d", type=TraceFieldType.OBJECT)})
        tool = UpdateTraceTool(schema)
        await tool.execute(_call({"meta": {"x": 1}}))
        await tool.execute(_call({"meta": {"y": 2}}))
        self.assertEqual(tool.current_trace()["meta"], {"x": 1, "y": 2})

    async def test_replaces_scalar_and_preserves_omitted(self) -> None:  # [Silent Failure]
        tool = UpdateTraceTool(_progress_schema())
        await tool.execute(_call({"goal": "first", "steps": ["a"]}))
        await tool.execute(_call({"goal": "second"}))
        trace = tool.current_trace()
        self.assertEqual(trace["goal"], "second")
        self.assertEqual(trace["steps"], ["a"])

    async def test_drops_unknown_keys(self) -> None:  # [Hidden Assumption]
        tool = UpdateTraceTool(_progress_schema())
        await tool.execute(_call({"goal": "g", "unknown": "x"}))
        self.assertNotIn("unknown", tool.current_trace())

    async def test_type_mismatch_returns_error(self) -> None:  # [Hidden Failure]
        tool = UpdateTraceTool(_progress_schema())
        result = await tool.execute(_call({"steps": "not-a-list"}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("output shape mismatch", result.output)
        self.assertEqual(tool.current_trace()["steps"], None)

    async def test_non_object_trace_returns_error(self) -> None:  # [Edge Case]
        tool = UpdateTraceTool(_progress_schema())
        result = await tool.execute(_call("nope"))
        self.assertEqual(result.status.value, "error")

    def test_input_schema_disallows_additional_properties(self) -> None:  # [Hidden Assumption]
        schema_dict = UpdateTraceTool(_progress_schema()).spec().input_schema
        self.assertFalse(schema_dict["properties"]["trace"]["additionalProperties"])


# ---------------------------------------------------------------------------
# Middleware cadence + safety (pure, with stubbed trace agent)
# ---------------------------------------------------------------------------
def _ctx(hook: MiddlewareHook, *, iteration_count: int, run_state: dict) -> MiddlewareContext:
    return MiddlewareContext(hook=hook, agent_name="main", iteration_count=iteration_count, run_state=run_state)


class _StubUpdates:
    def __init__(self, artifact: dict, error: str | None = None, raises: bool = False) -> None:
        self.artifact = artifact
        self.error = error
        self.raises = raises
        self.calls = 0

    async def run_update(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls += 1
        if self.raises:
            raise RuntimeError("boom")
        return dict(self.artifact), self.error


class ContinualTraceMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def _middleware(self, stub: _StubUpdates, *, every_n: int = 2) -> ContinualTraceMiddleware:
        option = TraceOption.continual(_ProgressModel, every_n_iterations=every_n)
        mw = ContinualTraceMiddleware(option, source_agent=object())
        from vidbyte.trace.continual import agent as agent_module

        self._orig = agent_module.ContinualTraceAgent.run_update
        agent_module.ContinualTraceAgent.run_update = classmethod(  # type: ignore[assignment]
            lambda cls, *a, **k: stub.run_update(*a, **k)
        )
        self.addCleanup(lambda: setattr(agent_module.ContinualTraceAgent, "run_update", self._orig))
        return mw

    async def test_no_update_on_non_interval_iterations(self) -> None:  # [Silent Failure]
        stub = _StubUpdates({"goal": "g"})
        mw = self._middleware(stub, every_n=2)
        run_state: dict = {}
        await mw.before_run(_ctx(MiddlewareHook.BEFORE_RUN, iteration_count=0, run_state=run_state))
        await mw.after_iteration(_ctx(MiddlewareHook.AFTER_ITERATION, iteration_count=1, run_state=run_state))
        self.assertEqual(stub.calls, 0)

    async def test_updates_on_interval(self) -> None:  # [Edge Case]
        stub = _StubUpdates({"goal": "g"})
        mw = self._middleware(stub, every_n=2)
        run_state: dict = {}
        await mw.before_run(_ctx(MiddlewareHook.BEFORE_RUN, iteration_count=0, run_state=run_state))
        await mw.after_iteration(_ctx(MiddlewareHook.AFTER_ITERATION, iteration_count=2, run_state=run_state))
        self.assertEqual(stub.calls, 1)
        self.assertEqual(run_state[RESULT_METADATA_KEY]["trace"], {"goal": "g"})

    async def test_after_run_not_double_when_interval_coincides(self) -> None:  # [Silent Failure]
        stub = _StubUpdates({"goal": "g"})
        mw = self._middleware(stub, every_n=2)
        run_state: dict = {}
        await mw.before_run(_ctx(MiddlewareHook.BEFORE_RUN, iteration_count=0, run_state=run_state))
        await mw.after_iteration(_ctx(MiddlewareHook.AFTER_ITERATION, iteration_count=2, run_state=run_state))
        await mw.after_run(_ctx(MiddlewareHook.AFTER_RUN, iteration_count=2, run_state=run_state))
        self.assertEqual(stub.calls, 1)

    async def test_after_run_forces_final_update(self) -> None:  # [Edge Case]
        stub = _StubUpdates({"goal": "g"})
        mw = self._middleware(stub, every_n=5)
        run_state: dict = {}
        await mw.before_run(_ctx(MiddlewareHook.BEFORE_RUN, iteration_count=0, run_state=run_state))
        await mw.after_iteration(_ctx(MiddlewareHook.AFTER_ITERATION, iteration_count=3, run_state=run_state))
        await mw.after_run(_ctx(MiddlewareHook.AFTER_RUN, iteration_count=3, run_state=run_state))
        self.assertEqual(stub.calls, 1)

    async def test_fail_open_records_error(self) -> None:  # [Hidden Failure]
        stub = _StubUpdates({"goal": "g"}, raises=True)
        mw = self._middleware(stub, every_n=1)
        run_state: dict = {}
        await mw.before_run(_ctx(MiddlewareHook.BEFORE_RUN, iteration_count=0, run_state=run_state))
        decision = await mw.after_iteration(_ctx(MiddlewareHook.AFTER_ITERATION, iteration_count=1, run_state=run_state))
        self.assertEqual(decision.action.value, "continue")
        self.assertGreaterEqual(run_state[RESULT_METADATA_KEY]["trace_metadata"]["error_count"], 1)

    def test_middleware_is_fail_open(self) -> None:  # [Hidden Assumption]
        self.assertFalse(ContinualTraceMiddleware.fail_closed)


# ---------------------------------------------------------------------------
# BaseAgent wiring
# ---------------------------------------------------------------------------
class BaseAgentTraceWiringTests(unittest.TestCase):
    def test_non_linear_runtime_rejects_trace_option(self) -> None:  # [Hidden Assumption]
        with self.assertRaises(ConfigurationError):
            Agent(name="a", system_prompt="s", runtime="mcts_search", trace_option=TraceOption.continual(_ProgressModel))

    def test_fork_preserves_trace_option(self) -> None:  # [Edge Case]
        agent = Agent(name="a", system_prompt="s", trace_option=TraceOption.continual(_ProgressModel))
        child = agent.fork(AgentForkSettings(name="b"))
        self.assertIsNotNone(child._trace_option)
        self.assertTrue(child._trace_option.enabled)


# ---------------------------------------------------------------------------
# Integration: main agent + trace sub-agent over a shared scripted runner
# ---------------------------------------------------------------------------
class _Lookup(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Look something up.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("lookup", "found")


def _fc(name: str, arguments: str, call_id: str) -> dict:
    return {"output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}]}


class _Resp:
    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


class ScriptedRunner:
    """Discriminates main-agent vs trace-agent calls by prompt content."""

    def __init__(self, *, trace_raises: bool = False) -> None:
        self.trace_raises = trace_raises
        self.main_payloads: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> _Resp:
        is_trace = "<trace_schema>" in prompt
        has_messages = "messages" in kwargs
        if is_trace:
            if self.trace_raises:
                raise RuntimeError("trace model failure")
            if not has_messages:
                iteration = self._iteration_from_prompt(prompt)
                return _Resp(_fc("updateTrace", '{"trace": {"steps": ["step-%d"]}}' % iteration, "t1"))
            return _Resp(_fc("isDone", '{"final_answer": "traced"}', "t2"))
        self.main_payloads.append(prompt + str(kwargs.get("messages", "")))
        if not has_messages:
            return _Resp(_fc("lookup", "{}", "m1"))
        return _Resp(_fc("isDone", '{"final_answer": "done"}', "m2"))

    @staticmethod
    def _iteration_from_prompt(prompt: str) -> int:
        match = re.search(r'"iteration_count":\s*(\d+)', prompt)
        return int(match.group(1)) if match else 0


class ContinualTraceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_accumulates_and_surfaces(self) -> None:  # [Silent Failure]
        runner = ScriptedRunner()
        agent = build_test_agent(
            name="worker",
            system_prompt="Work.",
            runner=runner,
            tools=[_Lookup()],
            trace_option=TraceOption.continual(_ProgressModel, every_n_iterations=1),
        )
        reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        trace = reply.metadata["trace"]
        self.assertIn("step-1", trace["steps"])
        self.assertIn("step-2", trace["steps"])
        self.assertGreaterEqual(reply.metadata["trace_metadata"]["update_count"], 2)
        self.assertEqual(agent.last_trace, trace)

    async def test_trace_never_leaks_into_main_context(self) -> None:  # [Silent Failure]
        runner = ScriptedRunner()
        agent = build_test_agent(
            name="worker",
            system_prompt="Work.",
            runner=runner,
            tools=[_Lookup()],
            trace_option=TraceOption.continual(_ProgressModel, every_n_iterations=1),
        )
        await agent.arun("task")
        for payload in runner.main_payloads:
            self.assertNotIn("step-1", payload)
            self.assertNotIn("step-2", payload)
            self.assertNotIn("trace_so_far", payload)

    async def test_main_run_succeeds_when_trace_fails(self) -> None:  # [Hidden Failure]
        runner = ScriptedRunner(trace_raises=True)
        agent = build_test_agent(
            name="worker",
            system_prompt="Work.",
            runner=runner,
            tools=[_Lookup()],
            trace_option=TraceOption.continual(_ProgressModel, every_n_iterations=1),
        )
        reply = await agent.arun("task")
        self.assertEqual(reply.content, "done")
        self.assertGreaterEqual(reply.metadata["trace_metadata"]["error_count"], 1)


if __name__ == "__main__":
    unittest.main()
