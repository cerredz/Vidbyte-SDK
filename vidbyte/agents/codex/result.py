"""Normalization of Codex turn results into Vidbyte messages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import AgentExecutionError, OutputSchemaViolationError
from vidbyte.providers.output_schema import OutputSchemaFormatter

_SUBAGENT_ITEM_TYPES = frozenset({"collabAgentToolCall", "subAgentActivity"})


@dataclass(frozen=True, slots=True)
class CodexRunResult:
    """Provider-neutral snapshot of one completed Codex turn."""

    thread_id: str
    turn_id: str
    status: str
    final_response: str | None
    duration_ms: int | None
    usage: Mapping[str, Any] | None
    items: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_sdk(cls, thread_id: str, result: Any) -> CodexRunResult:
        # Copies the bounded current-turn SDK result into plain typed data.
        return cls(
            thread_id=thread_id,
            turn_id=str(result.id),
            status=str(getattr(result.status, "value", result.status)),
            final_response=result.final_response,
            duration_ms=result.duration_ms,
            usage=CodexResultSerializer.mapping(result.usage),
            items=tuple(
                CodexResultSerializer.mapping(item) or {} for item in result.items
            ),
        )


class CodexResultSerializer:
    """Converts SDK models to safe JSON-like mappings."""

    @staticmethod
    def mapping(value: Any) -> dict[str, Any] | None:
        # Uses typed SDK serialization and rejects opaque provider objects.
        if value is None:
            return None
        if isinstance(value, Mapping):
            return dict(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json", by_alias=True)
            return dict(dumped) if isinstance(dumped, Mapping) else None
        return None


class CodexResultTranslator:
    """Builds Vidbyte messages and validates declared output schemas."""

    def __init__(self) -> None:
        # Reuses the SDK's provider-agnostic schema resolver and validator.
        self._schemas = OutputSchemaFormatter()

    def translate(self, result: CodexRunResult, *, agent_name: str, recipient: str, input_metadata: Mapping[str, Any], output_schema: type | Mapping[str, Any] | None, agent_metadata: Mapping[str, Any]) -> AgentMessage:
        # Validates the final output and attaches safe Codex lifecycle metadata.
        content = str(result.final_response or "")
        if not content:
            raise AgentExecutionError(
                f"Codex agent '{agent_name}' completed without a final response.",
                details={
                    "agent": agent_name,
                    "thread_id": result.thread_id,
                    "turn_id": result.turn_id,
                },
            )
        structured = self._structured_output(
            content, output_schema, agent_name, result.status
        )
        metadata = {
            **dict(agent_metadata),
            **dict(input_metadata),
            "provider": "codex",
            "codex_thread_id": result.thread_id,
            "codex_turn_id": result.turn_id,
            "codex_turn_status": result.status,
            "duration_ms": result.duration_ms,
            "usage": dict(result.usage or {}),
            "subagents": self._subagent_items(result.items),
            "provider_item_count": len(result.items),
        }
        return AgentMessage(
            sender=agent_name,
            recipient=recipient,
            content=content,
            metadata=metadata,
            structured=structured,
        )

    def _structured_output(self, content: str, schema: type | Mapping[str, Any] | None, agent_name: str, status: str) -> Any:
        # Parses and validates structured responses with Vidbyte's existing contract.
        if schema is None:
            return None
        structured, validation_error = self._schemas.validate(content, schema)
        if validation_error is None:
            return structured
        raise OutputSchemaViolationError(
            f"Codex agent '{agent_name}' declared an output_schema but produced no valid instance.",
            raw_output=content,
            validation_error=validation_error,
            stop_reason=status,
        )

    @staticmethod
    def _subagent_items(items: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
        # Retains only explicit collaboration activity and excludes reasoning items.
        return tuple(
            dict(item) for item in items if item.get("type") in _SUBAGENT_ITEM_TYPES
        )


__all__ = ["CodexResultTranslator", "CodexRunResult"]
