"""FILE: vidbyte/trace/providers/openinference.py

PURPOSE: Maps Vidbyte SpanSpec objects into OpenInference semantic convention attributes.
ROLE IN CODEBASE: One ProviderTraceTranslator implementation selected via provider="openinference".
ARCHITECTURE NOTE: openinference.span.kind is set on every span; only LLM/TOOL kinds get further verified field mappings. translate_end mirrors translate_start for close-time data (response text, usage) that only exists after a call returns.
COMMON MODIFICATION PATTERNS: Add a new _translate_* branch and its consumed-key set together when a new span kind's field mapping is verified against the live spec.
KNOWN EDGE CASES: Tool call arguments are JSON-encoded, never a Python repr, so downstream consumers can parse them.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, docs/design/trace-output-and-usage-attributes.md
TESTS: tests/test_openinference_trace_shape.py, tests/test_trace_close_attributes.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanKind, SpanSpec

_KIND_TO_OPENINFERENCE = {
    SpanKind.CHAIN: "CHAIN",
    SpanKind.LLM: "LLM",
    SpanKind.TOOL: "TOOL",
    SpanKind.RETRIEVER: "RETRIEVER",
    SpanKind.EMBEDDING: "EMBEDDING",
    SpanKind.PROMPT: "CHAIN",
    SpanKind.PARSER: "CHAIN",
}
_LLM_CONSUMED_KEYS = {"model", "input_messages", "messages", "input_tokens", "output_tokens"}
_TOOL_CONSUMED_KEYS = {"tool_name", "call_id", "arguments", "tool_input"}
_LLM_END_CONSUMED_KEYS = {"output_messages", "output_tokens", "total_tokens"}


class OpenInferenceProviderTranslator:
    """Maps semantic span specs into the OpenInference semantic conventions shape."""

    provider = "openinference"

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Dispatches to the LLM/tool mapping, or a generic passthrough that still sets span.kind.
        if spec.kind is SpanKind.LLM:
            return self._translate_llm(spec)
        if spec.kind is SpanKind.TOOL:
            return self._translate_tool(spec)
        return self._translate_generic(spec)

    def _translate_llm(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps an LLM-kind span into llm.* attributes per the OpenInference spec.
        attrs = dict(spec.attributes)
        out: dict[str, Any] = {"openinference.span.kind": "LLM"}
        if "model" in attrs:
            out["llm.model_name"] = attrs["model"]
        input_messages = attrs.get("input_messages") or attrs.get("messages") or ()
        for index, message in enumerate(input_messages):
            if isinstance(message, Mapping):
                out[f"llm.input_messages.{index}.message.role"] = message.get("role")
                out[f"llm.input_messages.{index}.message.content"] = message.get("content")
        if "input_tokens" in attrs:
            out["llm.token_count.prompt"] = attrs["input_tokens"]
        if "output_tokens" in attrs:
            out["llm.token_count.completion"] = attrs["output_tokens"]
        out.update(self._namespaced_extras(attrs, _LLM_CONSUMED_KEYS))
        return ProviderSpanPayload(name=spec.name, attributes=out)

    def _translate_tool(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps a TOOL-kind span into tool.*/tool_call.* attributes per the OpenInference spec.
        attrs = dict(spec.attributes)
        out: dict[str, Any] = {"openinference.span.kind": "TOOL"}
        tool_name = attrs.get("tool_name")
        if tool_name is not None:
            out["tool.name"] = tool_name
            out["tool_call.function.name"] = tool_name
        if "call_id" in attrs:
            out["tool_call.id"] = attrs["call_id"]
        arguments = attrs.get("arguments", attrs.get("tool_input"))
        if arguments is not None:
            out["tool_call.function.arguments"] = json.dumps(arguments, default=str)
        out.update(self._namespaced_extras(attrs, _TOOL_CONSUMED_KEYS))
        return ProviderSpanPayload(name=spec.name, attributes=out)

    def _translate_generic(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Sets only the required span.kind field, since no other OpenInference field applies outside LLM/TOOL.
        out = {"openinference.span.kind": _KIND_TO_OPENINFERENCE[spec.kind], **self._namespaced_extras(dict(spec.attributes), set())}
        return ProviderSpanPayload(name=spec.name, attributes=out)

    def translate_end(self, spec: SpanSpec, attributes: Mapping[str, Any]) -> dict[str, Any]:
        # Dispatches close-time attributes the same way translate_start dispatches open-time ones.
        if spec.kind is SpanKind.LLM:
            return self._translate_llm_end(attributes)
        return self._namespaced_extras(dict(attributes), set())

    def _translate_llm_end(self, attributes: Mapping[str, Any]) -> dict[str, Any]:
        # Maps close-time LLM fields: output messages and completion/total token counts.
        attrs = dict(attributes)
        out: dict[str, Any] = {}
        output_messages = attrs.get("output_messages") or ()
        for index, message in enumerate(output_messages):
            if isinstance(message, Mapping):
                out[f"llm.output_messages.{index}.message.role"] = message.get("role")
                out[f"llm.output_messages.{index}.message.content"] = message.get("content")
        if "output_tokens" in attrs:
            out["llm.token_count.completion"] = attrs["output_tokens"]
        if "total_tokens" in attrs:
            out["llm.token_count.total"] = attrs["total_tokens"]
        out.update(self._namespaced_extras(attrs, _LLM_END_CONSUMED_KEYS))
        return out

    @staticmethod
    def _namespaced_extras(attrs: dict[str, Any], consumed: set[str]) -> dict[str, Any]:
        # Prefixes every attribute not already mapped to a standard OpenInference field with vidbyte. to avoid collisions.
        return {f"vidbyte.{key}": value for key, value in attrs.items() if key not in consumed}


__all__ = ["OpenInferenceProviderTranslator"]
