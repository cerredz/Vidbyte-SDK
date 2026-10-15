"""FILE: vidbyte/lib/dataclasses/infinite.py

PURPOSE: Defines the six validated records of the InfiniteMemory agent: InfiniteTaskCard, one task a parent hands to a generator and verifier pair; InfiniteEntryDraft, one memory entry before it has an id; InfiniteEntry, one committed entry; InfiniteStagedEntry, a pair's entry waiting for its verdict; InfiniteResultCard, what a parent learns about one finished pair; and InfiniteWorkspaceUsage, the workspace's file count and token total.
ROLE IN CODEBASE: Built and read by vidbyte/agents/infinite/: the launch tool turns the model's task list into InfiniteTaskCards and each finished pair into an InfiniteResultCard, the memory tools build InfiniteEntryDrafts and InfiniteStagedEntries, the workspace returns InfiniteEntry and InfiniteWorkspaceUsage records, and the journal stores and reloads the result cards.
ARCHITECTURE NOTE: Validation only. Every check runs in __post_init__, so a constructed record is always valid and its callers never check it again. Sequence fields must already be tuples; the agents layer converts the model's JSON lists. Reading and writing the JSON-lines shapes lives in the workspace and journal modules, not here.
FUNCTION INVENTORY: Six frozen, slotted records, each with a __post_init__ that runs the field checks below; _text_field checks one text field; _text_items checks a tuple of text items; _count_field checks a whole number against its minimum; _choice_field checks an enum-typed field.
COMMON MODIFICATION PATTERNS: A new record field adds one field here and one check in its record's __post_init__; its bound goes in vidbyte/lib/constants/infinite.py. A new task-card field is also one property in the launch_subagent schema and one prompt leaf for its description.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, or any other layer above vidbyte/lib. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures; serialization lives in the workspace and the journal. 3. Do not convert a list or a string into a tuple here; a bare string would split into characters, so the caller converts and the record refuses anything else.
KNOWN EDGE CASES: One line means no line break of any kind, as str.splitlines sees it. A context item that starts with "#" must be an entry id ("#42"); any other item is a relative path. InfiniteResultCard.summary and review may be empty, because a failed pair has neither. True is refused wherever a whole number is expected, although Python counts it as an int.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 8.5 and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_delegation.py, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py, tests/features/infinite_memory_agent/test_infinite_memory_verification.py, and tests/features/infinite_memory_agent/test_infinite_memory_resume.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath

from vidbyte.lib.constants.infinite import (
    INFINITE_CONTEXT_MAX_ITEMS,
    INFINITE_MAX_REFS,
    INFINITE_MAX_TAGS,
    INFINITE_STAGED_KEY_PATTERN,
    INFINITE_TAG_PATTERN,
    INFINITE_TASK_NAME_PATTERN,
)
from vidbyte.lib.enums.infinite import (
    InfiniteEntryKind,
    InfiniteResultStatus,
    InfiniteVerdict,
)
from vidbyte.lib.errors import ConfigurationError


def _text_field(record: object, name: str, *, one_line: bool = False, may_be_empty: bool = False, pattern: str | None = None) -> None:
    # One text field: a string, non-blank unless it may be empty, on one
    # line when asked, and matching the pattern when one is given.
    value = getattr(record, name)
    if isinstance(value, str) and (may_be_empty or value.strip()) and (not one_line or value.splitlines() == [value]) and (pattern is None or re.fullmatch(pattern, value)):
        return
    rule = f"match {pattern}" if pattern is not None else "be one line of non-blank text" if one_line else "be text" if may_be_empty else "be non-blank text"
    raise ConfigurationError(f"{type(record).__name__}.{name} must {rule}; got {value!r}.", details={"field": f"{type(record).__name__}.{name}"})


def _text_items(record: object, name: str, *, most: int | None = None, one_line: bool = True, pattern: str | None = None) -> None:
    # A tuple of non-blank strings, no longer than `most`, each on one
    # line when asked and matching the pattern when one is given.
    value = getattr(record, name)
    if not isinstance(value, tuple) or (most is not None and len(value) > most):
        size = f"at most {most} " if most is not None else ""
        raise ConfigurationError(f"{type(record).__name__}.{name} must be a tuple of {size}strings; got {value!r}.", details={"field": f"{type(record).__name__}.{name}"})
    for item in value:
        if not isinstance(item, str) or not item.strip() or (one_line and item.splitlines() != [item]) or (pattern is not None and not re.fullmatch(pattern, item)):
            rule = f"match {pattern}" if pattern is not None else "be one line of non-blank text" if one_line else "be non-blank text"
            raise ConfigurationError(f"Each item of {type(record).__name__}.{name} must {rule}; got {item!r}.", details={"field": f"{type(record).__name__}.{name}"})


def _count_field(record: object, name: str, value: object, minimum: int) -> None:
    # A whole number at or above the minimum; True is refused although
    # Python counts it as an int.
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{type(record).__name__}.{name} must be a whole number of at least {minimum}; got {value!r}.", details={"field": f"{type(record).__name__}.{name}"})


def _choice_field(record: object, name: str, choices: type[Enum]) -> None:
    # An enum-typed field must hold a member of its enum, not its value.
    value = getattr(record, name)
    if not isinstance(value, choices):
        raise ConfigurationError(f"{type(record).__name__}.{name} must be an {choices.__name__}; got {value!r}.", details={"field": f"{type(record).__name__}.{name}"})


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
        _text_field(self, "name", pattern=INFINITE_TASK_NAME_PATTERN)

        # Both agents need real instructions, and the goal is what both
        # of them are told to reach.
        for name in ("goal", "generator_prompt", "verifier_prompt"):
            _text_field(self, name)

        # The verifier checks the work against the criteria, so there
        # must be at least one.
        _text_items(self, "done_criteria", one_line=False)
        if not self.done_criteria:
            raise ConfigurationError(f"InfiniteTaskCard.done_criteria must hold at least one criterion; got {self.done_criteria!r}.", details={"field": "InfiniteTaskCard.done_criteria"})

        # Context items are entry ids such as "#42" or relative paths of
        # workspace files, and there is a cap on how many a task
        # carries.
        _text_items(self, "context", most=INFINITE_CONTEXT_MAX_ITEMS)
        for item in self.context:
            number = item.removeprefix("#")
            if (item.startswith("#") and not (number.isascii() and number.isdigit())) or (not item.startswith("#") and PurePath(item).is_absolute()):
                raise ConfigurationError(f"Each item of InfiniteTaskCard.context must be an entry id such as #42 or a relative path; got {item!r}.", details={"field": "InfiniteTaskCard.context"})

        # Extra tools are named once each.
        _text_items(self, "tools")
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
        _choice_field(self, "kind", InfiniteEntryKind)
        _text_field(self, "text", one_line=True)
        _text_items(self, "tags", most=INFINITE_MAX_TAGS, pattern=INFINITE_TAG_PATTERN)
        _text_items(self, "refs", most=INFINITE_MAX_REFS)
        if self.supersedes is not None:
            _count_field(self, "supersedes", self.supersedes, 1)


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
        _count_field(self, "id", self.id, 1)
        if not isinstance(self.draft, InfiniteEntryDraft):
            raise ConfigurationError(f"InfiniteEntry.draft must be an InfiniteEntryDraft; got {self.draft!r}.", details={"field": "InfiniteEntry.draft"})
        for name in ("by", "run", "at"):
            _text_field(self, name, one_line=True)
        if self.verified_by is not None:
            _text_field(self, "verified_by", one_line=True)


@dataclass(frozen=True, slots=True)
class InfiniteStagedEntry:
    """A pair's entry waiting for the verdict: its staged key ("s1", "s2", ...), its author's key, and the draft."""

    key: str
    author: str
    draft: InfiniteEntryDraft

    def __post_init__(self) -> None:
        # The verifier names a staged entry by its key, so the key keeps
        # one fixed form.
        _text_field(self, "key", pattern=INFINITE_STAGED_KEY_PATTERN)
        _text_field(self, "author", one_line=True)
        if not isinstance(self.draft, InfiniteEntryDraft):
            raise ConfigurationError(f"InfiniteStagedEntry.draft must be an InfiniteEntryDraft; got {self.draft!r}.", details={"field": "InfiniteStagedEntry.draft"})


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
        _text_field(self, "name", pattern=INFINITE_TASK_NAME_PATTERN)
        _text_field(self, "key", one_line=True)
        _choice_field(self, "status", InfiniteResultStatus)
        _choice_field(self, "verdict", InfiniteVerdict)
        for name in ("summary", "review"):
            _text_field(self, name, may_be_empty=True)

        # Committed ids are entry ids, and every dropped entry and file
        # written is named in words.
        if not isinstance(self.entries, tuple):
            raise ConfigurationError(f"InfiniteResultCard.entries must be a tuple of entry ids; got {self.entries!r}.", details={"field": "InfiniteResultCard.entries"})
        for value in self.entries:
            _count_field(self, "entries", value, 1)
        _text_items(self, "dropped", one_line=False)
        _text_items(self, "files")


@dataclass(frozen=True, slots=True)
class InfiniteWorkspaceUsage:
    """How many files the workspace holds and their token total, as counted from disk."""

    files: int
    tokens: int

    def __post_init__(self) -> None:
        # Both are counts, so neither can be negative.
        for name in ("files", "tokens"):
            _count_field(self, name, getattr(self, name), 0)


__all__ = ["InfiniteEntry", "InfiniteEntryDraft", "InfiniteResultCard", "InfiniteStagedEntry", "InfiniteTaskCard", "InfiniteWorkspaceUsage"]
