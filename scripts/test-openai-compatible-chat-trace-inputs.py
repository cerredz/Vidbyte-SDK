from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.providers.xai import XAIProvider
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


class FakeTransport:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        # Captures request bodies and returns a configurable successful JSON response.
        self.response = response or {"choices": [{"message": {"content": "ok"}}]}
        self.requests: list[dict[str, object]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        # Records the outbound HTTP request shape without performing network I/O.
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {}), "timeout_seconds": timeout_seconds})
        return HttpResponse(status_code=200, body=json.dumps(self.response), headers={})


class FakeResponse:
    def __init__(self, text: str, raw: dict[str, Any] | None = None) -> None:
        # Stores text plus the raw provider shape used by tool-call parsing.
        self.text = text
        self.raw = raw or {"choices": [{"message": {"content": text}}]}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        # Serves responses in order and exposes a runner config for trace model names.
        self.responses = list(responses)
        self._config = type("Config", (), {"model": "grok-test"})()

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        # Returns the next fake model response and records no external side effects.
        if not self.responses:
            raise AssertionError("FakeRunner exhausted")
        return self.responses.pop(0)


class RecordingTracer(TracerBase):
    def __init__(self) -> None:
        # Records trace lifecycle calls for local assertions.
        self.spans_started: list[dict[str, Any]] = []
        self.spans_ended: list[dict[str, Any]] = []

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Returns a simple trace context for compatibility.
        return SpanContext(metadata={"name": name, "attributes": dict(attributes)})

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Accepts root trace completion without side effects.
        return None

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Records child span attributes for verification.
        context = SpanContext(metadata={"name": name, "attributes": dict(attributes)})
        self.spans_started.append({"name": name, "parent": parent, "attributes": dict(attributes), "ctx": context})
        return context

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Records span completion for verification.
        self.spans_ended.append({"ctx": context, "output": output, "error": error})


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    # Invokes the fake runner through the RunnerHandle async contract.
    return runner.run(prompt, **kwargs)


def output_text(response: object) -> str:
    # Extracts text from fake responses.
    return str(getattr(response, "text", response))


def output_metadata(response: object) -> dict[str, Any]:
    # Returns empty runner metadata for fake responses.
    return {}


class VerificationRunner:
    def __init__(self) -> None:
        # Tracks pass/fail counts for design-plan verification cases.
        self.passed = 0
        self.total = 0

    def run(self) -> int:
        # Executes every verification case and returns a process exit code.
        checks = (
            self.test_provider_includes_system_before_history,
            self.test_provider_preserves_no_history_behavior,
            self.test_provider_preserves_no_system_history_behavior,
            self.test_provider_uses_config_system,
            self.test_trace_inputs_include_provider_visible_messages,
            self.test_trace_inputs_keep_history_messages_field,
            self.test_trace_inputs_filter_secret_metadata,
            self.test_text_runner_xai_payload_includes_system_on_followup,
            self.test_tool_loop_followup_trace_is_readable,
            self.test_existing_payload_fields_still_pass_through,
        )
        for check in checks:
            self._run_check(check.__name__, check)
        print(f"{self.passed}/{self.total} tests passed")
        return 0 if self.passed == self.total else 1

    def _run_check(self, name: str, check: object) -> None:
        # Runs one check and prints a PASS or FAIL line.
        self.total += 1
        try:
            result = check()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            return
        self.passed += 1
        print(f"PASS {name}")

    def test_provider_includes_system_before_history(self) -> None:
        # Verifies system instructions are prepended when history exists.
        messages = self._provider_messages("Task", "System", ({"role": "assistant", "content": "draft"},))
        self._assert_equal(messages[0], {"role": "system", "content": "System"})
        self._assert_equal(messages[1], {"role": "assistant", "content": "draft"})
        self._assert_equal(messages[2], {"role": "user", "content": "Task"})

    def test_provider_preserves_no_history_behavior(self) -> None:
        # Verifies no-history chat messages remain system plus user prompt.
        messages = self._provider_messages("Task", "System", ())
        self._assert_equal(messages, [{"role": "system", "content": "System"}, {"role": "user", "content": "Task"}])

    def test_provider_preserves_no_system_history_behavior(self) -> None:
        # Verifies history-only calls still append the current user prompt.
        messages = self._provider_messages("Task", None, ({"role": "assistant", "content": "draft"},))
        self._assert_equal(messages, [{"role": "assistant", "content": "draft"}, {"role": "user", "content": "Task"}])

    def test_provider_uses_config_system(self) -> None:
        # Verifies configured system text is used when call-level system is absent.
        config = TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key", system="Configured", messages=({"role": "assistant", "content": "draft"},))
        messages = XAIProvider()._create_messages(config, "Task", None)
        self._assert_equal(messages[0], {"role": "system", "content": "Configured"})

    def test_trace_inputs_include_provider_visible_messages(self) -> None:
        # Verifies trace input_messages show system, history, and prompt in order.
        inputs = self._trace_inputs(metadata={})
        self._assert_equal(inputs["input_messages"][0]["role"], "system")
        self._assert_equal(inputs["input_messages"][1], {"role": "assistant", "content": "draft"})
        self._assert_equal(inputs["input_messages"][2], {"role": "user", "content": "Task"})

    def test_trace_inputs_keep_history_messages_field(self) -> None:
        # Verifies trace messages show full input while raw history remains inspectable.
        inputs = self._trace_inputs(metadata={})
        self._assert_equal(inputs["messages"], inputs["input_messages"])
        self._assert_equal(inputs["history_messages"], ({"role": "assistant", "content": "draft"},))

    def test_trace_inputs_filter_secret_metadata(self) -> None:
        # Verifies credential-like metadata keys are not sent to trace providers.
        inputs = self._trace_inputs(metadata={"eval_suite": "mbpp", "LANGSMITH_API_KEY": "secret", "XAI_API_KEY": "secret"})
        self._assert_equal(inputs["metadata"], {"eval_suite": "mbpp"})

    async def test_text_runner_xai_payload_includes_system_on_followup(self) -> None:
        # Verifies the actual xAI chat payload keeps system text when history exists.
        transport = FakeTransport()
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key"), transport=transport)
        await runner.arun("Task", system="System", messages=({"role": "assistant", "content": "draft"},))
        messages = transport.requests[0]["json_body"]["messages"]
        self._assert_equal(messages[0], {"role": "system", "content": "System"})
        self._assert_equal(messages[-1], {"role": "user", "content": "Task"})

    async def test_tool_loop_followup_trace_is_readable(self) -> None:
        # Verifies a plain assistant response stops instead of replaying code as history.
        tracer = RecordingTracer()
        runtime = AgentRuntime(agent_name="agent", system_prompt="System", tools=Tools(), permission_policy=PermissionPolicy(), config=AgentRuntimeConfig(max_iterations=3), tracer=tracer)
        runner = FakeRunner([FakeResponse("draft"), FakeResponse("", {"choices": [{"message": {"tool_calls": [{"id": "call-1", "function": {"name": "isDone", "arguments": "{\"final_answer\":\"done\"}"}}]}}]})])
        context = BaseAgentContext(system_prompt="System", history=(), file_paths=(), tools=(), budget=None)
        result = await runtime.arun("Task", handle=RunnerHandle(runner=runner, provider="xai", invoke=invoke_runner, extract_text=output_text, extract_metadata=output_metadata), context=context)
        llm_spans = [span for span in tracer.spans_started if span["name"] == "llm.call"]
        self._assert_equal(result.output, "draft")
        self._assert_equal(result.metadata["stop_reason"], "final_response")
        self._assert_equal(len(llm_spans), 1)
        first = llm_spans[0]["attributes"]
        self._assert_equal(first["messages"], first["input_messages"])
        self._assert_equal(first["messages"][0]["role"], "system")
        self._assert_equal(first["messages"][1], {"role": "user", "content": "Task"})

    async def test_existing_payload_fields_still_pass_through(self) -> None:
        # Verifies tools, tool choice, response format, and metadata still pass through.
        transport = FakeTransport()
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key"), transport=transport)
        tool = {"type": "function", "function": {"name": "isDone", "parameters": {"type": "object"}}}
        response_format = {"type": "json_object"}
        await runner.arun("Task", system="System", tools=(tool,), tool_choice="auto", response_format=response_format, metadata={"eval_suite": "mbpp"})
        body = transport.requests[0]["json_body"]
        self._assert_equal(body["tools"], [tool])
        self._assert_equal(body["tool_choice"], "auto")
        self._assert_equal(body["response_format"], response_format)
        self._assert_equal(body["metadata"], {"eval_suite": "mbpp"})

    def _provider_messages(self, prompt: str, system: str | None, messages: tuple[Mapping[str, Any], ...]) -> list[Mapping[str, Any]]:
        # Builds provider messages through the OpenAI-compatible provider helper.
        config = TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key", messages=messages)
        return XAIProvider()._create_messages(config, prompt, system)

    def _trace_inputs(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        # Builds trace inputs through the runtime helper.
        runtime = AgentRuntime(agent_name="agent", system_prompt="System", tools=Tools(), permission_policy=PermissionPolicy())
        runner = FakeRunner([])
        return runtime._llm_trace_inputs(handle=RunnerHandle(runner=runner, provider="xai", invoke=invoke_runner, extract_text=output_text, extract_metadata=output_metadata), message="Task", call_options={"system": "System", "messages": ({"role": "assistant", "content": "draft"},), "tools": ({"type": "function", "function": {"name": "isDone"}},)}, provider="xai", iteration_count=1, model_call_count=2, metadata=metadata)

    @staticmethod
    def _assert_equal(actual: object, expected: object) -> None:
        # Raises an AssertionError with useful context when values differ.
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    sys.exit(VerificationRunner().run())
