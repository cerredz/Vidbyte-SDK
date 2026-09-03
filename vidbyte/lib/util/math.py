"""FILE: vidbyte/lib/util/math.py

PURPOSE:
    Centralizes mean/percentile/max/argmax so every SDK caller that needs
    basic statistics (today: vidbyte/agents/speed/tracker.py) uses the exact
    same percentile formula rather than each defining its own.

ROLE IN CODEBASE:
    Called by vidbyte/agents/speed/tracker.py's _build_call_stats,
    _build_tool_call_stats, _build_step_stats, and the cold-start-overhead
    helper in _build_run_stats. Calls only the stdlib statistics module.

ARCHITECTURE NOTE:
    MathHelper is a static-method-only class; every method takes a plain
    Sequence[float] or Mapping[int, float] and returns None on empty input
    rather than raising, matching the None-is-not-yet-known idiom already
    used by UsageRollup.cost_usd elsewhere in the SDK. The percentile formula
    intentionally matches vidbyte/evals/types.py's EvalSuiteResult.p95_latency_ms
    so "p95" means the same thing everywhere in the SDK.

FUNCTION INVENTORY:
    MathHelper.mean_or_none(values) -> float | None: arithmetic mean, or None
    when values is empty. Tests: tests/test_agent_speed.py:MathHelperTests.
    MathHelper.percentile_or_none(values, fraction) -> float | None:
    nearest-rank percentile at fraction in [0, 1]; raises ValueError (not an
    SDK error class) for fraction outside that range, since every caller in
    this SDK passes a literal 0.50/0.95/0.99. Tests: same class.
    MathHelper.max_or_none(values) -> float | None: maximum value, or None
    when empty. Tests: same class.
    MathHelper.argmax_index(scored) -> int | None: the key with the largest
    value in scored, or None when scored is empty. Tests: same class.

COMMON MODIFICATION PATTERNS:
    Add a new general statistic as another @staticmethod here, not as an
    inline computation inside AgentSpeedTracker or any other caller. If the
    percentile formula ever changes, update vidbyte/evals/types.py's
    p95_latency_ms in the same change so "p95" stays consistent SDK-wide.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add any dependency on agents, sessions, or harnesses; this file
       must stay usable by an unrelated project with no SDK context.
    2. Do not wrap inputs in a dataclass; MathHelper's inputs are bare
       numeric sequences with no cross-field relationships to validate.
    3. Do not raise on empty input; return None, matching every other method.

KNOWN EDGE CASES:
    percentile_or_none raises plain ValueError (not AgentSpeedValidationError)
    for an out-of-range fraction, because this is a programmer error at an
    internal SDK call site, not a runtime condition an agent-facing caller
    can hit.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py (MathHelperTests, 9 cases covering empty input,
    populated input, the shared percentile formula, and argmax tie behavior).
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
        return max(scored, key=lambda key: scored[key]) if scored else None

    @staticmethod
    def min_or_none(values: Sequence[float]) -> float | None:
        """Return the minimum value in values, or None when values is empty."""
        return min(values) if values else None

    @staticmethod
    def stdev_or_none(values: Sequence[float]) -> float | None:
        """Return population standard deviation, or None when values is empty."""
        return statistics.pstdev(values) if values else None

    @staticmethod
    def sum_or_none(values: Sequence[float]) -> float | None:
        """Return the sum of values, or None when values is empty."""
        return sum(values) if values else None

    @staticmethod
    def weighted_rate_or_none(numerator: Sequence[float], denominator_seconds: Sequence[float]) -> float | None:
        """Return total numerator divided by total positive seconds, or None when unavailable."""
        seconds = sum(value for value in denominator_seconds if value > 0)
        return sum(numerator) / seconds if numerator and seconds > 0 else None

    @staticmethod
    def interval_union_seconds(intervals: Sequence[tuple[float, float]]) -> float | None:
        """Return elapsed seconds covered by the union of intervals, or None when empty."""
        if not intervals:
            return None
        ordered = sorted(intervals)
        start, end = ordered[0]
        total = 0.0
        for next_start, next_end in ordered[1:]:
            if next_start > end:
                total += end - start
                start, end = next_start, next_end
            else:
                end = max(end, next_end)
        return total + end - start

    @staticmethod
    def max_concurrency(intervals: Sequence[tuple[float, float]]) -> int | None:
        """Return the greatest number of intervals active at one time, or None when empty."""
        if not intervals:
            return None
        events = [(start, 1) for start, _ in intervals] + [(end, -1) for _, end in intervals]
        active = 0
        maximum = 0
        for _, delta in sorted(events, key=lambda event: (event[0], -event[1])):
            active += delta
            maximum = max(maximum, active)
        return maximum


__all__ = ["MathHelper"]
