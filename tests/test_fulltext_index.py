"""FILE: tests/test_fulltext_index.py

PURPOSE: Proves the canonical full-text helper of spec infinite-memory-context-economy item 8, FullTextIndex in vidbyte/lib/util/fulltext.py, and its records: quoting that makes any word safe, AND matching with porter stemming and no letter case, bm25 order, the hit limit and total count, the snippet cap, per-source replace and retain, the lazy table, the FTS5-missing refusal, the reentrant lock, and use from a worker thread.
ROLE IN CODEBASE: Root-level test of a vidbyte/lib/ helper over real stdlib sqlite3 with FTS5 (spec section 13: prior art tests/test_folder_usage.py). Also provides without_fts5(), which the InfiniteMemory pack imports to simulate an interpreter without FTS5 at the one seam spec section 13 allows: the helper's first table creation.
ARCHITECTURE NOTE: Nothing is mocked except, in the FTS5-missing tests, sqlite3.connect, which is wrapped so the real connection refuses any statement naming fts5 with the OperationalError a build without FTS5 raises ("no such module: fts5"). FTS5 tests are never skipped (spec A-1): a CI interpreter without FTS5 must fail them loudly.
FUNCTION INVENTORY: without_fts5 (context manager) with _RefuseFts5 (connection and cursor proxy); FullTextQueryTests (INV-8.2, INV-8.3, INV-8.6, EC-8.1); FullTextRefreshTests (INV-8.4 at helper level, section 9.1 refresh); FullTextLifecycleTests (FR-8.3, FR-8.4, INV-8.7 at helper level, INV-8.9 lock and threads); FullTextRecordTests (section 9.1 records).
COMMON MODIFICATION PATTERNS: Add a query case as rows plus one search() call; compare labels and totals, never raw SQL.
WHAT NOT TO DO IN THIS FILE: 1. Do not skip a test when FTS5 is missing. 2. Do not reach into the helper's private connection or tables; use its public methods. 3. Do not pass words without a letter or digit to search(); the tool drops them before the index sees them (INV-8.2, EC-8.7).
KNOWN EDGE CASES: bm25 ties have no defined order, so ranking cases use rows whose scores differ. The snippet cap is counted in word tokens; the ellipsis FTS5 adds is not a word.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-8.x), 8.5, 9.1, 12.3 rows 11-13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_fulltext_index.py -q
"""

from __future__ import annotations

import re
import sqlite3
import threading
import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from vidbyte.lib.errors import ConfigurationError

ROWS_A = (("notes/a.md", "notes/a.md:1", "Zeta lists Enterprise at 999 USD"), ("notes/a.md", "notes/a.md:2", "Enterprise enterprise enterprise plan"))
ROWS_B = (("notes/b.md", "notes/b.md:1", "Globex lists Team at 59 USD"),)


class _RefuseFts5:
    """A real sqlite3 connection or cursor that refuses every statement naming fts5, as an interpreter built without FTS5 does."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @staticmethod
    def _check(sql: object) -> None:
        if "fts5" in str(sql).lower():
            raise sqlite3.OperationalError("no such module: fts5")

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        self._check(sql)
        outcome = self._inner.execute(sql, *args, **kwargs)
        return self if outcome is self._inner else outcome

    def executemany(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        self._check(sql)
        return self._inner.executemany(sql, *args, **kwargs)

    def executescript(self, sql: str) -> Any:
        self._check(sql)
        return self._inner.executescript(sql)

    def cursor(self, *args: Any, **kwargs: Any) -> _RefuseFts5:
        return _RefuseFts5(self._inner.cursor(*args, **kwargs))

    def __iter__(self) -> Iterator[Any]:
        return iter(self._inner)

    def __enter__(self) -> _RefuseFts5:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._inner.__exit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@contextmanager
def without_fts5() -> Iterator[list[tuple[Any, ...]]]:
    """While active, every sqlite3 connection refuses FTS5 statements; yields the list of connect() calls made."""
    import vidbyte.lib.util.fulltext as fulltext

    real_connect = sqlite3.connect
    calls: list[tuple[Any, ...]] = []

    def connect(*args: Any, **kwargs: Any) -> _RefuseFts5:
        calls.append(args)
        return _RefuseFts5(real_connect(*args, **kwargs))

    with ExitStack() as stack:
        stack.enter_context(patch.object(sqlite3, "connect", connect))
        # A helper that imported connect by name is covered too.
        if hasattr(fulltext, "connect"):
            stack.enter_context(patch.object(fulltext, "connect", connect))
        yield calls


def _index(*groups: tuple[tuple[str, str, str], ...]) -> Any:
    # A fresh index holding each group of rows under its source, fingerprinted "f1".
    from vidbyte.lib.dataclasses.code_search import FullTextRow
    from vidbyte.lib.util.fulltext import FullTextIndex

    index = FullTextIndex()
    for rows in groups:
        index.replace(rows[0][0], "f1", [FullTextRow(*row) for row in rows])
    return index


def _labels(matches: Any) -> list[str]:
    return [hit.label for hit in matches.hits]


class FullTextQueryTests(unittest.TestCase):
    def test_match_expression_quotes_each_word_and_doubles_inner_quotes(self) -> None:
        # INV-8.2, EC-8.1: every word becomes one quoted phrase, so no word is an operator or a column filter.
        from vidbyte.lib.util.fulltext import FullTextIndex

        self.assertEqual(FullTextIndex.match_expression(["w1", "w2"]), '"w1" "w2"')
        self.assertEqual(FullTextIndex.match_expression(["price:59"]), '"price:59"')
        self.assertEqual(FullTextIndex.match_expression(['say"hi']), '"say""hi"')
        self.assertEqual(FullTextIndex.match_expression(["NEAR(a", "b)", "-c", "OR"]), '"NEAR(a" "b)" "-c" "OR"')

    def test_search_ands_the_words_stems_them_ignores_case_and_ranks_best_first(self) -> None:
        # INV-8.2, INV-8.3, D-11: porter stemming and unicode61 case folding, AND across words, bm25 best first, total counted.
        index = _index(ROWS_A, ROWS_B)
        both = index.search(["enterprise"], limit=10, snippet_tokens=12)
        self.assertEqual(_labels(both), ["notes/a.md:2", "notes/a.md:1"])
        self.assertEqual(both.total, 2)
        self.assertEqual(_labels(index.search(["enterprise", "zeta"], limit=10, snippet_tokens=12)), ["notes/a.md:1"])
        self.assertEqual(_labels(index.search(["ZETA"], limit=10, snippet_tokens=12)), ["notes/a.md:1"])
        listing = index.search(["listing"], limit=10, snippet_tokens=12)
        self.assertEqual(sorted(_labels(listing)), ["notes/a.md:1", "notes/b.md:1"])
        none = index.search(["enterprise", "globex"], limit=10, snippet_tokens=12)
        self.assertEqual((none.hits, none.total), ((), 0))

    def test_operator_and_column_syntax_inside_words_never_raises(self) -> None:
        # AC-8.2 at helper level, EC-8.1: FTS5 syntax in a word is searched as text, alone or together.
        index = _index(ROWS_A, ROWS_B)
        hostile = ["price:59", "NEAR(a", "b)", "-c", "AND", "OR", "NOT", "^start", "col:val", 'say"hi', "x*", "{rows}"]
        for word in hostile:
            with self.subTest(word=word):
                self.assertGreaterEqual(index.search([word], limit=10, snippet_tokens=12).total, 0)
        self.assertEqual(index.search(hostile, limit=10, snippet_tokens=12).total, 0)
        self.assertEqual(_labels(index.search(["USD", "59"], limit=10, snippet_tokens=12)), ["notes/b.md:1"])

    def test_the_limit_caps_the_hits_while_the_total_counts_every_match(self) -> None:
        # INV-8.3, AC-8.5 at helper level: 30 matching rows, limit 10.
        rows = tuple(("notes/k.md", f"notes/k.md:{n}", f"kappa row number {n} " + "filler " * n) for n in range(1, 31))
        matches = _index(rows).search(["kappa"], limit=10, snippet_tokens=12)
        self.assertEqual((len(matches.hits), matches.total), (10, 30))

    def test_a_snippet_holds_at_most_the_requested_tokens(self) -> None:
        # INV-8.6: snippet() is asked for snippet_tokens tokens; a 120-word row is cut to that many word tokens.
        from vidbyte.lib.util.fulltext import FULLTEXT_SNIPPET_MAX_TOKENS

        words = [f"word{n}" for n in range(120)]
        words[60] = "needle"
        index = _index((("notes/long.md", "notes/long.md:1", " ".join(words)),))
        for tokens in (1, 12, FULLTEXT_SNIPPET_MAX_TOKENS):
            with self.subTest(snippet_tokens=tokens):
                [hit] = index.search(["needle"], limit=1, snippet_tokens=tokens).hits
                counted = re.findall(r"\w+", hit.snippet)
                self.assertLessEqual(len(counted), tokens)
                self.assertIn("needle", counted)
        self.assertGreater(len(re.findall(r"\w+", index.search(["needle"], limit=1, snippet_tokens=FULLTEXT_SNIPPET_MAX_TOKENS).hits[0].snippet)), 12)

    def test_search_refuses_a_bad_limit_or_snippet_size(self) -> None:
        # INV-8.6, row 12: limit below 1 and snippet_tokens outside 1..FULLTEXT_SNIPPET_MAX_TOKENS are ValueErrors; bools and floats too.
        from vidbyte.lib.util.fulltext import FULLTEXT_SNIPPET_MAX_TOKENS

        index = _index(ROWS_A)
        for limit in (0, -1, True, 2.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    index.search(["zeta"], limit=limit, snippet_tokens=12)
        for tokens in (0, FULLTEXT_SNIPPET_MAX_TOKENS + 1, True, 1.5):
            with self.subTest(snippet_tokens=tokens):
                with self.assertRaises(ValueError):
                    index.search(["zeta"], limit=1, snippet_tokens=tokens)
        self.assertEqual(FULLTEXT_SNIPPET_MAX_TOKENS, 64)


class FullTextRefreshTests(unittest.TestCase):
    def test_replace_swaps_a_sources_rows_and_retain_drops_the_others(self) -> None:
        # Section 9.1 refresh: replace() keeps one fingerprint and one row set per source; retain() forgets every other source.
        from vidbyte.lib.dataclasses.code_search import FullTextRow

        index = _index(ROWS_A, ROWS_B)
        self.assertEqual((index.fingerprint("notes/a.md"), index.fingerprint("notes/b.md"), index.fingerprint("notes/c.md")), ("f1", "f1", None))
        index.replace("notes/a.md", "f2", [FullTextRow("notes/a.md", "notes/a.md:1", "Omicron replaced the old text")])
        self.assertEqual(index.fingerprint("notes/a.md"), "f2")
        self.assertEqual(index.search(["zeta"], limit=10, snippet_tokens=12).total, 0)
        self.assertEqual(_labels(index.search(["omicron"], limit=10, snippet_tokens=12)), ["notes/a.md:1"])
        index.retain(["notes/b.md"])
        self.assertIsNone(index.fingerprint("notes/a.md"))
        self.assertEqual(index.search(["omicron"], limit=10, snippet_tokens=12).total, 0)
        self.assertEqual(_labels(index.search(["globex"], limit=10, snippet_tokens=12)), ["notes/b.md:1"])
        index.replace("notes/b.md", "f3", [])
        self.assertEqual((index.fingerprint("notes/b.md"), index.search(["globex"], limit=10, snippet_tokens=12).total), ("f3", 0))


class FullTextLifecycleTests(unittest.TestCase):
    def test_full_text_index_is_exported_from_lib_util(self) -> None:
        # FR-8.3: the canonical helper is importable from vidbyte.lib.util.
        import vidbyte.lib.util as util
        from vidbyte.lib.util.fulltext import FullTextIndex

        self.assertIs(util.FullTextIndex, FullTextIndex)
        self.assertIn("FullTextIndex", util.__all__)

    def test_construction_opens_nothing_and_a_missing_fts5_fails_at_first_use(self) -> None:
        # FR-8.4, INV-8.7 at helper level: building the index never touches sqlite; the first use names FTS5 and the SQLite version.
        from vidbyte.lib.dataclasses.code_search import FullTextRow
        from vidbyte.lib.util.fulltext import FullTextIndex

        with without_fts5() as calls:
            index = FullTextIndex()
            self.assertEqual(calls, [], "FullTextIndex() opened a connection")
            for use in (lambda: index.search(["zeta"], limit=1, snippet_tokens=12), lambda: index.replace("notes/a.md", "f1", [FullTextRow("notes/a.md", "notes/a.md:1", "Zeta")])):
                with self.assertRaises(ConfigurationError) as caught:
                    use()
                text = str(caught.exception)
                self.assertIn("fts5", text.lower())
                self.assertIn(sqlite3.sqlite_version, text)
        self.assertEqual(_index(ROWS_A).search(["zeta"], limit=1, snippet_tokens=12).total, 1, "a new index outside the simulation works")

    def test_the_lock_is_a_reentrant_lock_a_caller_can_hold_across_calls(self) -> None:
        # INV-8.9, row 12: the public lock is an RLock, so a caller holding it can still call every method.
        index = _index(ROWS_A)
        self.assertIsInstance(index.lock, type(threading.RLock()))
        outcome: list[int] = []

        def search_holding_the_lock() -> None:
            with index.lock:
                index.fingerprint("notes/a.md")
                outcome.append(index.search(["zeta"], limit=1, snippet_tokens=12).total)

        worker = threading.Thread(target=search_holding_the_lock)
        worker.start()
        worker.join(timeout=30)
        self.assertFalse(worker.is_alive(), "a method blocked while its caller held the index lock")
        self.assertEqual(outcome, [1])

    def test_an_index_built_on_one_thread_is_searched_from_another(self) -> None:
        # INV-8.9, row 12: the connection allows cross-thread use, because each search runs in a worker thread.
        index = _index(ROWS_A)
        errors: list[BaseException] = []
        totals: list[int] = []

        def search() -> None:
            try:
                totals.append(index.search(["enterprise"], limit=10, snippet_tokens=12).total)
            except BaseException as exc:  # recorded and re-raised by the assertion below
                errors.append(exc)

        workers = [threading.Thread(target=search) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(totals, [2, 2, 2, 2])


class FullTextRecordTests(unittest.TestCase):
    def test_records_validate_their_fields(self) -> None:
        # Section 9.1: FullTextRow needs a non-blank source and label; FullTextMatches.total is an int at least len(hits).
        from vidbyte.lib.dataclasses.code_search import FullTextHit, FullTextMatches, FullTextRow

        for fields, name in (((" ", "notes/a.md:1", "text"), "source"), (("notes/a.md", "", "text"), "label"), (("notes/a.md", "\t", "text"), "label")):
            with self.subTest(fields=fields):
                with self.assertRaises(ConfigurationError) as caught:
                    FullTextRow(*fields)
                self.assertIn(name, str(caught.exception) + str(getattr(caught.exception, "details", "")))
        FullTextRow("notes/a.md", "notes/a.md:1", "")
        hit = FullTextHit("notes/a.md:1", "Zeta lists")
        for total in (0, -1, True, 1.0):
            with self.subTest(total=total):
                with self.assertRaises(ConfigurationError):
                    FullTextMatches((hit,), total)
        self.assertEqual(FullTextMatches((hit,), 5).total, 5)
        self.assertEqual(FullTextMatches((), 0).hits, ())


if __name__ == "__main__":
    unittest.main()
