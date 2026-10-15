"""FILE: vidbyte/lib/enums/infinite.py

PURPOSE: Defines the six closed vocabularies of the InfiniteMemory agent: the memory preset, the kind of a memory entry, a pair's result status and verdict, the journal event names, and the role an agent plays in the delegation tree.
ROLE IN CODEBASE: Typed fields of the records in vidbyte/lib/dataclasses/infinite.py and of InfiniteWorkspaceSettings (vidbyte/agents/infinite/settings.py); read by the workspace, journal, memory tools, launch tool, and runtime in vidbyte/agents/infinite/. Re-exported from vidbyte/lib/enums/__init__.py, and InfiniteMemoryPreset also from the root vidbyte package.
ARCHITECTURE NOTE: Every value is the member name in lowercase, and the values are what the on-disk JSON lines and the remember tool's schema carry, so a value is a file-format contract as well as a model-facing word.
FUNCTION INVENTORY: No functions; six str Enums: InfiniteMemoryPreset, InfiniteEntryKind, InfiniteResultStatus, InfiniteVerdict, InfiniteJournalEvent, and InfiniteAgentRole.
COMMON MODIFICATION PATTERNS: A new entry kind is one more InfiniteEntryKind member; the remember schema picks it up from the enum. A new preset needs one more case where InfiniteAgentMemory chooses its tools.
WHAT NOT TO DO IN THIS FILE: 1. Do not change a value; workspaces and journals already on disk carry it. 2. Do not add behavior or methods. 3. Do not define a feature constant here; constants live in vidbyte/lib/constants/infinite.py.
KNOWN EDGE CASES: InfiniteVerdict.UNCHECKED is never written by a verifier; it marks a verdict that was missing, a verifier that failed, or a verifier that was skipped.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py
"""

from __future__ import annotations

from enum import Enum


class InfiniteMemoryPreset(str, Enum):
    """Which memory tools every agent holds: SPARSE writes only append, FULL adds edit_file."""

    SPARSE = "sparse"
    FULL = "full"


class InfiniteEntryKind(str, Enum):
    """What one memory entry records."""

    DECISION = "decision"
    FACT = "fact"
    LESSON = "lesson"
    OPEN_QUESTION = "open_question"
    POINTER = "pointer"


class InfiniteResultStatus(str, Enum):
    """How a pair's generator ended: finished, stopped early with content, or failed."""

    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class InfiniteVerdict(str, Enum):
    """The verifier's judgment of a pair; UNCHECKED when no verdict was given."""

    PASSED = "passed"
    FIXED = "fixed"
    FAILED = "failed"
    UNCHECKED = "unchecked"


class InfiniteJournalEvent(str, Enum):
    """The record types of a run journal, in the order a run writes them."""

    RUN_STARTED = "run_started"
    PAIR_STARTED = "pair_started"
    PAIR_FINISHED = "pair_finished"
    RUN_FINISHED = "run_finished"


class InfiniteAgentRole(str, Enum):
    """The part an agent plays in the delegation tree, which decides its tools."""

    ROOT = "root"
    GENERATOR = "generator"
    VERIFIER = "verifier"


__all__ = ["InfiniteAgentRole", "InfiniteEntryKind", "InfiniteJournalEvent", "InfiniteMemoryPreset", "InfiniteResultStatus", "InfiniteVerdict"]
