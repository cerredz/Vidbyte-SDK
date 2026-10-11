"""FILE: vidbyte/lib/enums/decision_model.py

PURPOSE: Defines the closed connection modes for calibrated decision-model configurations.
ROLE IN CODEBASE: DecisionModelConfig uses these values to resolve TypeSafe or Vidbyte managed credentials and endpoints.
ARCHITECTURE NOTE: This lower-layer enum declares values only and imports no provider or agent behavior.
COMMON MODIFICATION PATTERNS: Add a mode only when its credential source and endpoint policy are implemented together.
KNOWN EDGE CASES: JevRuntimeSettings defaults to Vidbyte managed mode while standalone DecisionModelConfig defaults to TypeSafe.
RELATED DOCS: docs/design/jev-managed-gateway-credentials.md and field-guide/vidbyte-sdk/strict-config-dataclasses.md.
TESTS: tests/test_jev_managed_gateway.py and scripts/test-jev-managed-gateway.py.
"""

from __future__ import annotations

from enum import Enum


class DecisionModelMode(str, Enum):
    """Select direct TypeSafe access or the Vidbyte-managed decision gateway."""

    TYPESAFE = "typesafe"
    VIDBYTE_MANAGED = "vidbyte_managed"


__all__ = ["DecisionModelMode"]
