"""OpenTelemetry GenAI semantic conventions translator for Vidbyte semantic spans."""

from __future__ import annotations

from typing import Any

from vidbyte.trace.providers.base import ProviderSpanPayload
from vidbyte.trace.schema import SpanKind, SpanSpec

_LLM_CONSUMED_KEYS = {
    "model",
    "provider",
    "input_messages",
    "messages",
    "system",
    "system_prompt",
    "input_tokens",
    "output_tokens",
    "finish_reason",
}
_TOOL_CONSUMED_KEYS = {"tool_name", "call_id", "arguments", "tool_input"}
_AGENT_CONSUMED_KEYS = {"agent_name", "provider", "run_id"}


class OTelGenAIProviderTranslator:
    """Maps semantic span specs into the OpenTelemetry GenAI semantic conventions shape."""

    provider = "otel-genai"

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
        # Maps an agent.run span into an invoke_agent span per gen-ai-agent-spans.md.
        attrs = dict(spec.attributes)
        agent_name = attrs.get("agent_name") or "agent"
        out: dict[str, Any] = {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": agent_name}
        if "provider" in attrs:
            out["gen_ai.provider.name"] = attrs["provider"]
        if "run_id" in attrs:
            out["gen_ai.conversation.id"] = attrs["run_id"]
        out.update(self._namespaced_extras(attrs, _AGENT_CONSUMED_KEYS))
        return ProviderSpanPayload(name=f"invoke_agent {agent_name}", attributes=out)

    def _translate_llm(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps an LLM-kind span into a chat span per gen-ai-spans.md.
        attrs = dict(spec.attributes)
        model = attrs.get("model") or "unknown"
        out: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": attrs.get("provider") or "unknown",
            "gen_ai.request.model": model,
        }
        input_messages = attrs.get("input_messages") or attrs.get("messages")
        if input_messages is not None:
            out["gen_ai.input.messages"] = input_messages
        system = attrs.get("system") or attrs.get("system_prompt")
        if system is not None:
            out["gen_ai.system_instructions"] = system
        if "input_tokens" in attrs:
            out["gen_ai.usage.input_tokens"] = attrs["input_tokens"]
        if "output_tokens" in attrs:
            out["gen_ai.usage.output_tokens"] = attrs["output_tokens"]
        if "finish_reason" in attrs:
            out["gen_ai.response.finish_reasons"] = attrs["finish_reason"]
        out.update(self._namespaced_extras(attrs, _LLM_CONSUMED_KEYS))
        return ProviderSpanPayload(name=f"chat {model}", attributes=out)

    def _translate_tool(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Maps a TOOL-kind span into an execute_tool span per execute-tool-span.md.
        attrs = dict(spec.attributes)
        tool_name = attrs.get("tool_name") or "unknown_tool"
        out: dict[str, Any] = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool_name}
        if "call_id" in attrs:
            out["gen_ai.tool.call.id"] = attrs["call_id"]
        arguments = attrs.get("arguments", attrs.get("tool_input"))
        if arguments is not None:
            out["gen_ai.tool.call.arguments"] = arguments
        out.update(self._namespaced_extras(attrs, _TOOL_CONSUMED_KEYS))
        return ProviderSpanPayload(name=f"execute_tool {tool_name}", attributes=out)

    def _translate_generic(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Falls back to the semantic name with every attribute namespaced, since no gen_ai.* shape was verified for this span.
        attrs = dict(spec.attributes)
        out = {"gen_ai.operation.name": spec.name, **self._namespaced_extras(attrs, set())}
        return ProviderSpanPayload(name=spec.name, attributes=out)

    @staticmethod
    def _namespaced_extras(attrs: dict[str, Any], consumed: set[str]) -> dict[str, Any]:
        # Prefixes every attribute not already mapped to a standard gen_ai.* field with vidbyte. to avoid collisions.
        return {f"vidbyte.{key}": value for key, value in attrs.items() if key not in consumed}


__all__ = ["OTelGenAIProviderTranslator"]
