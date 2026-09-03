"""FILE: vidbyte/trace/providers/otel_genai.py

PURPOSE: Builds OpenTelemetry GenAI-shaped trace records directly from runtime trace calls.
ROLE IN CODEBASE: Provides the Trace.otel_genai() in-memory provider for agent.run, llm.call, and tool.call.
ARCHITECTURE NOTE: The provider maps raw runtime attributes into plain dictionaries and performs no export or endpoint management.
COMMON MODIFICATION PATTERNS: Add only provider-semantic mappings here; preserve raw extras under vidbyte.* and keep lifecycle handling in the shared base.
KNOWN EDGE CASES: Missing runtime metadata uses documented fallback names; unsupported attributes remain namespaced instead of being guessed into GenAI fields.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: tests/test_otel_genai_trace_shape.py, scripts/test-trace-shape-prebuilts.py
"""

from __future__ import annotations

from typing import Any

from vidbyte.trace.providers.base import _InMemoryShapeTrace

_GENAI_OPERATION = "gen_ai.operation.name"
_GENAI_PROVIDER = "gen_ai.provider.name"
_GENAI_AGENT = "gen_ai.agent.name"
_GENAI_CONVERSATION = "gen_ai.conversation.id"
_GENAI_MODEL = "gen_ai.request.model"
_GENAI_INPUT = "gen_ai.input.messages"
_GENAI_SYSTEM = "gen_ai.system_instructions"
_GENAI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_GENAI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
_GENAI_FINISH_REASONS = "gen_ai.response.finish_reasons"
_GENAI_TOOL = "gen_ai.tool.name"
_GENAI_TOOL_ID = "gen_ai.tool.call.id"
_GENAI_TOOL_ARGUMENTS = "gen_ai.tool.call.arguments"

_AGENT_FIELDS = frozenset({"agent_name", "provider", "run_id"})
_LLM_FIELDS = frozenset(
    {
        "model",
        "provider",
        "input_messages",
        "messages",
        "system",
        "system_prompt",
        "input_tokens",
        "output_tokens",
        "finish_reason",
        "finish_reasons",
    }
)
_TOOL_FIELDS = frozenset({"tool_name", "call_id", "arguments", "tool_input"})


class OTelGenAITrace(_InMemoryShapeTrace):
    """Builds OTel GenAI-shaped dictionaries directly from runtime trace calls."""

    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Dispatches on the same operation names emitted by BaseAgent and AgentRuntime.
        if name == "agent.run":
            return self._shape_agent(attributes)
        if name == "llm.call":
            return self._shape_llm(attributes)
        if name == "tool.call":
            return self._shape_tool(attributes)
        return name, self._generic_attributes(name, attributes)

    @staticmethod
    def _shape_update(name: str, attributes: dict[str, Any]) -> dict[str, Any]:
        # Maps only post-response LLM fields so start-time model and provider values remain intact.
        if name != "llm.call":
            return {}
        shaped: dict[str, Any] = {}
        if attributes.get("input_tokens") is not None:
            shaped[_GENAI_INPUT_TOKENS] = attributes["input_tokens"]
        if attributes.get("output_tokens") is not None:
            shaped[_GENAI_OUTPUT_TOKENS] = attributes["output_tokens"]
        finish_reasons = attributes.get("finish_reasons")
        if finish_reasons is None:
            finish_reasons = attributes.get("finish_reason")
        if finish_reasons is not None:
            shaped[_GENAI_FINISH_REASONS] = _as_finish_reasons(finish_reasons)
        return shaped

    @staticmethod
    def _shape_agent(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # @intent provider-shape Keep agent identity explicit for the invoke_agent record.
        agent_name = str(attributes.get("agent_name") or "agent")
        shaped: dict[str, Any] = {
            _GENAI_OPERATION: "invoke_agent",
            _GENAI_AGENT: agent_name,
        }
        if attributes.get("provider") is not None:
            shaped[_GENAI_PROVIDER] = str(attributes["provider"])
        if attributes.get("run_id") is not None:
            shaped[_GENAI_CONVERSATION] = str(attributes["run_id"])
        shaped.update(_namespaced(attributes, _AGENT_FIELDS))
        return f"invoke_agent {agent_name}", shaped

    @staticmethod
    def _shape_llm(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # @intent provider-shape Keep the chat record standards-aligned without fabricating optional metadata.
        model = str(attributes.get("model") or "unknown")
        provider = str(attributes.get("provider") or "unknown")
        shaped: dict[str, Any] = {
            _GENAI_OPERATION: "chat",
            _GENAI_PROVIDER: provider,
            _GENAI_MODEL: model,
        }
        input_messages = attributes.get("input_messages")
        if input_messages is None:
            input_messages = attributes.get("messages")
        if input_messages is not None:
            shaped[_GENAI_INPUT] = input_messages
        system_instructions = attributes.get("system")
        if system_instructions is None:
            system_instructions = attributes.get("system_prompt")
        if system_instructions is not None:
            shaped[_GENAI_SYSTEM] = system_instructions
        if attributes.get("input_tokens") is not None:
            shaped[_GENAI_INPUT_TOKENS] = attributes["input_tokens"]
        if attributes.get("output_tokens") is not None:
            shaped[_GENAI_OUTPUT_TOKENS] = attributes["output_tokens"]
        finish_reasons = attributes.get("finish_reasons")
        if finish_reasons is None:
            finish_reasons = attributes.get("finish_reason")
        if finish_reasons is not None:
            shaped[_GENAI_FINISH_REASONS] = _as_finish_reasons(finish_reasons)
        shaped.update(_namespaced(attributes, _LLM_FIELDS))
        return f"chat {model}", shaped

    @staticmethod
    def _shape_tool(attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Maps the tool call to the OTel execute_tool convention.
        tool_name = str(attributes.get("tool_name") or "unknown_tool")
        shaped: dict[str, Any] = {
            _GENAI_OPERATION: "execute_tool",
            _GENAI_TOOL: tool_name,
        }
        if attributes.get("call_id") is not None:
            shaped[_GENAI_TOOL_ID] = str(attributes["call_id"])
        arguments = attributes.get("arguments")
        if arguments is None:
            arguments = attributes.get("tool_input")
        if arguments is not None:
            shaped[_GENAI_TOOL_ARGUMENTS] = arguments
        shaped.update(_namespaced(attributes, _TOOL_FIELDS))
        return f"execute_tool {tool_name}", shaped

    @staticmethod
    def _generic_attributes(name: str, attributes: dict[str, Any]) -> dict[str, Any]:
        # Keeps unsupported operations honest instead of guessing a GenAI convention.
        return {_GENAI_OPERATION: name, **_namespaced(attributes, frozenset())}


def _namespaced(attributes: dict[str, Any], consumed: frozenset[str]) -> dict[str, Any]:
    # Retains runtime-specific context without colliding with standard GenAI fields.
    return {f"vidbyte.{key}": value for key, value in attributes.items() if key not in consumed}


def _as_finish_reasons(value: Any) -> Any:
    # The OTel field is an array; normalize the common scalar runtime value without coercing other shapes.
    if isinstance(value, str):
        return [value]
    if isinstance(value, tuple):
        return list(value)
    return value


__all__ = ["OTelGenAITrace"]
