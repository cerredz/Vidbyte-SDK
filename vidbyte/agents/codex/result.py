"""Normalization of Codex turn results into Vidbyte messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from openai_codex import TurnResult
    from openai_codex.generated.v2_all import ThreadItem, ThreadTokenUsage


class CodexResultSerializer:
    """Copies stable SDK result models into bounded Vidbyte dataclasses."""

    @classmethod
    def from_sdk(cls, thread_id: str, result: TurnResult) -> CodexRunResult:
        # Read the pinned SDK contract directly; malformed objects must not become empty data.
        final_response = result.final_response
        if not isinstance(final_response, str) or not final_response:
            raise CodexAgentError(
                "Codex completed without a final response.",
                failure_code=FailureCode.CODEX_RESPONSE_INVALID.value,
                operation="normalize_result",
            )
        return CodexRunResult(
            thread_id=thread_id,
            turn_id=result.id,
            status=result.status.value,
            final_response=final_response,
            duration_ms=result.duration_ms if result.duration_ms is not None else CODEX_ZERO_DURATION_MS,
            usage=cls._usage(result.usage),
            items=tuple(cls._item(item) for item in result.items),
        )

    @classmethod
    def _item(cls, value: ThreadItem) -> CodexItem:
        # @intent exclude-private-reasoning-before-serialization
        # Only reviewed SDK variants may expose payloads. Omit reasoning content
        # at the serialization boundary instead of copying it and deleting it later.
        item = value.root
        excluded = {"id", "type", "content"} if item.type == "reasoning" else {"id", "type"}
        payload = item.model_dump(mode="json", by_alias=True, exclude=excluded) if item.type in CODEX_SUPPORTED_ITEM_TYPES else {}
        return CodexItem(id=item.id, type=item.type, fields=payload)

    @classmethod
    def _usage(cls, value: ThreadTokenUsage | None) -> CodexUsage:
        # The provider may omit usage; otherwise preserve its typed cumulative counters.
        if value is None:
            return CodexUsage()
        total = value.total
        return CodexUsage(
            input_tokens=total.input_tokens,
            cached_input_tokens=total.cached_input_tokens,
            cache_write_input_tokens=total.cache_write_input_tokens or 0,
            output_tokens=total.output_tokens,
            reasoning_output_tokens=total.reasoning_output_tokens,
            total_tokens=total.total_tokens,
            model_context_window=value.model_context_window or 0,
        )


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
