"""FILE: vidbyte/agents/infinite/workspace.py

PURPOSE: Defines InfiniteWorkspace, the one memory folder every agent in an InfiniteMemory tree shares, and its deterministic guardrails: setup of the folder, the bookkeeping files, and the seeds; the file and token caps recounted from disk before every tool write; the sparse-entry rules; entry commits and supersedes; note writes and edits inside the allowed paths; and the workspace map every agent sees.
ROLE IN CODEBASE: Built once by InfiniteMemoryAgent (agent.py) from InfiniteWorkspaceSettings (settings.py); called by the memory tools (memory.py) for every remember, write_note, and edit_file, by the launch tool (launch.py) to resolve "#N" context ids and to commit a pair's staged entries, and by the runtime (runtime.py) and the launch tool to render the map.
ARCHITECTURE NOTE: All data is plain files under the root (spec section 9.1): entries.jsonl holds the live entries, superseded.jsonl the replaced ones, files.jsonl one description per created note. Nothing is cached; every check reads the disk, so files that bash or the developer wrote count too. Every write runs under one class-level lock and replaces whole files atomically (temp file plus os.replace), so a reader never sees half a line. Rule violations raise ToolExecutionError with what to fix, which the memory tools return to the model.
FUNCTION INVENTORY: __init__ and commit_entry are narrated main functions. usage, entries, check_entry, write_note, edit_file, and map_text are the public operations. _file_tokens counts every file's tokens from disk; _text reads one bookkeeping file; _entry_lines parses a bookkeeping file into entries; _entry_rules applies the sparse-entry rules; _note_path applies the note path rules; _room applies the workspace caps to a set of new file texts; _descriptions reads files.jsonl leniently for the map; _replace writes one file atomically; _entry_json and _stamp format one entry line and one UTC stamp.
COMMON MODIFICATION PATTERNS: A new guardrail is one more check in the operation it guards, with an @intent comment and a ToolExecutionError message that says what to fix. A new bookkeeping file adds its name to vidbyte/lib/constants/infinite.py, to the setup loop in __init__, and to the reserved paths in _note_path.
WHAT NOT TO DO IN THIS FILE: 1. Do not cache file counts, entries, or descriptions; bash can change the folder between any two calls. 2. Do not write outside the lock or write a file in place; use _replace. 3. Do not apply max_file_tokens to the bookkeeping files; only max_tokens bounds them (INV-19). 4. Do not raise from map_text on bad file content.
KNOWN EDGE CASES: A malformed line in entries.jsonl or superseded.jsonl makes every entry operation fail with the file and line number until it is fixed, while map_text keeps working. A supersede writes the old line to superseded.jsonl before it rewrites entries.jsonl, so a crash between the two leaves the line in both files rather than in neither. Token counts are TokenEstimate's character estimate of the utf-8 text, with undecodable bytes counted as replacement characters. Seeds are copied through LocalFileSystemBackend.copy, which keeps their permission bits, so a read-only seed leaves a read-only copy and the next setup over the same folder fails with PermissionError until that copy is made writable.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-16 to INV-24, and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_workspace.py, tests/features/infinite_memory_agent/test_infinite_memory_verification.py, and tests/features/infinite_memory_agent/test_infinite_memory_contract.py
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from vidbyte.agents.infinite.settings import InfiniteWorkspaceSettings
from vidbyte.lib.constants.infinite import (
    INFINITE_ENTRIES_FILE,
    INFINITE_FILES_FILE,
    INFINITE_MAP_MAX_TOKENS,
    INFINITE_MORE_FILES,
    INFINITE_NO_DESCRIPTION,
    INFINITE_NOTE_SUFFIXES,
    INFINITE_RUNS_DIRNAME,
    INFINITE_SEED_DIRNAME,
    INFINITE_SEED_LABEL,
    INFINITE_SUPERSEDED_FILE,
)
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.infinite import (
    InfiniteEntry,
    InfiniteEntryDraft,
    InfiniteStagedEntry,
    InfiniteWorkspaceUsage,
)
from vidbyte.lib.enums.infinite import InfiniteEntryKind
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError
from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend
from vidbyte.lib.tools.filesystem.permissions import FileSystemPermissions
from vidbyte.lib.util.text import (
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    SubstringCounter,
    TokenEstimate,
)
from vidbyte.prompts.catalog import Prompts


class InfiniteWorkspace:
    """The shared memory folder of one InfiniteMemory agent and the guardrails on every tool write to it."""

    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, settings: InfiniteWorkspaceSettings) -> None:
        self.settings = settings
        self.root = Path(settings.root)
        self._scope = FileSystemToolConfig(root=self.root)
        self.backend = LocalFileSystemBackend()

        # @intent the-workspace-is-ready-before-any-agent-starts
        # Create the folder and the three bookkeeping files, empty when
        # absent, so every agent can read them from its first call. Copy
        # each seed in, replacing an older copy, so the seeds always
        # match the developer's files.
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            for name in (INFINITE_ENTRIES_FILE, INFINITE_SUPERSEDED_FILE, INFINITE_FILES_FILE):
                (self.root / name).touch(exist_ok=True)
            for seed in settings.seed_files:
                self.backend.copy(Path(seed), self.root / INFINITE_SEED_DIRNAME / Path(seed).name)

        # Refuse a workspace that already breaks a cap, so no agent
        # starts in a workspace where every write would be refused.
        counts = self._file_tokens()
        if len(counts) > settings.max_files:
            raise ConfigurationError(f"The workspace at {self.root} holds {len(counts)} files, over max_files ({settings.max_files}); raise the cap or remove files.", details={"field": "max_files"})
        if sum(counts.values()) > settings.max_tokens:
            raise ConfigurationError(f"The workspace at {self.root} holds {sum(counts.values())} tokens, over max_tokens ({settings.max_tokens}); raise the cap or remove files.", details={"field": "max_tokens"})
        for seed in settings.seed_files:
            seed_tokens = counts[f"{INFINITE_SEED_DIRNAME}/{Path(seed).name}"]
            if seed_tokens > settings.max_file_tokens:
                raise ConfigurationError(f"The seed file {seed} is {seed_tokens} tokens, over max_file_tokens ({settings.max_file_tokens}); raise the cap or shorten the seed.", details={"field": "max_file_tokens"})

    def usage(self) -> InfiniteWorkspaceUsage:
        """Return the file count and token total of everything under the root except the run journals."""
        counts = self._file_tokens()
        return InfiniteWorkspaceUsage(files=len(counts), tokens=sum(counts.values()))

    def entries(self, ids: tuple[int, ...]) -> tuple[InfiniteEntry, ...]:
        """Return the live entries with these ids, in order, or raise ToolExecutionError naming the first id that is not live."""
        live = {entry.id: entry for entry, _ in self._entry_lines(INFINITE_ENTRIES_FILE, self._text(INFINITE_ENTRIES_FILE))}
        missing = [number for number in ids if number not in live]
        if missing:
            raise ToolExecutionError(f"Memory entry #{missing[0]} is not a live entry in {INFINITE_ENTRIES_FILE}; name only ids the map's memory holds.")
        return tuple(live[number] for number in ids)

    def check_entry(self, draft: InfiniteEntryDraft, staged: tuple[InfiniteStagedEntry, ...] = ()) -> None:
        """Raise ToolExecutionError when the draft breaks a sparse-entry rule against the live entries and the pair's staged entries."""
        self._entry_rules(draft, self._entry_lines(INFINITE_ENTRIES_FILE, self._text(INFINITE_ENTRIES_FILE)), staged)

    def commit_entry(self, draft: InfiniteEntryDraft, *, by: str, verified_by: str | None, run: str) -> InfiniteEntry:
        """Append the draft as a new live entry, moving the entry it supersedes to superseded.jsonl, and return it."""
        with self._lock:
            # Read the live and the replaced entries again under the lock,
            # because other agents may have committed since this entry
            # was staged.
            live_text = self._text(INFINITE_ENTRIES_FILE)
            live = self._entry_lines(INFINITE_ENTRIES_FILE, live_text)
            retired_text = self._text(INFINITE_SUPERSEDED_FILE)
            retired = self._entry_lines(INFINITE_SUPERSEDED_FILE, retired_text)

            # Check the entry against today's live memory.
            self._entry_rules(draft, live, ())

            # @intent entry-ids-never-repeat
            # The next id is one more than every id ever used, live or
            # replaced, so two commits never share an id.
            next_id = max((entry.id for entry, _ in (*live, *retired)), default=0) + 1
            entry = InfiniteEntry(id=next_id, draft=draft, by=by, verified_by=verified_by, run=run, at=self._stamp())
            line = self._entry_json(entry)

            # @intent supersede-is-a-move
            # A superseded entry leaves entries.jsonl unchanged in form and
            # lands, byte for byte, in superseded.jsonl, so grep over the
            # live memory no longer finds it.
            kept = [raw for old, raw in live if old.id != draft.supersedes]
            moved = [raw for old, raw in live if old.id == draft.supersedes]
            changed = {INFINITE_ENTRIES_FILE: "".join(f"{raw}\n" for raw in (*kept, line))}
            if moved:
                changed = {INFINITE_SUPERSEDED_FILE: "".join(f"{raw}\n" for _, raw in retired) + "".join(f"{raw}\n" for raw in moved), **changed}

            # Refuse the commit if the new files would pass a workspace
            # cap; the bookkeeping files have no per-file cap.
            self._room(self._file_tokens(), changed)

            # Write the replaced line first, then the live entries.
            for relative, text in changed.items():
                self._replace(relative, text)
        return entry

    def write_note(self, path: str, text: str, description: str | None, *, by: str, run: str, may_create: bool) -> bool:
        """Create the note or append text to it, record a new note's description, and return True when the note was created."""
        with self._lock:
            target, relative = self._note_path(path)
            created = not target.exists()
            # @intent new-notes-are-described-and-rationed
            # Each agent may create only a few files, and every new file
            # needs a short one-line description for the map.
            if created and not may_create:
                raise ToolExecutionError(f"{relative} does not exist, and you have used your allowance of new files; append to an existing note instead.")
            if created and (not isinstance(description, str) or not description.strip() or description.splitlines() != [description] or TokenEstimate.count(description) > self.settings.max_entry_tokens):
                raise ToolExecutionError(f"{relative} is a new file, so it needs a one-line description of at most {self.settings.max_entry_tokens} tokens for the workspace map.")
            # @intent one-note-stays-under-the-file-cap
            # Appending never grows a note past max_file_tokens.
            note = ("" if created else target.read_text(encoding="utf-8", errors="replace")) + text
            if TokenEstimate.count(note) > self.settings.max_file_tokens:
                raise ToolExecutionError(f"{relative} would be {TokenEstimate.count(note)} tokens, over max_file_tokens ({self.settings.max_file_tokens}); write a shorter text or start another note.")
            changed = {relative: note}
            if created:
                record = {"path": relative, "description": description, "by": by, "run": run, "at": self._stamp()}
                changed[INFINITE_FILES_FILE] = self._text(INFINITE_FILES_FILE) + json.dumps(record, ensure_ascii=False) + "\n"
            self._room(self._file_tokens(), changed)
            for name, content in changed.items():
                self._replace(name, content)
        return created

    def edit_file(self, path: str, old_text: str, new_text: str) -> None:
        """Replace the one occurrence of old_text in an existing note with new_text."""
        with self._lock:
            target, relative = self._note_path(path)
            if not target.is_file():
                raise ToolExecutionError(f"{relative} does not exist; create it with write_note first.")
            # @intent edits-replace-exactly-one-match
            # An edit must name one place in the file, so zero or several
            # matches are refused with the count found.
            content = target.read_text(encoding="utf-8", errors="replace")
            matches = SubstringCounter.count_overlapping(content, old_text) if old_text else 0
            if matches != 1:
                raise ToolExecutionError(f"old_text must appear exactly once in {relative}, but it appears {matches} times; include more of the surrounding text.")
            note = content.replace(old_text, new_text, 1)
            if TokenEstimate.count(note) > self.settings.max_file_tokens:
                raise ToolExecutionError(f"{relative} would be {TokenEstimate.count(note)} tokens, over max_file_tokens ({self.settings.max_file_tokens}); write a shorter replacement.")
            self._room(self._file_tokens(), {relative: note})
            self._replace(relative, note)

    def map_text(self) -> str:
        """Render the workspace map: the totals against their caps, then one line per file with its tokens and description."""
        # @intent the-map-never-fails-on-content
        # Every agent needs the map, so a malformed bookkeeping line only
        # costs that file its description; it never stops the render.
        counts = self._file_tokens()
        descriptions = self._descriptions(self._text(INFINITE_FILES_FILE))
        live = sum(1 for line in self._text(INFINITE_ENTRIES_FILE).split("\n") if line.strip())
        header = Prompts().get(Prompt.INFINITE_MEMORY_MAP_HEADER).format(files=len(counts), max_files=self.settings.max_files, tokens=sum(counts.values()), max_tokens=self.settings.max_tokens, entries=live)
        lines = [f"- {path} ({tokens} tokens): {INFINITE_SEED_LABEL if path.startswith(f'{INFINITE_SEED_DIRNAME}/') else descriptions.get(path, INFINITE_NO_DESCRIPTION)}" for path, tokens in counts.items()]
        rendered = "\n".join((header, *lines))
        if TokenEstimate.count(rendered) <= INFINITE_MAP_MAX_TOKENS:
            return rendered

        # @intent the-map-fits-its-cap
        # Past the cap, keep the first lines that fit and say how many
        # files were left out, leaving room for that closing line.
        room = INFINITE_MAP_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN - len(INFINITE_MORE_FILES.format(count=len(lines))) - len("\n")
        shown = header
        for index, line in enumerate(lines):
            if len(shown) + len("\n") + len(line) > room:
                return f"{shown}\n{INFINITE_MORE_FILES.format(count=len(lines) - index)}"
            shown = f"{shown}\n{line}"
        return shown

    def _file_tokens(self) -> dict[str, int]:
        # @intent caps-are-counted-from-disk
        # Every file under the root counts, whoever wrote it, except the
        # run journals, so bash cannot slip files past the caps.
        counts: dict[str, int] = {}
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root)
            if path.is_file() and relative.parts[0] != INFINITE_RUNS_DIRNAME:
                counts[relative.as_posix()] = TokenEstimate.count(path.read_text(encoding="utf-8", errors="replace"))
        return counts

    def _text(self, name: str) -> str:
        # One bookkeeping file's text, or "" when bash removed it.
        path = self.root / name
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    @staticmethod
    def _entry_lines(name: str, text: str) -> list[tuple[InfiniteEntry, str]]:
        # @intent bookkeeping-lines-are-checked-not-guessed
        # Each non-blank line must be one entry in the documented shape;
        # any other line stops entry operations with its file and line
        # number, so the model can repair it with bash.
        parsed: list[tuple[InfiniteEntry, str]] = []
        for number, raw in enumerate(text.split("\n"), start=1):
            line = raw.rstrip("\r")
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                draft = InfiniteEntryDraft(kind=InfiniteEntryKind(record["kind"]), text=record["text"], tags=tuple(record["tags"]) if isinstance(record["tags"], list) else record["tags"], refs=tuple(record["refs"]) if isinstance(record["refs"], list) else record["refs"], supersedes=record["supersedes"])
                parsed.append((InfiniteEntry(id=record["id"], draft=draft, by=record["by"], verified_by=record["verified_by"], run=record["run"], at=record["at"]), line))
            except (ValueError, KeyError, TypeError, ConfigurationError) as exc:
                raise ToolExecutionError(f"{name} line {number} is not a memory entry in the documented shape; fix or remove that line with bash.", details={"file": name, "line": number}) from exc
        return parsed

    def _entry_rules(self, draft: InfiniteEntryDraft, live: list[tuple[InfiniteEntry, str]], staged: tuple[InfiniteStagedEntry, ...]) -> None:
        # @intent memory-stays-sparse
        # An entry is short, new, and replaces only a live entry. Its
        # text is compared with case and spacing ignored, so a reworded
        # copy is not saved twice.
        if TokenEstimate.count(draft.text) > self.settings.max_entry_tokens:
            raise ToolExecutionError(f"The entry text is {TokenEstimate.count(draft.text)} tokens, over max_entry_tokens ({self.settings.max_entry_tokens}); shorten it to one short line, or save the full text with write_note and remember a one-line pointer to that note.")
        normal = " ".join(draft.text.split()).casefold()
        twin = next((entry for entry, _ in live if " ".join(entry.draft.text.split()).casefold() == normal), None)
        if twin is not None:
            raise ToolExecutionError(f"This text is already recorded as #{twin.id}; do not save it again.")
        sibling = next((item for item in staged if " ".join(item.draft.text.split()).casefold() == normal), None)
        if sibling is not None:
            raise ToolExecutionError(f"This text is already staged as {sibling.key}; do not stage it again.")
        if draft.supersedes is not None and all(entry.id != draft.supersedes for entry, _ in live):
            raise ToolExecutionError(f"supersedes names #{draft.supersedes}, which is not a live entry; give the id of an entry in {INFINITE_ENTRIES_FILE}.")

    def _note_path(self, path: str) -> tuple[Path, str]:
        # @intent notes-stay-in-their-lane
        # A note lives inside the workspace, has a text suffix, and is
        # never a seed, a run journal, or a bookkeeping file, which only
        # the memory tools and the journal write. Its path is one line,
        # because the pair's result card lists it as one, and holds no
        # colon, which on Windows names a hidden stream of another file.
        if path and path.splitlines() != [path]:
            raise ToolExecutionError(f"{path!r} breaks across lines; give a note path on one line.")
        try:
            target = FileSystemPermissions.resolve_scoped_path(self._scope, path)
        except ToolExecutionError as exc:
            raise ToolExecutionError(f"{path} is outside the workspace; give a path inside it, such as notes/topic.md.") from exc
        if target.suffix not in INFINITE_NOTE_SUFFIXES:
            raise ToolExecutionError(f"{path} must end in one of {', '.join(INFINITE_NOTE_SUFFIXES)}.")
        relative = target.relative_to(self.root)
        if ":" in relative.as_posix():
            raise ToolExecutionError(f"{relative.as_posix()} holds a colon; write the note path without one.")
        # A case-insensitive disk, such as macOS's default, keeps the
        # caller's spelling, so the protected names are matched with
        # case ignored.
        folded = relative.as_posix().casefold()
        if target.is_dir() or folded.split("/")[0] in (INFINITE_SEED_DIRNAME, INFINITE_RUNS_DIRNAME) or folded in (INFINITE_ENTRIES_FILE, INFINITE_SUPERSEDED_FILE, INFINITE_FILES_FILE):
            raise ToolExecutionError(f"{relative.as_posix()} is a seed file, a run journal, a memory file, or a folder, which no note may replace; write another path.")
        return target, relative.as_posix()

    def _room(self, counts: Mapping[str, int], changed: Mapping[str, str]) -> None:
        # @intent writes-never-pass-the-workspace-caps
        # The caps are checked against the files as they would be after
        # the write, counted from disk just before it.
        files = len(counts) + sum(1 for relative in changed if relative not in counts)
        tokens = sum(counts.values()) - sum(counts.get(relative, 0) for relative in changed) + sum(TokenEstimate.count(text) for text in changed.values())
        if files > self.settings.max_files:
            raise ToolExecutionError(f"This write would make {files} files, over max_files ({self.settings.max_files}); append to an existing note instead.")
        if tokens > self.settings.max_tokens:
            raise ToolExecutionError(f"This write would make the workspace {tokens} tokens, over max_tokens ({self.settings.max_tokens}); write less, or ask the developer to raise the cap.")

    def _replace(self, relative: str, text: str) -> None:
        # Write to a temporary file beside the target and swap it in, so
        # no reader ever sees a half-written file. A failed write or swap
        # removes the temporary file, which would otherwise count toward
        # the caps, and leaves the target as it was.
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
                file.write(text)
            os.replace(temporary, target)
        except BaseException:
            os.unlink(temporary)
            raise

    @staticmethod
    def _descriptions(text: str) -> dict[str, str]:
        # The last description files.jsonl records for each path; a line
        # that is not a JSON object with a text path and description is
        # skipped.
        found: dict[str, str] = {}
        for line in text.split("\n"):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and isinstance(record.get("path"), str) and isinstance(record.get("description"), str):
                found[record["path"]] = record["description"]
        return found

    @staticmethod
    def _entry_json(entry: InfiniteEntry) -> str:
        # One entries.jsonl line, with the keys in the documented order.
        draft = entry.draft
        record = {"id": entry.id, "kind": draft.kind.value, "text": draft.text, "tags": list(draft.tags), "refs": list(draft.refs), "supersedes": draft.supersedes, "by": entry.by, "verified_by": entry.verified_by, "run": entry.run, "at": entry.at}
        return json.dumps(record, ensure_ascii=False)

    @staticmethod
    def _stamp() -> str:
        # The current time in UTC, to the second.
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = ["InfiniteWorkspace"]
