"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_search.py

PURPOSE: Proves item 8 of spec infinite-memory-context-economy at the tool and agent level: search_memory's model-facing contract, ranked entry and note-line hits with a total line, safe quoting of any query, a refresh that sees bash writes, edits, and deletes, the index's exclusions, the FTS5-missing error that leaves the agent working, the hit and snippet caps, a read-only tool, one shared index per workspace searched in a worker thread under its lock, and the reserved name.
ROLE IN CODEBASE: Search layer of tests/features/infinite_memory_agent/. Builds the tool the way every agent does, through InfiniteMemoryAgentTools.get_tools(..., index), over a real InfiniteWorkspace in tmp_path, and runs whole agents through ScriptedTree.
ARCHITECTURE NOTE: Nothing is mocked but the model (ScriptedTree) and, in the FTS5-missing tests, sqlite3.connect through tests/test_fulltext_index.py's without_fts5(), the helper's table-creation seam that spec section 13 allows. RecordingIndex subclasses FullTextIndex to record which thread called it and whether its lock was already held by the caller, probed from a third thread before the helper takes the lock itself; its lock is a CountingRLock, which counts outermost holds so one span across refresh and search is told apart from two.
FUNCTION INVENTORY: _workspace / _search_tool / _search build and call the tool; _counts reads the integers of the total line; _hit_lines splits the output; CountingRLock counts lock spans; RecordingIndex records threads and lock state. Tests: spec (FR-8.5, INV-8.1, INV-0.3); AC-8.1 ranking; AC-8.2 and EC-8.1 hostile queries; FR-8.6, EC-8.2, EC-8.7 blank and punctuation queries; AC-8.3 and INV-8.4 refresh (agent bash write, then edit and delete); INV-8.5 and EC-8.3 exclusions and line numbers; INV-8.8 malformed entries; AC-8.4 and INV-8.7 FTS5 missing (tool and agent); AC-8.5 and INV-8.6 caps; AC-8.6 stemming miss; INV-8.1 read-only; INV-8.9 worker thread and lock; AC-8.7 one index per tree; EC-10.5 and FR-8.7 the reserved name.
COMMON MODIFICATION PATTERNS: Add a query case as files written under the workspace plus one _search call; compare whole hit lines and the total line's integers.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level; the pack must collect before the feature exists. 2. Do not skip a test when FTS5 is missing (spec A-1). 3. Do not rely on a same-size rewrite within one timestamp tick (EC-8.5); every edit here changes the file size. 4. Do not pin the total line's wording; only its two counts are spec.
KNOWN EDGE CASES: bm25 ranks a shorter row above a longer one with the same matches, which the ranking case uses for a deterministic order. The snippet's ellipsis is not a word, so tokens are counted as \\w+ runs after the hit label.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-8.x), 6.2 (AC-8.x), 7 (EC-8.x), 8.5, 9.2 (search_memory), 12.3 rows 16-24.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_search.py -q
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    PASSED_REVIEW,
    ROOT,
    TASK,
    ScriptedTree,
    build_agent,
    build_settings,
    entry_record,
    generator,
    is_error,
    launch,
    observe,
    project_dir,
    reply,
    snapshot,
    task,
    tool_call,
    tool_result,
    tool_results,
    verifier,
    workspace_root,
    write_jsonl,
)
from tests.test_fulltext_index import without_fts5
from vidbyte import tool
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.types import ToolCall, ToolPermission, ToolStatus

ZETA_ENTRY = "Zeta lists Enterprise at 999 USD"
# A long line with both words once: bm25 ranks it below the short entry.
ZETA_NOTE_LINE = "Background: " + " ".join(f"filler{n}" for n in range(40)) + " zeta enterprise mention"


def _workspace(tmp_path: Path) -> Any:
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace

    return InfiniteWorkspace(InfiniteWorkspaceSettings(root=workspace_root(tmp_path)))


def _search_tool(workspace: Any, tmp_path: Path, index: Any = None) -> Any:
    # FR-8.1, row 18: get_tools returns bash, grep, read_lines, then search_memory over the given index (the workspace's by default).
    from vidbyte.lib.constants.infinite import INFINITE_DEFAULT_MAX_READ_LINES
    from vidbyte.tools.toolsets import InfiniteMemoryAgentTools

    tools = InfiniteMemoryAgentTools.get_tools(project_dir(tmp_path), workspace.root, workspace.settings.max_tokens, INFINITE_DEFAULT_MAX_READ_LINES, workspace.full_text if index is None else index)
    assert [item.spec().name for item in tools] == ["bash", "grep", "read_lines", "search_memory"]
    return tools[3]


def _search(search_tool: Any, query: object) -> Any:
    return asyncio.run(search_tool.execute(ToolCall("search_memory", {"query": query})))


def _counts(output: str) -> list[int]:
    # The integers the last line states: the shown count and the total count, in any order.
    return sorted(int(number) for number in re.findall(r"\d+", output.splitlines()[-1]))


def _hit_lines(output: str) -> list[str]:
    return output.splitlines()[:-1]


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _sentences(text: str) -> int:
    return len(re.findall(r"[.!?](?:\s|$)", text.strip()))


def test_search_memory_spec_is_read_only_with_one_query_parameter_and_literal_descriptions(tmp_path: Path) -> None:
    """FR-8.5, INV-8.1, INV-0.3, section 9.2: name search_memory, READ, one required string query, 4-5 sentences each, no number."""
    from vidbyte.lib.constants.infinite import INFINITE_SEARCH_MEMORY_TOOL_NAME

    spec = _search_tool(_workspace(tmp_path), tmp_path).spec()
    assert spec.name == INFINITE_SEARCH_MEMORY_TOOL_NAME == "search_memory"
    assert spec.permission is ToolPermission.READ
    # The schema the model receives, whether the spec declares typed parameters or an input schema.
    from vidbyte.lib.tools.formatter import ToolsFormatter

    schema = ToolsFormatter.input_schema(spec)
    properties = dict(schema.get("properties") or {})
    assert {name: str(value.get("type")) for name, value in properties.items()} == {"query": "string"}
    assert list(schema.get("required") or ()) == ["query"]
    for text in (spec.description, str(properties["query"].get("description", ""))):
        assert 4 <= _sentences(text) <= 5, text
        assert not re.search(r"\d", text), f"a search_memory description states a number: {text}"
    lowered = spec.description.lower()
    assert "total" in lowered and ("case" in lowered or "capital" in lowered), spec.description


def test_an_entry_hit_comes_first_as_id_and_kind_and_the_last_line_counts_shown_and_total(tmp_path: Path) -> None:
    """AC-8.1, INV-8.3: entry #7 ranks above a long note line holding the same words; the last line states 2 of 2."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    _write(workspace.root, "notes/background.md", f"Intro line\n{ZETA_NOTE_LINE}\n")
    result = _search(_search_tool(workspace, tmp_path), "enterprise zeta")
    assert result.status is ToolStatus.SUCCESS, result.output
    hits = _hit_lines(result.output)
    assert hits[0].startswith("#7 fact: ") and "Zeta" in hits[0], result.output
    assert hits[1].startswith("notes/background.md:2: "), result.output
    assert len(hits) == 2 and _counts(result.output) == [2, 2]
    assert result.metadata == {"hits": 2, "total": 2}


def test_fts5_syntax_in_a_query_is_searched_as_text_and_never_raises(tmp_path: Path) -> None:
    """AC-8.2, INV-8.2, EC-8.1: operators, column filters, quotes and a bare star are plain words."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    _write(workspace.root, "notes/prices.md", "Team price:59 per seat\n")
    search_tool = _search_tool(workspace, tmp_path)
    for query in ('price:59 "x" NEAR(a b) -c *', "price:59", "NEAR(a", "zeta OR acme", "NOT zeta", "body:zeta", '"unclosed', "zeta*", "^zeta"):
        result = _search(search_tool, query)
        assert result.status is ToolStatus.SUCCESS, (query, result.output)
        assert set(result.metadata) == {"hits", "total"}, query
    assert _hit_lines(_search(search_tool, "price:59").output) == ["notes/prices.md:1: Team price:59 per seat"]
    assert _search(search_tool, "zeta OR acme").metadata["total"] == 0, "OR must be a word to match, not an operator"


def test_a_blank_query_is_refused_and_a_punctuation_only_query_matches_nothing(tmp_path: Path) -> None:
    """FR-8.6, EC-8.2, EC-8.7, INV-8.2: blank is invalid_argument; words with no letter or digit are dropped before quoting, leaving 0 of 0."""
    from vidbyte.lib.util import FullTextIndex

    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    search_tool = _search_tool(workspace, tmp_path)
    for blank in ("", "   ", "\n\t"):
        refused = _search(search_tool, blank)
        assert refused.status is ToolStatus.ERROR and refused.metadata.get("error") == "invalid_argument", repr(blank)
    # SQLite 3.38 matches nothing for an empty quoted phrase, so the results alone cannot show the drop (EC-8.7 forbids relying on that).
    # Record every expression the real match_expression builds, unchanged, and read its quoted phrases.
    real_match = FullTextIndex.match_expression
    expressions: list[str] = []

    def recording_match(words: Any) -> str:
        expression = real_match(words)
        expressions.append(expression)
        return expression

    with patch.object(FullTextIndex, "match_expression", staticmethod(recording_match)):
        for punctuation in ("...", "-- ... *", '" "'):
            empty = _search(search_tool, punctuation)
            assert empty.status is ToolStatus.SUCCESS, (punctuation, empty.output)
            assert empty.metadata == {"hits": 0, "total": 0} and len(empty.output.splitlines()) == 1 and _counts(empty.output) == [0, 0]
        assert _search(search_tool, "... zeta --").metadata == {"hits": 1, "total": 1}
    phrases = [re.findall(r'"((?:[^"]|"")*)"', expression) for expression in expressions]
    assert phrases and phrases[-1] == ["zeta"], expressions
    assert all(any(character.isalnum() for character in phrase) for group in phrases for phrase in group), f"a word with no letter or digit was quoted: {expressions}"


def test_a_note_bash_writes_after_a_search_is_found_by_the_next_search(tmp_path: Path) -> None:
    """AC-8.3, INV-8.4: the root searches, bash writes a note into the workspace, and the next search finds its line."""
    agent = build_agent(tmp_path)
    command = "mkdir -p memory/notes && printf 'Omicron charges 77 USD\\n' > memory/notes/fresh.md"
    tree = ScriptedTree({ROOT: [tool_call("search_memory", {"query": "omicron"}), tool_call("bash", {"command": command}), tool_call("search_memory", {"query": "omicron"}), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    searches = [content for name, content in tool_results(tree.calls_by(ROOT)[-1]) if name == "search_memory"]
    assert len(searches) == 2 and not any(is_error(text) for text in searches), searches
    assert _counts(searches[0]) == [0, 0]
    assert _hit_lines(searches[1]) == ["notes/fresh.md:1: Omicron charges 77 USD"], searches[1]


def test_an_edited_or_deleted_file_is_searched_as_it_now_is(tmp_path: Path) -> None:
    """INV-8.4: a rewrite (new size) and a delete are seen by the next search; a new file too."""
    workspace = _workspace(tmp_path)
    note = _write(workspace.root, "notes/plans.md", "Sigma plan 49 USD\n")
    search_tool = _search_tool(workspace, tmp_path)
    assert _hit_lines(_search(search_tool, "sigma").output) == ["notes/plans.md:1: Sigma plan 49 USD"]
    note.write_text("Sigma plan now costs 129 USD\n", encoding="utf-8", newline="\n")
    assert _hit_lines(_search(search_tool, "sigma").output) == ["notes/plans.md:1: Sigma plan now costs 129 USD"]
    _write(workspace.root, "notes/other.md", "Another sigma mention here\n")
    assert _counts(_search(search_tool, "sigma").output) == [2, 2]
    note.unlink()
    assert _hit_lines(_search(search_tool, "sigma").output) == ["notes/other.md:1: Another sigma mention here"]
    assert _counts(_search(search_tool, "costs").output) == [0, 0]


def test_the_index_holds_live_entry_text_and_numbered_note_lines_and_nothing_else(tmp_path: Path) -> None:
    """INV-8.5, EC-8.3: .runs, superseded.jsonl, files.jsonl, oversize and NUL files are left out; lines keep grep's numbers; entries are their text only."""
    from vidbyte.lib.util import FullTextIndex
    from vidbyte.tools.builtins.code_search import InfiniteSearchMemoryTool

    workspace = _workspace(tmp_path)
    root = workspace.root
    write_jsonl(root / "entries.jsonl", [entry_record(7, ZETA_ENTRY, tags=("tagword",))])
    write_jsonl(root / "superseded.jsonl", [entry_record(3, "Superword old price 10 USD")])
    write_jsonl(root / "files.jsonl", [{"path": "notes/a.md", "description": "Descword pricing notes", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"}])
    _write(root, ".runs/20261015T024900Z-1a2b3c4d.jsonl", '{"event": "run_started", "task": "Journalword task"}\n')
    _write(root, "notes/a.md", "first line\n\nkappa on line three\n")
    _write(root, "notes/big.md", "Bigword " + "x" * 1_200 + "\n")
    (root / "notes" / "binary.md").write_bytes(b"Nulword start\x00binary\n")
    search_tool = InfiniteSearchMemoryTool(root, index=FullTextIndex(), max_file_bytes=1_000)
    assert _hit_lines(_search(search_tool, "kappa").output) == ["notes/a.md:3: kappa on line three"]
    assert _hit_lines(_search(search_tool, "zeta").output)[0].startswith("#7 fact: ")
    for absent in ("superword", "descword", "journalword", "bigword", "nulword", "verified_by", "tagword", "20261015T024900Z"):
        assert _search(search_tool, absent).metadata == {"hits": 0, "total": 0}, absent


def test_a_malformed_entry_line_is_left_out_and_never_fails_a_search(tmp_path: Path) -> None:
    """INV-8.8: one broken line between two entries; both entries are still found and the search succeeds."""
    workspace = _workspace(tmp_path)
    good = [entry_record(1, "Alpha lists Basic at 49 USD"), entry_record(2, "Beta lists Basic at 59 USD")]
    import json

    (workspace.root / "entries.jsonl").write_text(json.dumps(good[0]) + "\n{not json Basic\n" + json.dumps(good[1]) + "\n", encoding="utf-8", newline="\n")
    result = _search(_search_tool(workspace, tmp_path), "basic")
    assert result.status is ToolStatus.SUCCESS, result.output
    assert sorted(line.split(":")[0] for line in _hit_lines(result.output)) == ["#1 fact", "#2 fact"]
    assert result.metadata == {"hits": 2, "total": 2}


def test_without_fts5_the_tool_returns_fts5_unavailable_naming_fts5_and_the_version(tmp_path: Path) -> None:
    """AC-8.4, INV-8.7, FR-8.4: building the workspace and the tool succeeds; the call is an error result, not an exception."""
    import sqlite3

    with without_fts5():
        workspace = _workspace(tmp_path)
        _write(workspace.root, "notes/a.md", "kappa line\n")
        result = _search(_search_tool(workspace, tmp_path), "kappa")
    assert result.status is ToolStatus.ERROR
    assert result.metadata == {"error": "fts5_unavailable"}
    assert "fts5" in result.output.lower() and sqlite3.sqlite_version in result.output


def test_without_fts5_the_agent_still_runs_and_grep_still_works(tmp_path: Path) -> None:
    """AC-8.4, INV-8.7: the root's search_memory call errors, its grep finds the note, and the run finishes."""
    _write(workspace_root(tmp_path), "notes/a.md", "kappa pricing line\n")
    with without_fts5():
        agent = build_agent(tmp_path)
        tree = ScriptedTree({ROOT: [tool_call("search_memory", {"query": "kappa"}), tool_call("grep", {"pattern": "kappa"}), reply("done")]})
        with tree.install():
            answer = agent.run(TASK)
    tree.assert_complete()
    assert answer.content == "done"
    last = tree.calls_by(ROOT)[-1]
    assert is_error(tool_result(last, "search_memory")) and "fts5" in tool_result(last, "search_memory").lower()
    assert tool_result(last, "grep") == "notes/a.md:1\n1: kappa pricing line"


def test_at_most_ten_hits_are_shown_with_snippets_of_at_most_twelve_tokens(tmp_path: Path) -> None:
    """AC-8.5, INV-8.3, INV-8.6: 30 matching long lines give INFINITE_SEARCH_MAX_HITS hit lines and the total line."""
    from vidbyte.lib.constants.infinite import INFINITE_SEARCH_MAX_HITS, INFINITE_SEARCH_SNIPPET_TOKENS

    workspace = _workspace(tmp_path)
    lines = [" ".join(f"word{row}x{n}" for n in range(15)) + f" lambda " + " ".join(f"tail{row}x{n}" for n in range(15)) for row in range(30)]
    _write(workspace.root, "notes/long.md", "\n".join(lines) + "\n")
    result = _search(_search_tool(workspace, tmp_path), "lambda")
    hits = _hit_lines(result.output)
    assert len(hits) == INFINITE_SEARCH_MAX_HITS == 10
    assert _counts(result.output) == [10, 30] and result.metadata == {"hits": 10, "total": 30}
    for hit in hits:
        label, snippet = re.match(r"(notes/long\.md:\d+): (.*)", hit).groups()
        assert len(re.findall(r"\w+", snippet)) <= INFINITE_SEARCH_SNIPPET_TOKENS == 12, hit
        assert "lambda" in snippet


def test_a_word_no_row_holds_gives_only_the_total_line_with_zero_of_zero(tmp_path: Path) -> None:
    """AC-8.6, INV-8.2: "pricing" stems to "price", which no row holds, so the AND of the three words matches nothing."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    result = _search(_search_tool(workspace, tmp_path), "enterprise pricing zeta")
    assert result.status is ToolStatus.SUCCESS
    assert len(result.output.splitlines()) == 1 and _counts(result.output) == [0, 0]
    assert result.metadata == {"hits": 0, "total": 0}


def test_search_memory_never_writes_the_workspace(tmp_path: Path) -> None:
    """INV-8.1: every byte under the workspace, journals included, is the same after several searches."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    _write(workspace.root, "notes/a.md", "kappa line\n")
    before = snapshot(workspace.root, include_runs=True)
    search_tool = _search_tool(workspace, tmp_path)
    for query in ("kappa", "zeta", "nothing here", "..."):
        _search(search_tool, query)
    assert snapshot(workspace.root, include_runs=True) == before


class CountingRLock:
    """A real re-entrant lock that counts its outermost acquisitions, so one span held across refresh and search (1) differs from two spans (2)."""

    def __init__(self) -> None:
        self.inner = threading.RLock()
        self.outermost = 0
        self._depth = 0

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        got = self.inner.acquire(blocking, timeout)
        if got:
            # Only the owning thread changes the depth, and only while it holds the inner lock.
            self._depth += 1
            if self._depth == 1:
                self.outermost += 1
        return got

    def release(self) -> None:
        self._depth -= 1
        self.inner.release()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()


class RecordingIndex:
    """Built lazily as a FullTextIndex subclass: records the calling thread and whether the caller already held the lock, which counts its spans."""

    @staticmethod
    def build() -> Any:
        from vidbyte.lib.util import FullTextIndex

        class Recording(FullTextIndex):
            def __init__(self) -> None:
                super().__init__()
                self.lock = CountingRLock()
                self.seen: list[tuple[str, int, bool]] = []

            def _note(self, method: str) -> None:
                # Probe from a third thread, before the helper takes the lock itself: a held lock means the caller holds it.
                # The probe uses the inner lock, so it never adds to the span count.
                free: list[bool] = []

                def probe() -> None:
                    got = self.lock.inner.acquire(blocking=False)
                    if got:
                        self.lock.inner.release()
                    free.append(got)

                prober = threading.Thread(target=probe)
                prober.start()
                prober.join(timeout=10)
                self.seen.append((method, threading.get_ident(), not free[0]))

            def fingerprint(self, source: str) -> str | None:
                self._note("fingerprint")
                return super().fingerprint(source)

            def replace(self, source: str, fingerprint: str, rows: Any) -> None:
                self._note("replace")
                super().replace(source, fingerprint, rows)

            def retain(self, sources: Any) -> None:
                self._note("retain")
                super().retain(sources)

            def search(self, words: Any, *, limit: int, snippet_tokens: int) -> Any:
                self._note("search")
                return super().search(words, limit=limit, snippet_tokens=snippet_tokens)

        return Recording()


def test_a_search_refreshes_and_searches_in_a_worker_thread_holding_the_index_lock(tmp_path: Path) -> None:
    """INV-8.9, EC-8.4: every index call of one search_memory call runs off the event loop's thread, with the lock already held by the tool."""
    workspace = _workspace(tmp_path)
    _write(workspace.root, "notes/a.md", "kappa line\n")
    index = RecordingIndex.build()
    search_tool = _search_tool(workspace, tmp_path, index=index)
    loop_threads: list[int] = []

    async def call() -> Any:
        loop_threads.append(threading.get_ident())
        return await search_tool.execute(ToolCall("search_memory", {"query": "kappa"}))

    spans_before = index.lock.outermost
    result = asyncio.run(call())
    assert result.metadata == {"hits": 1, "total": 1}
    methods = [method for method, _, _ in index.seen]
    assert "search" in methods and "replace" in methods, methods
    for method, thread, held in index.seen:
        assert thread != loop_threads[0], f"{method} ran on the event loop's thread"
        assert held, f"{method} ran without the tool holding index.lock"
    # A worker pool reuses its thread, so one thread id alone cannot show one held span; the lock's own count can.
    assert index.lock.outermost - spans_before == 1, "the refresh and the search must run under one hold of index.lock, not one hold each"


def test_one_index_serves_the_whole_tree_and_every_search_sees_the_disk_at_call_time(tmp_path: Path) -> None:
    """AC-8.7, INV-8.9: FullTextIndex is built once (counted at the class) while the root, a generator and its verifier each search."""
    from vidbyte.lib.util import FullTextIndex

    built: list[object] = []
    real_init = FullTextIndex.__init__

    def counting_init(self: Any) -> None:
        built.append(self)
        real_init(self)

    root = workspace_root(tmp_path)
    _write(root, "notes/root.md", "kappa root line\n")

    def generator_writes(_: object) -> None:
        _write(root, "notes/gen.md", "kappa generator line\n")

    def verifier_swaps(_: object) -> None:
        (root / "notes" / "gen.md").unlink()
        _write(root, "notes/ver.md", "kappa verifier line\n")

    def root_cleans(_: object) -> None:
        shutil.rmtree(root / "notes")

    with patch.object(FullTextIndex, "__init__", counting_init):
        agent = build_agent(tmp_path)
        tree = ScriptedTree(
            {
                ROOT: [tool_call("search_memory", {"query": "kappa"}), launch(task("alpha")), observe(root_cleans, tool_call("search_memory", {"query": "kappa"})), reply("done")],
                generator("alpha"): [observe(generator_writes, tool_call("search_memory", {"query": "kappa"})), reply("ALPHA-SUMMARY")],
                verifier("alpha"): [observe(verifier_swaps, tool_call("search_memory", {"query": "kappa"})), reply(PASSED_REVIEW)],
            }
        )
        with tree.install():
            agent.run(TASK)
    tree.assert_complete()
    assert len(built) == 1, f"FullTextIndex was built {len(built)} times for one workspace"
    assert built[0] is agent.workspace.full_text
    root_searches = [content for name, content in tool_results(tree.calls_by(ROOT)[-1]) if name == "search_memory"]
    assert _hit_lines(root_searches[0]) == ["notes/root.md:1: kappa root line"]
    assert _counts(root_searches[1]) == [0, 0]
    generator_hits = sorted(_hit_lines(tool_result(tree.calls_by(generator("alpha"))[-1], "search_memory")))
    assert generator_hits == ["notes/gen.md:1: kappa generator line", "notes/root.md:1: kappa root line"]
    verifier_hits = sorted(_hit_lines(tool_result(tree.calls_by(verifier("alpha"))[-1], "search_memory")))
    assert verifier_hits == ["notes/root.md:1: kappa root line", "notes/ver.md:1: kappa verifier line"]


@tool(name="search_memory")
def developer_search_memory(query: str) -> str:
    """A developer tool that reuses the reserved name."""
    return query


def test_a_developer_tool_named_search_memory_is_refused(tmp_path: Path) -> None:
    """EC-10.5, FR-8.7: search_memory joins INFINITE_RESERVED_TOOL_NAMES, so settings refuse a tool with that name."""
    from vidbyte.lib.constants.infinite import INFINITE_RESERVED_TOOL_NAMES, INFINITE_SEARCH_MEMORY_TOOL_NAME

    assert INFINITE_SEARCH_MEMORY_TOOL_NAME in INFINITE_RESERVED_TOOL_NAMES
    with pytest.raises(ConfigurationError) as caught:
        build_settings(tmp_path, tools=(developer_search_memory,))
    assert "search_memory" in str(caught.value)


# -------- S5: text UTF-8 cannot encode (EC-8.8)

# A note name UTF-8 cannot encode on both CI hosts: a lone surrogate on
# Windows, and the byte 0xFF on Linux, which Python lists back as
# \udcff through surrogateescape.
UNENCODABLE_NAME = "bad\udcff.md"


def test_a_query_holding_a_nul_or_a_lone_surrogate_gives_the_result_of_its_clean_words(tmp_path: Path) -> None:
    """INV-8.2, EC-8.8, T-1 (review R-2, R-8): a NUL reads as a space and a lone surrogate is removed, so each query returns exactly what its clean twin returns; a query of NULs or surrogates alone is 0 of 0, not invalid_argument."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(7, ZETA_ENTRY), entry_record(8, "Alpha beta gamma pricing")])
    _write(workspace.root, "notes/prices.md", "Zeta price sheet\n")
    search_tool = _search_tool(workspace, tmp_path)
    # "ze\ud800ta" pins removal: a surrogate read as a space would
    # search "ze" and "ta" and match nothing.
    twins = (("alpha\x00beta", "alpha beta"), ("zeta\x00", "zeta"), ("\ud800zeta", "zeta"), ("ze\ud800ta", "zeta"), ("zeta \udcff", "zeta"))
    for dirty, clean in twins:
        expected = _search(search_tool, clean)
        assert expected.metadata["total"] > 0, f"precondition: the clean twin {clean!r} matches"
        result = _search(search_tool, dirty)
        assert result.status is ToolStatus.SUCCESS, (ascii(dirty), result.output)
        assert (result.output, result.metadata) == (expected.output, expected.metadata), ascii(dirty)
    for nothing in ("\x00", "\x00 \x00\x00", "\ud800", "\udcff \x00"):
        empty = _search(search_tool, nothing)
        assert empty.status is ToolStatus.SUCCESS, (ascii(nothing), empty.output)
        assert empty.metadata == {"hits": 0, "total": 0} and _counts(empty.output) == [0, 0], ascii(nothing)


def test_an_entry_line_holding_a_lone_surrogate_is_left_out_and_every_later_search_still_works(tmp_path: Path) -> None:
    """INV-8.8, EC-8.8, INV-8.5 (review R-2, R-8): lines whose text or kind hold an escaped lone surrogate are skipped as malformed; the other entries and a note are found on the next search, the one after it, and from a fresh index."""
    from vidbyte.lib.util import FullTextIndex

    workspace = _workspace(tmp_path)
    entries = workspace.root / "entries.jsonl"
    alpha, omega = entry_record(1, "Alpha lists Basic at 49 USD"), entry_record(4, "Omega lists Basic at 89 USD")
    write_jsonl(entries, [alpha])
    _write(workspace.root, "notes/plans.md", "Gamma plan costs 79 USD\n")
    search_tool = _search_tool(workspace, tmp_path)
    # Build the index from clean files first: the bad lines then arrive
    # through the refresh, the path that left every later search
    # failing.
    assert _hit_lines(_search(search_tool, "alpha").output) == ["#1 fact: Alpha lists Basic at 49 USD"]
    # Valid JSON as bash can write it: json.dumps escapes each lone
    # surrogate as \ud800. The workspace itself refuses such text.
    bad_text = entry_record(2, "Delta lists Basic at 59 USD \ud800")
    bad_kind = entry_record(3, "Epsilon lists Basic at 69 USD", kind="fa\ud800ct")
    write_jsonl(entries, [alpha, bad_text, bad_kind, omega])
    assert entries.read_text(encoding="utf-8").count("\\ud800") == 2, "precondition: both bad lines are on disk as JSON escapes"
    expected_basic = ["#1 fact: Alpha lists Basic at 49 USD", "#4 fact: Omega lists Basic at 89 USD"]
    for attempt in ("first", "second"):
        basic = _search(search_tool, "basic")
        assert basic.status is ToolStatus.SUCCESS, (attempt, basic.output)
        assert sorted(_hit_lines(basic.output)) == expected_basic and basic.metadata == {"hits": 2, "total": 2}, (attempt, basic.output)
        assert _hit_lines(_search(search_tool, "gamma").output) == ["notes/plans.md:1: Gamma plan costs 79 USD"], attempt
        for left_out in ("delta", "epsilon"):
            assert _search(search_tool, left_out).metadata == {"hits": 0, "total": 0}, (attempt, left_out)
    fresh = _search(_search_tool(workspace, tmp_path, index=FullTextIndex()), "basic")
    assert sorted(_hit_lines(fresh.output)) == expected_basic, fresh.output


def test_a_note_whose_name_utf8_cannot_encode_is_left_out_and_every_other_search_works(tmp_path: Path) -> None:
    """EC-8.8, INV-8.5 (review R-2, R-8): a note named with a lone surrogate (Windows) or a non-UTF-8 byte (Linux) gives no hits; the entries and the other note are found on this search and the next."""
    workspace = _workspace(tmp_path)
    write_jsonl(workspace.root / "entries.jsonl", [entry_record(1, "Alpha lists Basic at 49 USD")])
    _write(workspace.root, "notes/plans.md", "Kappa plan costs 79 USD\n")
    search_tool = _search_tool(workspace, tmp_path)
    assert _hit_lines(_search(search_tool, "kappa").output) == ["notes/plans.md:1: Kappa plan costs 79 USD"]
    try:
        _write(workspace.root, f"notes/{UNENCODABLE_NAME}", "Kappa hidden line\n")
    except OSError as exc:
        # A filesystem that refuses such names (macOS APFS) can never
        # hold the file this case is about.
        pytest.skip(f"this filesystem refuses a name UTF-8 cannot encode: {exc}")
    assert UNENCODABLE_NAME in [path.name for path in (workspace.root / "notes").iterdir()], "precondition: the name is listed back unencodable"
    for attempt in ("first", "second"):
        kappa = _search(search_tool, "kappa")
        assert kappa.status is ToolStatus.SUCCESS, (attempt, kappa.output)
        assert _hit_lines(kappa.output) == ["notes/plans.md:1: Kappa plan costs 79 USD"] and kappa.metadata == {"hits": 1, "total": 1}, (attempt, kappa.output)
        assert _search(search_tool, "hidden").metadata == {"hits": 0, "total": 0}, attempt
        assert _hit_lines(_search(search_tool, "alpha").output) == ["#1 fact: Alpha lists Basic at 49 USD"], attempt


# -------- S5: a warm search reads only what changed (NFR-8.1)

# Every path opened while _files_opened_under is active, recorded by
# one audit hook; a hook cannot be removed, so it is added once per
# process and records nothing outside that block.
_OPENED_PATHS: list[str] = []
_RECORDING: list[bool] = []
_AUDIT_HOOK_ADDED: list[bool] = []


def _record_file_open(event: str, args: tuple[Any, ...]) -> None:
    # Python raises "open" for open, io.open, os.open and every pathlib
    # read, in the opening thread, so the worker thread's reads count;
    # stat, resolve and scandir raise no "open" event.
    if _RECORDING and event == "open" and args and isinstance(args[0], (str, bytes)):
        _OPENED_PATHS.append(os.fsdecode(args[0]))


@contextmanager
def _files_opened_under(root: Path) -> Iterator[list[str]]:
    """Yields a list that, once the block ends, holds the root-relative POSIX path of every file opened under root inside it, by any API."""
    if not _AUDIT_HOOK_ADDED:
        sys.addaudithook(_record_file_open)
        _AUDIT_HOOK_ADDED.append(True)
    opened: list[str] = []
    _OPENED_PATHS.clear()
    _RECORDING.append(True)
    try:
        yield opened
    finally:
        _RECORDING.clear()
        bases = (root.resolve(), root)
        for raw in _OPENED_PATHS:
            path = Path(os.path.abspath(raw))
            base = next((candidate for candidate in bases if path.is_relative_to(candidate)), None)
            if base is not None:
                opened.append(path.relative_to(base).as_posix())


def test_a_warm_search_opens_no_unchanged_file_and_reads_a_changed_one_again(tmp_path: Path) -> None:
    """NFR-8.1 stand-in, INV-8.4 (review R-7, R-10): a search with nothing changed opens no workspace file; after one note and the entries change, the next search opens exactly those two, and the one after opens nothing again."""
    workspace = _workspace(tmp_path)
    root = workspace.root
    write_jsonl(root / "entries.jsonl", [entry_record(7, ZETA_ENTRY)])
    notes = [f"notes/n{number:02d}.md" for number in range(12)]
    for number, relative in enumerate(notes):
        _write(root, relative, f"Kappa fact number {number}\n")
    search_tool = _search_tool(workspace, tmp_path)
    with _files_opened_under(root) as cold:
        first = _search(search_tool, "kappa")
    # The cold search builds the index, so it must read every file. If
    # the hook missed this platform's reads, this fails here rather
    # than letting the warm check below pass on an empty list.
    assert {"entries.jsonl", *notes} <= set(cold), sorted(set(cold))
    assert first.metadata == {"hits": 10, "total": 12}
    with _files_opened_under(root) as warm:
        second = _search(search_tool, "kappa")
    assert second.metadata == first.metadata
    assert warm == [], f"a search with nothing changed opened {len(warm)} workspace files: {sorted(set(warm))}"
    # A new size changes each fingerprint, so both are read again.
    _write(root, "notes/n03.md", "Kappa fact three now rewritten\n")
    write_jsonl(root / "entries.jsonl", [entry_record(7, ZETA_ENTRY), entry_record(8, "Kappa entry added later")])
    with _files_opened_under(root) as changed:
        third = _search(search_tool, "rewritten")
    assert set(changed) == {"notes/n03.md", "entries.jsonl"}, sorted(set(changed))
    assert _hit_lines(third.output) == ["notes/n03.md:1: Kappa fact three now rewritten"], third.output
    with _files_opened_under(root) as settled:
        fourth = _search(search_tool, "added")
    assert settled == [], sorted(set(settled))
    assert _hit_lines(fourth.output) == ["#8 fact: Kappa entry added later"], fourth.output
