"""FILE: vidbyte/lib/util/fulltext.py

PURPOSE: Defines FullTextIndex, the canonical in-memory full-text index: rows of text grouped by the source file they came from, matched by every query word (porter stemming, no letter case), ranked best first by bm25, and returned as short snippets with a count of every match.
ROLE IN CODEBASE: Held once per InfiniteWorkspace as full_text (vidbyte/agents/infinite/workspace.py) and searched by InfiniteSearchMemoryTool (vidbyte/tools/builtins/code_search/search_memory.py), which every agent in one InfiniteMemory tree shares. Any feature that needs ranked word search over text it already holds in files should use this class instead of its own sqlite code.
ARCHITECTURE NOTE: One stdlib sqlite3 connection to ":memory:" holds one FTS5 table, rows(source UNINDEXED, label UNINDEXED, body), tokenized with 'porter unicode61'. Nothing is opened in __init__: the first method that needs the table opens the connection, so building the owner never fails on an interpreter without FTS5, and that first use raises ConfigurationError naming FTS5 and the SQLite version. Each source's fingerprint and the rowids its rows were given live beside the table in plain dicts, so replace and retain delete by rowid; FTS5 keeps no index on the UNINDEXED source column, so a delete by source would scan the whole table. Every method that touches the index or its bookkeeping takes the public reentrant lock, and the connection allows use from any thread, so a caller may refresh and search in a worker thread while holding the lock across both.
FUNCTION INVENTORY: FullTextIndex.fingerprint(source) returns the fingerprint stored with a source; replace(source, fingerprint, rows) swaps a source's rows; retain(sources) drops every other source; search(words, limit=, snippet_tokens=) returns FullTextMatches, refusing a bad size with ValueError through RecordFieldValidator; match_expression(words) is the static quoting rule. Helpers _table (the lazy table) and _delete (one source's rows) are flat.
COMMON MODIFICATION PATTERNS: A new query option is a keyword on search with a refusal in the isinstance shape, forwarded as a bound parameter. A new stored field is a new UNINDEXED column, filled from a new FullTextRow field.
WHAT NOT TO DO IN THIS FILE: 1. Do not open the connection in __init__; the owner is built before anyone knows whether FTS5 exists. 2. Do not put query text into the MATCH expression unquoted; any word could be an operator or a column filter. 3. Do not delete rows by source; delete by the rowids recorded for it. 4. Do not import from a layer above vidbyte/lib.
KNOWN EDGE CASES: An empty word list matches nothing and runs no MATCH. A word holding no letter or digit quotes to a phrase FTS5 matches nothing with on SQLite 3.38, but callers drop such words first rather than rely on that. bm25 ties have no defined order. The snippet cap counts word tokens; the ellipsis FTS5 adds at a cut is not a word.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md (section 9.1, INV-8.2, INV-8.6, INV-8.9, D-11); vidbyte/lib/README.md
TESTS: tests/test_fulltext_index.py; and through search_memory, tests/features/infinite_memory_agent/test_infinite_memory_search.py
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Collection, Sequence

from vidbyte.lib.dataclasses.code_search import (
    FullTextHit,
    FullTextMatches,
    FullTextRow,
)
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ConfigurationError

# The fewest hits one search may ask for, and the fewest and most word
# tokens one snippet may hold.
FULLTEXT_MIN_HITS = 1
FULLTEXT_SNIPPET_MIN_TOKENS = 1
FULLTEXT_SNIPPET_MAX_TOKENS = 64


class FullTextIndex:
    """An in-memory FTS5 index of text rows grouped by source, searched by AND of quoted words."""

    def __init__(self) -> None:
        # @intent the-index-opens-nothing-until-first-use
        # The owner is built with its workspace, before anyone knows the
        # interpreter's SQLite has FTS5, so nothing is opened here and a
        # missing FTS5 fails only the first search, never the build.
        # @intent one-lock-guards-every-call-on-the-index
        # One index is shared by every agent of a tree and searched from
        # worker threads, so every method takes this reentrant lock, and
        # a caller holds it across a refresh and the search that
        # follows.
        self.lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        self._fingerprints: dict[str, str] = {}
        self._rowids: dict[str, range] = {}
        self._next_rowid = 1

    def fingerprint(self, source: str) -> str | None:
        """Return the fingerprint stored when the source's rows were last replaced, or None."""
        with self.lock:
            return self._fingerprints.get(source)

    def replace(self, source: str, fingerprint: str, rows: Sequence[FullTextRow]) -> None:
        """Swap every row stored for the source for the given rows, and store its new fingerprint."""
        with self.lock:
            # Open the table on first use, then drop the source's old
            # rows by the rowids they were given.
            connection = self._table()
            self._delete(connection, source)
            # Insert the new rows under consecutive rowids, so the
            # source's rows are one recorded range the next replace can
            # delete.
            first = self._next_rowid
            with connection:
                connection.executemany("insert into rows (rowid, source, label, body) values (?, ?, ?, ?)", [(first + offset, row.source, row.label, row.text) for offset, row in enumerate(rows)])
            self._next_rowid = first + len(rows)
            self._rowids[source] = range(first, self._next_rowid)
            self._fingerprints[source] = fingerprint

    def retain(self, sources: Collection[str]) -> None:
        """Drop the rows and fingerprint of every source not named."""
        with self.lock:
            dropped = [source for source in self._fingerprints if source not in sources]
            if not dropped:
                return
            connection = self._table()
            for source in dropped:
                self._delete(connection, source)
                del self._fingerprints[source]

    def search(self, words: Sequence[str], *, limit: int, snippet_tokens: int) -> FullTextMatches:
        """Return the best rows holding every word, best first, with a snippet of each, and the count of every match."""
        # Refuse sizes the query cannot honor before touching the table.
        # The shared validator checks them (no bool, no float), and a
        # bad size is the caller's ValueError, not a configuration
        # error.
        try:
            RecordFieldValidator.require_int(limit, "limit", minimum=FULLTEXT_MIN_HITS)
            RecordFieldValidator.require_int(snippet_tokens, "snippet_tokens", minimum=FULLTEXT_SNIPPET_MIN_TOKENS, maximum=FULLTEXT_SNIPPET_MAX_TOKENS)
        except ConfigurationError as exc:
            raise ValueError(exc.message) from exc
        # With no word there is nothing to match, so no MATCH runs.
        if not words:
            return FullTextMatches((), 0)
        with self.lock:
            # Open the table on first use, then match the AND of the
            # quoted words, best bm25 score first, and count every
            # matching row for the total line.
            connection = self._table()
            expression = FullTextIndex.match_expression(words)
            found = connection.execute("select label, snippet(rows, 2, '', '', '…', ?) from rows where rows match ? order by bm25(rows) limit ?", (snippet_tokens, expression, limit)).fetchall()
            (total,) = connection.execute("select count(*) from rows where rows match ?", (expression,)).fetchone()
        return FullTextMatches(tuple(FullTextHit(label, snippet) for label, snippet in found), total)

    @staticmethod
    def match_expression(words: Sequence[str]) -> str:
        """Return the MATCH expression for the AND of the words, each one quoted phrase."""
        # @intent every-query-word-is-one-quoted-phrase
        # Unquoted, a word such as price:59 is a column filter and NEAR(
        # or a lone quote is a syntax error; inside double quotes, with
        # its own quotes doubled, any text is only words to match.
        return " ".join('"' + word.replace('"', '""') + '"' for word in words)

    def _table(self) -> sqlite3.Connection:
        # Return the connection, opening it and creating the table on
        # first use; a SQLite without FTS5 fails here, named plainly.
        if self._connection is not None:
            return self._connection
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            connection.execute("create virtual table rows using fts5(source UNINDEXED, label UNINDEXED, body, tokenize='porter unicode61')")
        except sqlite3.Error as exc:
            connection.close()
            raise ConfigurationError(f"Full-text search needs SQLite's FTS5 extension, which this Python's SQLite {sqlite3.sqlite_version} does not provide ({exc}).", details={"sqlite_version": sqlite3.sqlite_version}) from exc
        self._connection = connection
        return connection

    def _delete(self, connection: sqlite3.Connection, source: str) -> None:
        # Delete one source's rows by the rowid range recorded for it;
        # FTS5 has no index on the source column to delete by.
        recorded = self._rowids.pop(source, range(0))
        if recorded:
            with connection:
                connection.execute("delete from rows where rowid >= ? and rowid < ?", (recorded.start, recorded.stop))


__all__ = [
    "FULLTEXT_MIN_HITS",
    "FULLTEXT_SNIPPET_MAX_TOKENS",
    "FULLTEXT_SNIPPET_MIN_TOKENS",
    "FullTextIndex",
]
