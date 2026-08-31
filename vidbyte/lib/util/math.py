"""Context Protocol Header

Description:
    General-purpose numeric aggregation with no dependency on any SDK feature.
Purpose:
    Centralizes mean/percentile/max/argmax so every SDK caller that needs basic
    statistics (today: vidbyte.agents.speed.tracker) uses the exact same
    percentile formula rather than each defining its own.
Architecture:
    - MathHelper: a static-method-only class; every method takes plain
      Sequence[float] or Mapping[int, float] and returns None on empty input
      rather than raising, matching the None-is-not-yet-known idiom already
      used by UsageRollup.cost_usd elsewhere in the SDK.
Relations:
    Consumed by vidbyte.agents.speed.tracker. Percentile formula intentionally
    matches vidbyte.evals.types.EvalSuiteResult.p95_latency_ms so "p95" means
    the same thing everywhere in the SDK.
Similar Files:
    - vidbyte/evals/types.py (the pre-existing p95_latency_ms this mirrors)
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence


class MathHelper:
    """Static-method home for general numeric aggregation used across the SDK."""

    @staticmethod
    def mean_or_none(values: Sequence[float]) -> float | None:
        """Return the arithmetic mean of values, or None when values is empty."""
        return statistics.mean(values) if values else None

    @staticmethod
    def percentile_or_none(values: Sequence[float], fraction: float) -> float | None:
        """Return the nearest-rank percentile at fraction in [0, 1], or None when values is empty."""
        if not values:
            return None
        if not (0.0 <= fraction <= 1.0):
            raise ValueError(f"fraction must be within [0, 1], got {fraction}.")
        ordered = sorted(values)
        index = int(len(ordered) * fraction)
        return ordered[min(index, len(ordered) - 1)]

    @staticmethod
    def max_or_none(values: Sequence[float]) -> float | None:
        """Return the maximum value in values, or None when values is empty."""
        return max(values) if values else None

    @staticmethod
    def argmax_index(scored: Mapping[int, float]) -> int | None:
        """Return the key with the largest value in scored, or None when scored is empty."""
        return max(scored, key=scored.get) if scored else None


__all__ = ["MathHelper"]
