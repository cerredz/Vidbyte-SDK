"""FILE: vidbyte/lib/constants/jev_compaction.py

PURPOSE: Declares the thresholds, clip lengths, and defaults of JevAgent dynamic compaction in one place.
ROLE IN CODEBASE: `vidbyte/agents/jev/settings.py` validates against the settings bounds; `vidbyte/agents/jev/compaction/` reads the rest.
ARCHITECTURE NOTE: Separate from `vidbyte/lib/constants/jev.py`, which holds TypeSafe wire limits rather than one capability's policy.
COMMON MODIFICATION PATTERNS: Retune a threshold only against a labeled set of real boundaries; every value here is an untuned starting point.
KNOWN EDGE CASES: Token counts are estimates at four characters per token, so they bound cost roughly, never exactly.
RELATED DOCS: docs/design/jev-dynamic-compaction.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

# Policy defaults and bounds.
JEV_COMPACTION_DEFAULT_MIN_RECLAIM_TOKENS: int = 8_000
JEV_COMPACTION_MIN_RECLAIM_TOKENS_FLOOR: int = 1
JEV_COMPACTION_KEEP_RECENT_CLOSED_UNITS: int = 1
JEV_COMPACTION_CHARS_PER_TOKEN: int = 4
JEV_COMPACTION_RECORD_TOKEN_ALLOWANCE: int = 400

# Jev decision policy. The boundary bar is high because a false boundary costs a cache miss.
JEV_COMPACTION_BOUNDARY_THRESHOLD: float = 0.8
JEV_COMPACTION_MAX_CONSECUTIVE_JEV_ERRORS: int = 3

# Step rendering for the Jev state: text and arguments only, clipped, with long units shortened in the middle.
JEV_COMPACTION_STEP_TEXT_CHARS: int = 600
JEV_COMPACTION_TOOL_ARGUMENT_CHARS: int = 300
JEV_COMPACTION_UNIT_HEAD_STEPS: int = 2
JEV_COMPACTION_UNIT_TAIL_STEPS: int = 5

# Step rendering for the record writer, which needs outputs to report findings.
JEV_COMPACTION_WRITER_OUTPUT_CHARS: int = 3_000
JEV_COMPACTION_WRITER_TASK_CHARS: int = 2_000
JEV_COMPACTION_WRITER_MAX_ITERATIONS: int = 2

# Result metadata key for the frozen JevCompactionReport.
JEV_COMPACTION_METADATA_KEY: str = "jev_dynamic_compaction"

__all__ = [
    "JEV_COMPACTION_BOUNDARY_THRESHOLD",
    "JEV_COMPACTION_CHARS_PER_TOKEN",
    "JEV_COMPACTION_DEFAULT_MIN_RECLAIM_TOKENS",
    "JEV_COMPACTION_KEEP_RECENT_CLOSED_UNITS",
    "JEV_COMPACTION_MAX_CONSECUTIVE_JEV_ERRORS",
    "JEV_COMPACTION_METADATA_KEY",
    "JEV_COMPACTION_MIN_RECLAIM_TOKENS_FLOOR",
    "JEV_COMPACTION_RECORD_TOKEN_ALLOWANCE",
    "JEV_COMPACTION_STEP_TEXT_CHARS",
    "JEV_COMPACTION_TOOL_ARGUMENT_CHARS",
    "JEV_COMPACTION_UNIT_HEAD_STEPS",
    "JEV_COMPACTION_UNIT_TAIL_STEPS",
    "JEV_COMPACTION_WRITER_MAX_ITERATIONS",
    "JEV_COMPACTION_WRITER_OUTPUT_CHARS",
    "JEV_COMPACTION_WRITER_TASK_CHARS",
]
