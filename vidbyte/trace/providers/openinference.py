"""FILE: vidbyte/trace/providers/openinference.py

PURPOSE: Maps Vidbyte SpanSpec objects into OpenInference semantic convention attributes.
ROLE IN CODEBASE: One ProviderTraceTranslator implementation selected via provider="openinference".
ARCHITECTURE NOTE: openinference.span.kind is set on every span; only LLM/TOOL kinds get further verified field mappings.
COMMON MODIFICATION PATTERNS: Add a new _translate_* branch and its consumed-key set together when a new span kind's field mapping is verified against the live spec.
KNOWN EDGE CASES: Tool call arguments are JSON-encoded, never a Python repr, so downstream consumers can parse them.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_openinference_trace_shape.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.tracing import (
    OpenInferenceLLMShape,
    OpenInferenceShapeDefinition,
    OpenInferenceToolShape,
)
from vidbyte.lib.enums.tracing import OpenInferenceAttribute, TraceProvider, TraceShapeNamespace
from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanKind, SpanSpec

# Validated shape contract declared at the provider line so consumed keys and kind mapping are a single frozen object.
trace_shape = OpenInferenceShapeDefinition()
_KIND_TO_OPENINFERENCE = trace_shape.kind_mapping
_LLM_CONSUMED_KEYS: frozenset[str] = trace_shape.llm_consumed_keys
_TOOL_CONSUMED_KEYS: frozenset[str] = trace_shape.tool_consumed_keys


class OpenInferenceProviderTranslator:
    """Maps semantic span specs into the OpenInference semantic conventions shape."""

    provider = TraceProvider.OPENINFERENCE.value
    shape = trace_shape

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Dispatches to the LLM/tool mapping, or a generic passthrough that still sets span.kind.
        if spec.kind is SpanKind.LLM:
            return self._translate_llm(spec)
        if spec.kind is SpanKind.TOOL:
            return self._translate_tool(spec)
        return self._translate_generic(spec)

    def _translate_llm(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps an LLM-kind span into llm.* attributes per the OpenInference spec via a validated shape dataclass.
        attrs = dict(spec.attributes)
        # Fill the typed shape dataclass so attribute construction is validated, not ad-hoc dict literals.
        llm_shape = OpenInferenceLLMShape(
            span_name=spec.name,
            span_kind=_KIND_TO_OPENINFERENCE[spec.kind.value].value,
            model_name=str(attrs["model"]) if "model" in attrs else None,
            input_messages=attrs.get("input_messages") or attrs.get("messages"),
            prompt_tokens=attrs.get("input_tokens") if isinstance(attrs.get("input_tokens"), int) else None,
            completion_tokens=attrs.get("output_tokens") if isinstance(attrs.get("output_tokens"), int) else None,
            extras=self._namespaced_extras(attrs, _LLM_CONSUMED_KEYS),
        )
        out: dict[str, Any] = {OpenInferenceAttribute.SPAN_KIND.value: llm_shape.span_kind}
        if llm_shape.model_name is not None:
            out[OpenInferenceAttribute.LLM_MODEL_NAME.value] = llm_shape.model_name
        input_messages = llm_shape.input_messages or ()
        for index, message in enumerate(input_messages):
            if isinstance(message, Mapping):
                out[f"llm.input_messages.{index}.message.role"] = message.get("role")
                out[f"llm.input_messages.{index}.message.content"] = message.get("content")
        if llm_shape.prompt_tokens is not None:
            out[OpenInferenceAttribute.LLM_TOKEN_COUNT_PROMPT.value] = llm_shape.prompt_tokens
        if llm_shape.completion_tokens is not None:
            out[OpenInferenceAttribute.LLM_TOKEN_COUNT_COMPLETION.value] = llm_shape.completion_tokens
        out.update(llm_shape.extras)
        return ProviderSpanPayload(name=llm_shape.span_name, attributes=out)

    def _translate_tool(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps a TOOL-kind span into tool.*/tool_call.* attributes via a validated shape dataclass.
        attrs = dict(spec.attributes)
        tool_name = attrs.get("tool_name")
        call_id = attrs.get("call_id")
        arguments = attrs.get("arguments", attrs.get("tool_input"))
        encoded_arguments = json.dumps(arguments, default=str) if arguments is not None else None
        tool_shape = OpenInferenceToolShape(
            span_name=spec.name,
            span_kind=_KIND_TO_OPENINFERENCE[spec.kind.value].value,
            tool_name=str(tool_name) if tool_name is not None else None,
            call_id=str(call_id) if call_id is not None else None,
            function_arguments=encoded_arguments,
            extras=self._namespaced_extras(attrs, _TOOL_CONSUMED_KEYS),
        )
        out: dict[str, Any] = {OpenInferenceAttribute.SPAN_KIND.value: tool_shape.span_kind}
        if tool_shape.tool_name is not None:
            out[OpenInferenceAttribute.TOOL_NAME.value] = tool_shape.tool_name
            out[OpenInferenceAttribute.TOOL_CALL_FUNCTION_NAME.value] = tool_shape.tool_name
        if tool_shape.call_id is not None:
            out[OpenInferenceAttribute.TOOL_CALL_ID.value] = tool_shape.call_id
        if tool_shape.function_arguments is not None:
            out[OpenInferenceAttribute.TOOL_CALL_FUNCTION_ARGUMENTS.value] = tool_shape.function_arguments
        out.update(tool_shape.extras)
        return ProviderSpanPayload(name=tool_shape.span_name, attributes=out)

    def _translate_generic(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Sets only the required span.kind field, since no other OpenInference field applies outside LLM/TOOL.
        out = {OpenInferenceAttribute.SPAN_KIND.value: _KIND_TO_OPENINFERENCE[spec.kind.value].value, **self._namespaced_extras(dict(spec.attributes), frozenset())}
        return ProviderSpanPayload(name=spec.name, attributes=out)

    @staticmethod
    def _namespaced_extras(attrs: dict[str, Any], consumed: frozenset[str]) -> dict[str, Any]:
        # Prefixes every attribute not already mapped to a standard OpenInference field with vidbyte. to avoid collisions.
        return {f"{TraceShapeNamespace.VIDBYTE.value}.{key}": value for key, value in attrs.items() if key not in consumed}


__all__ = ["OpenInferenceProviderTranslator", "trace_shape"]
