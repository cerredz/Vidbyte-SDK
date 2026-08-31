"""FILE: vidbyte/lib/dataclasses/tracing.py

PURPOSE: Typed, validated dataclasses for the OTel transport and the GenAI/OpenInference trace shapes.
ROLE IN CODEBASE: Owned by vidbyte/lib; consumed by vidbyte/providers/tracing and vidbyte/trace/providers so every tracer constructor and translator builds from validated contracts instead of raw dicts.
ARCHITECTURE NOTE: Each dataclass is frozen, slot-based, and validates in __post_init__ with strict type and value checks that raise ConfigurationError/TracerConfigurationError rather than silently coercing.
COMMON MODIFICATION PATTERNS: Add a new shape or transport option by extending the dataclass and its validation together; do not add new free-form **kwargs to a tracer or translator.
KNOWN EDGE CASES: Headers must be Mapping[str, str] with non-empty keys; endpoint must be http(s) URL when provided; shape dataclasses freeze consumed-key sets to prevent accidental mutation.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/lib/enums/tracing.py
TESTS: tests/test_otel_tracer_transport.py, tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.tracing import OpenInferenceSpanKind, TraceProvider
from vidbyte.lib.errors import ConfigurationError, TracerConfigurationError


def _require_non_empty_str(value: str | None, field_name: str) -> str | None:
    # Validates that a string field is non-empty after stripping when provided.
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TracerConfigurationError(f"{field_name} must be a non-empty string when provided.")
    return value.strip()


def _require_headers(value: Mapping[str, str] | None, field_name: str) -> Mapping[str, str] | None:
    # Validates headers is Mapping[str, str] with non-empty string keys/values.
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TracerConfigurationError(f"{field_name} must be a mapping of str->str when provided.")
    normalized: dict[str, str] = {}
    for key, val in value.items():
        if not isinstance(key, str) or not key.strip():
            raise TracerConfigurationError(f"{field_name} keys must be non-empty strings.")
        if not isinstance(val, str):
            raise TracerConfigurationError(f"{field_name} values must be strings.")
        normalized[key.strip()] = val
    return normalized


@dataclass(frozen=True, slots=True)
class OTelTracerConfig:
    """Validated construction contract for the destination-agnostic OTel tracer.

    Mirrors OTelTracer.__init__ inputs but validates eagerly so misconfiguration
    fails at construction with a typed error rather than later at span time.
    """

    endpoint: str | None = None
    headers: Mapping[str, str] | None = None
    service_name: str | None = None
    exporter: Any = None

    def __post_init__(self) -> None:
        # Validates endpoint URL shape, headers mapping, and service name.
        normalized_endpoint = _require_non_empty_str(self.endpoint, "endpoint")
        if normalized_endpoint is not None and not (normalized_endpoint.startswith("http://") or normalized_endpoint.startswith("https://")):
            raise TracerConfigurationError("endpoint must start with http:// or https://.")
        object.__setattr__(self, "endpoint", normalized_endpoint)
        object.__setattr__(self, "headers", _require_headers(self.headers, "headers"))
        normalized_service = _require_non_empty_str(self.service_name, "service_name")
        object.__setattr__(self, "service_name", normalized_service)


@dataclass(frozen=True, slots=True)
class OTelSpanContextData:
    """Validated carrier for a raw OpenTelemetry span and its context token."""

    span: Any = field(default=None)
    token: Any = field(default=None)


@dataclass(frozen=True, slots=True)
class OTelGenAIShapeDefinition:
    """Top-level shape contract for the OTel GenAI translator.

    Declared as trace_shape={dataclass} alongside the provider marker so the
    shape's consumed keys and operation names are a single validated object.
    """

    provider: str = field(default=TraceProvider.OTEL_GENAI.value)
    llm_consumed_keys: frozenset[str] = field(default_factory=lambda: frozenset({"model", "provider", "input_messages", "messages", "system", "system_prompt", "input_tokens", "output_tokens", "finish_reason"}))
    tool_consumed_keys: frozenset[str] = field(default_factory=lambda: frozenset({"tool_name", "call_id", "arguments", "tool_input"}))
    agent_consumed_keys: frozenset[str] = field(default_factory=lambda: frozenset({"agent_name", "provider", "run_id"}))

    def __post_init__(self) -> None:
        # Validates provider marker and that consumed-key sets are non-empty frozensets of strings.
        if self.provider != TraceProvider.OTEL_GENAI.value:
            raise ConfigurationError(f"OTelGenAIShapeDefinition provider must be {TraceProvider.OTEL_GENAI.value!r}.")
        for field_name in ("llm_consumed_keys", "tool_consumed_keys", "agent_consumed_keys"):
            value = getattr(self, field_name)
            if not isinstance(value, frozenset) or not value or not all(isinstance(item, str) and item.strip() for item in value):
                raise ConfigurationError(f"{field_name} must be a non-empty frozenset of non-empty strings.")
            object.__setattr__(self, field_name, frozenset(item.strip() for item in value))


@dataclass(frozen=True, slots=True)
class OpenInferenceShapeDefinition:
    """Top-level shape contract for the OpenInference translator."""

    provider: str = field(default=TraceProvider.OPENINFERENCE.value)
    kind_mapping: Mapping[str, OpenInferenceSpanKind] = field(default_factory=lambda: _default_openinference_kind_mapping())
    llm_consumed_keys: frozenset[str] = field(default_factory=lambda: frozenset({"model", "input_messages", "messages", "input_tokens", "output_tokens"}))
    tool_consumed_keys: frozenset[str] = field(default_factory=lambda: frozenset({"tool_name", "call_id", "arguments", "tool_input"}))

    def __post_init__(self) -> None:
        # Validates provider marker and that kind_mapping is a non-empty mapping of string keys.
        if self.provider != TraceProvider.OPENINFERENCE.value:
            raise ConfigurationError(f"OpenInferenceShapeDefinition provider must be {TraceProvider.OPENINFERENCE.value!r}.")
        if not isinstance(self.kind_mapping, Mapping) or not self.kind_mapping:
            raise ConfigurationError("kind_mapping must be a non-empty mapping.")
        for key, value in self.kind_mapping.items():
            if not isinstance(key, str) or not key.strip():
                raise ConfigurationError("kind_mapping keys must be non-empty strings.")
            if not isinstance(value, OpenInferenceSpanKind):
                raise ConfigurationError("kind_mapping values must be OpenInferenceSpanKind.")
        for field_name in ("llm_consumed_keys", "tool_consumed_keys"):
            value = getattr(self, field_name)
            if not isinstance(value, frozenset) or not value or not all(isinstance(item, str) and item.strip() for item in value):
                raise ConfigurationError(f"{field_name} must be a non-empty frozenset of non-empty strings.")
            object.__setattr__(self, field_name, frozenset(item.strip() for item in value))


def _default_openinference_kind_mapping() -> dict[str, OpenInferenceSpanKind]:
    # Builds the default kind mapping using string keys (SpanKind values) to keep lib layer independent of trace schema.
    return {
        "chain": OpenInferenceSpanKind.CHAIN,
        "llm": OpenInferenceSpanKind.LLM,
        "tool": OpenInferenceSpanKind.TOOL,
        "retriever": OpenInferenceSpanKind.RETRIEVER,
        "embedding": OpenInferenceSpanKind.EMBEDDING,
        "prompt": OpenInferenceSpanKind.CHAIN,
        "parser": OpenInferenceSpanKind.CHAIN,
    }


@dataclass(frozen=True, slots=True)
class OTelGenAIAgentShape:
    """Structured payload for an agent.run -> invoke_agent GenAI span."""

    span_name: str
    operation_name: str
    agent_name: str
    provider_name: str | None = None
    conversation_id: str | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates required string fields are non-empty.
        if not isinstance(self.span_name, str) or not self.span_name.strip():
            raise ConfigurationError("OTelGenAIAgentShape.span_name must be a non-empty string.")
        if not isinstance(self.operation_name, str) or not self.operation_name.strip():
            raise ConfigurationError("OTelGenAIAgentShape.operation_name must be a non-empty string.")
        if not isinstance(self.agent_name, str) or not self.agent_name.strip():
            raise ConfigurationError("OTelGenAIAgentShape.agent_name must be a non-empty string.")
        object.__setattr__(self, "span_name", self.span_name.strip())
        object.__setattr__(self, "operation_name", self.operation_name.strip())
        object.__setattr__(self, "agent_name", self.agent_name.strip())


@dataclass(frozen=True, slots=True)
class OTelGenAILLMShape:
    """Structured payload for a SpanKind.LLM -> chat GenAI span."""

    span_name: str
    operation_name: str
    provider_name: str
    request_model: str
    input_messages: Any | None = None
    system_instructions: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reasons: Any | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates required string fields and token counts when provided.
        for name in ("span_name", "operation_name", "provider_name", "request_model"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                raise ConfigurationError(f"OTelGenAILLMShape.{name} must be a non-empty string.")
            object.__setattr__(self, name, val.strip())
        if self.input_tokens is not None and (not isinstance(self.input_tokens, int) or isinstance(self.input_tokens, bool) or self.input_tokens < 0):
            raise ConfigurationError("OTelGenAILLMShape.input_tokens must be a non-negative integer when provided.")
        if self.output_tokens is not None and (not isinstance(self.output_tokens, int) or isinstance(self.output_tokens, bool) or self.output_tokens < 0):
            raise ConfigurationError("OTelGenAILLMShape.output_tokens must be a non-negative integer when provided.")


@dataclass(frozen=True, slots=True)
class OTelGenAIToolShape:
    """Structured payload for a SpanKind.TOOL -> execute_tool GenAI span."""

    span_name: str
    operation_name: str
    tool_name: str
    call_id: str | None = None
    call_arguments: Any | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates required string fields.
        for name in ("span_name", "operation_name", "tool_name"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                raise ConfigurationError(f"OTelGenAIToolShape.{name} must be a non-empty string.")
            object.__setattr__(self, name, val.strip())


@dataclass(frozen=True, slots=True)
class OpenInferenceLLMShape:
    """Structured payload for an OpenInference LLM span."""

    span_name: str
    span_kind: str
    model_name: str | None = None
    input_messages: Any | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates span_name and span_kind are non-empty strings.
        for name in ("span_name", "span_kind"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                raise ConfigurationError(f"OpenInferenceLLMShape.{name} must be a non-empty string.")
            object.__setattr__(self, name, val.strip())


@dataclass(frozen=True, slots=True)
class OpenInferenceToolShape:
    """Structured payload for an OpenInference TOOL span."""

    span_name: str
    span_kind: str
    tool_name: str | None = None
    call_id: str | None = None
    function_arguments: str | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates span_name and span_kind.
        for name in ("span_name", "span_kind"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                raise ConfigurationError(f"OpenInferenceToolShape.{name} must be a non-empty string.")
            object.__setattr__(self, name, val.strip())


__all__ = [
    "OTelGenAIAgentShape",
    "OTelGenAILLMShape",
    "OTelGenAIShapeDefinition",
    "OTelGenAIToolShape",
    "OTelSpanContextData",
    "OTelTracerConfig",
    "OpenInferenceLLMShape",
    "OpenInferenceShapeDefinition",
    "OpenInferenceToolShape",
]
