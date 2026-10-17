"""FILE: vidbyte/tools/builtins/code_search/search_memory.py

PURPOSE: Defines InfiniteSearchMemoryTool, the search_memory tool every InfiniteMemory agent holds: ranked full-text search over the workspace's live memory entries and note lines, returning the best hits as short snippets and a count of every match.
ROLE IN CODEBASE: Built by InfiniteMemoryAgentTools.get_tools (vidbyte/tools/toolsets/infinite.py) after read_lines, over the one FullTextIndex (vidbyte/lib/util/fulltext.py) that InfiniteWorkspace owns as full_text, so the root, every generator and verifier, and every retriever search one index. Exported by vidbyte/tools/builtins/code_search/__init__.py beside GrepTool.
ARCHITECTURE NOTE: A BaseCodeSearchTool subclass, so the ignore rules, the byte cap, the NUL-byte skip, and the line numbering are grep's. Each call refreshes the shared index file by file from an (st_mtime_ns, st_size) fingerprint and then searches it, both in one worker thread while holding the index's lock, so the event loop keeps serving the other agents and one call sees one consistent index; the index itself and its FTS5 table are the lib helper's. Live entries are indexed from entries.jsonl by their text alone, labelled "#id kind"; every other text file is indexed one row per non-blank line, labelled "path:line". The bookkeeping names (the run journals, entries.jsonl, superseded.jsonl, and files.jsonl) are never indexed as notes.
FUNCTION INVENTORY: spec declares the tool with literal descriptions; execute is the narrated main function, which checks the query, runs _lookup in a worker thread, and renders the hits; _lookup is the worker thread's narrated step, which holds the lock across the refresh and the search; _stamp, _entry_rows, and _note_rows each do one step of the refresh.
COMMON MODIFICATION PATTERNS: A new kind of indexed text is one more source in _lookup with a rows helper beside _entry_rows and _note_rows. A new query option is a parameter in spec and a keyword passed to FullTextIndex.search, whose bounds stay in vidbyte/lib/constants/infinite.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not read a file or call the index on the event loop; everything after the query check runs in _lookup through asyncio.to_thread. 2. Do not take the index's lock twice in one call; the refresh and the search share one hold. 3. Do not write to the workspace; the tool is READ. 4. Do not put a number in the model-facing descriptions; the caps are constants.
KNOWN EDGE CASES: A file rewritten with the same size within one filesystem timestamp tick keeps its old rows until a later write changes the size or the time (spec EC-8.5). A file that vanishes between the listing and the read is left out of this call's index. A malformed entries.jsonl line is skipped, never an error. A query whose words hold no letter or digit matches nothing and runs no MATCH. Without FTS5 every call returns fts5_unavailable and every other tool keeps working.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md (sections 6.1 INV-8.1 to INV-8.9, 9.1, and 9.2); vidbyte/tools/README.md; vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_search.py
"""

from __future__ import annotations

import asyncio
import json
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
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


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
            description=(
                "Search the workspace's live memory entries and note lines for every word of the query, best match first. "
                "Word forms are matched loosely, so other endings of a word count, and letter case is ignored. "
                "Each hit names an entry by its id and kind, or a note by its path and line number, then shows a short snippet, so you know what to read next. "
                "The last line says how many hits are shown and how many matched in total. "
                "Use it before grep whenever you look for a fact, a decision, or a topic by its words rather than by an exact pattern."
            ),
            permission=ToolPermission.READ,
            parameters=(
                ToolParameter(
                    "query",
                    "string",
                    "Plain words to search for, separated by spaces; a hit must hold every word. "
                    "It is not a pattern, so quotes, colons, stars, and search operators are searched as ordinary text. "
                    "Words with no letter or digit are left out. "
                    "Give a few distinctive words rather than a whole sentence, because every extra word must also match.",
                ),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Refresh the shared index from the disk, search it for every word of the query, and return the best hits and the total."""
        # Refuse a query with no text at all, so the model knows to send
        # words; then keep only the words that hold a letter or a digit,
        # because a word of punctuation alone would quote to an empty
        # phrase whose meaning FTS5 does not promise.
        query = call.arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult.error(self.name, "query must hold at least one word to search for.", metadata={"error": "invalid_argument"})
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
            # List what the index should hold: the live entries file and
            # every other text file grep would read.
            entries = self.root_dir / INFINITE_ENTRIES_FILE
            sources = {self.relative_path(path): path for path in self.iter_files()}
            if entries.is_file() and self.is_text_file(entries):
                sources[INFINITE_ENTRIES_FILE] = entries

            # Re-read only the files whose fingerprint changed, taking the
            # fingerprint before the read, so a write that lands during
            # the read is read again next time; a file that vanished
            # since the listing is left out.
            kept: list[str] = []
            for source, path in sources.items():
                try:
                    stamp = self._stamp(path)
                    if index.fingerprint(source) != stamp:
                        index.replace(source, stamp, self._entry_rows(path) if source == INFINITE_ENTRIES_FILE else self._note_rows(source, path))
                except OSError:
                    continue
                kept.append(source)

            # Drop the rows of every file that is gone, then search.
            index.retain(kept)
            return index.search(words, limit=INFINITE_SEARCH_MAX_HITS, snippet_tokens=INFINITE_SEARCH_SNIPPET_TOKENS)

    @staticmethod
    def _stamp(path: Path) -> str:
        # The file's fingerprint: its modification time in nanoseconds
        # and its size.
        status = path.stat()
        return f"{status.st_mtime_ns}:{status.st_size}"

    @staticmethod
    def _entry_rows(path: Path) -> list[FullTextRow]:
        # @intent only-entry-text-is-searched
        # Each live entry is one row of its text alone, labelled by its
        # id and kind; a malformed line is left out and never fails the
        # search, so the workspace's own checks stay the place to fix it.
        rows: list[FullTextRow] = []
        for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
            try:
                record = json.loads(line)
                number = RecordFieldValidator.require_int(record["id"], "id", minimum=INFINITE_FIRST_ENTRY_ID)
                kind = RecordFieldValidator.require_text(record["kind"], "kind", one_line=True)
                rows.append(FullTextRow(INFINITE_ENTRIES_FILE, f"#{number} {kind}", RecordFieldValidator.require_text(record["text"], "text", allow_blank=True)))
            except (ValueError, KeyError, TypeError, ConfigurationError):
                continue
        return rows

    def _note_rows(self, source: str, path: Path) -> list[FullTextRow]:
        # One row per non-blank line, numbered as grep and read_lines
        # number lines.
        return [FullTextRow(source, f"{source}:{number}", line) for number, line in enumerate(self.read_text_lines(path), start=1) if line.strip()]


__all__ = ["InfiniteSearchMemoryTool"]
