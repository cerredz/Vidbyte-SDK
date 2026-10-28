"""FILE: vidbyte/lib/enums/usage.py

PURPOSE:
    Defines the closed vocabularies of run-level usage accounting: which kind of
    model a priced call came from, why a run's usage could not be accounted, and
    the speed and inference geography an Anthropic response bills at.

ROLE IN CODEBASE:
    UsageKind tags every UsageRecord built by vidbyte/agents/pricing/tracker.py
    (generative calls from the agent loop, decision calls from
    vidbyte/lib/runners/decision.py). UsageAccountingFailure names the reasons
    UsageAccountingError reports when JevAgent fails closed in
    vidbyte/agents/jev/usage.py. AnthropicSpeed and AnthropicInferenceGeo name
    the usage.speed and usage.inference_geo values AnthropicUsage.cost_usd in
    vidbyte/agents/pricing/anthropic.py prices. All are re-exported from
    vidbyte/lib/enums/__init__.py.

ARCHITECTURE NOTE:
    Pure value sets with no behavior, so the lib-level usage-ledger contract and
    the agent-level tracker and policy share one vocabulary without an upward import.

FUNCTION INVENTORY:
    UsageKind: str Enum with GENERATIVE and DECISION members.
    UsageAccountingFailure: str Enum with RECORDING_ERROR, UNREPORTED_USAGE, and UNPRICED_CALL members.
    AnthropicSpeed: str Enum with STANDARD and FAST members.
    AnthropicInferenceGeo: str Enum with GLOBAL, US, and NOT_AVAILABLE members.

COMMON MODIFICATION PATTERNS:
    A new model family that is billed separately adds a UsageKind member and a
    matching kind-filtered rollup in JevUsageAccount.report(); a new fail-closed
    reason adds a UsageAccountingFailure member and its check in JevUsageAccount.
    A new Anthropic speed or geography adds a member here and its rate or
    multiplier in the pricebook; until then AnthropicUsage leaves it unpriced.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add behavior or methods; these are value sets only.
    2. Do not reuse UsageRecordingIntegrity for failure reasons; integrity is one of several reasons.

KNOWN EDGE CASES:
    Anthropic may report a speed or geography these enums lack; it fails the
    enum lookup, so the call is priced as None rather than at standard rates.

RELATED DOCS:
    docs/design/jev-run-usage-ledger.md; docs/design/anthropic-usage-price-modifiers.md

TESTS:
    tests/test_jev_usage_ledger.py; tests/features/sdk_model_usage/test_anthropic_price_modifiers.py.
"""

from __future__ import annotations

from enum import Enum


class UsageKind(str, Enum):
    """Which kind of model produced one priced call in a run's usage ledger."""

    GENERATIVE = "generative"
    DECISION = "decision"


class UsageAccountingFailure(str, Enum):
    """Why a run's usage could not be fully recorded and priced from the pricebook."""

    RECORDING_ERROR = "recording_error"
    UNREPORTED_USAGE = "unreported_usage"
    UNPRICED_CALL = "unpriced_call"


class AnthropicSpeed(str, Enum):
    """The speed an Anthropic response's usage.speed says the call ran at."""

    STANDARD = "standard"
    FAST = "fast"


class AnthropicInferenceGeo(str, Enum):
    """Where an Anthropic response's usage.inference_geo says inference ran."""

    GLOBAL = "global"
    US = "us"
    NOT_AVAILABLE = "not_available"


__all__ = ["AnthropicInferenceGeo", "AnthropicSpeed", "UsageAccountingFailure", "UsageKind"]
