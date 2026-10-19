"""FILE: vidbyte/lib/enums/infinite.py

PURPOSE: Defines the ten closed vocabularies of the InfiniteMemory agent: the memory preset, the kind of a memory entry, a pair's result status and verdict, the journal event names, the role an agent plays in the delegation tree, and the four vocabularies of its run events: the event kind, why a staged entry was dropped, how a note changed, and why a run stopped.
ROLE IN CODEBASE: Typed fields of the records in vidbyte/lib/dataclasses/infinite.py (the event records included) and of InfiniteWorkspaceSettings (vidbyte/agents/infinite/settings.py); read by the workspace, journal, memory tools, launch tool, runtime, and InfiniteEvents in vidbyte/agents/infinite/. Re-exported from vidbyte/lib/enums/__init__.py; InfiniteMemoryPreset and InfiniteEventKind also from the root vidbyte package and vidbyte.agents.
ARCHITECTURE NOTE: Every value is the member name in lowercase, and the values are what the on-disk JSON lines and the remember tool's schema carry, so a value is a file-format contract as well as a model-facing word. The event values are a contract with the event consumers (the CLI and the dashboard), which store them.
FUNCTION INVENTORY: No functions; ten str Enums: InfiniteMemoryPreset, InfiniteEntryKind, InfiniteResultStatus, InfiniteVerdict, InfiniteJournalEvent, InfiniteAgentRole, InfiniteEventKind (the 14 run event kinds), InfiniteDropReason, InfiniteFileChange, and InfiniteStopCause.
COMMON MODIFICATION PATTERNS: A new entry kind is one more InfiniteEntryKind member; the remember schema picks it up from the enum. A new preset needs one more case where InfiniteAgentMemory chooses its tools. A new event kind is one more InfiniteEventKind member, one details record, one kind-to-record entry on InfiniteEvent, one summary template, and one InfiniteEvents method.
WHAT NOT TO DO IN THIS FILE: 1. Do not change a value; workspaces and journals already on disk carry it. 2. Do not add behavior or methods. 3. Do not define a feature constant here; constants live in vidbyte/lib/constants/infinite.py.
KNOWN EDGE CASES: InfiniteVerdict.UNCHECKED is never written by a verifier; it marks a verdict that was missing, a verifier that failed, or a verifier that was skipped. InfiniteEventKind shares the run_started and run_finished values with InfiniteJournalEvent on purpose; they are separate vocabularies, one for live events and one for journal records.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.1); docs/spec/infinite-memory-events/spec.md (sections 8.5 and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py; tests/features/infinite_memory_agent/test_infinite_memory_events_records.py
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


class InfiniteEventKind(str, Enum):
    """What one run event reports: the run's life, a pair's life, a memory change, a note write, or a refusal."""

    RUN_STARTED = "run_started"
    RUN_RESUMED = "run_resumed"
    RUN_FINISHED = "run_finished"
    RUN_STOPPED = "run_stopped"
    BATCH_REJECTED = "batch_rejected"
    SUBAGENT_LAUNCHED = "subagent_launched"
    SUBAGENT_REPLAYED = "subagent_replayed"
    GENERATOR_FINISHED = "generator_finished"
    SUBAGENT_FINISHED = "subagent_finished"
    MEMORY_SAVED = "memory_saved"
    MEMORY_STAGED = "memory_staged"
    MEMORY_DROPPED = "memory_dropped"
    FILE_WRITTEN = "file_written"
    TOOL_REFUSED = "tool_refused"


class InfiniteDropReason(str, Enum):
    """Why a staged entry was never committed: the verifier dropped it, the pair had no verdict, or a rule refused it."""

    VERIFIER = "verifier"
    UNCHECKED = "unchecked"
    RULE = "rule"


class InfiniteFileChange(str, Enum):
    """How a note changed: written new, appended to, or edited in place."""

    CREATED = "created"
    APPENDED = "appended"
    EDITED = "edited"


class InfiniteStopCause(str, Enum):
    """Why a run stopped before it finished: an error, or a cancellation or interrupt."""

    FAILED = "failed"
    CANCELLED = "cancelled"


__all__ = ["InfiniteAgentRole", "InfiniteDropReason", "InfiniteEntryKind", "InfiniteEventKind", "InfiniteFileChange", "InfiniteJournalEvent", "InfiniteMemoryPreset", "InfiniteResultStatus", "InfiniteStopCause", "InfiniteVerdict"]
