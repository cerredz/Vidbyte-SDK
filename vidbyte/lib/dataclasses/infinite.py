"""FILE: vidbyte/lib/dataclasses/infinite.py

PURPOSE: Defines the 22 validated records of the InfiniteMemory agent: InfiniteTaskCard, one task a parent hands to a generator and verifier pair; InfiniteEntryDraft, one memory entry before it has an id; InfiniteEntry, one committed entry; InfiniteStagedEntry, a pair's entry waiting for its verdict; InfiniteResultCard, what a parent learns about one finished pair; InfiniteWorkspaceUsage, the workspace's file count and token total; InfiniteCommittedEntry and InfiniteDroppedEntry, what became of one staged entry; InfiniteEvent, one run event; and the 13 details records its kinds carry, joined in the InfiniteEventDetails alias.
ROLE IN CODEBASE: Built and read by vidbyte/agents/infinite/: the launch tool turns the model's task list into InfiniteTaskCards and each finished pair into an InfiniteResultCard, the memory tools build InfiniteEntryDrafts and InfiniteStagedEntries, the workspace returns InfiniteEntry and InfiniteWorkspaceUsage records, and the journal stores and reloads the result cards. InfinitePair and InfiniteAgentMemory build InfiniteCommittedEntry and InfiniteDroppedEntry items on the run path; InfiniteEvent and the details records are built only by InfiniteEvents (vidbyte/agents/infinite/events.py) and handed to the caller's on_event sink. InfiniteEvent is exported from vidbyte and vidbyte.agents; the details records only from here.
ARCHITECTURE NOTE: Validation only. Every check runs in __post_init__, so a constructed record is always valid and its callers never check it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py); only this feature's own rules, such as what a context item may name, are written here. Sequence fields must already be tuples; the agents layer converts the model's JSON lists. Reading and writing the JSON-lines shapes lives in the workspace and journal modules, not here.
FUNCTION INVENTORY: 22 frozen, slotted records, each with a __post_init__ that checks its fields through RecordFieldValidator and RecordFieldConverter and then applies its own rules: InfiniteTaskCard, InfiniteEntryDraft, InfiniteEntry, InfiniteStagedEntry, InfiniteResultCard, InfiniteWorkspaceUsage, InfiniteCommittedEntry, InfiniteDroppedEntry, the details records InfiniteRunStartedDetails, InfiniteRunResumedDetails, InfiniteRunFinishedDetails, InfiniteRunStoppedDetails, InfiniteRefusalDetails, InfiniteSubagentLaunchedDetails, InfiniteSubagentReplayedDetails, InfiniteGeneratorFinishedDetails, InfiniteSubagentFinishedDetails, InfiniteMemorySavedDetails, InfiniteMemoryStagedDetails, InfiniteMemoryDroppedDetails, InfiniteFileWrittenDetails, and InfiniteEvent, whose DETAILS_TYPES maps each kind to its details record. InfiniteEventDetails is the union of the 13 details records.
COMMON MODIFICATION PATTERNS: A new record field adds one field here and one RecordFieldValidator or RecordFieldConverter call in its record's __post_init__; its bound goes in vidbyte/lib/constants/infinite.py. A new event kind adds one details record here, one InfiniteEventDetails member, and one DETAILS_TYPES entry; a new details field adds its cap and its worst case to docs/spec/infinite-memory-events/spec.md section 9.1. A check the canonical validators lack becomes a new option or method there, never a helper here. A new task-card field is also one property in the launch_subagent schema and one prompt leaf for its description.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, or any other layer above vidbyte/lib. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures; serialization lives in the workspace and the journal, and an event's consumer serializes it with dataclasses.asdict. 3. Do not convert a list or a string into a tuple here; a bare string would split into characters, so the caller converts and the record refuses anything else.
KNOWN EDGE CASES: One line means no line break of any kind, as str.splitlines sees it. A context item that starts with "#" must be an entry id ("#42"); any other item is a relative path. InfiniteResultCard.summary and review may be empty, because a failed pair has neither. True is refused wherever a whole number is expected, although Python counts it as an int. A refusal names the field as Record.field, or Record.field[index] for one item of a tuple, except in the event records, where an item that breaks a cap is named by its list (Record.field), because the event contract names fields, not items. InfiniteCommittedEntry and InfiniteDroppedEntry carry no event caps, because the pair builds them with full text; the details record that shows them checks their texts. The worst-case size of every details record lives in docs/spec/infinite-memory-events/spec.md section 9.1.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.1); docs/spec/infinite-memory-events/spec.md (sections 8.5 and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_events_records.py, tests/features/infinite_memory_agent/test_infinite_memory_delegation.py, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py, tests/features/infinite_memory_agent/test_infinite_memory_verification.py, and tests/features/infinite_memory_agent/test_infinite_memory_resume.py
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, ClassVar

from vidbyte.lib.constants.infinite import (
    INFINITE_CONTEXT_MAX_ITEMS,
    INFINITE_EVENT_KEY_MAX_CHARS,
    INFINITE_EVENT_LABEL_MAX_CHARS,
    INFINITE_EVENT_LINE_MAX_CHARS,
    INFINITE_EVENT_MAX_COUNT,
    INFINITE_EVENT_MAX_ITEMS,
    INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND,
    INFINITE_EVENT_PATH_MAX_CHARS,
    INFINITE_EVENT_SUMMARY_MAX_CHARS,
    INFINITE_EVENT_TEXT_MAX_CHARS,
    INFINITE_FIRST_ENTRY_ID,
    INFINITE_MAX_REFS,
    INFINITE_MAX_TAGS,
    INFINITE_MIN_COUNT,
    INFINITE_RUN_ID_PATTERN,
    INFINITE_STAGED_KEY_PATTERN,
    INFINITE_TAG_PATTERN,
    INFINITE_TASK_NAME_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteDropReason,
    InfiniteEntryKind,
    InfiniteEventKind,
    InfiniteFileChange,
    InfiniteMemoryPreset,
    InfiniteResultStatus,
    InfiniteStopCause,
    InfiniteVerdict,
)
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class InfiniteTaskCard:
    """One task for a generator and verifier pair: its name, goal, done criteria, the two prompts, and the context and extra tools it gets."""

    name: str
    goal: str
    done_criteria: tuple[str, ...]
    generator_prompt: str
    verifier_prompt: str
    context: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # The name becomes part of every key and agent name in the pair,
        # so it must be a short lowercase slug.
        RecordFieldValidator.require_text(self.name, "InfiniteTaskCard.name", pattern=INFINITE_TASK_NAME_PATTERN)

        # Both agents need real instructions, and the goal is what both
        # of them are told to reach.
        for name in ("goal", "generator_prompt", "verifier_prompt"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteTaskCard.{name}")

        # The verifier checks the work against the criteria, so there
        # must be at least one.
        RecordFieldValidator.require_text_items(self.done_criteria, "InfiniteTaskCard.done_criteria")
        if not self.done_criteria:
            raise ConfigurationError(f"InfiniteTaskCard.done_criteria must hold at least one criterion; got {self.done_criteria!r}.", details={"field": "InfiniteTaskCard.done_criteria"})

        # Context items are entry ids such as "#42" or relative paths of
        # workspace files, and there is a cap on how many a task
        # carries.
        RecordFieldValidator.require_text_items(self.context, "InfiniteTaskCard.context", max_items=INFINITE_CONTEXT_MAX_ITEMS, one_line=True)
        for item in self.context:
            number = item.removeprefix("#")
            if (item.startswith("#") and not (number.isascii() and number.isdigit())) or (not item.startswith("#") and PurePath(item).is_absolute()):
                raise ConfigurationError(f"Each item of InfiniteTaskCard.context must be an entry id such as #42 or a relative path; got {item!r}.", details={"field": "InfiniteTaskCard.context"})

        # Extra tools are named once each.
        RecordFieldValidator.require_text_items(self.tools, "InfiniteTaskCard.tools", one_line=True)
        if len(set(self.tools)) != len(self.tools):
            raise ConfigurationError(f"InfiniteTaskCard.tools must not name a tool twice; got {self.tools!r}.", details={"field": "InfiniteTaskCard.tools"})


@dataclass(frozen=True, slots=True)
class InfiniteEntryDraft:
    """One memory entry as an agent wrote it, before the workspace gives it an id."""

    kind: InfiniteEntryKind
    text: str
    tags: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    supersedes: int | None = None

    def __post_init__(self) -> None:
        # An entry is one line of a known kind with a few short labels,
        # so memory stays sparse; the token cap is the workspace's
        # check.
        RecordFieldValidator.require_enum(self.kind, InfiniteEntryKind, "InfiniteEntryDraft.kind")
        RecordFieldValidator.require_text(self.text, "InfiniteEntryDraft.text", one_line=True)
        RecordFieldValidator.require_text_items(self.tags, "InfiniteEntryDraft.tags", max_items=INFINITE_MAX_TAGS, pattern=INFINITE_TAG_PATTERN, one_line=True)
        RecordFieldValidator.require_text_items(self.refs, "InfiniteEntryDraft.refs", max_items=INFINITE_MAX_REFS, one_line=True)
        if self.supersedes is not None:
            RecordFieldValidator.require_int(self.supersedes, "InfiniteEntryDraft.supersedes", minimum=INFINITE_FIRST_ENTRY_ID)


@dataclass(frozen=True, slots=True)
class InfiniteEntry:
    """One committed memory entry: its id, its content, who wrote and verified it, the run, and when."""

    id: int
    draft: InfiniteEntryDraft
    by: str
    verified_by: str | None
    run: str
    at: str

    def __post_init__(self) -> None:
        # Ids start at 1; the author, the run, and the stamp are one
        # line each, and a root entry has no verifier.
        RecordFieldValidator.require_int(self.id, "InfiniteEntry.id", minimum=INFINITE_FIRST_ENTRY_ID)
        RecordFieldConverter.require_instance(self.draft, "InfiniteEntry.draft", InfiniteEntryDraft)
        for name in ("by", "run", "at"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteEntry.{name}", one_line=True)
        RecordFieldValidator.require_optional_text(self.verified_by, "InfiniteEntry.verified_by", one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteStagedEntry:
    """A pair's entry waiting for the verdict: its staged key ("s1", "s2", ...), its author's key, and the draft."""

    key: str
    author: str
    draft: InfiniteEntryDraft

    def __post_init__(self) -> None:
        # The verifier names a staged entry by its key, so the key keeps
        # one fixed form.
        RecordFieldValidator.require_text(self.key, "InfiniteStagedEntry.key", pattern=INFINITE_STAGED_KEY_PATTERN)
        RecordFieldValidator.require_text(self.author, "InfiniteStagedEntry.author", one_line=True)
        RecordFieldConverter.require_instance(self.draft, "InfiniteStagedEntry.draft", InfiniteEntryDraft)


@dataclass(frozen=True, slots=True)
class InfiniteResultCard:
    """What a parent learns about one finished pair: status, verdict, the capped summary and review, the committed entry ids, the dropped entries, and the files written."""

    name: str
    key: str
    status: InfiniteResultStatus
    verdict: InfiniteVerdict
    summary: str
    review: str
    entries: tuple[int, ...]
    dropped: tuple[str, ...]
    files: tuple[str, ...]

    def __post_init__(self) -> None:
        # The name and key identify the pair; a failed pair has no
        # summary or review, so those two may be empty.
        RecordFieldValidator.require_text(self.name, "InfiniteResultCard.name", pattern=INFINITE_TASK_NAME_PATTERN)
        RecordFieldValidator.require_text(self.key, "InfiniteResultCard.key", one_line=True)
        RecordFieldValidator.require_enum(self.status, InfiniteResultStatus, "InfiniteResultCard.status")
        RecordFieldValidator.require_enum(self.verdict, InfiniteVerdict, "InfiniteResultCard.verdict")
        for name in ("summary", "review"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteResultCard.{name}", allow_blank=True)

        # Committed ids are entry ids, and every dropped entry and file
        # written is named in words.
        RecordFieldConverter.require_instance(self.entries, "InfiniteResultCard.entries", tuple)
        for index, number in enumerate(self.entries):
            RecordFieldValidator.require_int(number, f"InfiniteResultCard.entries[{index}]", minimum=INFINITE_FIRST_ENTRY_ID)
        RecordFieldValidator.require_text_items(self.dropped, "InfiniteResultCard.dropped")
        RecordFieldValidator.require_text_items(self.files, "InfiniteResultCard.files", one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteWorkspaceUsage:
    """How many files the workspace holds and their token total, as counted from disk."""

    files: int
    tokens: int

    def __post_init__(self) -> None:
        # Both are counts, so neither can be negative.
        for name in ("files", "tokens"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteWorkspaceUsage.{name}", minimum=INFINITE_MIN_COUNT)


@dataclass(frozen=True, slots=True)
class InfiniteCommittedEntry:
    """One staged entry a pair committed: its staged key, the entry id it got, its kind, and its full text."""

    staged_key: str
    entry_id: int
    kind: InfiniteEntryKind
    text: str

    def __post_init__(self) -> None:
        # Built on the run path with the entry's full text, so no event
        # cap applies; the details record that shows it checks the caps.
        RecordFieldValidator.require_text(self.staged_key, "InfiniteCommittedEntry.staged_key", pattern=INFINITE_STAGED_KEY_PATTERN)
        RecordFieldValidator.require_int(self.entry_id, "InfiniteCommittedEntry.entry_id", minimum=INFINITE_FIRST_ENTRY_ID)
        RecordFieldValidator.require_enum(self.kind, InfiniteEntryKind, "InfiniteCommittedEntry.kind")
        RecordFieldValidator.require_text(self.text, "InfiniteCommittedEntry.text", one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteDroppedEntry:
    """One staged entry a pair never committed: its staged key, its full text, why it was dropped, and the note the card shows."""

    key: str
    text: str
    reason: InfiniteDropReason
    note: str

    def __post_init__(self) -> None:
        # Built on the run path with full text, like
        # InfiniteCommittedEntry; the note is the card's wording.
        RecordFieldValidator.require_text(self.key, "InfiniteDroppedEntry.key", pattern=INFINITE_STAGED_KEY_PATTERN)
        RecordFieldValidator.require_text(self.text, "InfiniteDroppedEntry.text", one_line=True)
        RecordFieldValidator.require_enum(self.reason, InfiniteDropReason, "InfiniteDroppedEntry.reason")
        RecordFieldValidator.require_text(self.note, "InfiniteDroppedEntry.note", allow_blank=True)


@dataclass(frozen=True, slots=True)
class InfiniteRunStartedDetails:
    """run_started: the task, the model, the preset, the delegation and loop limits, and the root's extra tools and seed file names."""

    task: str
    model: str
    preset: InfiniteMemoryPreset
    max_depth: int
    max_parallel: int
    max_agents: int
    max_iterations: int | None
    extras: tuple[str, ...]
    extras_omitted: int
    seeds: tuple[str, ...]
    seeds_omitted: int

    def __post_init__(self) -> None:
        # The task may span lines; the model is one line.
        RecordFieldValidator.require_text(self.task, "InfiniteRunStartedDetails.task", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_text(self.model, "InfiniteRunStartedDetails.model", max_chars=INFINITE_EVENT_LINE_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_enum(self.preset, InfiniteMemoryPreset, "InfiniteRunStartedDetails.preset")
        # Limits are reported up to the count cap, and a loop may have
        # no iteration limit at all.
        for name in ("max_depth", "max_parallel", "max_agents", "extras_omitted", "seeds_omitted"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteRunStartedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        if self.max_iterations is not None:
            RecordFieldValidator.require_int(self.max_iterations, "InfiniteRunStartedDetails.max_iterations", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        # Each list shows at most five one-line labels; an item that
        # breaks a cap is named by its list.
        for name in ("extras", "seeds"):
            RecordFieldValidator.require_text_items(getattr(self, name), f"InfiniteRunStartedDetails.{name}", max_items=INFINITE_EVENT_MAX_ITEMS)
            for item in getattr(self, name):
                RecordFieldValidator.require_text(item, f"InfiniteRunStartedDetails.{name}", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteRunResumedDetails:
    """run_resumed: the task, how many pairs finished earlier, and the pair keys that started and never finished."""

    task: str
    finished: int
    interrupted: tuple[str, ...]
    interrupted_omitted: int

    def __post_init__(self) -> None:
        # Interrupted pairs are named by key, at most five of them.
        RecordFieldValidator.require_text(self.task, "InfiniteRunResumedDetails.task", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        for name in ("finished", "interrupted_omitted"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteRunResumedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        RecordFieldValidator.require_text_items(self.interrupted, "InfiniteRunResumedDetails.interrupted", max_items=INFINITE_EVENT_MAX_ITEMS)
        for item in self.interrupted:
            RecordFieldValidator.require_text(item, "InfiniteRunResumedDetails.interrupted", max_chars=INFINITE_EVENT_KEY_MAX_CHARS, one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteRunFinishedDetails:
    """run_finished: the stop reason, the root's answer, the finished pairs, the agents started, and the run's usage."""

    stop_reason: str
    answer: str
    pairs: int
    agents: int
    tokens: int
    cost_usd: float | None

    def __post_init__(self) -> None:
        # None means a part of the cost is unknown; a known cost may be
        # 0 but never negative.
        RecordFieldValidator.require_text(self.stop_reason, "InfiniteRunFinishedDetails.stop_reason", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, allow_blank=True, one_line=True)
        RecordFieldValidator.require_text(self.answer, "InfiniteRunFinishedDetails.answer", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        for name in ("pairs", "agents", "tokens"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteRunFinishedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        if self.cost_usd is not None:
            RecordFieldValidator.require_number(self.cost_usd, "InfiniteRunFinishedDetails.cost_usd", maximum=sys.float_info.max, allow_zero=True)


@dataclass(frozen=True, slots=True)
class InfiniteRunStoppedDetails:
    """run_stopped: whether the run failed or was cancelled, the exception's class name, and its message."""

    reason: InfiniteStopCause
    error_type: str
    message: str

    def __post_init__(self) -> None:
        # An exception may carry no message, so only the class name
        # must be there.
        RecordFieldValidator.require_enum(self.reason, InfiniteStopCause, "InfiniteRunStoppedDetails.reason")
        RecordFieldValidator.require_text(self.error_type, "InfiniteRunStoppedDetails.error_type", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_text(self.message, "InfiniteRunStoppedDetails.message", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)


@dataclass(frozen=True, slots=True)
class InfiniteRefusalDetails:
    """batch_rejected and tool_refused: the tool that refused the call and the problem it reported."""

    tool: str
    problem: str

    def __post_init__(self) -> None:
        # The problem is the text the model saw, cut to the text cap.
        RecordFieldValidator.require_text(self.tool, "InfiniteRefusalDetails.tool", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_text(self.problem, "InfiniteRefusalDetails.problem", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)


@dataclass(frozen=True, slots=True)
class InfiniteSubagentLaunchedDetails:
    """subagent_launched: the pair's name, key, launcher key, and depth, and its task card cut to the event caps."""

    name: str
    key: str
    parent: str
    depth: int
    goal: str
    done_criteria: tuple[str, ...]
    done_criteria_omitted: int
    generator_prompt: str
    verifier_prompt: str
    context: tuple[str, ...]
    context_omitted: int
    tools: tuple[str, ...]
    tools_omitted: int

    def __post_init__(self) -> None:
        # The pair is named by its task name and two keys.
        RecordFieldValidator.require_text(self.name, "InfiniteSubagentLaunchedDetails.name", pattern=INFINITE_TASK_NAME_PATTERN)
        for name in ("key", "parent"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteSubagentLaunchedDetails.{name}", max_chars=INFINITE_EVENT_KEY_MAX_CHARS, one_line=True)
        for name in ("depth", "done_criteria_omitted", "context_omitted", "tools_omitted"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteSubagentLaunchedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        # The card's texts keep their line breaks, cut to their caps.
        RecordFieldValidator.require_text(self.goal, "InfiniteSubagentLaunchedDetails.goal", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        for name in ("generator_prompt", "verifier_prompt"):
            RecordFieldValidator.require_text(getattr(self, name), f"InfiniteSubagentLaunchedDetails.{name}", max_chars=INFINITE_EVENT_LINE_MAX_CHARS, allow_blank=True)
        # Each list shows at most five items under its own cap and line
        # rule; an item that breaks one is named by its list.
        for name, cap, one_line in (("done_criteria", INFINITE_EVENT_LINE_MAX_CHARS, False), ("context", INFINITE_EVENT_LABEL_MAX_CHARS, True), ("tools", INFINITE_EVENT_LABEL_MAX_CHARS, True)):
            RecordFieldValidator.require_text_items(getattr(self, name), f"InfiniteSubagentLaunchedDetails.{name}", max_items=INFINITE_EVENT_MAX_ITEMS)
            for item in getattr(self, name):
                RecordFieldValidator.require_text(item, f"InfiniteSubagentLaunchedDetails.{name}", max_chars=cap, one_line=one_line)


@dataclass(frozen=True, slots=True)
class InfiniteSubagentReplayedDetails:
    """subagent_replayed: the finished pair whose recorded result is reused, with its status and verdict."""

    name: str
    key: str
    status: InfiniteResultStatus
    verdict: InfiniteVerdict

    def __post_init__(self) -> None:
        # Only the pair's identity and outcome; its card is already
        # known from the run that finished it.
        RecordFieldValidator.require_text(self.name, "InfiniteSubagentReplayedDetails.name", pattern=INFINITE_TASK_NAME_PATTERN)
        RecordFieldValidator.require_text(self.key, "InfiniteSubagentReplayedDetails.key", max_chars=INFINITE_EVENT_KEY_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_enum(self.status, InfiniteResultStatus, "InfiniteSubagentReplayedDetails.status")
        RecordFieldValidator.require_enum(self.verdict, InfiniteVerdict, "InfiniteSubagentReplayedDetails.verdict")


@dataclass(frozen=True, slots=True)
class InfiniteGeneratorFinishedDetails:
    """generator_finished: the generator's status, stop reason, cut summary, tool calls, usage, and time from launch to reply."""

    status: InfiniteResultStatus
    stop_reason: str
    summary: str
    tool_calls: int
    tokens: int
    cost_usd: float | None
    duration_ms: int

    def __post_init__(self) -> None:
        # A failed generator has an empty summary; the cost is None
        # when any part of it is unknown.
        RecordFieldValidator.require_enum(self.status, InfiniteResultStatus, "InfiniteGeneratorFinishedDetails.status")
        RecordFieldValidator.require_text(self.stop_reason, "InfiniteGeneratorFinishedDetails.stop_reason", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, allow_blank=True, one_line=True)
        RecordFieldValidator.require_text(self.summary, "InfiniteGeneratorFinishedDetails.summary", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        for name in ("tool_calls", "tokens", "duration_ms"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteGeneratorFinishedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        if self.cost_usd is not None:
            RecordFieldValidator.require_number(self.cost_usd, "InfiniteGeneratorFinishedDetails.cost_usd", maximum=sys.float_info.max, allow_zero=True)


@dataclass(frozen=True, slots=True)
class InfiniteSubagentFinishedDetails:
    """subagent_finished: the pair's outcome, its cut review, the entries it committed and dropped, the notes it wrote, and its usage."""

    name: str
    key: str
    status: InfiniteResultStatus
    verdict: InfiniteVerdict
    review: str
    committed: tuple[InfiniteCommittedEntry, ...]
    committed_omitted: int
    dropped: tuple[InfiniteDroppedEntry, ...]
    dropped_omitted: int
    files: tuple[str, ...]
    files_omitted: int
    tokens: int
    cost_usd: float | None

    def __post_init__(self) -> None:
        # The pair's identity and outcome, as on its journaled card.
        RecordFieldValidator.require_text(self.name, "InfiniteSubagentFinishedDetails.name", pattern=INFINITE_TASK_NAME_PATTERN)
        RecordFieldValidator.require_text(self.key, "InfiniteSubagentFinishedDetails.key", max_chars=INFINITE_EVENT_KEY_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_enum(self.status, InfiniteResultStatus, "InfiniteSubagentFinishedDetails.status")
        RecordFieldValidator.require_enum(self.verdict, InfiniteVerdict, "InfiniteSubagentFinishedDetails.verdict")
        RecordFieldValidator.require_text(self.review, "InfiniteSubagentFinishedDetails.review", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        for name in ("committed_omitted", "dropped_omitted", "files_omitted", "tokens"):
            RecordFieldValidator.require_int(getattr(self, name), f"InfiniteSubagentFinishedDetails.{name}", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        if self.cost_usd is not None:
            RecordFieldValidator.require_number(self.cost_usd, "InfiniteSubagentFinishedDetails.cost_usd", maximum=sys.float_info.max, allow_zero=True)
        # @intent shown-items-carry-the-event-caps
        # The items hold full text, so this record caps what it shows:
        # five per list, each text one line of at most 64 characters,
        # each note at most 64, a failing item named by its list.
        RecordFieldConverter.require_instance(self.committed, "InfiniteSubagentFinishedDetails.committed", tuple)
        RecordFieldConverter.to_tuple(self.committed, "InfiniteSubagentFinishedDetails.committed", item_type=InfiniteCommittedEntry, max_items=INFINITE_EVENT_MAX_ITEMS)
        for entry in self.committed:
            RecordFieldValidator.require_text(entry.staged_key, "InfiniteSubagentFinishedDetails.committed", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, pattern=INFINITE_STAGED_KEY_PATTERN)
            RecordFieldValidator.require_text(entry.text, "InfiniteSubagentFinishedDetails.committed", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, one_line=True)
        RecordFieldConverter.require_instance(self.dropped, "InfiniteSubagentFinishedDetails.dropped", tuple)
        RecordFieldConverter.to_tuple(self.dropped, "InfiniteSubagentFinishedDetails.dropped", item_type=InfiniteDroppedEntry, max_items=INFINITE_EVENT_MAX_ITEMS)
        for item in self.dropped:
            RecordFieldValidator.require_text(item.key, "InfiniteSubagentFinishedDetails.dropped", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, pattern=INFINITE_STAGED_KEY_PATTERN)
            RecordFieldValidator.require_text(item.text, "InfiniteSubagentFinishedDetails.dropped", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, one_line=True)
            RecordFieldValidator.require_text(item.note, "InfiniteSubagentFinishedDetails.dropped", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_text_items(self.files, "InfiniteSubagentFinishedDetails.files", max_items=INFINITE_EVENT_MAX_ITEMS)
        for path in self.files:
            RecordFieldValidator.require_text(path, "InfiniteSubagentFinishedDetails.files", max_chars=INFINITE_EVENT_LINE_MAX_CHARS, one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteMemorySavedDetails:
    """memory_saved: one entry the root committed at once, with its id, kind, cut text, tags, refs, and the entry it replaces."""

    id: int
    kind: InfiniteEntryKind
    text: str
    tags: tuple[str, ...]
    refs: tuple[str, ...]
    supersedes: int | None

    def __post_init__(self) -> None:
        # The entry as committed; tags and refs keep the entry rule's
        # limit of eight.
        RecordFieldValidator.require_int(self.id, "InfiniteMemorySavedDetails.id", minimum=INFINITE_FIRST_ENTRY_ID, maximum=INFINITE_EVENT_MAX_COUNT)
        RecordFieldValidator.require_enum(self.kind, InfiniteEntryKind, "InfiniteMemorySavedDetails.kind")
        RecordFieldValidator.require_text(self.text, "InfiniteMemorySavedDetails.text", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True, one_line=True)
        RecordFieldValidator.require_text_items(self.tags, "InfiniteMemorySavedDetails.tags", max_items=INFINITE_MAX_TAGS)
        for tag in self.tags:
            RecordFieldValidator.require_text(tag, "InfiniteMemorySavedDetails.tags", pattern=INFINITE_TAG_PATTERN)
        RecordFieldValidator.require_text_items(self.refs, "InfiniteMemorySavedDetails.refs", max_items=INFINITE_MAX_REFS)
        for ref in self.refs:
            RecordFieldValidator.require_text(ref, "InfiniteMemorySavedDetails.refs", max_chars=INFINITE_EVENT_LINE_MAX_CHARS, one_line=True)
        if self.supersedes is not None:
            RecordFieldValidator.require_int(self.supersedes, "InfiniteMemorySavedDetails.supersedes", minimum=INFINITE_FIRST_ENTRY_ID, maximum=INFINITE_EVENT_MAX_COUNT)


@dataclass(frozen=True, slots=True)
class InfiniteMemoryStagedDetails:
    """memory_staged: one entry a pair's agent proposed, with its staged key, kind, cut text, and the entry it would replace."""

    key: str
    kind: InfiniteEntryKind
    text: str
    supersedes: int | None

    def __post_init__(self) -> None:
        # The staged key is how the verifier and the finished pair name
        # this entry later.
        RecordFieldValidator.require_text(self.key, "InfiniteMemoryStagedDetails.key", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, pattern=INFINITE_STAGED_KEY_PATTERN)
        RecordFieldValidator.require_enum(self.kind, InfiniteEntryKind, "InfiniteMemoryStagedDetails.kind")
        RecordFieldValidator.require_text(self.text, "InfiniteMemoryStagedDetails.text", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True, one_line=True)
        if self.supersedes is not None:
            RecordFieldValidator.require_int(self.supersedes, "InfiniteMemoryStagedDetails.supersedes", minimum=INFINITE_FIRST_ENTRY_ID, maximum=INFINITE_EVENT_MAX_COUNT)


@dataclass(frozen=True, slots=True)
class InfiniteMemoryDroppedDetails:
    """memory_dropped: one staged entry the verifier dropped, with its staged key, a short cut of its text, the reason, and the note."""

    key: str
    text: str
    reason: InfiniteDropReason
    note: str

    def __post_init__(self) -> None:
        # The full text is in the matching memory_staged event, so this
        # one carries only a label-sized cut of it.
        RecordFieldValidator.require_text(self.key, "InfiniteMemoryDroppedDetails.key", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, pattern=INFINITE_STAGED_KEY_PATTERN)
        RecordFieldValidator.require_text(self.text, "InfiniteMemoryDroppedDetails.text", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, allow_blank=True, one_line=True)
        RecordFieldValidator.require_enum(self.reason, InfiniteDropReason, "InfiniteMemoryDroppedDetails.reason")
        RecordFieldValidator.require_text(self.note, "InfiniteMemoryDroppedDetails.note", max_chars=INFINITE_EVENT_LABEL_MAX_CHARS, allow_blank=True)


@dataclass(frozen=True, slots=True)
class InfiniteFileWrittenDetails:
    """file_written: the note's workspace-relative path, how it changed, how many characters the call wrote, an excerpt, and a created note's description."""

    path: str
    change: InfiniteFileChange
    added_chars: int
    excerpt: str
    description: str

    def __post_init__(self) -> None:
        # The excerpt keeps its line breaks; the description is empty
        # unless the call created the note.
        RecordFieldValidator.require_text(self.path, "InfiniteFileWrittenDetails.path", max_chars=INFINITE_EVENT_PATH_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_enum(self.change, InfiniteFileChange, "InfiniteFileWrittenDetails.change")
        RecordFieldValidator.require_int(self.added_chars, "InfiniteFileWrittenDetails.added_chars", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        RecordFieldValidator.require_text(self.excerpt, "InfiniteFileWrittenDetails.excerpt", max_chars=INFINITE_EVENT_TEXT_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_text(self.description, "InfiniteFileWrittenDetails.description", max_chars=INFINITE_EVENT_LINE_MAX_CHARS, allow_blank=True, one_line=True)


# The details record of every event kind; batch_rejected and
# tool_refused share InfiniteRefusalDetails.
InfiniteEventDetails = InfiniteRunStartedDetails | InfiniteRunResumedDetails | InfiniteRunFinishedDetails | InfiniteRunStoppedDetails | InfiniteRefusalDetails | InfiniteSubagentLaunchedDetails | InfiniteSubagentReplayedDetails | InfiniteGeneratorFinishedDetails | InfiniteSubagentFinishedDetails | InfiniteMemorySavedDetails | InfiniteMemoryStagedDetails | InfiniteMemoryDroppedDetails | InfiniteFileWrittenDetails


@dataclass(frozen=True, slots=True)
class InfiniteEvent:
    """One run event: its kind, the run, the agent whose action produced it, when, a one-line summary, and the kind's details record."""

    # Which details record each kind carries, read-only.
    DETAILS_TYPES: ClassVar[Mapping[InfiniteEventKind, type[Any]]] = MappingProxyType({
        InfiniteEventKind.RUN_STARTED: InfiniteRunStartedDetails,
        InfiniteEventKind.RUN_RESUMED: InfiniteRunResumedDetails,
        InfiniteEventKind.RUN_FINISHED: InfiniteRunFinishedDetails,
        InfiniteEventKind.RUN_STOPPED: InfiniteRunStoppedDetails,
        InfiniteEventKind.BATCH_REJECTED: InfiniteRefusalDetails,
        InfiniteEventKind.SUBAGENT_LAUNCHED: InfiniteSubagentLaunchedDetails,
        InfiniteEventKind.SUBAGENT_REPLAYED: InfiniteSubagentReplayedDetails,
        InfiniteEventKind.GENERATOR_FINISHED: InfiniteGeneratorFinishedDetails,
        InfiniteEventKind.SUBAGENT_FINISHED: InfiniteSubagentFinishedDetails,
        InfiniteEventKind.MEMORY_SAVED: InfiniteMemorySavedDetails,
        InfiniteEventKind.MEMORY_STAGED: InfiniteMemoryStagedDetails,
        InfiniteEventKind.MEMORY_DROPPED: InfiniteMemoryDroppedDetails,
        InfiniteEventKind.FILE_WRITTEN: InfiniteFileWrittenDetails,
        InfiniteEventKind.TOOL_REFUSED: InfiniteRefusalDetails,
    })

    kind: InfiniteEventKind
    run_id: str
    agent_key: str
    role: InfiniteAgentRole
    depth: int
    at: datetime
    summary: str
    details: InfiniteEventDetails

    def __post_init__(self) -> None:
        # The run and the acting agent: the journal's run id, a key of
        # at most 512 characters, the agent's role and its depth.
        RecordFieldValidator.require_enum(self.kind, InfiniteEventKind, "InfiniteEvent.kind")
        RecordFieldValidator.require_text(self.run_id, "InfiniteEvent.run_id", pattern=INFINITE_RUN_ID_PATTERN)
        RecordFieldValidator.require_text(self.agent_key, "InfiniteEvent.agent_key", max_chars=INFINITE_EVENT_KEY_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_enum(self.role, InfiniteAgentRole, "InfiniteEvent.role")
        RecordFieldValidator.require_int(self.depth, "InfiniteEvent.depth", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_MAX_COUNT)
        # @intent event-times-are-utc-milliseconds
        # A UTC time stamped to the millisecond, so every consumer reads
        # the same instant at the precision the backend stores.
        RecordFieldValidator.require_utc_datetime(self.at, "InfiniteEvent.at", resolution_microseconds=INFINITE_EVENT_MICROSECONDS_PER_MILLISECOND)
        # A one-line summary, and the details record this kind uses.
        RecordFieldValidator.require_text(self.summary, "InfiniteEvent.summary", max_chars=INFINITE_EVENT_SUMMARY_MAX_CHARS, one_line=True)
        RecordFieldConverter.require_instance(self.details, "InfiniteEvent.details", InfiniteEvent.DETAILS_TYPES[self.kind])


__all__ = ["InfiniteCommittedEntry", "InfiniteDroppedEntry", "InfiniteEntry", "InfiniteEntryDraft", "InfiniteEvent", "InfiniteEventDetails", "InfiniteFileWrittenDetails", "InfiniteGeneratorFinishedDetails", "InfiniteMemoryDroppedDetails", "InfiniteMemorySavedDetails", "InfiniteMemoryStagedDetails", "InfiniteRefusalDetails", "InfiniteResultCard", "InfiniteRunFinishedDetails", "InfiniteRunResumedDetails", "InfiniteRunStartedDetails", "InfiniteRunStoppedDetails", "InfiniteStagedEntry", "InfiniteSubagentFinishedDetails", "InfiniteSubagentLaunchedDetails", "InfiniteSubagentReplayedDetails", "InfiniteTaskCard", "InfiniteWorkspaceUsage"]
