"""Context Protocol Header

FILE: vidbyte/lib/enums/fallback.py
PURPOSE: Defines the closed set of per-hop fallback policy kinds accepted by the
         shared fallback configuration contract.
ROLE IN CODEBASE: Policy implementations in vidbyte/agents/fallback/policies.py
                  advertise one of these values; the dataclasses in
                  vidbyte/lib/dataclasses/agents.py validate them without
                  importing the higher-level agent package.
ARCHITECTURE NOTE: This enum keeps the dependency-free lib contract layer as the
                    source of truth for supported policy kinds.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-fallback-policies.md
"""

from __future__ import annotations

from enum import Enum


class FallbackPolicyType(str, Enum):
    """Supported policy kinds for a model-to-model fallback transition."""

    LATENCY = "latency"
    COST_BUDGET = "cost_budget"


__all__ = ["FallbackPolicyType"]
