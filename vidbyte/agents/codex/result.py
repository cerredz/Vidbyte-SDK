"""Normalization of Codex turn results into Vidbyte messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_NAME,
    CODEX_ROOT_FORK_DEPTH,
    CODEX_SUBAGENT_ITEM_TYPES,
    CODEX_SUPPORTED_ITEM_TYPES,
    CODEX_ZERO_DURATION_MS,
)
from vidbyte.lib.dataclasses.codex import (
    CodexItem,
    CodexMessageData,
    CodexResultTranslationRequest,
    CodexRunResult,
    CodexUsage,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, OutputSchemaViolationError
from vidbyte.providers.output_schema import OutputSchemaFormatter


class CodexResultSerializer:
    """Copies stable SDK result models into bounded Vidbyte dataclasses."""

    @classmethod
    def from_sdk(cls, thread_id: str, result: object) -> CodexRunResult:
        final_response = getattr(result, "final_response", None)
        if not isinstance(final_response, str) or not final_response:
            raise CodexAgentError(
                "Codex completed without a final response.",
                failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                operation="normalize_result",
            )
        return CodexRunResult(
            thread_id=thread_id,
            turn_id=str(getattr(result, "id", "")),
            status=str(
                getattr(
                    getattr(result, "status", ""),
                    "value",
                    getattr(result, "status", ""),
                )
            ),
            final_response=final_response,
            duration_ms=int(
                getattr(result, "duration_ms", CODEX_ZERO_DURATION_MS)
                or CODEX_ZERO_DURATION_MS
            ),
            usage=cls._usage(getattr(result, "usage", None)),
            items=tuple(cls._item(item) for item in getattr(result, "items", ())),
        )

    @classmethod
    def _item(cls, value: object) -> CodexItem:
        payload = cls._mapping(value)
        nested = payload.get("root")
        if isinstance(nested, Mapping):
            payload = dict(nested)
        item_type = str(payload.pop("type", "unknown"))
        item_id = str(payload.pop("id", ""))
        if item_type == "reasoning":
            payload.pop("content", None)
        if item_type not in CODEX_SUPPORTED_ITEM_TYPES:
            payload = {}
        return CodexItem(id=item_id, type=item_type, fields=payload)

    @classmethod
    def _usage(cls, value: object) -> CodexUsage:
        payload = cls._mapping(value)
        total = payload.get("total", {})
        if not isinstance(total, Mapping):
            total = {}
        return CodexUsage(
            input_tokens=int(total.get("inputTokens", 0) or 0),
            cached_input_tokens=int(total.get("cachedInputTokens", 0) or 0),
            cache_write_input_tokens=int(total.get("cacheWriteInputTokens", 0) or 0),
            output_tokens=int(total.get("outputTokens", 0) or 0),
            reasoning_output_tokens=int(total.get("reasoningOutputTokens", 0) or 0),
            total_tokens=int(total.get("totalTokens", 0) or 0),
            model_context_window=int(payload.get("modelContextWindow", 0) or 0),
        )

    @staticmethod
    def _mapping(value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json", by_alias=True)
            return dict(dumped) if isinstance(dumped, Mapping) else {}
        return {}


class CodexResultTranslator:
    """Builds Vidbyte messages and validates declared output schemas."""

    def __init__(self) -> None:
        self._schemas = OutputSchemaFormatter()

    def translate(self, request: CodexResultTranslationRequest) -> AgentMessage:
        # @intent typed-provider-result
        # Validate output and publish deterministic Codex data separately from
        # generic metadata so callers never need to parse provider dictionaries.
        result = request.result
        agent = request.agent
        structured = self._structured_output(
            result.final_response, agent.output_schema, agent.name, result.status
        )
        lineage = dict(agent.metadata)
        codex = CodexMessageData(
            thread_id=result.thread_id,
            turn_id=result.turn_id,
            status=result.status,
            duration_ms=result.duration_ms,
            usage=result.usage,
            items=result.items,
            subagents=tuple(
                item for item in result.items if item.type in CODEX_SUBAGENT_ITEM_TYPES
            ),
            forked_from_thread_id=str(lineage.get("forked_from_thread_id", "")),
            fork_depth=int(
                lineage.get("fork_depth", CODEX_ROOT_FORK_DEPTH)
                or CODEX_ROOT_FORK_DEPTH
            ),
        )
        metadata = {
            **lineage,
            **dict(request.input_metadata),
            "provider": CODEX_PROVIDER_NAME,
            "provider_item_count": len(result.items),
        }
        return AgentMessage(
            sender=agent.name,
            recipient=request.recipient,
            content=result.final_response,
            metadata=metadata,
            structured=structured,
            codex=codex,
        )

    def _structured_output(
        self,
        content: str,
        schema: type | Mapping[str, Any] | None,
        agent_name: str,
        status: str,
    ) -> Any:
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


__all__ = ["CodexResultSerializer", "CodexResultTranslator"]
