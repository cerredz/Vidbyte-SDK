from __future__ import annotations

import json
import unittest
from typing import Mapping

from pydantic import BaseModel

from vidbyte.agents import AgentRuntime
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.enums import StructuredOutputMode
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.providers.structured_output import ProviderStructuredOutputPlanner
from vidbyte.tools import ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class RowsResult(BaseModel):
    rows: list[str]
    count: int


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []


class FakeTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        # Records one provider request and returns a canned JSON response.
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {}), "timeout_seconds": timeout_seconds})
        return HttpResponse(status_code=200, body=json.dumps(self.response), headers={})


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    # Records model-call kwargs and returns the next fake response.
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    # Normalizes fake runner responses the same way production callbacks do.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    # Returns fake response metadata for runtime accounting.
    return dict(getattr(response, "metadata", {}))


def is_done_response(final_answer: str) -> FakeResponse:
    # Builds an OpenAI-shaped internal isDone tool call with the requested answer.
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": final_answer}), "call_id": "done"}]})


class ProviderNativeStructuredOutputsTests(unittest.IsolatedAsyncioTestCase):
    def test_mode_coercion_and_invalid_value(self) -> None:
        self.assertIs(StructuredOutputMode.coerce(None), StructuredOutputMode.AUTO)
        self.assertIs(StructuredOutputMode.coerce("native"), StructuredOutputMode.NATIVE)
        self.assertIs(StructuredOutputMode.coerce(StructuredOutputMode.PROMPT), StructuredOutputMode.PROMPT)
        with self.assertRaises(ConfigurationError):
            StructuredOutputMode.coerce("bad")

    def test_planner_provider_shapes(self) -> None:
        planner = ProviderStructuredOutputPlanner()
        openai = planner.plan(provider="openai", schema=RowsResult, mode=StructuredOutputMode.AUTO)
        anthropic = planner.plan(provider="anthropic", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)
        gemini = planner.plan(provider="gemini", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)
        compatible = planner.plan(provider="openrouter", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)

        self.assertEqual(openai.response_format["type"], "json_schema")
        self.assertIn("schema", openai.response_format)
        self.assertEqual(anthropic.response_format, {"type": "json_schema", "schema": {"type": "object"}})
        self.assertEqual(gemini.response_format, {"type": "object"})
        self.assertIn("json_schema", compatible.response_format)

    def test_planner_prompt_and_native_unsupported_modes(self) -> None:
        planner = ProviderStructuredOutputPlanner()
        prompt = planner.plan(provider="unknown", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)
        explicit_prompt = planner.plan(provider="openai", schema={"type": "object"}, mode=StructuredOutputMode.PROMPT)

        self.assertTrue(prompt.use_prompt_hint)
        self.assertIsNone(explicit_prompt.response_format)
        self.assertTrue(explicit_prompt.use_prompt_hint)
        with self.assertRaises(ConfigurationError):
            planner.plan(provider="unknown", schema={"type": "object"}, mode=StructuredOutputMode.NATIVE)

    async def test_runtime_auto_native_passes_response_format_and_validates_result(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), output_schema=RowsResult)
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])

        result = await runtime.arun("task", runner=runner, context=context, provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        response_format = runner.calls[0]["kwargs"]["response_format"]
        system = runner.calls[0]["kwargs"]["system"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertNotIn("Your final response MUST", system)
        self.assertIsInstance(result.structured, RowsResult)

    async def test_runtime_prompt_mode_uses_hint_without_response_format(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), output_schema=RowsResult, structured_output_mode=StructuredOutputMode.PROMPT)
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])

        await runtime.arun("task", runner=runner, context=context, provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertNotIn("response_format", runner.calls[0]["kwargs"])
        self.assertIn("Your final response MUST", runner.calls[0]["kwargs"]["system"])

    async def test_runtime_invalid_native_output_still_records_validation_error(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), output_schema=RowsResult)
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        runner = FakeRunner([is_done_response("not json")])

        result = await runtime.arun("task", runner=runner, context=context, provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)

        self.assertIsNone(result.structured)
        self.assertIn("output_schema_error", result.metadata)

    def test_runtime_respects_user_response_format_override_in_auto_mode(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), output_schema=RowsResult)
        context = BaseAgentContext(system_prompt="Work.")
        custom = {"type": "json_object"}

        options = runtime._build_iteration_call_options({"response_format": custom}, context, (), [], provider="openai")

        self.assertEqual(options["response_format"], custom)

    def test_runtime_native_mode_rejects_user_response_format_override(self) -> None:
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), output_schema=RowsResult, structured_output_mode=StructuredOutputMode.NATIVE)
        context = BaseAgentContext(system_prompt="Work.")

        with self.assertRaises(ConfigurationError):
            runtime._build_iteration_call_options({"response_format": {"type": "json_object"}}, context, (), [], provider="openai")

    def test_runtime_strict_provider_tool_schema_reaches_catalog(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return topic

        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), strict_provider_tool_schemas=True)
        schemas = runtime._resolve_tool_schemas("anthropic")

        self.assertTrue(any(schema.get("strict") is True for schema in schemas))

    def test_anthropic_provider_serializes_response_format(self) -> None:
        transport = FakeTransport({"content": [{"type": "text", "text": "{}"}]})
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"), transport=transport)

        runner.run("Hello", response_format={"type": "json_schema", "schema": {"type": "object"}})

        payload = transport.requests[0]["json_body"]
        self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")


if __name__ == "__main__":
    unittest.main()
