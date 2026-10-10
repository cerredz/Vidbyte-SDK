"""FILE: vidbyte/lib/enums/usage.py

PURPOSE:
    Defines the closed vocabularies of run-level usage accounting: which kind of
    model a priced call came from, and why a run's usage could not be accounted.

ROLE IN CODEBASE:
    UsageKind tags every UsageRecord built by vidbyte/agents/pricing/tracker.py
    (generative calls from the agent loop, decision calls from
    vidbyte/lib/runners/decision.py). UsageAccountingFailure names the reasons
    UsageAccountingError reports when JevAgent fails closed in
    vidbyte/agents/jev/usage.py. Both are re-exported from vidbyte/lib/enums/__init__.py.

ARCHITECTURE NOTE:
    Pure value sets with no behavior, so the lib-level usage-ledger contract and
    the agent-level tracker and policy share one vocabulary without an upward import.

FUNCTION INVENTORY:
    UsageKind: str Enum with GENERATIVE and DECISION members.
    UsageAccountingFailure: str Enum with RECORDING_ERROR, UNREPORTED_USAGE, and UNPRICED_CALL members.

COMMON MODIFICATION PATTERNS:
    A new model family that is billed separately adds a UsageKind member and a
    matching kind-filtered rollup in JevUsageAccount.report(); a new fail-closed
    reason adds a UsageAccountingFailure member and its check in JevUsageAccount.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add behavior or methods; these are value sets only.
    2. Do not reuse UsageRecordingIntegrity for failure reasons; integrity is one of several reasons.

KNOWN EDGE CASES:
    None; both enums are closed sets with no ambiguous states.

RELATED DOCS:
    docs/design/jev-run-usage-ledger.md

TESTS:
    tests/test_jev_usage_ledger.py.
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


__all__ = ["UsageAccountingFailure", "UsageKind"]
