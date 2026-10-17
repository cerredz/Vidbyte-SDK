"""FILE: vidbyte/tools/builtins/code_search/search_memory.py

PURPOSE: Defines InfiniteSearchMemoryTool, the search_memory tool every InfiniteMemory agent holds: ranked full-text search over the workspace's live memory entries and note lines, returning the best hits as short snippets and a count of every match.
ROLE IN CODEBASE: Built by InfiniteMemoryAgentTools.get_tools (vidbyte/tools/toolsets/infinite.py) after read_lines, over the one FullTextIndex (vidbyte/lib/util/fulltext.py) that InfiniteWorkspace owns as full_text, so the root, every generator and verifier, and every retriever search one index. Exported by vidbyte/tools/builtins/code_search/__init__.py beside GrepTool.
ARCHITECTURE NOTE: A BaseCodeSearchTool subclass, so the ignore rules, the byte cap, the NUL-byte skip, and the line numbering are grep's. The refresh lists the workspace with its own os.scandir walk instead of grep's iter_files, which reads every file to sniff it: the walk keeps grep's rules, takes each fingerprint from the listing, and sniffs only a file whose fingerprint changed, so a search with nothing changed opens no file (spec NFR-8.1). Each call refreshes the shared index file by file from an (st_mtime_ns, st_size) fingerprint and then searches it, both in one worker thread while holding the index's lock, so the event loop keeps serving the other agents and one call sees one consistent index; the index itself and its FTS5 table are the lib helper's. Live entries are indexed from entries.jsonl by their text alone, labelled "#id kind"; every other text file is indexed one row per non-blank line, labelled "path:line". The bookkeeping names (the run journals, entries.jsonl, superseded.jsonl, and files.jsonl) are never indexed as notes.
FUNCTION INVENTORY: spec declares the tool with literal descriptions; execute is the narrated main function, which checks the query, runs _lookup in a worker thread, and renders the hits; _lookup is the worker thread's narrated step, which holds the lock across the refresh and the search; _listing, _entry_rows, and _note_rows each do one step of the refresh: _listing walks the workspace once and fingerprints every file from the walk, and the two rows helpers, which take the same (source, path) arguments so _lookup picks one per file, sniff and read one changed file.
COMMON MODIFICATION PATTERNS: A new kind of indexed text is one more source in _lookup with a rows helper beside _entry_rows and _note_rows. A new query option is a parameter in spec and a keyword passed to FullTextIndex.search, whose bounds stay in vidbyte/lib/constants/infinite.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not read a file or call the index on the event loop; everything after the query check runs in _lookup through asyncio.to_thread. 2. Do not take the index's lock twice in one call; the refresh and the search share one hold. 3. Do not write to the workspace; the tool is READ. 4. Do not put a number in the model-facing descriptions; the caps are constants. 5. Do not list the workspace with grep's iter_files or sniff a file whose fingerprint is unchanged; a warm search must open no file. Make such changes here, never in code_search/base.py, whose walk grep and glob share.
KNOWN EDGE CASES: A file rewritten with the same size within one filesystem timestamp tick keeps its old rows until a later write changes the size or the time (spec EC-8.5). A file that vanishes between the listing and the read is left out of this call's index. A changed file grep would skip as binary is kept with no rows, so it is not sniffed again until it changes. A folder reached twice, through a link or a junction, is walked once. A malformed entries.jsonl line is skipped, never an error, and so is a line whose kind or text UTF-8 cannot encode (a lone surrogate written as a JSON escape). A file whose name UTF-8 cannot encode is left out of the call (spec EC-8.8). The blank-query check reads the query as given; after it, each NUL reads as a space and each lone surrogate is dropped, so no query text can fail the bind or the MATCH. A query whose words hold no letter or digit matches nothing and runs no MATCH. Without FTS5 every call returns fts5_unavailable and every other tool keeps working.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md (sections 6.1 INV-8.1 to INV-8.9, 9.1, and 9.2); vidbyte/tools/README.md; vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_search.py
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from contextlib import suppress
from pathlib import Path

from vidbyte.lib.constants.infinite import (
    INFINITE_BOOKKEEPING_NAMES,
    INFINITE_ENTRIES_FILE,
    INFINITE_FIRST_ENTRY_ID,
    INFINITE_SEARCH_MAX_HITS,
    INFINITE_SEARCH_MEMORY_TOOL_NAME,
    INFINITE_SEARCH_SNIPPET_TOKENS,
)
from vidbyte.lib.dataclasses.code_search import FullTextMatches, FullTextRow
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.fulltext import FullTextIndex
from vidbyte.tools.builtins.code_search.base import BaseCodeSearchTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class InfiniteSearchMemoryTool(BaseCodeSearchTool):
    """Rank the workspace's live memory entries and note lines by how well they match every word of a query."""

    def __init__(self, workspace_root: str | Path, *, index: FullTextIndex, max_file_bytes: int) -> None:
        """Search workspace_root through the shared index, skipping the bookkeeping names and files over max_file_bytes as grep does."""
        super().__init__(workspace_root, ignore_patterns=INFINITE_BOOKKEEPING_NAMES, max_file_bytes=max_file_bytes)
        self.index = index

    def spec(self) -> ToolSpec:
        """Return the read-only search_memory declaration with its one query parameter."""
        return ToolSpec(
            name=INFINITE_SEARCH_MEMORY_TOOL_NAME,
            description="Search the workspace's live memory entries and note lines for every word of the query, best match first. Word forms are matched loosely, so other endings of a word count, and letter case is ignored. Each hit names an entry by its id and kind, or a note by its path and line number, then shows a short snippet, so you know what to read next. The last line says how many hits are shown and how many matched in total. Use it before grep whenever you look for a fact, a decision, or a topic by its words rather than by an exact pattern.",
            permission=ToolPermission.READ,
            parameters=(
                ToolParameter(
                    "query",
                    "string",
                    "Plain words to search for, separated by spaces; a hit must hold every word. It is not a pattern, so quotes, colons, stars, and search operators are searched as ordinary text. Words with no letter or digit are left out. Give a few distinctive words rather than a whole sentence, because every extra word must also match.",
                ),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Refresh the shared index from the disk, search it for every word of the query, and return the best hits and the total."""
        # Refuse a query with no text at all, so the model knows to send
        # words. The check reads the query as given, so a query of NULs
        # alone is searched and matches nothing.
        query = call.arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult.error(self.name, "query must hold at least one word to search for.", metadata={"error": "invalid_argument"})
        # Read each NUL as a space and drop each character UTF-8 cannot
        # encode, a lone surrogate, because SQLite can bind neither and
        # FTS5 stops reading at a NUL. Then keep only the words that
        # hold a letter or a digit, because a word of punctuation alone
        # would quote to an empty phrase whose meaning FTS5 does not
        # promise.
        query = query.replace("\x00", " ").encode("utf-8", "ignore").decode("utf-8")
        words = tuple(word for word in query.split() if any(character.isalnum() for character in word))

        # @intent search-memory-runs-off-the-event-loop
        # Reading the workspace and every SQLite call run in a worker
        # thread, so the event loop keeps serving the other agents of the
        # tree while this one searches.
        try:
            matches = await asyncio.to_thread(self._lookup, words)
        except ConfigurationError as exc:
            # An interpreter whose SQLite lacks FTS5 fails the index's
            # first use; only this tool stops working.
            return ToolResult.error(self.name, exc.message, metadata={"error": "fts5_unavailable"})

        # One line per hit, best first, then the line that counts the
        # hits shown and every match.
        lines = [f"{hit.label}: {hit.snippet}" for hit in matches.hits]
        lines.append(f"{len(matches.hits)} of {matches.total} matching entries and note lines shown.")
        return ToolResult.success(self.name, "\n".join(lines), metadata={"hits": len(matches.hits), "total": matches.total})

    def _lookup(self, words: tuple[str, ...]) -> FullTextMatches:
        # Refresh the index to the disk as it is now and search it; runs
        # in a worker thread.
        # @intent one-lock-hold-spans-refresh-and-search
        # The index is shared by every agent of the tree, so the lock is
        # held across the refresh and the search: no other call can swap
        # a file's rows in between, and the result matches one state.
        index = self.index
        with index.lock:
            # List what the index should hold, each file with the
            # fingerprint the listing took: every text file grep would
            # read, and the live entries file.
            listed = self._listing()

            # Re-read only the files whose fingerprint changed. The
            # fingerprint was taken before the read, so a write that
            # lands during the read is read again next time. A file
            # that vanished since the listing, or whose name UTF-8
            # cannot encode, is left out of this call.
            kept: set[str] = set()
            for source, (path, stamp) in listed.items():
                read_rows = self._entry_rows if source == INFINITE_ENTRIES_FILE else self._note_rows
                try:
                    rows = None if index.fingerprint(source) == stamp else read_rows(source, Path(path))
                except (OSError, UnicodeError):
                    continue
                if rows is not None:
                    index.replace(source, stamp, rows)
                kept.add(source)

            # Drop the rows of every file that is gone, then search.
            index.retain(kept)
            return index.search(words, limit=INFINITE_SEARCH_MAX_HITS, snippet_tokens=INFINITE_SEARCH_SNIPPET_TOKENS)

    def _listing(self) -> dict[str, tuple[str, str]]:
        # Map each file the index should hold, by the name grep reports
        # it under, to its path and its fingerprint: the modification
        # time in nanoseconds and the size.
        # @intent a-warm-search-opens-no-unchanged-file
        # Grep's shared walk resolves every file and reads each one to
        # sniff it, a whole read of the workspace per search. This walk
        # lists each folder once, resolves only folders and links, and
        # takes the fingerprint from the listing, so a search with
        # nothing changed opens no file. Grep's rules stay: the ignored
        # names, no linked folder, the in-root and once-per-file guards,
        # and the byte cap.
        root = self.root_dir
        listed: dict[str, tuple[str, str]] = {}
        walked: set[Path] = set()
        pending = [str(root)]
        while pending:
            folder = pending.pop()
            real_folder = Path(folder).resolve()
            if real_folder in walked or not real_folder.is_relative_to(root):
                continue
            walked.add(real_folder)
            prefix = "" if real_folder == root else f"{real_folder.relative_to(root).as_posix()}/"
            try:
                with os.scandir(folder) as found:
                    children = [child for child in found if child.name not in self.ignore_patterns]
            except OSError:
                continue
            subfolders: list[str] = []
            for child in children:
                try:
                    status, linked = child.stat(), child.is_symlink()
                except OSError:
                    continue
                if stat.S_ISDIR(status.st_mode):
                    subfolders += [] if linked else [child.path]
                    continue
                # A linked file is listed under its target's name, once,
                # and only when the target is inside the workspace.
                name, path = f"{prefix}{child.name}", child.path
                if linked:
                    real = Path(path).resolve()
                    name, path = (real.relative_to(root).as_posix(), str(real)) if real.is_relative_to(root) else ("", "")
                if name and stat.S_ISREG(status.st_mode) and status.st_size <= self.max_file_bytes:
                    listed.setdefault(name, (path, f"{status.st_mtime_ns}:{status.st_size}"))
            # Walk the subfolders depth first in listing order, as grep.
            pending.extend(reversed(subfolders))

        # The live entries file is a bookkeeping name, so the walk skips
        # it; it is listed by itself, last, while it fits the byte cap.
        entries = root / INFINITE_ENTRIES_FILE
        with suppress(OSError):
            status = entries.stat()
            if stat.S_ISREG(status.st_mode) and status.st_size <= self.max_file_bytes:
                listed[INFINITE_ENTRIES_FILE] = (str(entries), f"{status.st_mtime_ns}:{status.st_size}")
        return listed

    def _entry_rows(self, source: str, path: Path) -> list[FullTextRow]:
        # @intent only-entry-text-is-searched
        # Each live entry is one row of its text alone, labelled by its
        # id and kind; a malformed line is left out and never fails the
        # search, so the workspace's own checks stay the place to fix it.
        # An entries file grep would skip as binary gives no rows.
        rows: list[FullTextRow] = []
        if not self.is_text_file(path):
            return rows
        for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
            try:
                record = json.loads(line)
                number = RecordFieldValidator.require_int(record["id"], "id", minimum=INFINITE_FIRST_ENTRY_ID)
                kind = RecordFieldValidator.require_text(record["kind"], "kind", one_line=True)
                text = RecordFieldValidator.require_text(record["text"], "text", allow_blank=True)
                # A kind or text UTF-8 cannot encode, a lone surrogate
                # bash wrote as a JSON escape, is malformed too: SQLite
                # could not store it, and the encode error is a
                # ValueError.
                f"{kind}{text}".encode("utf-8")
                rows.append(FullTextRow(source, f"#{number} {kind}", text))
            except (ValueError, KeyError, TypeError, ConfigurationError):
                continue
        return rows

    def _note_rows(self, source: str, path: Path) -> list[FullTextRow]:
        # One row per non-blank line, numbered as grep and read_lines
        # number lines. A name UTF-8 cannot encode raises here, before
        # the file is opened, because SQLite could not store it as the
        # label; the refresh then leaves the file out. A file grep would
        # skip as binary gives no rows.
        source.encode("utf-8")
        if not self.is_text_file(path):
            return []
        return [FullTextRow(source, f"{source}:{number}", line) for number, line in enumerate(self.read_text_lines(path), start=1) if line.strip()]


__all__ = ["InfiniteSearchMemoryTool"]
