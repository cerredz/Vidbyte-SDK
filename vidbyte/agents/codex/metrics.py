"""FILE: vidbyte/agents/codex/metrics.py

PURPOSE: Records one native Codex turn into Vidbyte's shared usage accounting.
ROLE IN CODEBASE: agent.py calls this after the transport returns; UsageTracker owns
    pricing, ledgers, and rollups. This module only decides recordability and shape.
ARCHITECTURE NOTE: The tracker duck-types provider/model/usage off a response object,
    so a normalized Codex result enters through the CodexUsageResponse shim.
FUNCTION INVENTORY: record_usage(request) -> UsageRecord | None files at most one
    record per turn; _recordable_usage gates it; _model_name and _usage_payload shape it.
COMMON MODIFICATION PATTERNS: Add a recordability condition to _recordable_usage and a
    payload key to _usage_payload; leave cost arithmetic to the pricing registry.
WHAT NOT TO DO IN THIS FILE: Do not compute cost, do not record CodexRunResult.usage
    (it is cumulative), and do not raise on a metering failure after Codex did work.
KNOWN EDGE CASES: Absent usage records nothing while a genuine zero snapshot records;
    a custom thread model_provider records nothing because no rate can be trusted.
RELATED DOCS: docs/design/codex-usage-tracking.md
TESTS: tests/test_codex_usage_tracking.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.pricing.records import UsageRecord
from vidbyte.lib.constants.codex import CODEX_USAGE_PROVIDER
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexUsage,
    CodexUsageResponse,
    CodexUsageTranslationRequest,
)


class CodexMetricsTranslator:
    """Records one native turn's usage into Vidbyte's shared accounting."""

    @classmethod
    def record_usage(cls, request: CodexUsageTranslationRequest) -> UsageRecord | None:
        # @intent one-native-turn-one-accounting-record
        # File the per-turn delta exactly once. CodexRunResult.usage is cumulative
        # for the thread, so recording it would inflate a multi-turn run silently.
        usage = cls._recordable_usage(request)
        if usage is None:
            return None
        response = CodexUsageResponse(
            provider=CODEX_USAGE_PROVIDER,
            model=cls._model_name(request.settings),
            usage=cls._usage_payload(usage),
        )
        return request.tracker.record_call(response)  # type: ignore[attr-defined]

    @staticmethod
    def _recordable_usage(request: CodexUsageTranslationRequest) -> CodexUsage | None:
        # @intent absent-usage-is-not-zero-usage
        # Return the turn delta only when the provider actually reported one. An
        # unknown backend also yields nothing, because pricing it under OpenAI rates
        # would invent a dollar figure for a model the account is not billed for.
        if request.settings.thread.model_provider:
            return None
        if not request.result.usage_available:
            return None
        return request.result.last_usage

    @staticmethod
    def _model_name(settings: CodexAgentSettings) -> str:
        # A turn override outranks the thread default, matching how Codex resolves it.
        return settings.turn.model or settings.thread.model

    @staticmethod
    def _usage_payload(usage: CodexUsage) -> dict[str, Any]:
        # Nests cached and reasoning counts where OpenAIUsage.from_usage_payload reads
        # them; cache-write tokens stay top-level so they survive on the parsed raw.
        return {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "input_tokens_details": {"cached_tokens": usage.cached_input_tokens},
            "output_tokens_details": {
                "reasoning_tokens": usage.reasoning_output_tokens
            },
            "cache_write_input_tokens": usage.cache_write_input_tokens,
        }


__all__ = ["CodexMetricsTranslator"]
