from __future__ import annotations

import os
import types
import unittest
from typing import Any
from unittest.mock import patch

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput
from vidbyte.agents import AgentRuntime
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.errors import ConfigurationError, TracerConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.trace import Trace
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec, Tools
from vidbyte.tools.security import PermissionPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class RecordingTracer(TracerBase):
    """Test double that records every tracer call for assertion."""

    def __init__(self) -> None:
        self.traces_started: list[dict] = []
        self.traces_ended: list[dict] = []
        self.spans_started: list[dict] = []
        self.spans_ended: list[dict] = []
        self._counter = 0

    def _ctx(self, kind: str) -> SpanContext:
        self._counter += 1
        return SpanContext(metadata={"id": self._counter, "kind": kind})

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        ctx = self._ctx("trace")
        self.traces_started.append({"name": name, "attributes": attributes, "ctx": ctx})
        return ctx

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.traces_ended.append({"ctx": context, "output": output, "error": error})

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        ctx = self._ctx("span")
        self.spans_started.append({"name": name, "parent": parent, "attributes": attributes, "ctx": ctx})
        return ctx

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.spans_ended.append({"ctx": context, "output": output, "error": error})


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        return self.responses.pop(0)


class AlwaysDoneRunner:
    """Immediately returns isDone so tests don't need multi-turn setup."""

    def __init__(self) -> None:
        self._config = types.SimpleNamespace(provider="xai", model="grok-test")

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
        )


class WriteTool(BaseTool):
    def __init__(self) -> None:
        self.call_count = 0

    def spec(self) -> ToolSpec:
        return ToolSpec(name="write", description="Write.", permission=ToolPermission.WRITE)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.call_count += 1
        return ToolResult.success("write", "written")


async def _invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    return runner.run(prompt, **kwargs)


def _output_text(r: object) -> str:
    return str(getattr(r, "text", r))


def _output_metadata(r: object) -> dict:
    return {}


# ---------------------------------------------------------------------------
# NullTracer tests
# ---------------------------------------------------------------------------

class NullTracerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracer = NullTracer()

    def test_start_trace_returns_span_context(self) -> None:
        ctx = self.tracer.start_trace("agent.run")
        self.assertIsInstance(ctx, SpanContext)

    def test_start_span_returns_span_context(self) -> None:
        ctx = self.tracer.start_span("llm.call")
        self.assertIsInstance(ctx, SpanContext)

    def test_end_trace_accepts_no_args(self) -> None:
        ctx = self.tracer.start_trace("agent.run")
        self.tracer.end_trace(ctx)  # should not raise

    def test_end_trace_accepts_output_and_error(self) -> None:
        ctx = self.tracer.start_trace("agent.run")
        self.tracer.end_trace(ctx, output="hello", error=ValueError("boom"))

    def test_end_span_accepts_no_args(self) -> None:
        ctx = self.tracer.start_span("tool.call")
        self.tracer.end_span(ctx)  # should not raise

    def test_end_span_accepts_output_and_error(self) -> None:
        ctx = self.tracer.start_span("tool.call")
        self.tracer.end_span(ctx, output="result", error=RuntimeError("oops"))


# ---------------------------------------------------------------------------
# BaseAgent tracer wiring tests
# ---------------------------------------------------------------------------

class BaseAgentTracerWiringTests(unittest.IsolatedAsyncioTestCase):
    def _make_agent(self, tracer=None) -> BaseAgent:
        return BaseAgent(
            name="test-agent",
            system_prompt="Be helpful.",
            runner=AlwaysDoneRunner(),
            tracer=tracer,
        )

    def _make_agent_with_trace(self, trace=None) -> BaseAgent:
        # Builds a test agent through the new trace= alias.
        return BaseAgent(
            name="test-agent",
            system_prompt="Be helpful.",
            runner=AlwaysDoneRunner(),
            trace=trace,
        )

    def test_defaults_to_null_tracer_when_tracer_is_none(self) -> None:
        agent = self._make_agent(tracer=None)
        self.assertIsInstance(agent._tracer, NullTracer)

    def test_instantiates_tracer_class_when_class_is_passed(self) -> None:
        agent = self._make_agent(tracer=RecordingTracer)
        self.assertIsInstance(agent._tracer, RecordingTracer)

    def test_uses_tracer_instance_directly_when_instance_is_passed(self) -> None:
        tracer = RecordingTracer()
        agent = self._make_agent(tracer=tracer)
        self.assertIs(agent._tracer, tracer)

    async def test_start_trace_called_before_generate_reply(self) -> None:
        tracer = RecordingTracer()
        agent = self._make_agent(tracer=tracer)
        await agent.generate_reply("hello")
        self.assertEqual(len(tracer.traces_started), 1)
        self.assertEqual(tracer.traces_started[0]["name"], "agent.run")

    async def test_end_trace_called_after_generate_reply(self) -> None:
        tracer = RecordingTracer()
        agent = self._make_agent(tracer=tracer)
        await agent.generate_reply("hello")
        self.assertEqual(len(tracer.traces_ended), 1)
        self.assertIsNone(tracer.traces_ended[0]["error"])

    async def test_end_trace_called_with_error_on_failure(self) -> None:
        tracer = RecordingTracer()

        class BombRunner:
            def run(self, *a: object, **kw: object) -> None:
                raise RuntimeError("runner exploded")

        agent = BaseAgent(
            name="bomb-agent",
            system_prompt="Crash.",
            runner=BombRunner(),
            tracer=tracer,
        )
        with self.assertRaises(Exception):
            await agent.generate_reply("hello")

        self.assertEqual(len(tracer.traces_ended), 1)
        self.assertIsNotNone(tracer.traces_ended[0]["error"])

    def test_fork_propagates_tracer_instance(self) -> None:
        tracer = RecordingTracer()
        parent = self._make_agent(tracer=tracer)
        child = parent.fork(name="child-agent")
        self.assertIs(child._tracer, tracer)

    def test_trace_alias_accepts_off_preset(self) -> None:
        # Verifies Trace.off() can be supplied through the trace= alias.
        agent = self._make_agent_with_trace(trace=Trace.off())
        self.assertIsInstance(agent._tracer, NullTracer)

    def test_trace_alias_instantiates_tracer_class(self) -> None:
        # Verifies trace= preserves existing tracer class normalization.
        agent = self._make_agent_with_trace(trace=RecordingTracer)
        self.assertIsInstance(agent._tracer, RecordingTracer)

    def test_trace_alias_uses_tracer_instance_directly(self) -> None:
        # Verifies trace= preserves existing tracer instance normalization.
        tracer = RecordingTracer()
        agent = self._make_agent_with_trace(trace=tracer)
        self.assertIs(agent._tracer, tracer)

    def test_trace_alias_rejects_tracer_and_trace_together(self) -> None:
        # Verifies users cannot supply both tracing entry points at once.
        with self.assertRaises(ConfigurationError):
            BaseAgent(
                name="test-agent",
                system_prompt="Be helpful.",
                runner=AlwaysDoneRunner(),
                tracer=RecordingTracer(),
                trace=Trace.off(),
            )

    def test_fork_preserves_tracer_from_trace_alias(self) -> None:
        # Verifies forking keeps the resolved trace alias tracer instance.
        tracer = RecordingTracer()
        parent = self._make_agent_with_trace(trace=tracer)
        child = parent.fork(name="child-agent")
        self.assertIs(child._tracer, tracer)

    async def test_start_trace_attributes_include_agent_name(self) -> None:
        tracer = RecordingTracer()
        agent = self._make_agent(tracer=tracer)
        await agent.generate_reply("hi")
        attrs = tracer.traces_started[0]["attributes"]
        self.assertEqual(attrs.get("agent_name"), "test-agent")

    async def test_start_trace_attributes_include_prompt_model_and_safe_metadata(self) -> None:
        tracer = RecordingTracer()
        agent = self._make_agent(tracer=tracer)
        await agent.generate_reply(
            AgentInput("solve this", metadata={"case": "visible", "LANGSMITH_API_KEY": "secret"}),
            trace_metadata={"eval_suite": "mbpp", "XAI_API_KEY": "secret"},
        )
        attrs = tracer.traces_started[0]["attributes"]
        self.assertEqual(attrs["prompt"], "solve this")
        self.assertEqual(attrs["provider"], "xai")
        self.assertEqual(attrs["model"], "grok-test")
        self.assertEqual(attrs["metadata"]["case"], "visible")
        self.assertEqual(attrs["metadata"]["eval_suite"], "mbpp")
        self.assertNotIn("LANGSMITH_API_KEY", attrs["metadata"])
        self.assertNotIn("XAI_API_KEY", attrs["metadata"])


# ---------------------------------------------------------------------------
# AgentRuntime span hooks tests
# ---------------------------------------------------------------------------

class AgentRuntimeSpanTests(unittest.IsolatedAsyncioTestCase):
    def _make_runtime(self, tracer: TracerBase) -> AgentRuntime:
        return AgentRuntime(
            agent_name="rt-agent",
            system_prompt="system",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(),
            tracer=tracer,
        )

    async def test_emits_llm_span_per_invoke_runner_call(self) -> None:
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
        ])
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun(
            "prompt",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=context,
        )
        llm_spans = [s for s in tracer.spans_started if s["name"] == "llm.call"]
        self.assertEqual(len(llm_spans), 1)

    async def test_llm_span_is_closed_after_invoke_runner(self) -> None:
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
        ])
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun(
            "prompt",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=context,
        )
        # At minimum the LLM span is closed; isDone tool also closes a span.
        llm_spans_started = [s for s in tracer.spans_started if s["name"] == "llm.call"]
        self.assertEqual(len(llm_spans_started), 1)
        self.assertGreaterEqual(len(tracer.spans_ended), 1)

    async def test_llm_span_parent_is_trace_context(self) -> None:
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        root_ctx = SpanContext(metadata={"id": 999})
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
        ])
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun(
            "prompt",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=context,
            trace_context=root_ctx,
        )
        llm_span = next(s for s in tracer.spans_started if s["name"] == "llm.call")
        self.assertIs(llm_span["parent"], root_ctx)

    async def test_llm_span_inputs_include_prompt_model_and_safe_metadata(self) -> None:
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
        ])
        runner._config = types.SimpleNamespace(provider="xai", model="grok-test")
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun(
            "prompt",
            handle=RunnerHandle(runner=runner, provider="xai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=context,
            metadata={"eval_suite": "mbpp", "LANGSMITH_API_KEY": "secret"},
        )
        attrs = next(s for s in tracer.spans_started if s["name"] == "llm.call")["attributes"]
        self.assertEqual(attrs["agent_name"], "rt-agent")
        self.assertEqual(attrs["provider"], "xai")
        self.assertEqual(attrs["model"], "grok-test")
        self.assertEqual(attrs["prompt"], "prompt")
        self.assertEqual(attrs["system"], "System prompt:\nsys")
        self.assertEqual(attrs["metadata"], {"eval_suite": "mbpp"})
        self.assertEqual(
            attrs["messages"],
            (
                {"role": "system", "content": "System prompt:\nsys"},
                {"role": "user", "content": "prompt"},
            ),
        )
        self.assertEqual(attrs["input_messages"], attrs["messages"])
        self.assertNotIn("history_messages", attrs)

    async def test_llm_span_messages_include_full_input_when_history_exists(self) -> None:
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        runner = FakeRunner([
            FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}),
        ])
        handle = RunnerHandle(runner=runner, provider="xai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata)

        inputs = runtime._llm_trace_inputs(
            handle,
            "prompt",
            {
                "system": "System prompt:\nsys",
                "messages": ({"role": "assistant", "content": "draft"},),
            },
            "xai",
            1,
            2,
            {},
        )

        self.assertEqual(
            inputs["messages"],
            (
                {"role": "system", "content": "System prompt:\nsys"},
                {"role": "assistant", "content": "draft"},
                {"role": "user", "content": "prompt"},
            ),
        )
        self.assertEqual(inputs["input_messages"], inputs["messages"])
        self.assertEqual(inputs["history_messages"], ({"role": "assistant", "content": "draft"},))

    async def test_tool_span_emitted_per_tool_execution(self) -> None:
        tracer = RecordingTracer()
        tool = WriteTool()
        tools = Tools().add(tool)
        runtime = AgentRuntime(
            agent_name="rt-agent",
            system_prompt="sys",
            tools=tools,
            permission_policy=PermissionPolicy(),
            tracer=tracer,
        )
        runner = FakeRunner([
            FakeResponse(
                "",
                {"output": [
                    {"type": "function_call", "name": "write", "arguments": "{}"},
                    {"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'},
                ]},
            ),
        ])
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun(
            "prompt",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke_runner, extract_text=_output_text, extract_metadata=_output_metadata),
            context=context,
        )
        tool_spans = [s for s in tracer.spans_started if s["name"] == "tool.call"]
        self.assertGreaterEqual(len(tool_spans), 1)

    async def test_tool_span_closed_even_when_tool_raises(self) -> None:
        tracer = RecordingTracer()

        class BombTool(BaseTool):
            def spec(self) -> ToolSpec:
                return ToolSpec(name="bomb", description="Explodes.")
            async def execute(self, call: ToolCall) -> ToolResult:
                raise RuntimeError("tool boom")

        tools = Tools().add(BombTool())
        runtime = AgentRuntime(
            agent_name="rt-agent",
            system_prompt="sys",
            tools=tools,
            permission_policy=PermissionPolicy(),
            tracer=tracer,
        )
        call = ToolCall(tool_name="bomb", arguments={})
        await runtime.execute_tool_call(call, provider="openai")
        tool_spans_ended = [s for s in tracer.spans_ended]
        self.assertEqual(len(tool_spans_ended), 1)
        self.assertIsNotNone(tool_spans_ended[0]["error"])


# ---------------------------------------------------------------------------
# TracerConfigurationError tests (import-error simulation)
# ---------------------------------------------------------------------------

class TracerConfigurationErrorTests(unittest.TestCase):
    def test_langfuse_raises_on_missing_install(self) -> None:
        from vidbyte.providers.tracing.langfuse import LangfuseTracer
        with patch.dict("sys.modules", {"langfuse": None}):
            with self.assertRaises(TracerConfigurationError) as cm:
                LangfuseTracer(public_key="pk", secret_key="sk")
            self.assertIn("langfuse", str(cm.exception).lower())

    def test_langfuse_raises_on_missing_credentials(self) -> None:
        import sys
        if "langfuse" not in sys.modules:
            self.skipTest("langfuse not installed; skipping credential test")
        from vidbyte.providers.tracing.langfuse import LangfuseTracer
        import os
        env_backup = {k: os.environ.pop(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if k in os.environ}
        try:
            with self.assertRaises(TracerConfigurationError):
                LangfuseTracer()
        finally:
            os.environ.update(env_backup)

    def test_langsmith_raises_on_missing_install(self) -> None:
        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": None}):
            with self.assertRaises(TracerConfigurationError) as cm:
                LangSmithTracer(api_key="key")
            self.assertIn("langsmith", str(cm.exception).lower())

    def test_langsmith_raises_on_missing_credentials(self) -> None:
        import sys
        if "langsmith" not in sys.modules:
            self.skipTest("langsmith not installed; skipping credential test")
        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        import os
        env_backup = {}
        if "LANGSMITH_API_KEY" in os.environ:
            env_backup["LANGSMITH_API_KEY"] = os.environ.pop("LANGSMITH_API_KEY")
        try:
            with self.assertRaises(TracerConfigurationError):
                LangSmithTracer()
        finally:
            os.environ.update(env_backup)

    def test_phoenix_raises_on_missing_install(self) -> None:
        from vidbyte.providers.tracing.phoenix import PhoenixTracer
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.trace": None}):
            with self.assertRaises(TracerConfigurationError) as cm:
                PhoenixTracer()
            self.assertIn("opentelemetry", str(cm.exception).lower())


class LangSmithTracerDiagnosticsTests(unittest.TestCase):
    def _module_with_client(self, client_cls: type[Any]) -> types.ModuleType:
        # Builds a fake langsmith module exposing the requested Client class.
        module = types.ModuleType("langsmith")
        module.Client = client_cls
        return module

    def test_langsmith_omits_api_url_without_endpoint(self) -> None:
        # [Edge Case] Client construction should not pass api_url unless endpoint is configured.
        calls: list[dict[str, Any]] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                calls.append(dict(kwargs))

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            with patch.dict(os.environ, {}, clear=True):
                LangSmithTracer(api_key="test-key")
        self.assertEqual(calls, [{"api_key": "test-key", "omit_traced_runtime_info": True}])

    def test_langsmith_endpoint_env_passed_as_api_url(self) -> None:
        # [Edge Case] LANGSMITH_ENDPOINT must be forwarded to the LangSmith client.
        calls: list[dict[str, Any]] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                calls.append(dict(kwargs))

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            with patch.dict(os.environ, {"LANGSMITH_ENDPOINT": "https://api.smith.langchain.com"}, clear=True):
                LangSmithTracer(api_key="test-key")
        self.assertEqual(calls, [{"api_key": "test-key", "omit_traced_runtime_info": True, "api_url": "https://api.smith.langchain.com"}])

    def test_langsmith_can_include_runtime_info_when_requested(self) -> None:
        # [Edge Case] Callers can opt back into LangSmith's automatic runtime metadata.
        calls: list[dict[str, Any]] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                calls.append(dict(kwargs))

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            with patch.dict(os.environ, {}, clear=True):
                LangSmithTracer(api_key="test-key", include_runtime_info=True)
        self.assertEqual(calls, [{"api_key": "test-key", "omit_traced_runtime_info": False}])

    def test_langsmith_strict_create_failure_raises_sanitized_error(self) -> None:
        # [Hidden Failure] Strict mode must fail loudly without leaking key-like strings.
        class Client:
            def __init__(self, **kwargs: Any) -> None:
                pass

            def create_run(self, **kwargs: Any) -> None:
                raise RuntimeError("bad key lsv2_pt_secret and xai-secret")

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            tracer = LangSmithTracer(api_key="test-key", strict=True)
            with self.assertRaises(TracerConfigurationError) as cm:
                tracer.start_trace("agent.run")
        message = str(cm.exception)
        self.assertIn("lsv2_[REDACTED]", message)
        self.assertIn("xai-[REDACTED]", message)
        self.assertNotIn("lsv2_pt_secret", message)
        self.assertNotIn("xai-secret", message)

    def test_langsmith_nonstrict_records_last_error(self) -> None:
        # [Silent Failure] Non-strict mode should keep the run alive while preserving diagnostics.
        class Client:
            def __init__(self, **kwargs: Any) -> None:
                pass

            def create_run(self, **kwargs: Any) -> None:
                raise RuntimeError("delivery failed lsv2_pt_secret")

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            tracer = LangSmithTracer(api_key="test-key")
            tracer.start_trace("agent.run")
        self.assertIsNotNone(tracer.last_error)
        self.assertIn("lsv2_[REDACTED]", str(tracer.last_error))

    def test_langsmith_strict_update_failure_raises(self) -> None:
        # [Hidden Failure] Strict mode must also fail when update_run is rejected.
        class Client:
            def __init__(self, **kwargs: Any) -> None:
                pass

            def create_run(self, **kwargs: Any) -> None:
                pass

            def update_run(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("update rejected")

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            tracer = LangSmithTracer(api_key="test-key", strict=True)
            context = tracer.start_trace("agent.run")
            with self.assertRaises(TracerConfigurationError):
                tracer.end_trace(context, output="ok")

    def test_langsmith_update_uses_datetime_end_time(self) -> None:
        # [Hidden Assumption] LangSmith update_run expects a datetime-like end_time.
        captured: list[Any] = []

        class Client:
            def __init__(self, **kwargs: Any) -> None:
                pass

            def create_run(self, **kwargs: Any) -> None:
                pass

            def update_run(self, *args: Any, **kwargs: Any) -> None:
                captured.append(kwargs["end_time"])

        from vidbyte.providers.tracing.langsmith import LangSmithTracer
        with patch.dict("sys.modules", {"langsmith": self._module_with_client(Client)}):
            tracer = LangSmithTracer(api_key="test-key", strict=True)
            context = tracer.start_trace("agent.run")
            tracer.end_trace(context, output="ok")
        self.assertTrue(hasattr(captured[0], "isoformat"))


# ---------------------------------------------------------------------------
# Cancellation / BaseException trace-closure tests  (#142)
# ---------------------------------------------------------------------------

class CancelledRunner:
    """Raises asyncio.CancelledError on the first invoke to simulate task cancellation."""

    def __init__(self) -> None:
        self._config = types.SimpleNamespace(provider="xai", model="grok-test")

    def run(self, prompt: str, **kwargs: object) -> None:
        raise NotImplementedError("sync path unused")


async def _invoke_cancelled(runner: object, prompt: str, **kwargs: object) -> None:
    import asyncio
    raise asyncio.CancelledError("simulated task cancellation")


class GenerateReplyCancellationTests(unittest.IsolatedAsyncioTestCase):
    """Verifies generate_reply closes its root trace on CancelledError."""

    def _make_cancelling_agent(self, tracer: TracerBase) -> BaseAgent:
        return BaseAgent(
            name="cancel-agent",
            system_prompt="Be helpful.",
            runner=CancelledRunner(),
            tracer=tracer,
        )

    async def test_root_trace_closed_on_cancelled_error(self) -> None:
        # [Hidden Failure] CancelledError previously bypassed end_trace, leaving trace pending.
        import asyncio
        tracer = RecordingTracer()
        agent = self._make_cancelling_agent(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await agent.generate_reply("hello")
        self.assertEqual(len(tracer.traces_ended), 1, "root trace must be closed exactly once")

    async def test_root_trace_closed_with_error_on_cancelled_error(self) -> None:
        # [Silent Failure] Trace must not be closed as success when cancelled.
        import asyncio
        tracer = RecordingTracer()
        agent = self._make_cancelling_agent(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await agent.generate_reply("hello")
        self.assertIsNotNone(tracer.traces_ended[0]["error"])

    async def test_cancelled_error_propagates_after_trace_close(self) -> None:
        # [Hidden Assumption] Callers expect CancelledError (or wrapping) to propagate.
        import asyncio
        tracer = RecordingTracer()
        agent = self._make_cancelling_agent(tracer)
        raised = False
        try:
            await agent.generate_reply("hello")
        except (asyncio.CancelledError, Exception):
            raised = True
        self.assertTrue(raised, "exception must propagate to caller after trace is closed")

    async def test_active_prompt_reset_on_cancelled_error(self) -> None:
        # [Edge Case] Agent _active_prompt must be cleared even when CancelledError is raised.
        import asyncio
        tracer = RecordingTracer()
        agent = self._make_cancelling_agent(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await agent.generate_reply("hello")
        self.assertEqual(agent._active_prompt, "")

    async def test_root_trace_not_double_closed_on_normal_exception(self) -> None:
        # [Edge Case] Standard Exception path must still close the trace exactly once.
        tracer = RecordingTracer()

        class BombRunner:
            def run(self, *a: object, **kw: object) -> None:
                raise RuntimeError("explode")

        agent = BaseAgent(
            name="bomb-agent",
            system_prompt="Crash.",
            runner=BombRunner(),
            tracer=tracer,
        )
        with self.assertRaises(Exception):
            await agent.generate_reply("hello")
        self.assertEqual(len(tracer.traces_ended), 1, "exactly one end_trace call on Exception path")

    async def test_end_trace_receives_base_exception_instance(self) -> None:
        # [Silent Failure] The error recorded must be the actual BaseException, not None or a string.
        import asyncio
        tracer = RecordingTracer()
        agent = self._make_cancelling_agent(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await agent.generate_reply("hello")
        recorded_error = tracer.traces_ended[0]["error"]
        self.assertIsInstance(recorded_error, BaseException)


class LlmSpanCancellationTests(unittest.IsolatedAsyncioTestCase):
    """Verifies _invoke_with_middleware closes the llm.call span on CancelledError."""

    def _make_runtime(self, tracer: TracerBase) -> AgentRuntime:
        return AgentRuntime(
            agent_name="rt-agent",
            system_prompt="system",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(),
            tracer=tracer,
        )

    def _cancelling_handle(self) -> RunnerHandle:
        # Returns a RunnerHandle whose invoke raises CancelledError.
        return RunnerHandle(
            runner=CancelledRunner(),
            provider="xai",
            invoke=_invoke_cancelled,
            extract_text=_output_text,
            extract_metadata=_output_metadata,
        )

    async def _run_with_stub_trace_inputs(self, runtime: AgentRuntime, handle: RunnerHandle) -> None:
        # Runs arun with _llm_trace_inputs stubbed to {} to bypass the pre-existing
        # duplicate-definition bug that causes TypeError before invoke is reached.
        from unittest.mock import patch
        from vidbyte.lib.dataclasses.context import BaseAgentContext
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        with patch.object(type(runtime), "_llm_trace_inputs", return_value={}):
            await runtime.arun("prompt", handle=handle, context=context)

    async def test_llm_span_closed_on_cancelled_error(self) -> None:
        # [Hidden Failure] CancelledError previously bypassed end_span for llm.call.
        import asyncio
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await self._run_with_stub_trace_inputs(runtime, self._cancelling_handle())
        llm_spans_ended = [s for s in tracer.spans_ended if any(
            started["name"] == "llm.call" and started["ctx"] is s["ctx"]
            for started in tracer.spans_started
        )]
        self.assertEqual(len(llm_spans_ended), 1, "llm.call span must be closed exactly once on cancellation")

    async def test_llm_span_closed_with_error_on_cancelled_error(self) -> None:
        # [Silent Failure] llm.call span must not be marked as success on cancellation.
        import asyncio
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        with self.assertRaises((asyncio.CancelledError, Exception)):
            await self._run_with_stub_trace_inputs(runtime, self._cancelling_handle())
        llm_span_end = next(
            (s for s in tracer.spans_ended if any(
                started["name"] == "llm.call" and started["ctx"] is s["ctx"]
                for started in tracer.spans_started
            )),
            None,
        )
        self.assertIsNotNone(llm_span_end)
        self.assertIsNotNone(llm_span_end["error"])

    async def test_cancelled_error_propagates_from_runtime(self) -> None:
        # [Hidden Assumption] CancelledError (or wrapping) must reach the caller after span close.
        import asyncio
        tracer = RecordingTracer()
        runtime = self._make_runtime(tracer)
        raised = False
        try:
            await self._run_with_stub_trace_inputs(runtime, self._cancelling_handle())
        except (asyncio.CancelledError, Exception):
            raised = True
        self.assertTrue(raised)


class TracerBaseContractTests(unittest.TestCase):
    """Verifies the widened BaseException type hint is structurally correct."""

    def test_end_trace_accepts_base_exception_without_type_error(self) -> None:
        # [Hidden Assumption] end_trace must accept any BaseException, not just Exception.
        import asyncio
        tracer = RecordingTracer()
        ctx = tracer.start_trace("agent.run")
        tracer.end_trace(ctx, error=asyncio.CancelledError("cancelled"))
        self.assertEqual(len(tracer.traces_ended), 1)
        self.assertIsInstance(tracer.traces_ended[0]["error"], asyncio.CancelledError)

    def test_end_span_accepts_base_exception_without_type_error(self) -> None:
        # [Hidden Assumption] end_span must accept any BaseException, not just Exception.
        import asyncio
        tracer = RecordingTracer()
        ctx = tracer.start_span("llm.call")
        tracer.end_span(ctx, error=asyncio.CancelledError("cancelled"))
        self.assertEqual(len(tracer.spans_ended), 1)
        self.assertIsInstance(tracer.spans_ended[0]["error"], asyncio.CancelledError)


if __name__ == "__main__":
    unittest.main()

