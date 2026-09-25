"""FILE: vidbyte/lib/enums/jev_compaction.py

PURPOSE: Defines the closed vocabularies of JevAgent dynamic compaction: trigger keys, unit-of-work answer labels, record sources, and disable reasons.
ROLE IN CODEBASE: `vidbyte/agents/jev/compaction/` builds Jev questions, ledger decisions, and the run report from these members; tests match on them.
ARCHITECTURE NOTE: Kept apart from `vidbyte/lib/enums/jev.py`, which mirrors TypeSafe's wire vocabulary; these values belong to one JevAgent capability.
COMMON MODIFICATION PATTERNS: Add a JevCompactionTriggerKey member together with its settings flag and its JevCompactionTrigger subclass.
KNOWN EDGE CASES: JevUnitOfWorkLabel values are Jev option names sent on the wire, so renaming one changes the question Jev answers.
RELATED DOCS: docs/design/jev-dynamic-compaction.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

from enum import Enum


class JevCompactionTriggerKey(str, Enum):
    """One way of finding a point where finished context may be compacted; each maps to a settings flag."""

    UNIT_OF_WORK = "unit_of_work"


class JevUnitOfWorkLabel(str, Enum):
    """Options of the unit-of-work choice question about the latest step."""

    CONTINUES = "continues"
    STARTS_NEW = "starts_new"
    UNCLEAR = "unclear"


class JevCompactionRecordSource(str, Enum):
    """Where the record that replaced a compacted unit came from."""

    WRITER = "writer"
    FALLBACK = "fallback"


class JevCompactionDisabledReason(str, Enum):
    """Why dynamic compaction stopped acting for the rest of a run."""

    JEV_UNAVAILABLE = "jev_unavailable"
    JEV_ERRORS = "jev_errors"
    HISTORY_REPLACED = "history_replaced"
    HISTORY_OUT_OF_SYNC = "history_out_of_sync"


__all__ = [
    "JevCompactionDisabledReason",
    "JevCompactionRecordSource",
    "JevCompactionTriggerKey",
    "JevUnitOfWorkLabel",
]
