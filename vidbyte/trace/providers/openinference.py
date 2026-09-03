"""FILE: vidbyte/trace/providers/openinference.py

PURPOSE: Builds OpenInference-shaped trace records directly from runtime trace calls.
ROLE IN CODEBASE: Provides the Trace.openinference() in-memory provider for agent.run, llm.call, and tool.call.
ARCHITECTURE NOTE: The provider maps raw runtime attributes into plain dictionaries and performs no export or endpoint management.
COMMON MODIFICATION PATTERNS: Add only provider-semantic mappings here; preserve raw extras under vidbyte.* and keep lifecycle handling in the shared base.
KNOWN EDGE CASES: Missing runtime metadata is omitted; unrecognized operation names use OpenInference CHAIN, while known retriever and embedding names get their specific kinds.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: tests/test_openinference_trace_shape.py, scripts/test-trace-shape-prebuilts.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.trace.providers.base import _InMemoryShapeTrace

_SPAN_KIND = "openinference.span.kind"
_LLM_SYSTEM = "llm.system"
_LLM_PROVIDER = "llm.provider"
_LLM_MODEL = "llm.model_name"
_LLM_INPUT_TOKENS = "llm.token_count.prompt"
_LLM_OUTPUT_TOKENS = "llm.token_count.completion"
_LLM_TOTAL_TOKENS = "llm.token_count.total"
_LLM_FINISH_REASON = "llm.finish_reason"
_TOOL_NAME = "tool.name"
_TOOL_ID = "tool_call.id"
_TOOL_FUNCTION_NAME = "tool_call.function.name"
_TOOL_ARGUMENTS = "tool_call.function.arguments"
_AGENT_NAME = "agent.name"

_AGENT_FIELDS = frozenset({"agent_name"})
_LLM_FIELDS = frozenset(
    {
        "model",
        "provider",
        "input_messages",
        "messages",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "finish_reason",
    }
)
_TOOL_FIELDS = frozenset({"tool_name", "call_id", "arguments", "tool_input"})


class OpenInferenceTrace(_InMemoryShapeTrace):
    """Builds OpenInference-shaped dictionaries directly from runtime trace calls."""

    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Dispatches on the operation names emitted by the agent and runtime.
        if name == "agent.run":
            return self._shape_agent(attributes)
        if name == "llm.call":
            return self._shape_llm(attributes)
        if name == "tool.call":
            return self._shape_tool(attributes)
        return name, {
            _SPAN_KIND: _span_kind(name),
            **_namespaced(attributes, frozenset()),
        }

    @staticmethod
    def _shape_update(name: str, attributes: dict[str, Any]) -> dict[str, Any]:
        # Maps only post-response LLM fields so start-time identity and messages remain intact.
        if name != "llm.call":
            return {}
        return _llm_usage(attributes)

    @staticmethod
    def _shape_agent(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # @intent provider-shape Keep agent identity explicit so the AGENT record remains attributable.
        shaped: dict[str, Any] = {_SPAN_KIND: "AGENT"}
        agent_name = attributes.get("agent_name")
        if agent_name is not None:
            shaped[_AGENT_NAME] = str(agent_name)
        shaped.update(_namespaced(attributes, _AGENT_FIELDS))
        return "agent.run", shaped

    @staticmethod
    def _shape_llm(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # @intent provider-shape Keep the LLM record limited to documented fields and flattened messages.
        shaped: dict[str, Any] = {_SPAN_KIND: "LLM"}
        shaped.update(_llm_identity(attributes))
        shaped.update(_llm_messages(attributes))
        shaped.update(_llm_usage(attributes))
        shaped.update(_namespaced(attributes, _LLM_FIELDS))
        return "llm.call", shaped

    @staticmethod
    def _shape_tool(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Maps the tool call to OpenInference's tool and function-call attributes.
        shaped: dict[str, Any] = {_SPAN_KIND: "TOOL"}
        tool_name = attributes.get("tool_name")
        if tool_name is not None:
            tool_name = str(tool_name)
            shaped[_TOOL_NAME] = tool_name
            shaped[_TOOL_FUNCTION_NAME] = tool_name
        if attributes.get("call_id") is not None:
            shaped[_TOOL_ID] = str(attributes["call_id"])
        arguments = attributes.get("arguments")
        if arguments is None:
            arguments = attributes.get("tool_input")
        if arguments is not None:
            shaped[_TOOL_ARGUMENTS] = _json_text(arguments)
        shaped.update(_namespaced(attributes, _TOOL_FIELDS))
        return "tool.call", shaped


def _span_kind(name: str) -> str:
    # Maps known provider-neutral operation families to documented OpenInference kinds.
    if name.startswith("retriever."):
        return "RETRIEVER"
    if name.startswith("embedding."):
        return "EMBEDDING"
    return "CHAIN"


def _llm_identity(attributes: dict[str, Any]) -> dict[str, Any]:
    # @intent provider-shape Preserve provider/model identity without inventing absent values.
    shaped: dict[str, Any] = {}
    provider = attributes.get("provider")
    if provider is not None:
        shaped[_LLM_SYSTEM] = str(provider)
        shaped[_LLM_PROVIDER] = str(provider)
    model = attributes.get("model")
    if model is not None:
        shaped[_LLM_MODEL] = str(model)
    return shaped


def _llm_messages(attributes: dict[str, Any]) -> dict[str, Any]:
    # @intent provider-shape Flatten only mapping messages so malformed runtime values remain namespaced.
    messages = attributes.get("input_messages")
    if messages is None:
        messages = attributes.get("messages")
    if messages is None:
        return {}
    shaped: dict[str, Any] = {}
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            continue
        if message.get("role") is not None:
            shaped[f"llm.input_messages.{index}.message.role"] = message["role"]
        if message.get("content") is not None:
            shaped[f"llm.input_messages.{index}.message.content"] = message["content"]
    return shaped


def _llm_usage(attributes: dict[str, Any]) -> dict[str, Any]:
    # @intent provider-shape Copy usage and finish fields only when the runtime supplied them.
    fields = {
        "input_tokens": _LLM_INPUT_TOKENS,
        "output_tokens": _LLM_OUTPUT_TOKENS,
        "total_tokens": _LLM_TOTAL_TOKENS,
        "finish_reason": _LLM_FINISH_REASON,
    }
    return {target: attributes[name] for name, target in fields.items() if attributes.get(name) is not None}


def _namespaced(attributes: dict[str, Any], consumed: frozenset[str]) -> dict[str, Any]:
    # Retains runtime-specific context without colliding with OpenInference fields.
    return {f"vidbyte.{key}": value for key, value in attributes.items() if key not in consumed}


def _json_text(value: Any) -> str:
    # OpenInference requires tool_call.function.arguments to be a JSON string.
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)


__all__ = ["OpenInferenceTrace"]
