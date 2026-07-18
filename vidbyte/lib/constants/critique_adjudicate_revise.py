"""Context Protocol Header

Description:
    Shared bounds and protocol enums for the critique-adjudicate-revise algorithm.
Purpose:
    Keeps denial-of-service limits and closed protocol vocabularies out of the public
    configuration dataclass so validation code and runtime orchestration share one source.
Architecture:
    Pure constants module with no side effects. Imported by the context algorithm config
    and any runtime code that must mirror the same hard bounds.
Relations:
    Consumed by vidbyte.context.algorithms.critique_adjudicate_revise.
"""

from __future__ import annotations

MAX_CRITICS = 16
MAX_FINDINGS = 64
MAX_EVIDENCE = 16
MAX_FIELD_CHARS = 20_000
MAX_CANDIDATE_CHARS = 1_000_000
MAX_STAGE_INPUT_CHARS = 2_000_000
MAX_STAGE_ITERATIONS = 100
MAX_STAGE_TOOL_CALLS = 100

FINDING_CATEGORIES = frozenset({"correctness", "requirements", "security", "performance", "evidence", "clarity", "other"})
FINDING_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
EVIDENCE_SOURCE_KINDS = frozenset({"task", "candidate", "artifact", "tool"})
REJECTION_REASONS = frozenset({"unsupported", "duplicate", "contradicted", "out_of_scope", "not_actionable"})
RESERVED_SOURCES = frozenset({"original_task", "candidate"})

__all__ = [
    "EVIDENCE_SOURCE_KINDS",
    "FINDING_CATEGORIES",
    "FINDING_SEVERITIES",
    "MAX_CANDIDATE_CHARS",
    "MAX_CRITICS",
    "MAX_EVIDENCE",
    "MAX_FIELD_CHARS",
    "MAX_FINDINGS",
    "MAX_STAGE_INPUT_CHARS",
    "MAX_STAGE_ITERATIONS",
    "MAX_STAGE_TOOL_CALLS",
    "REJECTION_REASONS",
    "RESERVED_SOURCES",
]
