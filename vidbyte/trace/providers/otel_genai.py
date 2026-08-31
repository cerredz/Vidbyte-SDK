"""FILE: vidbyte/trace/providers/otel_genai.py

PURPOSE: Maps Vidbyte SpanSpec objects into OpenTelemetry GenAI semantic convention attributes.
ROLE IN CODEBASE: One ProviderTraceTranslator implementation selected via provider="otel-genai".
ARCHITECTURE NOTE: Only agent/LLM/tool span kinds use verified gen_ai.* fields; everything else falls back to a namespaced vidbyte.* passthrough.
COMMON MODIFICATION PATTERNS: Add a new _translate_* branch and its consumed-key set together when a new span kind's gen_ai.* mapping is verified against the live spec.
KNOWN EDGE CASES: Missing model/tool_name/agent_name fall back to stable placeholders instead of raising.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_otel_genai_trace_shape.py
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.dataclasses.tracing import (
    OTelGenAIAgentShape,
    OTelGenAILLMShape,
    OTelGenAIShapeDefinition,
    OTelGenAIToolShape,
)
from vidbyte.lib.enums.tracing import GenAIAttribute, GenAIOperation, OTelDefault, TraceProvider, TraceShapeNamespace
from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanKind, SpanSpec

# Validated shape contract declared at the provider line so consumed keys are a single frozen object.
trace_shape = OTelGenAIShapeDefinition()
_LLM_CONSUMED_KEYS: frozenset[str] = trace_shape.llm_consumed_keys
_TOOL_CONSUMED_KEYS: frozenset[str] = trace_shape.tool_consumed_keys
_AGENT_CONSUMED_KEYS: frozenset[str] = trace_shape.agent_consumed_keys


class OTelGenAIProviderTranslator:
    """Maps semantic span specs into the OpenTelemetry GenAI semantic conventions shape."""

    provider = TraceProvider.OTEL_GENAI.value
    shape = trace_shape

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Dispatches to the verified agent/LLM/tool mapping, or a generic namespaced fallback.
        if spec.name == "agent.run":
            return self._translate_agent(spec)
        if spec.kind is SpanKind.LLM:
            return self._translate_llm(spec)
        if spec.kind is SpanKind.TOOL:
            return self._translate_tool(spec)
        return self._translate_generic(spec)

    def _translate_agent(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps an agent.run span into an invoke_agent span per gen-ai-agent-spans.md via a validated shape dataclass.
        attrs = dict(spec.attributes)
        agent_name = str(attrs.get("agent_name") or OTelDefault.UNKNOWN_AGENT.value)
        provider_name = attrs.get("provider")
        conversation_id = attrs.get("run_id")
        agent_shape = OTelGenAIAgentShape(
            span_name=f"{GenAIOperation.INVOKE_AGENT.value} {agent_name}",
            operation_name=GenAIOperation.INVOKE_AGENT.value,
            agent_name=agent_name,
            provider_name=str(provider_name) if provider_name is not None else None,
            conversation_id=str(conversation_id) if conversation_id is not None else None,
            extras=self._namespaced_extras(attrs, _AGENT_CONSUMED_KEYS),
        )
        out: dict[str, Any] = {
            GenAIAttribute.OPERATION_NAME.value: agent_shape.operation_name,
            GenAIAttribute.AGENT_NAME.value: agent_shape.agent_name,
        }
        if agent_shape.provider_name is not None:
            out[GenAIAttribute.PROVIDER_NAME.value] = agent_shape.provider_name
        if agent_shape.conversation_id is not None:
            out[GenAIAttribute.CONVERSATION_ID.value] = agent_shape.conversation_id
        out.update(agent_shape.extras)
        return ProviderSpanPayload(name=agent_shape.span_name, attributes=out)

    def _translate_llm(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps an LLM-kind span into a chat span per gen-ai-spans.md via a validated shape dataclass.
        attrs = dict(spec.attributes)
        model = str(attrs.get("model") or OTelDefault.UNKNOWN_MODEL.value)
        provider_name = str(attrs.get("provider") or OTelDefault.UNKNOWN_MODEL.value)
        llm_shape = OTelGenAILLMShape(
            span_name=f"{GenAIOperation.CHAT.value} {model}",
            operation_name=GenAIOperation.CHAT.value,
            provider_name=provider_name,
            request_model=model,
            input_messages=attrs.get("input_messages") or attrs.get("messages"),
            system_instructions=attrs.get("system") or attrs.get("system_prompt"),
            input_tokens=attrs.get("input_tokens") if isinstance(attrs.get("input_tokens"), int) else None,
            output_tokens=attrs.get("output_tokens") if isinstance(attrs.get("output_tokens"), int) else None,
            finish_reasons=attrs.get("finish_reason"),
            extras=self._namespaced_extras(attrs, _LLM_CONSUMED_KEYS),
        )
        out: dict[str, Any] = {
            GenAIAttribute.OPERATION_NAME.value: llm_shape.operation_name,
            GenAIAttribute.PROVIDER_NAME.value: llm_shape.provider_name,
            GenAIAttribute.REQUEST_MODEL.value: llm_shape.request_model,
        }
        if llm_shape.input_messages is not None:
            out[GenAIAttribute.INPUT_MESSAGES.value] = llm_shape.input_messages
        if llm_shape.system_instructions is not None:
            out[GenAIAttribute.SYSTEM_INSTRUCTIONS.value] = llm_shape.system_instructions
        if llm_shape.input_tokens is not None:
            out[GenAIAttribute.USAGE_INPUT_TOKENS.value] = llm_shape.input_tokens
        if llm_shape.output_tokens is not None:
            out[GenAIAttribute.USAGE_OUTPUT_TOKENS.value] = llm_shape.output_tokens
        if llm_shape.finish_reasons is not None:
            out[GenAIAttribute.RESPONSE_FINISH_REASONS.value] = llm_shape.finish_reasons
        out.update(llm_shape.extras)
        return ProviderSpanPayload(name=llm_shape.span_name, attributes=out)

    def _translate_tool(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps a TOOL-kind span into an execute_tool span per execute-tool-span.md via a validated shape dataclass.
        attrs = dict(spec.attributes)
        tool_name = str(attrs.get("tool_name") or OTelDefault.UNKNOWN_TOOL.value)
        tool_shape = OTelGenAIToolShape(
            span_name=f"{GenAIOperation.EXECUTE_TOOL.value} {tool_name}",
            operation_name=GenAIOperation.EXECUTE_TOOL.value,
            tool_name=tool_name,
            call_id=str(attrs["call_id"]) if "call_id" in attrs else None,
            call_arguments=attrs.get("arguments", attrs.get("tool_input")),
            extras=self._namespaced_extras(attrs, _TOOL_CONSUMED_KEYS),
        )
        out: dict[str, Any] = {
            GenAIAttribute.OPERATION_NAME.value: tool_shape.operation_name,
            GenAIAttribute.TOOL_NAME.value: tool_shape.tool_name,
        }
        if tool_shape.call_id is not None:
            out[GenAIAttribute.TOOL_CALL_ID.value] = tool_shape.call_id
        if tool_shape.call_arguments is not None:
            out[GenAIAttribute.TOOL_CALL_ARGUMENTS.value] = tool_shape.call_arguments
        out.update(tool_shape.extras)
        return ProviderSpanPayload(name=tool_shape.span_name, attributes=out)

    def _translate_generic(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Falls back to the semantic name with every attribute namespaced, since no gen_ai.* shape was verified for this span.
        attrs = dict(spec.attributes)
        out = {GenAIAttribute.OPERATION_NAME.value: spec.name, **self._namespaced_extras(attrs, frozenset())}
        return ProviderSpanPayload(name=spec.name, attributes=out)

    @staticmethod
    def _namespaced_extras(attrs: dict[str, Any], consumed: frozenset[str]) -> dict[str, Any]:
        # Prefixes every attribute not already mapped to a standard gen_ai.* field with vidbyte. to avoid collisions.
        return {f"{TraceShapeNamespace.VIDBYTE.value}.{key}": value for key, value in attrs.items() if key not in consumed}


__all__ = ["OTelGenAIProviderTranslator", "trace_shape"]
