from __future__ import annotations

import asyncio
import inspect
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from vidbyte.agents import AgentRuntime, BaseAgent
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.tools import ToolSpec
from vidbyte.lib.enums import AgentRuntimeType, StructuredOutputMode
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import StreamingTextModelRunner, TextModelRunner
from vidbyte.providers import tool_spec_to_provider_schema
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.structured_output import ProviderStructuredOutputPlanner
from vidbyte.tools import ToolResult, Tools, ToolsFormatter, tool, vidbyte_tool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.security import PermissionPolicy


class RowsResult(BaseModel):
    rows: list[str]
    count: int


class FakeResponse:
    def __init__(self, text: str, raw: dict[str, Any], metadata: Mapping[str, Any] | None = None) -> None:
        # Store fake model text, raw provider payload, and optional metadata.
        self.text = text
        self.raw = raw
        self.metadata = dict(metadata or {})


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        # Queue fake responses and record invocation kwargs.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []


class FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        # Record request payloads while returning a canned JSON response.
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, Any] | None = None, timeout_seconds: float = 60.0, **kwargs: Any) -> HttpResponse:
        # Capture one HTTP request and return a JSON body without network access.
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {}), "timeout_seconds": timeout_seconds})
        return HttpResponse(status_code=200, body=json.dumps(self.response), headers={})


class FakeStreamTransport:
    def __init__(self, lines: list[str]) -> None:
        # Record streaming request payloads and replay canned SSE lines.
        self.lines = list(lines)
        self.requests: list[dict[str, Any]] = []

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, Any] | None = None, timeout_seconds: float = 60.0, **kwargs: Any) -> list[str]:
        # Capture one streaming request and return fake event lines.
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {}), "timeout_seconds": timeout_seconds})
        return list(self.lines)


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> FakeResponse:
    # Record model-call kwargs and pop the next fake model response.
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    # Normalize fake model responses to their text surface.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict[str, Any]:
    # Normalize fake model responses to metadata dictionaries.
    return dict(getattr(response, "metadata", {}))


def is_done_response(final_answer: str) -> FakeResponse:
    # Build the internal isDone tool call shape used by the linear runtime.
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": final_answer}), "call_id": "done"}]})


def provider_done_response(provider: str, final_answer: str) -> FakeResponse:
    # Build the internal isDone tool call in the selected provider's raw shape.
    arguments = {"final_answer": final_answer}
    if provider == "anthropic":
        return FakeResponse("", {"content": [{"type": "tool_use", "id": "done", "name": "isDone", "input": arguments}]})
    if provider == "gemini":
        return FakeResponse("", {"candidates": [{"content": {"parts": [{"functionCall": {"name": "isDone", "args": arguments}}]}}]})
    return is_done_response(final_answer)


def make_runtime(**kwargs: Any) -> AgentRuntime:
    # Build a small linear runtime with safe defaults for verification cases.
    return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), **kwargs)


def build_context(runtime: AgentRuntime) -> BaseAgentContext:
    # Create a context using the runtime's own context builder.
    return runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())


def assert_raises(exc_type: type[BaseException], func: Callable[[], Any]) -> BaseException:
    # Assert a synchronous callable raises the expected exception type.
    try:
        func()
    except exc_type as exc:
        return exc
    raise AssertionError(f"Expected {exc_type.__name__}")


def check_mode_coercion_none() -> None:
    # Verify None selects AUTO.
    assert StructuredOutputMode.coerce(None) is StructuredOutputMode.AUTO


def check_mode_coercion_strings() -> None:
    # Verify supported strings map to enum members.
    assert StructuredOutputMode.coerce("auto") is StructuredOutputMode.AUTO
    assert StructuredOutputMode.coerce("native") is StructuredOutputMode.NATIVE
    assert StructuredOutputMode.coerce("prompt") is StructuredOutputMode.PROMPT


def check_mode_coercion_invalid() -> None:
    # Verify invalid modes fail fast.
    assert_raises(ConfigurationError, lambda: StructuredOutputMode.coerce("bad"))


def check_mode_value_stability() -> None:
    # Verify enum values remain stable for metadata and logging.
    assert StructuredOutputMode.AUTO.value == "auto"


def check_mode_coercion_existing_member() -> None:
    # Verify enum values pass through unchanged.
    assert StructuredOutputMode.coerce(StructuredOutputMode.PROMPT) is StructuredOutputMode.PROMPT


def check_planner_schema_none() -> None:
    # Verify absent schemas produce an empty plan.
    plan = ProviderStructuredOutputPlanner().plan(provider="openai", schema=None, mode=StructuredOutputMode.AUTO)
    assert plan.response_format is None
    assert plan.use_prompt_hint is False


def check_planner_prompt_mode() -> None:
    # Verify prompt mode uses PR #91 prompt fallback.
    plan = ProviderStructuredOutputPlanner().plan(provider="openai", schema=RowsResult, mode=StructuredOutputMode.PROMPT)
    assert plan.response_format is None
    assert plan.use_prompt_hint is True


def check_planner_native_unsupported() -> None:
    # Verify native-only mode rejects unsupported providers.
    assert_raises(ConfigurationError, lambda: ProviderStructuredOutputPlanner().plan(provider="unknown-provider", schema=RowsResult, mode=StructuredOutputMode.NATIVE))


def check_planner_openai_shape() -> None:
    # Verify OpenAI Responses API shape.
    plan = ProviderStructuredOutputPlanner().plan(provider="openai", schema=RowsResult, mode=StructuredOutputMode.AUTO)
    assert plan.response_format["type"] == "json_schema"
    assert plan.response_format["name"] == "agent_output"
    assert "schema" in plan.response_format
    assert plan.response_format["strict"] is True
    assert "json_schema" not in plan.response_format
    assert plan.use_prompt_hint is False


def check_planner_compatible_shape() -> None:
    # Verify OpenAI-compatible chat response_format shape.
    plan = ProviderStructuredOutputPlanner().plan(provider="openrouter", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)
    assert plan.response_format["type"] == "json_schema"
    assert plan.response_format["json_schema"]["name"] == "agent_output"
    assert plan.response_format["json_schema"]["strict"] is True


def check_planner_anthropic_shape() -> None:
    # Verify Anthropic JSON schema response format shape.
    plan = ProviderStructuredOutputPlanner().plan(provider="anthropic", schema={"type": "object"}, mode=StructuredOutputMode.AUTO)
    assert plan.response_format == {"type": "json_schema", "schema": {"type": "object"}}


def check_planner_gemini_shape() -> None:
    # Verify Gemini receives the raw resolved schema.
    schema = {"type": "object", "properties": {"rows": {"type": "array"}}}
    plan = ProviderStructuredOutputPlanner().plan(provider="gemini", schema=schema, mode=StructuredOutputMode.AUTO)
    assert plan.response_format == schema


def check_planner_pydantic_resolution() -> None:
    # Verify Pydantic models resolve through the shared validator.
    plan = ProviderStructuredOutputPlanner().plan(provider="openai", schema=RowsResult, mode=StructuredOutputMode.AUTO)
    assert plan.response_format["schema"]["properties"]["rows"]["type"] == "array"


def check_planner_raw_dict_not_mutated() -> None:
    # Verify raw dict schemas are copied before provider wrapping.
    schema = {"type": "object", "properties": {}}
    plan = ProviderStructuredOutputPlanner().plan(provider="openrouter", schema=schema, mode=StructuredOutputMode.AUTO)
    plan.response_format["json_schema"]["schema"]["properties"]["added"] = {"type": "string"}
    assert "added" not in schema["properties"]


def check_text_runner_response_format_none_preserves_payload() -> None:
    # Verify no response_format leaves OpenAI payload unchanged.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    runner.run("Hello", response_format=None)
    assert "text" not in transport.requests[0]["json_body"]


def check_text_runner_call_scoped_response_format() -> None:
    # Verify call-scoped response_format reaches provider config.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    runner.run("Hello", response_format={"type": "json_schema", "schema": {"type": "object"}})
    assert transport.requests[0]["json_body"]["text"]["format"]["type"] == "json_schema"


def check_text_runner_config_response_format_preserved() -> None:
    # Verify runner-level response_format remains effective.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key", response_format={"type": "json_object"}), transport=transport)
    runner.run("Hello")
    assert transport.requests[0]["json_body"]["text"]["format"] == {"type": "json_object"}


def check_text_runner_run_forwards_response_format() -> None:
    # Verify sync run forwards response_format through the async path.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    runner.run("Hello", response_format={"type": "json_object"})
    assert transport.requests[0]["json_body"]["text"]["format"] == {"type": "json_object"}


def check_streaming_no_response_format_preserves_payload() -> None:
    # Verify streaming without response_format omits structured output payload.
    transport = FakeStreamTransport([json.dumps({"type": "response.text.delta", "delta": "ok"})])
    runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    assert list(runner.stream("Hello")) == ["ok"]
    assert "text" not in transport.requests[0]["json_body"]


def check_streaming_response_format_passes_config() -> None:
    # Verify streaming with response_format reaches the provider payload.
    transport = FakeStreamTransport([json.dumps({"type": "response.text.delta", "delta": "ok"})])
    runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    assert list(runner.stream("Hello", response_format={"type": "json_object"})) == ["ok"]
    assert transport.requests[0]["json_body"]["text"]["format"] == {"type": "json_object"}


def check_streaming_preserves_tools_choice_messages() -> None:
    # Verify streaming response_format does not drop existing call options.
    transport = FakeStreamTransport([json.dumps({"type": "response.text.delta", "delta": "ok"})])
    runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    list(runner.stream("Hello", tools=({"type": "function", "name": "x"},), tool_choice="auto", messages=({"role": "user", "content": "prior"},), response_format={"type": "json_object"}))
    payload = transport.requests[0]["json_body"]
    assert payload["tools"] == [{"type": "function", "name": "x"}]
    assert payload["tool_choice"] == "auto"
    assert isinstance(payload["input"], list)


def check_streaming_unsupported_provider_fails_at_init() -> None:
    # Verify unsupported streaming providers fail during runner construction.
    assert_raises(UnsupportedProviderError, lambda: StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-test", api_key="key"), response_format={"type": "json_object"}))


def check_anthropic_omits_output_config_when_none() -> None:
    # Verify Anthropic payload is unchanged without response_format.
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"), transport=transport)
    runner.run("Hello")
    assert "output_config" not in transport.requests[0]["json_body"]


def check_anthropic_adds_output_config_format() -> None:
    # Verify Anthropic response_format serializes to output_config.format.
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"), transport=transport)
    runner.run("Hello", response_format={"type": "json_schema", "schema": {"type": "object"}})
    assert transport.requests[0]["json_body"]["output_config"]["format"]["type"] == "json_schema"


def check_anthropic_preserves_tools_thinking_metadata() -> None:
    # Verify Anthropic response_format coexists with existing payload fields.
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    config = TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key", tools=({"name": "lookup", "input_schema": {"type": "object"}},), tool_choice={"type": "tool", "name": "lookup"}, thinking_config={"type": "enabled"}, metadata={"static": "yes"})
    runner = TextModelRunner(config, transport=transport)
    runner.run("Hello", metadata={"call": "yes"}, response_format={"type": "json_schema", "schema": {"type": "object"}})
    payload = transport.requests[0]["json_body"]
    assert payload["tools"][0]["name"] == "lookup"
    assert payload["tool_choice"]["name"] == "lookup"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["metadata"] == {"static": "yes", "call": "yes"}


def check_anthropic_extra_body_overrides_output_config() -> None:
    # Verify existing extra_body precedence can override output_config.
    transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
    config = TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key", extra_body={"output_config": {"format": {"type": "custom"}}})
    runner = TextModelRunner(config, transport=transport)
    runner.run("Hello", response_format={"type": "json_schema", "schema": {"type": "object"}})
    assert transport.requests[0]["json_body"]["output_config"]["format"] == {"type": "custom"}


def check_strict_empty_tools_returns_empty() -> None:
    # Verify empty catalogs remain empty in strict mode.
    assert Tools().provider_schemas("openai", strict=True) == ()


def check_strict_does_not_mutate_input_schema() -> None:
    # Verify strict formatting does not mutate ToolSpec input schema.
    spec = ToolSpec(name="lookup", description="Lookup.", input_schema={"type": "object", "properties": {"topic": {"type": "string"}}})
    original = dict(spec.input_schema)
    tool_spec_to_provider_schema(spec, "openai", strict=True)
    assert spec.input_schema == original


def check_strict_anthropic_schema() -> None:
    # Verify Anthropic strict tool declarations include top-level strict.
    @vidbyte_tool
    def lookup(topic: str) -> str:
        """Look up a topic."""
        return topic

    schema = tool_spec_to_provider_schema(lookup.spec(), "anthropic", strict=True)
    assert schema["strict"] is True


def check_strict_openai_schema() -> None:
    # Verify OpenAI-compatible strict tool declarations include function strict.
    @vidbyte_tool
    def lookup(topic: str) -> str:
        """Look up a topic."""
        return topic

    schema = tool_spec_to_provider_schema(lookup.spec(), "openai", strict=True)
    assert schema["function"]["strict"] is True


def check_strict_gemini_no_undocumented_field() -> None:
    # Verify Gemini strict mode remains shape-compatible.
    @vidbyte_tool
    def lookup(topic: str) -> str:
        """Look up a topic."""
        return topic

    schema = tool_spec_to_provider_schema(lookup.spec(), "gemini", strict=True)
    assert schema["name"] == "lookup"
    assert "strict" not in schema
    assert "parameters" in schema


def check_strict_false_preserves_existing_shape() -> None:
    # Verify strict defaults preserve existing schema shape.
    @vidbyte_tool
    def lookup(topic: str) -> str:
        """Look up a topic."""
        return topic

    strict_false = tool_spec_to_provider_schema(lookup.spec(), "openai", strict=False)
    default = tool_spec_to_provider_schema(lookup.spec(), "openai")
    assert strict_false == default


def check_runtime_without_output_schema_no_response_format_or_hint() -> None:
    # Verify agents without output_schema do not change model call options.
    runtime = make_runtime(output_schema=None)
    context = BaseAgentContext(system_prompt="Work.")
    options = runtime._build_iteration_call_options({}, context, (), [], provider="openai")
    assert "response_format" not in options
    assert "Your final response MUST" not in options["system"]


async def check_runtime_openai_auto_response_format() -> None:
    # Verify AUTO mode attaches OpenAI native response_format.
    runtime = make_runtime(output_schema=RowsResult)
    runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])
    result = await runtime.arun("task", runner=runner, context=build_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert runner.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert isinstance(result.structured, RowsResult)


async def check_runtime_anthropic_auto_response_format() -> None:
    # Verify AUTO mode attaches Anthropic native response_format.
    runtime = make_runtime(output_schema=RowsResult)
    runner = FakeRunner([provider_done_response("anthropic", json.dumps({"rows": ["a"], "count": 1}))])
    await runtime.arun("task", runner=runner, context=build_context(runtime), provider="anthropic", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert runner.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert "schema" in runner.calls[0]["kwargs"]["response_format"]


async def check_runtime_gemini_auto_response_format() -> None:
    # Verify AUTO mode attaches raw Gemini schema.
    runtime = make_runtime(output_schema=RowsResult)
    runner = FakeRunner([provider_done_response("gemini", json.dumps({"rows": ["a"], "count": 1}))])
    await runtime.arun("task", runner=runner, context=build_context(runtime), provider="gemini", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert runner.calls[0]["kwargs"]["response_format"]["properties"]["rows"]["type"] == "array"


def check_runtime_native_supported_skips_prompt_hint() -> None:
    # Verify native-supported providers do not also append prompt fallback.
    runtime = make_runtime(output_schema=RowsResult)
    context = BaseAgentContext(system_prompt="Work.")
    options = runtime._build_iteration_call_options({}, context, (), [], provider="openai")
    assert "response_format" in options
    assert "Your final response MUST" not in options["system"]


def check_runtime_prompt_mode_uses_hint_only() -> None:
    # Verify prompt mode appends PR #91 hint and skips response_format.
    runtime = make_runtime(output_schema=RowsResult, structured_output_mode=StructuredOutputMode.PROMPT)
    context = BaseAgentContext(system_prompt="Work.")
    options = runtime._build_iteration_call_options({}, context, (), [], provider="openai")
    assert "response_format" not in options
    assert "Your final response MUST" in options["system"]


async def check_runtime_native_unsupported_before_runner_call() -> None:
    # Verify NATIVE unsupported providers fail before invoking the runner.
    runtime = make_runtime(output_schema=RowsResult, structured_output_mode=StructuredOutputMode.NATIVE)
    runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])
    try:
        await runtime.arun("task", runner=runner, context=build_context(runtime), provider="unknown-provider", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    except ConfigurationError:
        pass
    else:
        raise AssertionError("Expected ConfigurationError")
    assert runner.calls == []


def check_runtime_user_response_format_not_overwritten() -> None:
    # Verify AUTO mode respects user-supplied response_format.
    runtime = make_runtime(output_schema=RowsResult)
    custom = {"type": "json_object"}
    options = runtime._build_iteration_call_options({"response_format": custom}, BaseAgentContext(system_prompt="Work."), (), [], provider="openai")
    assert options["response_format"] is custom


def check_runtime_strict_internal_tools_present() -> None:
    # Verify strict mode with no user tools still returns internal tool schemas.
    runtime = make_runtime(strict_provider_tool_schemas=True)
    schemas = runtime._resolve_tool_schemas("openai")
    assert any(schema.get("function", {}).get("name") == "isDone" for schema in schemas)


def check_runtime_strict_reaches_catalog() -> None:
    # Verify runtime passes strict=True into provider schema formatting.
    @tool
    def lookup(topic: str) -> str:
        """Look up a topic."""
        return topic

    runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), strict_provider_tool_schemas=True)
    schemas = runtime._resolve_tool_schemas("anthropic")
    assert any(schema.get("strict") is True for schema in schemas)


def check_strict_tool_call_parsing_still_works() -> None:
    # Verify strict schema formatting does not affect provider tool-call parsing.
    assert ToolsFormatter.parse_tool_calls({"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "openai"}', "call_id": "1"}]}, "openai")[0].arguments["topic"] == "openai"
    assert ToolsFormatter.parse_tool_calls({"content": [{"type": "tool_use", "id": "2", "name": "lookup", "input": {"topic": "anthropic"}}]}, "anthropic")[0].arguments["topic"] == "anthropic"
    assert ToolsFormatter.parse_tool_calls({"candidates": [{"content": {"parts": [{"functionCall": {"name": "lookup", "args": {"topic": "gemini"}}}]}}]}, "gemini")[0].arguments["topic"] == "gemini"


def check_strict_does_not_affect_local_output_validation() -> None:
    # Verify local ToolSpec.output_schema validation still runs independently of strict provider schemas.
    spec = ToolSpec(name="lookup", description="Lookup.", output_schema=RowsResult)
    result = ToolExecutor._apply_output_schema(ToolResult.success("lookup", json.dumps({"rows": ["a"], "count": 1})), spec)
    assert isinstance(result.structured, RowsResult)


async def check_native_invalid_output_records_error() -> None:
    # Verify native structured output still goes through local validation.
    runtime = make_runtime(output_schema=RowsResult)
    runner = FakeRunner([is_done_response("not json")])
    result = await runtime.arun("task", runner=runner, context=build_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert result.structured is None
    assert "output_schema_error" in result.metadata


async def check_native_valid_output_populates_structured() -> None:
    # Verify valid native output populates AgentResult.structured.
    runtime = make_runtime(output_schema=RowsResult)
    runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])
    result = await runtime.arun("task", runner=runner, context=build_context(runtime), provider="openai", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert isinstance(result.structured, RowsResult)


async def check_prompt_fallback_still_validates() -> None:
    # Verify prompt fallback uses the same local validator.
    runtime = make_runtime(output_schema=RowsResult, structured_output_mode=StructuredOutputMode.PROMPT)
    runner = FakeRunner([is_done_response(json.dumps({"rows": ["a"], "count": 1}))])
    result = await runtime.arun("task", runner=runner, context=build_context(runtime), provider="unknown-provider", invoke_runner=invoke_runner, runner_output_text=runner_output_text, runner_output_metadata=runner_output_metadata)
    assert isinstance(result.structured, RowsResult)


def check_base_agent_fork_preserves_new_fields() -> None:
    # Verify BaseAgent stores and forks new structured-output settings.
    parent = BaseAgent(name="parent", system_prompt="Work.", output_schema=RowsResult, structured_output_mode="prompt", strict_provider_tool_schemas=True)
    child = parent.fork(name="child")
    assert child.output_schema is RowsResult
    assert child.structured_output_mode is StructuredOutputMode.PROMPT
    assert child.strict_provider_tool_schemas is True


def check_base_agent_runtime_receives_new_fields() -> None:
    # Verify BaseAgent passes new settings into linear runtime construction.
    agent = BaseAgent(name="agent", system_prompt="Work.", output_schema=RowsResult, structured_output_mode="native", strict_provider_tool_schemas=True, runtime=AgentRuntimeType.LINEAR)
    runtime = agent._runtime()
    assert runtime.output_schema is RowsResult
    assert runtime.structured_output_mode is StructuredOutputMode.NATIVE
    assert runtime.strict_provider_tool_schemas is True


def check_openai_provider_no_schema_payload() -> None:
    # Verify OpenAI provider omits text.format without response_format.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    runner.run("Hello")
    assert "text" not in transport.requests[0]["json_body"]


def check_openai_provider_schema_payload() -> None:
    # Verify OpenAI provider serializes text.format when requested.
    transport = FakeTransport({"output_text": "ok"})
    runner = TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"), transport=transport)
    runner.run("Hello", response_format={"type": "json_schema", "schema": {"type": "object"}})
    assert transport.requests[0]["json_body"]["text"]["format"]["type"] == "json_schema"


def check_gemini_provider_schema_payload() -> None:
    # Verify Gemini provider serializes responseMimeType and responseSchema.
    provider = GeminiProvider(text_config=TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-test", api_key="key"))
    payload = provider._create_payload(replace(provider._text_config, response_format={"type": "object"}), "Hello", None, None)
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseSchema"] == {"type": "object"}


CASES: tuple[tuple[str, Callable[[], Any] | Callable[[], Awaitable[Any]]], ...] = (
    ("StructuredOutputMode: coerce(None) returns AUTO", check_mode_coercion_none),
    ("StructuredOutputMode: coerce supported strings", check_mode_coercion_strings),
    ("StructuredOutputMode: invalid mode raises", check_mode_coercion_invalid),
    ("StructuredOutputMode: value remains stable", check_mode_value_stability),
    ("StructuredOutputMode: existing enum member passes through", check_mode_coercion_existing_member),
    ("Planner: schema=None returns empty plan", check_planner_schema_none),
    ("Planner: PROMPT mode uses prompt hint", check_planner_prompt_mode),
    ("Planner: NATIVE unsupported raises", check_planner_native_unsupported),
    ("Planner: OpenAI shape", check_planner_openai_shape),
    ("Planner: OpenAI-compatible shape", check_planner_compatible_shape),
    ("Planner: Anthropic shape", check_planner_anthropic_shape),
    ("Planner: Gemini raw schema shape", check_planner_gemini_shape),
    ("Planner: Pydantic schema resolution", check_planner_pydantic_resolution),
    ("Planner: raw dict schema is copied", check_planner_raw_dict_not_mutated),
    ("TextModelRunner: response_format=None preserves payload", check_text_runner_response_format_none_preserves_payload),
    ("TextModelRunner: call-scoped response_format passes through", check_text_runner_call_scoped_response_format),
    ("TextModelRunner: runner-level response_format preserved", check_text_runner_config_response_format_preserved),
    ("TextModelRunner: run() forwards response_format", check_text_runner_run_forwards_response_format),
    ("StreamingTextModelRunner: no response_format preserves payload", check_streaming_no_response_format_preserves_payload),
    ("StreamingTextModelRunner: response_format passes provider config", check_streaming_response_format_passes_config),
    ("StreamingTextModelRunner: tools/tool_choice/messages preserved", check_streaming_preserves_tools_choice_messages),
    ("StreamingTextModelRunner: unsupported provider fails at init", check_streaming_unsupported_provider_fails_at_init),
    ("AnthropicProvider: response_format=None omits output_config", check_anthropic_omits_output_config_when_none),
    ("AnthropicProvider: response_format adds output_config.format", check_anthropic_adds_output_config_format),
    ("AnthropicProvider: tools/thinking/metadata preserved", check_anthropic_preserves_tools_thinking_metadata),
    ("AnthropicProvider: extra_body can override output_config", check_anthropic_extra_body_overrides_output_config),
    ("Strict tools: empty catalog returns empty tuple", check_strict_empty_tools_returns_empty),
    ("Strict tools: formatting does not mutate input schema", check_strict_does_not_mutate_input_schema),
    ("Strict tools: Anthropic top-level strict", check_strict_anthropic_schema),
    ("Strict tools: OpenAI-compatible function strict", check_strict_openai_schema),
    ("Strict tools: Gemini no undocumented strict field", check_strict_gemini_no_undocumented_field),
    ("Strict tools: strict=False preserves default shape", check_strict_false_preserves_existing_shape),
    ("AgentRuntime: no output_schema has no response_format or hint", check_runtime_without_output_schema_no_response_format_or_hint),
    ("AgentRuntime: OpenAI AUTO passes response_format", check_runtime_openai_auto_response_format),
    ("AgentRuntime: Anthropic AUTO passes response_format", check_runtime_anthropic_auto_response_format),
    ("AgentRuntime: Gemini AUTO passes raw schema", check_runtime_gemini_auto_response_format),
    ("AgentRuntime: native provider skips prompt hint", check_runtime_native_supported_skips_prompt_hint),
    ("AgentRuntime: PROMPT mode uses hint only", check_runtime_prompt_mode_uses_hint_only),
    ("AgentRuntime: NATIVE unsupported fails before runner", check_runtime_native_unsupported_before_runner_call),
    ("AgentRuntime: user response_format not overwritten", check_runtime_user_response_format_not_overwritten),
    ("AgentRuntime: strict no user tools keeps internal tool", check_runtime_strict_internal_tools_present),
    ("AgentRuntime: strict flag reaches catalog", check_runtime_strict_reaches_catalog),
    ("AgentRuntime: strict schemas do not affect tool parsing", check_strict_tool_call_parsing_still_works),
    ("AgentRuntime: strict schemas do not affect local output validation", check_strict_does_not_affect_local_output_validation),
    ("PR91 validation: invalid native output records error", check_native_invalid_output_records_error),
    ("PR91 validation: valid native output populates structured", check_native_valid_output_populates_structured),
    ("PR91 validation: prompt fallback still validates", check_prompt_fallback_still_validates),
    ("BaseAgent: fork preserves new fields", check_base_agent_fork_preserves_new_fields),
    ("BaseAgent: runtime receives new fields", check_base_agent_runtime_receives_new_fields),
    ("Manual QA: OpenAI no schema omits text.format", check_openai_provider_no_schema_payload),
    ("Manual QA: OpenAI schema includes text.format", check_openai_provider_schema_payload),
    ("Manual QA: Gemini schema includes generationConfig fields", check_gemini_provider_schema_payload),
)


def run_case(name: str, func: Callable[[], Any] | Callable[[], Awaitable[Any]]) -> bool:
    # Execute one verification case and print its PASS/FAIL line.
    try:
        result = func()
        if inspect.isawaitable(result):
            asyncio.run(result)
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        return False
    print(f"PASS {name}")
    return True


def main() -> int:
    # Run all verification cases and return a process exit code.
    passed = 0
    for name, func in CASES:
        if run_case(name, func):
            passed += 1
    total = len(CASES)
    print(f"{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
