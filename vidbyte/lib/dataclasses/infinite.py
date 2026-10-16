"""FILE: vidbyte/lib/dataclasses/infinite.py

PURPOSE: Defines the six validated records of the InfiniteMemory agent: InfiniteTaskCard, one task a parent hands to a generator and verifier pair; InfiniteEntryDraft, one memory entry before it has an id; InfiniteEntry, one committed entry; InfiniteStagedEntry, a pair's entry waiting for its verdict; InfiniteResultCard, what a parent learns about one finished pair; and InfiniteWorkspaceUsage, the workspace's file count and token total.
ROLE IN CODEBASE: Built and read by vidbyte/agents/infinite/: the launch tool turns the model's task list into InfiniteTaskCards and each finished pair into an InfiniteResultCard, the memory tools build InfiniteEntryDrafts and InfiniteStagedEntries, the workspace returns InfiniteEntry and InfiniteWorkspaceUsage records, and the journal stores and reloads the result cards.
ARCHITECTURE NOTE: Validation only. Every check runs in __post_init__, so a constructed record is always valid and its callers never check it again. Each field check is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py); only this feature's own rules, such as what a context item may name, are written here. Sequence fields must already be tuples; the agents layer converts the model's JSON lists. Reading and writing the JSON-lines shapes lives in the workspace and journal modules, not here.
FUNCTION INVENTORY: Six frozen, slotted records, each with a __post_init__ that checks its fields through RecordFieldValidator and RecordFieldConverter and then applies its own rules.
COMMON MODIFICATION PATTERNS: A new record field adds one field here and one RecordFieldValidator or RecordFieldConverter call in its record's __post_init__; its bound goes in vidbyte/lib/constants/infinite.py. A check the canonical validators lack becomes a new option or method there, never a helper here. A new task-card field is also one property in the launch_subagent schema and one prompt leaf for its description.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, or any other layer above vidbyte/lib. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures; serialization lives in the workspace and the journal. 3. Do not convert a list or a string into a tuple here; a bare string would split into characters, so the caller converts and the record refuses anything else.
KNOWN EDGE CASES: One line means no line break of any kind, as str.splitlines sees it. A context item that starts with "#" must be an entry id ("#42"); any other item is a relative path. InfiniteResultCard.summary and review may be empty, because a failed pair has neither. True is refused wherever a whole number is expected, although Python counts it as an int. A refusal names the field as Record.field, or Record.field[index] for one item of a tuple.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_delegation.py, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py, tests/features/infinite_memory_agent/test_infinite_memory_verification.py, and tests/features/infinite_memory_agent/test_infinite_memory_resume.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from vidbyte.lib.constants.infinite import (
    INFINITE_CONTEXT_MAX_ITEMS,
    INFINITE_FIRST_ENTRY_ID,
    INFINITE_MAX_REFS,
    INFINITE_MAX_TAGS,
    INFINITE_MIN_COUNT,
    INFINITE_STAGED_KEY_PATTERN,
    INFINITE_TAG_PATTERN,
    INFINITE_TASK_NAME_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.infinite import (
    InfiniteEntryKind,
    InfiniteResultStatus,
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


__all__ = ["InfiniteEntry", "InfiniteEntryDraft", "InfiniteResultCard", "InfiniteStagedEntry", "InfiniteTaskCard", "InfiniteWorkspaceUsage"]
