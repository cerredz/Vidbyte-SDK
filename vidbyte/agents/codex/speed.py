"""FILE: vidbyte/agents/codex/speed.py

PURPOSE: Records one native Codex turn's latency into Vidbyte's shared speed ledger.
ROLE IN CODEBASE: agent.py calls this on both turn outcomes; AgentSpeedTracker owns
    every clock, ledger, and statistic. This module only shapes the input records.
ARCHITECTURE NOTE: The interval is measured locally in the tracker's monotonic clock,
    never copied from the provider's duration_ms, which is a different clock domain
    and excludes app-server startup, connection setup, and result normalization.
FUNCTION INVENTORY: record_turn(request) files one successful or failed CallSpeedRecord;
    _model_name resolves turn over thread; _token_counts reads the per-turn delta only.
COMMON MODIFICATION PATTERNS: Add a turn outcome to record_turn and its record type here;
    leave aggregation, history, and integrity to AgentSpeedTracker.
WHAT NOT TO DO IN THIS FILE: Do not set first_token_at without a real streaming boundary,
    do not name the provider "openai" (that is the priced usage record's requirement),
    and do not fill step, tool, or concurrency fields that describe a Vidbyte-owned loop.
KNOWN EDGE CASES: RunSpeedStats fields for tool time, concurrency, and first-tool latency
    stay empty on purpose: Codex owns its inner loop and exposes no such intervals.
RELATED DOCS: docs/design/codex-speed-tracking.md
TESTS: tests/test_codex_speed_tracking.py; python scripts/run_ci.py.
"""

from __future__ import annotations

import asyncio

from vidbyte.lib.constants.codex import CODEX_PROVIDER_NAME, CODEX_UNKNOWN_MODEL
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexRunResult,
    CodexSpeedResponse,
    CodexSpeedTranslationRequest,
)
from vidbyte.lib.dataclasses.speed import (
    CallSpeedRecord,
    RecordModelCallFailureInput,
    RecordModelCallInput,
)


class CodexSpeedTranslator:
    """Records one native turn's latency into Vidbyte's shared speed ledger."""

    @classmethod
    def record_turn(
        cls, request: CodexSpeedTranslationRequest
    ) -> CallSpeedRecord | None:
        # @intent measure-what-the-caller-actually-waited-for
        # One turn produces one record on either outcome. A failed turn is recorded
        # too, because a 120-second timeout is exactly the latency an operator needs.
        model = cls._model_name(request.settings)
        if request.error is not None:
            return cls._record_failure(request, model)
        return cls._record_success(request, model)

    @classmethod
    def _record_success(
        cls, request: CodexSpeedTranslationRequest, model: str
    ) -> CallSpeedRecord | None:
        # @intent absent-first-token-not-zero
        # Streaming is unimplemented, so there is no first-token boundary to measure.
        # A zero would read as an instant first token in every statistic consuming it.
        result = request.result
        if result is None:
            return None
        input_tokens, output_tokens = cls._token_counts(result)
        return request.tracker.record_call(  # type: ignore[attr-defined]
            RecordModelCallInput(
                response=CodexSpeedResponse(
                    provider=CODEX_PROVIDER_NAME, model=model
                ),
                dispatched_at=request.dispatched_at,
                first_token_at=None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

    @staticmethod
    def _record_failure(
        request: CodexSpeedTranslationRequest, model: str
    ) -> CallSpeedRecord | None:
        # @intent record-the-latency-of-what-went-wrong
        # A timed-out turn is the latency an operator most needs, and cancellation is
        # a distinct outcome from failure that must stay labelled as one.
        error = request.error
        return request.tracker.record_call_failure(  # type: ignore[attr-defined]
            RecordModelCallFailureInput(
                provider=CODEX_PROVIDER_NAME,
                model=model,
                dispatched_at=request.dispatched_at,
                error_type=type(error).__name__,
                cancelled=isinstance(error, asyncio.CancelledError),
            )
        )

    @staticmethod
    def _model_name(settings: CodexAgentSettings) -> str:
        # A turn override outranks the thread default, matching how Codex resolves it.
        return settings.turn.model or settings.thread.model or CODEX_UNKNOWN_MODEL

    @staticmethod
    def _token_counts(result: CodexRunResult) -> tuple[int | None, int | None]:
        # Throughput denominators come from the per-turn delta; the cumulative snapshot
        # would inflate every turn after the first. Absent usage stays absent, not zero.
        usage = result.last_usage
        if not result.usage_available or usage is None:
            return (None, None)
        return (usage.input_tokens, usage.output_tokens)


__all__ = ["CodexSpeedTranslator"]
