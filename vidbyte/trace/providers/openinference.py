"""OpenInference semantic conventions translator for Vidbyte semantic spans."""

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

    @staticmethod
    def _namespaced_extras(attrs: dict[str, Any], consumed: set[str]) -> dict[str, Any]:
        # Prefixes every attribute not already mapped to a standard OpenInference field with vidbyte. to avoid collisions.
        return {f"vidbyte.{key}": value for key, value in attrs.items() if key not in consumed}


__all__ = ["OpenInferenceProviderTranslator"]
