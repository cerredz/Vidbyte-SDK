"""FILE: vidbyte/lib/constants/speed.py

PURPOSE: Defines named operational limits and numeric conventions for speed metrics.
ROLE IN CODEBASE: Keeps speed aggregation thresholds centralized and discoverable.
ARCHITECTURE NOTE: This module contains immutable constants only; tracker behavior lives elsewhere.
COMMON MODIFICATION PATTERNS: Add a named constant here before introducing another speed policy literal.
KNOWN EDGE CASES: Percentile fractions are shared by current and historical rollups.
RELATED DOCS: docs/design/agent-speed-stats-expansion.md
TESTS: Covered by the agent speed tracker tests and scripts/run_ci.py.
"""

from __future__ import annotations

MAX_AGENT_SPEED_HISTORY_RUNS = 100
AGENT_SPEED_FIRST_INDEX = 1
AGENT_SPEED_FIRST_RETRY_INDEX = 1
AGENT_SPEED_MIN_PARALLEL_CALLS = 2
AGENT_SPEED_MILLISECONDS_PER_SECOND = 1000
AGENT_SPEED_P50 = 0.50
AGENT_SPEED_P90 = 0.90
AGENT_SPEED_P95 = 0.95
AGENT_SPEED_P99 = 0.99
AGENT_SPEED_ZERO_COUNT = 0
AGENT_SPEED_ZERO_SECONDS = 0.0

__all__ = [
    "AGENT_SPEED_FIRST_INDEX",
    "AGENT_SPEED_FIRST_RETRY_INDEX",
    "AGENT_SPEED_MILLISECONDS_PER_SECOND",
    "AGENT_SPEED_MIN_PARALLEL_CALLS",
    "AGENT_SPEED_P50",
    "AGENT_SPEED_P95",
    "AGENT_SPEED_P99",
    "AGENT_SPEED_ZERO_COUNT",
    "AGENT_SPEED_ZERO_SECONDS",
    "MAX_AGENT_SPEED_HISTORY_RUNS",
]
