"""FILE: vidbyte/agents/codex/result.py

PURPOSE: Copies typed native results and validates Vidbyte structured output.
ROLE IN CODEBASE: Separates transport snapshots from the public AgentMessage boundary.
ARCHITECTURE NOTE: Only SDK types imported for checking; installing Codex is optional.
COMMON MODIFICATION PATTERNS: Copy explicit SDK fields and preserve absent values.
WHAT NOT TO DO IN THIS FILE: Reflect arbitrary objects or serialize private reasoning.
KNOWN EDGE CASES: Interrupted turns may lack text; SDK run raises for failed turns.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/pull/409
TESTS: Offline typed-result checks and python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_NAME,
    CODEX_ROOT_FORK_DEPTH,
    CODEX_SUBAGENT_ITEM_TYPES,
    CODEX_SUPPORTED_ITEM_TYPES,
)
from vidbyte.lib.dataclasses.codex import (
    CodexItem,
    CodexMessageData,
    CodexResultTranslationRequest,
    CodexRunResult,
    CodexTurnError,
    CodexUsage,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, OutputSchemaViolationError
from vidbyte.providers.output_schema import OutputSchemaFormatter

if TYPE_CHECKING:
    from openai_codex import TurnResult
    from openai_codex.generated.v2_all import ThreadItem, TokenUsageBreakdown, TurnError


class CodexResultSerializer:
    """Copies stable SDK result models into bounded Vidbyte dataclasses."""

    @classmethod
    def from_sdk(cls, thread_id: str, result: TurnResult) -> CodexRunResult:
        # Read the pinned SDK contract directly; malformed objects must not become empty data.
        final_response = result.final_response
        if result.status.value == "completed" and not final_response:
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
            duration_ms=result.duration_ms,
            usage=cls._usage(result.usage.total, result.usage.model_context_window)
            if result.usage
            else CodexUsage(),
            items=tuple(cls._item(item) for item in result.items),
            started_at=result.started_at,
            completed_at=result.completed_at,
            error=cls._error(result.error),
            last_usage=cls._usage(result.usage.last, result.usage.model_context_window)
            if result.usage
            else None,
            usage_available=result.usage is not None,
        )

    @classmethod
    def _item(cls, value: ThreadItem) -> CodexItem:
        # @intent exclude-private-reasoning-before-serialization
        # Only reviewed SDK variants may expose payloads. Omit reasoning content
        # at the serialization boundary instead of copying it and deleting it later.
        item = value.root
        excluded = (
            {"id", "type", "content"} if item.type == "reasoning" else {"id", "type"}
        )
        payload = (
            item.model_dump(mode="json", by_alias=True, exclude=excluded)
            if item.type in CODEX_SUPPORTED_ITEM_TYPES
            else {}
        )
        return CodexItem(id=item.id, type=item.type, fields=payload)

    @classmethod
    def _usage(
        cls, value: TokenUsageBreakdown, context_window: int | None
    ) -> CodexUsage:
        # Copy the selected provider snapshot without manufacturing per-turn deltas.
        return CodexUsage(
            input_tokens=value.input_tokens,
            cached_input_tokens=value.cached_input_tokens,
            cache_write_input_tokens=value.cache_write_input_tokens or 0,
            output_tokens=value.output_tokens,
            reasoning_output_tokens=value.reasoning_output_tokens,
            total_tokens=value.total_tokens,
            model_context_window=context_window or 0,
        )

    @staticmethod
    def _error(value: TurnError | None) -> CodexTurnError | None:
        # Preserve provider diagnostics only when present in the typed result contract.
        if value is None:
            return None
        return CodexTurnError(
            message=value.message,
            additional_details=value.additional_details,
            codex_error_info=value.codex_error_info.model_dump(
                mode="json", by_alias=True
            )
            if value.codex_error_info
            else None,
        )


class CodexResultTranslator:
    """Builds Vidbyte messages and validates declared output schemas."""

    def __init__(self) -> None:
        self._schemas = OutputSchemaFormatter()

    def translate(self, request: CodexResultTranslationRequest) -> AgentMessage:
        # @intent typed-provider-result
        # Validate output and publish deterministic Codex data separately from
        # generic metadata so callers never need to parse provider dictionaries.
        result = self.normalize(request)
        agent = request.agent
        lineage = dict(agent.metadata)
        codex = CodexMessageData(
            thread_id=result.thread_id,
            turn_id=result.turn_id,
            status=result.status,
            duration_ms=result.duration_ms,
            usage=result.usage,
            items=result.items,
            started_at=result.started_at,
            completed_at=result.completed_at,
            error=result.error,
            last_usage=result.last_usage,
            usage_available=result.usage_available,
            final_response=result.final_response,
            structured=result.structured,
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
            content=result.final_response or "",
            metadata=metadata,
            structured=result.structured,
            codex=codex,
        )

    def normalize(self, request: CodexResultTranslationRequest) -> CodexRunResult:
        # @intent validate-only-completed-answers
        # Validate once at the Vidbyte boundary, retaining the complete native snapshot.
        # Interrupted/failed results are diagnostic outcomes, not schema-compliant answers.
        result = request.result
        if result.status != "completed":
            return replace(result, structured=None)
        structured = self._structured_output(
            result.final_response or "",
            request.agent.output_schema,
            request.agent.name,
            result.status,
        )
        return replace(result, structured=structured)

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
