"""FILE: vidbyte/lib/enums/tracing.py

PURPOSE: Centralizes closed string vocabularies for tracing transports and trace shape translators.
ROLE IN CODEBASE: Owned by vidbyte/lib; imported by provider tracers and ProviderTraceTranslator implementations instead of inline literals.
ARCHITECTURE NOTE: Every string that identifies a provider, env var, span kind, or semantic attribute lives here so callers match exhaustively against enums rather than ad-hoc strings.
COMMON MODIFICATION PATTERNS: Add a new TraceProvider or semantic attribute here and expose it through vidbyte.lib.enums; do not redeclare the literal in a translator or tracer.
KNOWN EDGE CASES: Enum values are the exact wire strings required by external specs (OpenInference, OTel GenAI); changing a value is a breaking wire-format change.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/schema.py, vidbyte/providers/tracing/otel.py
TESTS: tests/test_otel_tracer_transport.py, tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py
"""

from __future__ import annotations

from enum import Enum


class TraceProvider(str, Enum):
    """Registered provider translator names resolved by _TraceFactory."""

    GENERIC = "generic"
    LANGSMITH = "langsmith"
    OTEL_GENAI = "otel-genai"
    OPENINFERENCE = "openinference"


class OTelEndpointEnvVar(str, Enum):
    """Environment variables resolved for the destination-agnostic OTel tracer."""

    TRACES_ENDPOINT = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"


class PhoenixEndpoint(str, Enum):
    """Phoenix-specific endpoint defaults."""

    DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"
    ENV_VAR = "PHOENIX_COLLECTOR_ENDPOINT"


class OTelDefault(str, Enum):
    """Default resource and placeholder values for OTel tracing."""

    SERVICE_NAME = "vidbyte-agent"
    RESOURCE_SERVICE_NAME_KEY = "service.name"
    OUTPUT_VALUE = "output.value"
    ERROR_MESSAGE = "error.message"
    UNKNOWN_MODEL = "unknown"
    UNKNOWN_TOOL = "unknown_tool"
    UNKNOWN_AGENT = "agent"


class OpenInferenceSpanKind(str, Enum):
    """Valid values for openinference.span.kind."""

    LLM = "LLM"
    TOOL = "TOOL"
    CHAIN = "CHAIN"
    RETRIEVER = "RETRIEVER"
    EMBEDDING = "EMBEDDING"


class OpenInferenceAttribute(str, Enum):
    """Wire attribute keys for the OpenInference semantic conventions."""

    SPAN_KIND = "openinference.span.kind"
    LLM_MODEL_NAME = "llm.model_name"
    LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
    LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
    TOOL_NAME = "tool.name"
    TOOL_CALL_ID = "tool_call.id"
    TOOL_CALL_FUNCTION_NAME = "tool_call.function.name"
    TOOL_CALL_FUNCTION_ARGUMENTS = "tool_call.function.arguments"


class GenAIAttribute(str, Enum):
    """Wire attribute keys for the OTel GenAI semantic conventions (gen_ai.*)."""

    OPERATION_NAME = "gen_ai.operation.name"
    AGENT_NAME = "gen_ai.agent.name"
    PROVIDER_NAME = "gen_ai.provider.name"
    CONVERSATION_ID = "gen_ai.conversation.id"
    REQUEST_MODEL = "gen_ai.request.model"
    INPUT_MESSAGES = "gen_ai.input.messages"
    SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
    USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
    TOOL_NAME = "gen_ai.tool.name"
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"


class GenAIOperation(str, Enum):
    """Valid values for gen_ai.operation.name."""

    INVOKE_AGENT = "invoke_agent"
    CHAT = "chat"
    EXECUTE_TOOL = "execute_tool"


class SpanNamePrefix(str, Enum):
    """Name prefixes inspected by PhoenixTracer's legacy guessing path."""

    LLM = "llm."
    TOOL = "tool."


class TraceShapeNamespace(str, Enum):
    """Namespace prefix for unmapped Vidbyte attributes."""

    VIDBYTE = "vidbyte"


__all__ = [
    "GenAIAttribute",
    "GenAIOperation",
    "OTelDefault",
    "OTelEndpointEnvVar",
    "OpenInferenceAttribute",
    "OpenInferenceSpanKind",
    "PhoenixEndpoint",
    "SpanNamePrefix",
    "TraceProvider",
    "TraceShapeNamespace",
]
