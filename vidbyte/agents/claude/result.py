"""FILE: vidbyte/agents/claude/result.py

PURPOSE: Accumulates the provider message stream and validates Vidbyte structured output.
ROLE IN CODEBASE: Separates transport stream state from the public AgentMessage boundary.
ARCHITECTURE NOTE: Only SDK types passed in are inspected; installing Claude stays optional.
COMMON MODIFICATION PATTERNS: Read explicit result fields defensively and preserve absent values.
KNOWN EDGE CASES: A success subtype with no structured_output is a failure, not a valid answer.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/structured-outputs.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from vidbyte.lib.constants.claude import (
    CLAUDE_PROVIDER_NAME,
    CLAUDE_ROOT_FORK_DEPTH,
    CLAUDE_SUBAGENT_TOOL_NAMES,
    CLAUDE_SUPPORTED_BLOCK_TYPES,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.claude import (
    ClaudeItem,
    ClaudeMessageData,
    ClaudeResultTranslationRequest,
    ClaudeRunResult,
    ClaudeSdkTypes,
    ClaudeUsage,
)
from vidbyte.lib.enums.claude import ClaudeBlockType, ClaudeResultSubtype
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeAgentError, OutputSchemaViolationError
from vidbyte.providers.output_schema import OutputSchemaFormatter


class ClaudeStreamAccumulator:
    """Collects one provider message stream; never escapes the transport that owns it."""

    def __init__(self) -> None:
        # Starts every field absent so a missing provider value is never read as zero.
        self.session_id = ""
        self.subtype = ""
        self.terminal_reason = ""
        self.result: str | None = None
        self.duration_ms: int | None = None
        self.duration_api_ms: int | None = None
        self.num_turns: int | None = None
        self.structured_output: Mapping[str, Any] | None = None
        self.usage = ClaudeUsage()
        self.usage_available = False
        self.result_available = False
        self.has_result = False
        self.items: list[ClaudeItem] = []

    def consume(self, message: object, sdk: ClaudeSdkTypes) -> None:
        # Routes one provider message to the reader that owns its shape.
        if isinstance(message, sdk.result_message):
            self._consume_result(message)
        elif isinstance(message, sdk.assistant_message):
            self._consume_assistant(message, sdk)
        elif isinstance(message, sdk.system_message):
            self._consume_system(message)

    def _consume_system(self, message: object) -> None:
        # @intent capture-identity-at-the-earliest-message
        # The init system message carries the session id before any turn completes,
        # so a run that dies mid-stream still leaves a resumable identity behind.
        data = getattr(message, "data", None)
        session_id = data.get("session_id") if isinstance(data, Mapping) else None
        self.session_id = str(
            session_id or getattr(message, "session_id", "") or self.session_id
        )

    def _consume_assistant(self, message: object, sdk: ClaudeSdkTypes) -> None:
        # Appends every supported content block, skipping the ones excluded by policy.
        for block in getattr(message, "content", ()) or ():
            item = ClaudeResultSerializer.item(block, sdk)
            if item is not None:
                self.items.append(item)

    def _consume_result(self, message: object) -> None:
        # Records the terminal snapshot, keeping absent fields distinguishable from zero.
        self.has_result = True
        self.session_id = str(getattr(message, "session_id", "") or self.session_id)
        self.subtype = str(getattr(message, "subtype", "") or "")
        self.terminal_reason = str(getattr(message, "terminal_reason", "") or "")
        text = getattr(message, "result", None)
        self.result = text if text is None else str(text)
        self.result_available = text is not None
        self.duration_ms = _optional_int(message, "duration_ms")
        self.duration_api_ms = _optional_int(message, "duration_api_ms")
        self.num_turns = _optional_int(message, "num_turns")
        structured = getattr(message, "structured_output", None)
        self.structured_output = (
            dict(structured) if isinstance(structured, Mapping) else None
        )
        self.usage, self.usage_available = ClaudeResultSerializer.usage(message)


def _optional_int(message: object, field_name: str) -> int | None:
    # Returns a provider integer when present, preserving absence as None.
    value = getattr(message, field_name, None)
    return None if value is None else int(value)


def _optional_number(message: object, field_name: str) -> float | None:
    # Returns a provider number when present, preserving absence as None.
    value = getattr(message, field_name, None)
    return None if value is None else float(value)


class ClaudeResultSerializer:
    """Freezes an accumulated stream into a bounded, immutable Vidbyte record."""

    @classmethod
    def from_stream(cls, accumulator: ClaudeStreamAccumulator) -> ClaudeRunResult:
        # @intent a-stream-without-a-terminal-result-is-not-an-answer
        # The provider signals completion only through its result message, so a closed
        # stream without one leaves no status, session id, or usage to report.
        if not accumulator.has_result:
            raise ClaudeAgentError(
                "Claude closed its message stream without a terminal result.",
                failure_code=FailureCode.CLAUDE_RESPONSE_INVALID.value,
                operation="normalize_result",
            )
        cls._require_usable_success(accumulator)
        return ClaudeRunResult(
            session_id=accumulator.session_id,
            subtype=accumulator.subtype,
            terminal_reason=accumulator.terminal_reason,
            result=accumulator.result,
            duration_ms=accumulator.duration_ms,
            duration_api_ms=accumulator.duration_api_ms,
            num_turns=accumulator.num_turns,
            usage=accumulator.usage,
            items=tuple(accumulator.items),
            structured_output=accumulator.structured_output,
            usage_available=accumulator.usage_available,
            result_available=accumulator.result_available,
        )

    @staticmethod
    def _require_usable_success(accumulator: ClaudeStreamAccumulator) -> None:
        # Rejects a reported success that carries neither text nor structured output.
        if accumulator.subtype != ClaudeResultSubtype.SUCCESS.value:
            return
        if not accumulator.result and accumulator.structured_output is None:
            raise ClaudeAgentError(
                "Claude reported success without a result or structured output.",
                failure_code=FailureCode.CLAUDE_RESPONSE_INVALID.value,
                operation="normalize_result",
            )

    @classmethod
    def item(cls, block: object, sdk: ClaudeSdkTypes) -> ClaudeItem | None:
        # @intent exclude-private-thinking-before-serialization
        # Only reviewed block kinds may expose payloads. Omit thinking content at the
        # serialization boundary instead of copying it and deleting it afterwards.
        block_type = str(getattr(block, "type", "") or "")
        if block_type not in CLAUDE_SUPPORTED_BLOCK_TYPES:
            return None
        readers = {
            ClaudeBlockType.TEXT.value: cls._text_fields,
            ClaudeBlockType.TOOL_USE.value: cls._tool_use_fields,
            ClaudeBlockType.TOOL_RESULT.value: cls._tool_result_fields,
        }
        return ClaudeItem(
            id=str(getattr(block, "id", "") or getattr(block, "tool_use_id", "") or ""),
            type=block_type,
            fields=readers[block_type](block),
        )

    @staticmethod
    def _text_fields(block: object) -> dict[str, Any]:
        # Copies the assistant's visible text exactly as the provider produced it.
        return {"text": str(getattr(block, "text", "") or "")}

    @staticmethod
    def _tool_use_fields(block: object) -> dict[str, Any]:
        # Copies the tool name and its validated input mapping.
        payload = getattr(block, "input", None)
        return {
            "name": str(getattr(block, "name", "") or ""),
            "input": dict(payload) if isinstance(payload, Mapping) else {},
        }

    @staticmethod
    def _tool_result_fields(block: object) -> dict[str, Any]:
        # @intent bounded-tool-result-record
        # A tool result's content can nest arbitrary blocks and arbitrary size, so the
        # record keeps its identity and error flag without copying the payload.
        content = getattr(block, "content", None)
        return {
            "tool_use_id": str(getattr(block, "tool_use_id", "") or ""),
            "is_error": bool(getattr(block, "is_error", False)),
            "content_block_count": len(content)
            if isinstance(content, (list, tuple))
            else 0,
        }

    @staticmethod
    def usage(message: object) -> tuple[ClaudeUsage, bool]:
        # Copies provider counters and reports whether any of them were present.
        fields = (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        counters = {name: _optional_int(message, name) for name in fields}
        cost = _optional_number(message, "total_cost_usd")
        available = cost is not None or any(
            value is not None for value in counters.values()
        )
        usage = ClaudeUsage(
            input_tokens=counters["input_tokens"] or 0,
            output_tokens=counters["output_tokens"] or 0,
            cache_read_input_tokens=counters["cache_read_input_tokens"] or 0,
            cache_creation_input_tokens=counters["cache_creation_input_tokens"] or 0,
            total_cost_usd=cost or 0.0,
        )
        return usage, available


class ClaudeResultTranslator:
    """Builds Vidbyte messages and validates declared output schemas."""

    def __init__(self) -> None:
        # Holds the shared formatter so provider dicts become the caller's declared type.
        self._schemas = OutputSchemaFormatter()

    def translate(self, request: ClaudeResultTranslationRequest) -> AgentMessage:
        # @intent typed-provider-result
        # Validate output and publish deterministic Claude data separately from generic
        # metadata so callers never need to parse provider dictionaries themselves.
        result = self.normalize(request)
        agent = request.agent
        lineage = dict(agent.metadata)
        claude = ClaudeMessageData(
            session_id=result.session_id,
            subtype=result.subtype,
            terminal_reason=result.terminal_reason,
            usage=result.usage,
            items=result.items,
            subagents=self._subagents(result),
            forked_from_session_id=str(lineage.get("forked_from_session_id", "")),
            fork_depth=int(
                lineage.get("fork_depth", CLAUDE_ROOT_FORK_DEPTH)
                or CLAUDE_ROOT_FORK_DEPTH
            ),
            duration_ms=result.duration_ms,
            duration_api_ms=result.duration_api_ms,
            num_turns=result.num_turns,
            usage_available=result.usage_available,
            result=result.result,
            structured=result.structured,
        )
        return AgentMessage(
            sender=agent.name,
            recipient=request.recipient,
            content=result.result or "",
            metadata={
                **lineage,
                **dict(request.input_metadata),
                "provider": CLAUDE_PROVIDER_NAME,
                "provider_item_count": len(result.items),
            },
            structured=result.structured,
            claude=claude,
        )

    def normalize(self, request: ClaudeResultTranslationRequest) -> ClaudeRunResult:
        # @intent validate-only-completed-answers
        # Validate once at the Vidbyte boundary. A failed or budget-capped run is a
        # diagnostic outcome, never a schema-compliant answer to hand a caller.
        result = request.result
        if request.agent.output_schema is None:
            return replace(result, structured=None)
        if result.subtype != ClaudeResultSubtype.SUCCESS.value:
            return replace(result, structured=None)
        structured = self._structured_output(
            result, request.agent.output_schema, request.agent.name
        )
        return replace(result, structured=structured)

    def _structured_output(
        self, result: ClaudeRunResult, schema: type | Mapping[str, Any], agent_name: str
    ) -> Any:
        # @intent a-success-without-structured-output-is-still-a-failure
        # The provider can report success and omit structured output entirely, which
        # would otherwise reach the caller as a silent None on a declared contract.
        if result.structured_output is None:
            raise OutputSchemaViolationError(
                f"Claude agent '{agent_name}' declared an output_schema but produced no structured output.",
                raw_output=result.result or "",
                validation_error="provider reported success with no structured_output",
                stop_reason=result.subtype,
            )
        payload = json.dumps(dict(result.structured_output))
        structured, validation_error = self._schemas.validate(payload, schema)
        if validation_error is None:
            return structured
        raise OutputSchemaViolationError(
            f"Claude agent '{agent_name}' returned structured output that violates its schema.",
            raw_output=payload,
            validation_error=validation_error,
            stop_reason=result.subtype,
        )

    @staticmethod
    def _subagents(result: ClaudeRunResult) -> tuple[ClaudeItem, ...]:
        # Selects the tool-use items that delegated work to a provider subagent.
        return tuple(
            item
            for item in result.items
            if item.type == ClaudeBlockType.TOOL_USE.value
            and str(item.fields.get("name", "")) in CLAUDE_SUBAGENT_TOOL_NAMES
        )


__all__ = [
    "ClaudeResultSerializer",
    "ClaudeResultTranslator",
    "ClaudeStreamAccumulator",
]
