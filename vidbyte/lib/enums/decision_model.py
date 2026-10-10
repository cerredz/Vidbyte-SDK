"""FILE: vidbyte/lib/enums/decision_model.py

PURPOSE: Defines the closed connection modes for calibrated decision-model configurations: `TYPESAFE` is the direct (own-key) mode for every decision provider, and `VIDBYTE_MANAGED` is Vidbyte's managed gateway, which serves TypeSafe only.
ROLE IN CODEBASE: DecisionModelConfig uses these values to resolve either the provider's own credentials and endpoint (direct mode, any decision provider) or Vidbyte managed credentials and the gateway endpoint (TypeSafe only).
ARCHITECTURE NOTE: This lower-layer enum declares values only and imports no provider or agent behavior.
COMMON MODIFICATION PATTERNS: Add a mode only when its credential source and endpoint policy are implemented together.
KNOWN EDGE CASES: JevRuntimeSettings defaults to Vidbyte managed mode while standalone DecisionModelConfig defaults to direct TypeSafe. The member name `TYPESAFE` predates the other decision providers and means "direct", whichever provider is configured; DecisionModelConfig refuses `VIDBYTE_MANAGED` for any provider but TypeSafe.
RELATED DOCS: docs/design/jev-managed-gateway-credentials.md and field-guide/vidbyte-sdk/strict-config-dataclasses.md.
TESTS: tests/test_jev_managed_gateway.py and scripts/test-jev-managed-gateway.py.
"""

from __future__ import annotations

from enum import Enum


class DecisionModelMode(str, Enum):
    """Select direct access with the provider's own key (`TYPESAFE`, valid for every decision provider) or the Vidbyte-managed gateway (`VIDBYTE_MANAGED`, TypeSafe only)."""

    TYPESAFE = "typesafe"
    VIDBYTE_MANAGED = "vidbyte_managed"


__all__ = ["DecisionModelMode"]
