"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_workspace.py

PURPOSE: Proves the workspace guardrails the model meets through its memory tools: remember's sparse-entry rules and quota, supersede as a move, write_note's path, suffix, description, new-file and size rules, the file and token caps recomputed from disk (bash writes included), edit_file's single-match rule, bookkeeping files bounded only by the workspace total, grep over a large entries.jsonl, and the workspace map in every system string. Since the S4 review it also proves edit_file's caps, that a write the disk refuses becomes a clean refusal with no temp file left, and that a refused paste tells the model to keep it in a note.
ROLE IN CODEBASE: Workspace layer of tests/features/infinite_memory_agent/ (spec AC-14..AC-18, AC-34, AC-42; INV-17..INV-22, INV-32; EC-18..EC-25, EC-42; S4 review findings R-6, R-8, R-11). Exercises vidbyte/agents/infinite/workspace.py and vidbyte/agents/infinite/memory.py through the root agent's tools, and InfiniteWorkspace directly for the map and usage checks.
ARCHITECTURE NOTE: The root's scripted calls each observe the workspace bytes before answering, so a rejected tool call is proven to change nothing by comparing the snapshot taken at the call that issued it with the one taken at the next call. Tool results are read from the root's last call's history, in order.
FUNCTION INVENTORY: test_root_remember_rejects_each_rule_breaking_entry_and_enforces_the_quota (AC-14, EC-18, EC-19, INV-17, INV-32); test_root_supersede_moves_the_old_entry_out_of_entries_and_out_of_grep (AC-15, INV-15, INV-18, D-15); test_write_note_refuses_every_path_and_size_breach_and_changes_nothing (AC-16, EC-20..EC-22, INV-19, INV-20); test_write_note_refuses_a_new_file_at_the_file_cap / test_write_note_counts_files_bash_wrote_toward_the_token_cap (AC-16, EC-23, INV-19); test_edit_file_replaces_a_unique_match_and_refuses_an_ambiguous_one (AC-17, EC-25); test_entries_file_is_bounded_by_the_workspace_total_not_the_note_cap (AC-34); test_grep_finds_a_live_entry_in_an_entries_file_over_one_megabyte (AC-42); test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration (AC-18, INV-22); test_a_map_over_its_cap_ends_with_the_remaining_file_count (AC-18, EC-42, D-16); test_map_labels_and_usage_read_the_disk_and_never_fail_on_bad_lines (INV-19, INV-22, EC-24); test_grep_hides_superseded_entries_and_journals (D-15); test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing (R-11, INV-19, INV-32); test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file (R-8, INV-32, INV-19); test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files (R-8, INV-32, INV-20); test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer (R-6, EC-18). _recorder, _results, _seed_file and _failing_write are small builders and readers.
COMMON MODIFICATION PATTERNS: Add a rejected remember or write_note case to the ordered call list of its test, and keep it before the valid calls so a rejection that wrongly consumed quota shows up.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not fake bash; AC-16's bypass case needs a real file written outside the tools. 3. Do not compare map text to a hand-written rendering; only paths, descriptions, the catalog labels, and the cap are spec. 4. Do not fake the filesystem anywhere else: the R-8 test's one-shot os.replace failure is the pack's only fault injection on that seam, granted for that finding alone.
KNOWN EDGE CASES: The ../x.md and absolute-path cases resolve outside the workspace, so the test also checks that nothing appeared there. Bash needs a POSIX bash or Git for Windows bash on the host, as the coding-agent bash tests do. A colon in a note path is legal on POSIX, so the colon test can only fail on NTFS, where the colon names a data stream.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2, 6.3, 9.1 and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_workspace.py -q
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from string import Formatter
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MAP_HEADER,
    PASSED_REVIEW,
    ROOT,
    TASK,
    ModelCall,
    ScriptedTree,
    build_agent,
    entry_record,
    generator,
    int_token,
    is_error,
    journal_records,
    launch,
    map_section,
    observe,
    prompt_text,
    read_jsonl,
    reply,
    simple_pair,
    snapshot,
    task,
    template_regex,
    tool_call,
    tool_results,
    verifier,
    workspace_root,
    write_jsonl,
)


def _recorder(root: Path, states: list[dict[str, bytes]]) -> Callable[[ModelCall], None]:
    """An observe() action that keeps the workspace's bytes (journals included) as they were at each call."""

    def record(call: ModelCall) -> None:
        states.append(snapshot(root, include_runs=True))

    return record


def _results(tree: ScriptedTree) -> list[str]:
    """Every tool result content the root saw, in call order."""
    return [content for _, content in tool_results(tree.calls_by(ROOT)[-1])]


def _seed_file(tmp_path: Path, text: str = "Competitors: Acme, Globex.") -> Path:
    path = tmp_path / "inputs" / "brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- remember (AC-14, AC-15)


REJECTED_REMEMBERS: tuple[tuple[str, dict[str, Any], tuple[Any, ...]], ...] = (
    ("two-line text", {"kind": "fact", "text": "Acme is 49 USD\nGlobex is 59 USD"}, ()),
    ("text over max_entry_tokens", {"kind": "fact", "text": "Acme pricing detail " * 15}, ()),
    ("four tags", {"kind": "fact", "text": "Acme raised prices", "tags": ["acme", "pricing", "q3", "saas"]}, ("tags",)),
    ("kind outside the enum", {"kind": "opinion", "text": "Acme looks expensive"}, ("opinion",)),
    ("supersedes a missing id", {"kind": "fact", "text": "Acme now charges 52 USD", "supersedes": 77}, (77,)),
    ("text of a live entry", {"kind": "fact", "text": "  prices are   listed in usd "}, ("already recorded as #41",)),
)


def test_root_remember_rejects_each_rule_breaking_entry_and_enforces_the_quota(tmp_path: Path) -> None:
    """AC-14, EC-18, EC-19, INV-17, INV-32: each bad remember is an error with the quota line and changes nothing; rejections cost no quota; the sixth accepted call is refused."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(41, "Prices Are Listed In USD")])
    agent = build_agent(tmp_path)
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    valid = [f"Valid fact number {n} about competitor pricing" for n in range(1, 7)]
    calls = [args for _, args, _ in REJECTED_REMEMBERS] + [{"kind": "fact", "text": text} for text in valid]
    tree = ScriptedTree({ROOT: [observe(watch, tool_call("remember", args)) for args in calls] + [observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    results = _results(tree)
    assert len(results) == len(calls) == 12
    rejected_template = template_regex(prompt_text("memory_rejected_prompt"))
    quota_template = template_regex(prompt_text("quota_line"))
    saved_template = template_regex(prompt_text("remember_saved_prompt"))
    for index, (label, _, named) in enumerate(REJECTED_REMEMBERS):
        content = results[index]
        assert is_error(content), f"{label} was accepted: {content}"
        assert rejected_template.search(content) and quota_template.search(content), f"{label}: {content}"
        for token in named:
            pattern = int_token(token) if isinstance(token, int) else re.compile(re.escape(str(token)))
            assert pattern.search(content), f"{label} does not name {token!r}: {content}"
        assert states[index] == states[index + 1], f"{label} changed the workspace"
    for offset in range(5):
        content = results[len(REJECTED_REMEMBERS) + offset]
        assert not is_error(content), content
        assert saved_template.search(content) and quota_template.search(content), content
        assert int_token(42 + offset).search(content), f"the success output does not name id {42 + offset}: {content}"
    sixth = results[-1]
    assert is_error(sixth) and quota_template.search(sixth), sixth
    assert int_token(0).search(sixth) and int_token(5).search(sixth), f"the quota line should read 0 of 5: {sixth}"
    assert states[-2] == states[-1], "the refused sixth call changed the workspace"
    entries = read_jsonl(root / "entries.jsonl")
    assert [entry["id"] for entry in entries] == [41, 42, 43, 44, 45, 46]
    run_id = journal_records(root)[0]["run"]
    for entry, text in zip(entries[1:], valid[:5], strict=True):
        assert (entry["text"], entry["by"], entry["verified_by"], entry["run"]) == (text, "root", None, run_id)


def test_root_supersede_moves_the_old_entry_out_of_entries_and_out_of_grep(tmp_path: Path) -> None:
    """AC-15, INV-15, INV-18, D-15: a root supersede commits at once with verified_by null, moves #1's line unchanged, and grep no longer finds it."""
    root = workspace_root(tmp_path)
    original = entry_record(1, "Acme list price is 10 USD")
    write_jsonl(root / "entries.jsonl", [original])
    original_line = (root / "entries.jsonl").read_text(encoding="utf-8").strip()
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("remember", {"kind": "fact", "text": "Acme list price rose to 12 USD", "supersedes": 1}),
                tool_call("grep", {"pattern": "Acme list price is 10 USD"}),
                reply("done"),
            ]
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    saved, grepped = _results(tree)
    assert not is_error(saved) and int_token(2).search(saved)
    entries = read_jsonl(root / "entries.jsonl")
    assert [(entry["id"], entry["text"], entry["supersedes"], entry["verified_by"]) for entry in entries] == [(2, "Acme list price rose to 12 USD", 1, None)]
    assert [line.strip() for line in (root / "superseded.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()] == [original_line]
    assert grepped.strip() == "No matches found."


# ---------------------------------------------------------------- write_note (AC-16)


def test_write_note_refuses_every_path_and_size_breach_and_changes_nothing(tmp_path: Path) -> None:
    """AC-16, EC-20..EC-22, INV-19, INV-20, INV-32: each bad write_note is an error that changes no file; a valid create writes the note and its files.jsonl line; a later call appends."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path, workspace={"seed_files": (_seed_file(tmp_path),), "max_file_tokens": 30})
    seed_before = (root / "seed" / "brief.md").read_bytes()
    outside = tmp_path / "outside.md"
    rejected = (
        ("new path without description", {"path": "notes/a.md", "text": "First line of notes."}),
        ("parent escape", {"path": "../x.md", "text": "x", "description": "Escape attempt"}),
        ("absolute path outside", {"path": str(outside), "text": "x", "description": "Escape attempt"}),
        ("seed file", {"path": "seed/brief.md", "text": "x", "description": "Overwrite the seed"}),
        ("bookkeeping file", {"path": "entries.jsonl", "text": "x", "description": "Corrupt entries"}),
        ("journal folder", {"path": ".runs/hack.jsonl", "text": "x", "description": "Corrupt the journal"}),
        ("code suffix", {"path": "notes/a.py", "text": "print(1)", "description": "A code file"}),
    )
    created = {"path": "notes/a.md", "text": "Acme lists Pro at 49 USD.", "description": "Competitor prices"}
    later = (
        ("second new file", {"path": "notes/b.md", "text": "Globex", "description": "A second file"}),
        ("append over max_file_tokens", {"path": "notes/a.md", "text": "y" * 200}),
    )
    appended = {"path": "notes/a.md", "text": " Globex lists Team at 59 USD."}
    calls = [args for _, args in rejected] + [created] + [args for _, args in later] + [appended]
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    tree = ScriptedTree({ROOT: [observe(watch, tool_call("write_note", args)) for args in calls] + [observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    results = _results(tree)
    rejected_template = template_regex(prompt_text("memory_rejected_prompt"))
    refused_indexes = list(range(len(rejected))) + [len(rejected) + 1, len(rejected) + 2]
    labels = [label for label, _ in rejected] + ["valid create"] + [label for label, _ in later] + ["valid append"]
    for index in refused_indexes:
        assert is_error(results[index]) and rejected_template.search(results[index]), f"{labels[index]}: {results[index]}"
        assert states[index] == states[index + 1], f"{labels[index]} changed the workspace"
    saved_template = template_regex(prompt_text("note_saved_prompt"))
    for index in (len(rejected), len(calls) - 1):
        assert not is_error(results[index]) and saved_template.search(results[index]), f"{labels[index]}: {results[index]}"
    assert not (tmp_path / "project" / "x.md").exists() and not outside.exists()
    assert not (root / "notes" / "a.py").exists() and not (root / "notes" / "b.md").exists() and not (root / ".runs" / "hack.jsonl").exists()
    assert (root / "seed" / "brief.md").read_bytes() == seed_before
    note = (root / "notes" / "a.md").read_text(encoding="utf-8")
    assert note.startswith("Acme lists Pro at 49 USD.") and "Globex lists Team at 59 USD." in note and "yyyy" not in note
    (described,) = read_jsonl(root / "files.jsonl")
    assert (described["path"], described["description"], described["by"]) == ("notes/a.md", "Competitor prices", "root")
    assert described["run"] == journal_records(root)[0]["run"]
    assert datetime.fromisoformat(described["at"]).utcoffset().total_seconds() == 0


def test_write_note_refuses_a_new_file_at_the_file_cap(tmp_path: Path) -> None:
    """AC-16, INV-19: with three bookkeeping files and one seed at max_files=4, a new note is refused and nothing changes."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path, workspace={"seed_files": (_seed_file(tmp_path),), "max_files": 4})
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    tree = ScriptedTree({ROOT: [observe(watch, tool_call("write_note", {"path": "notes/new.md", "text": "Fresh", "description": "A new note"})), observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    (refused,) = _results(tree)
    assert is_error(refused) and ("max_files" in refused or int_token(4).search(refused)), refused
    assert states[0] == states[1]
    assert not (root / "notes" / "new.md").exists()


def test_write_note_counts_files_bash_wrote_toward_the_token_cap(tmp_path: Path) -> None:
    """AC-16, EC-23, INV-19, D-10: after bash writes 6,000 characters into the workspace, a small write_note that would pass max_tokens=1000 is refused."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path, workspace={"max_tokens": 1_000, "max_file_tokens": 1_000})
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("bash", {"command": "printf '%6000s' x > memory/big.txt"}),
                tool_call("write_note", {"path": "notes/small.md", "text": "Small finding.", "description": "A small note"}),
                reply("done"),
            ]
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    bashed, refused = _results(tree)
    assert not is_error(bashed), bashed
    assert (root / "big.txt").stat().st_size == 6_000
    assert is_error(refused) and ("max_tokens" in refused or int_token(1_000).search(refused)), refused
    assert not (root / "notes" / "small.md").exists()
    assert read_jsonl(root / "files.jsonl") == []


# ---------------------------------------------------------------- edit_file (AC-17)


def test_edit_file_replaces_a_unique_match_and_refuses_an_ambiguous_one(tmp_path: Path) -> None:
    """AC-17, EC-25, INV-6, INV-18: under FULL a unique match is replaced, two matches are refused stating 2, and pair agents hold edit_file too."""
    from vidbyte.lib.enums import InfiniteMemoryPreset

    root = workspace_root(tmp_path)
    for name, text in (("one.md", "keep old here"), ("two.md", "x and x")):
        path = root / "notes" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    write_jsonl(root / "files.jsonl", [{"path": f"notes/{name}", "description": f"Note {name}", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"} for name in ("one.md", "two.md")])
    agent = build_agent(tmp_path, workspace={"preset": InfiniteMemoryPreset.FULL})
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("edit_file", {"path": "notes/one.md", "old_text": "old", "new_text": "new"}),
                tool_call("edit_file", {"path": "notes/two.md", "old_text": "x", "new_text": "y"}),
                launch(task("fix")),
                reply("done"),
            ],
            **simple_pair("fix", "FIX-SUMMARY"),
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    replaced, ambiguous, _ = _results(tree)
    assert not is_error(replaced), replaced
    assert (root / "notes" / "one.md").read_text(encoding="utf-8") == "keep new here"
    assert is_error(ambiguous) and int_token(2).search(ambiguous), ambiguous
    assert (root / "notes" / "two.md").read_text(encoding="utf-8") == "x and x"
    assert "edit_file" in tree.first_call(generator("fix")).tools and "edit_file" in tree.first_call(verifier("fix")).tools


# ---------------------------------------------------------------- bookkeeping size (AC-34, AC-42)


def test_entries_file_is_bounded_by_the_workspace_total_not_the_note_cap(tmp_path: Path) -> None:
    """AC-34, INV-19: with entries.jsonl alone above max_file_tokens, a root remember and a pair commit are both written."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(index, f"Historic pricing fact {index:02d} " + "h" * 90) for index in range(1, 11)])
    assert len((root / "entries.jsonl").read_text(encoding="utf-8")) > 400, "entries.jsonl must start above max_file_tokens=100"
    agent = build_agent(tmp_path, workspace={"max_file_tokens": 100, "max_tokens": 10_000})
    tree = ScriptedTree(
        {
            ROOT: [tool_call("remember", {"kind": "fact", "text": "Root fact beyond the note cap"}), launch(task("p")), reply("done")],
            generator("p"): [tool_call("remember", {"kind": "fact", "text": "Pair fact beyond the note cap"}), reply("P-SUMMARY")],
            verifier("p"): [reply(PASSED_REVIEW)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert not any(is_error(content) for content in _results(tree))
    texts = [entry["text"] for entry in read_jsonl(root / "entries.jsonl")]
    assert "Root fact beyond the note cap" in texts and "Pair fact beyond the note cap" in texts


def test_grep_finds_a_live_entry_in_an_entries_file_over_one_megabyte(tmp_path: Path) -> None:
    """AC-42, D-15: when max_tokens lets entries.jsonl pass 1,000,000 bytes, grep still searches it."""
    root = workspace_root(tmp_path)
    # About 1.19 MB (about 297,000 tokens): past grep's old 1 MB skip, inside max_tokens=400,000.
    filler = [entry_record(index, f"Filler pricing entry {index:05d}") for index in range(1, 5_601)]
    write_jsonl(root / "entries.jsonl", [*filler, entry_record(5_601, "NEEDLE-ENTRY Zeta lists Enterprise at 999 USD")])
    assert (root / "entries.jsonl").stat().st_size > 1_000_000
    agent = build_agent(tmp_path, workspace={"max_tokens": 400_000})
    tree = ScriptedTree({ROOT: [tool_call("grep", {"pattern": "NEEDLE-ENTRY"}), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    (found,) = _results(tree)
    assert not is_error(found) and "entries.jsonl" in found and "NEEDLE-ENTRY Zeta lists Enterprise at 999 USD" in found, found[:500]


# ---------------------------------------------------------------- the workspace map (AC-18, INV-22)


def test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration(tmp_path: Path) -> None:
    """AC-18, INV-22: every root call's system has the map with the existing note; calls after write_note list the new file; a generator's first call has the map too."""
    root = workspace_root(tmp_path)
    existing = root / "notes" / "existing.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("Existing pricing notes body.\n", encoding="utf-8")
    write_jsonl(root / "files.jsonl", [{"path": "notes/existing.md", "description": "Existing pricing notes", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"}])
    agent = build_agent(tmp_path)
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("write_note", {"path": "notes/new.md", "text": "Fresh findings about pricing.", "description": "Fresh pricing findings"}),
                launch(task("alpha")),
                reply("done"),
            ],
            **simple_pair("alpha", "ALPHA-SUMMARY"),
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    for call in root_calls:
        current = map_section(call.system)
        assert "notes/existing.md" in current and "Existing pricing notes" in current
    assert "notes/new.md" not in map_section(root_calls[0].system)
    for call in root_calls[1:]:
        current = map_section(call.system)
        assert "notes/new.md" in current and "Fresh pricing findings" in current, "the root's map was not rendered again after its tool iteration"
    for child in (generator("alpha"), verifier("alpha")):
        assert MAP_HEADER in tree.first_call(child).system
        assert "notes/new.md" in map_section(tree.first_call(child).system)


def test_a_map_over_its_cap_ends_with_the_remaining_file_count(tmp_path: Path) -> None:
    """AC-18, EC-42, D-16: with 300 notes the map stays within INFINITE_MAP_MAX_TOKENS and says how many files it left out."""
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.constants.infinite import INFINITE_MAP_MAX_TOKENS, INFINITE_MORE_FILES
    from vidbyte.lib.util import TokenEstimate

    root = tmp_path / "memory"
    notes = [f"notes/f-{index:04d}.md" for index in range(1, 301)]
    for relative in notes:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Pricing note {relative}\n", encoding="utf-8")
    write_jsonl(root / "files.jsonl", [{"path": relative, "description": f"Pricing note number {relative[8:12]}", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"} for relative in notes])
    workspace = InfiniteWorkspace(InfiniteWorkspaceSettings(root=root, max_files=400))
    rendered = workspace.map_text()
    assert TokenEstimate.count(rendered) <= INFINITE_MAP_MAX_TOKENS
    before, _, after_count = INFINITE_MORE_FILES.partition("{count}")
    more = re.search(re.escape(before) + r"(\d+)" + re.escape(after_count), rendered)
    assert more, f"the map does not end with {INFINITE_MORE_FILES!r}"
    listed_notes = sum(1 for relative in notes if relative in rendered)
    left_out = int(more.group(1))
    assert 0 < left_out and 303 - listed_notes - 3 <= left_out <= 303 - listed_notes, (left_out, listed_notes)


def test_map_labels_and_usage_read_the_disk_and_never_fail_on_bad_lines(tmp_path: Path) -> None:
    """INV-19, INV-22, EC-24: seeds carry the seed label, undescribed or unreadable files show no description, bad bookkeeping lines never break the map, and usage skips .runs/."""
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.constants.infinite import INFINITE_NO_DESCRIPTION, INFINITE_SEED_LABEL
    from vidbyte.lib.util import TokenEstimate

    root = tmp_path / "memory"
    for name, text in (("plain.md", "Plain note.\n"), ("described.md", "Described note.\n"), ("broken.md", "Broken note.\n")):
        path = root / "notes" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    (root / "files.jsonl").write_text(
        '{"path": "notes/described.md", "description": "Described pricing note", "by": "root", "run": "20261015T024900Z-1a2b3c4d", "at": "2026-10-15T02:51:07Z"}\n{oops\n["notes/broken.md", "Broken description"]\n',
        encoding="utf-8",
        newline="\n",
    )
    write_jsonl(root / "entries.jsonl", [entry_record(1, "Acme is 49 USD"), entry_record(2, "Globex is 59 USD")])
    with (root / "entries.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("{not json\n")
    (root / ".runs").mkdir()
    (root / ".runs" / "20261014T090000Z-0a0b0c0d.jsonl").write_text("x" * 4_000, encoding="utf-8")
    workspace = InfiniteWorkspace(InfiniteWorkspaceSettings(root=root, seed_files=(_seed_file(tmp_path),)))
    rendered = workspace.map_text()

    def line_for(relative: str) -> str:
        lines = [line for line in rendered.splitlines() if relative in line]
        assert len(lines) == 1, f"{relative} should be on exactly one map line: {lines}"
        return lines[0]

    assert INFINITE_SEED_LABEL in line_for("seed/brief.md")
    assert INFINITE_NO_DESCRIPTION in line_for("notes/plain.md")
    assert "Described pricing note" in line_for("notes/described.md")
    assert INFINITE_NO_DESCRIPTION in line_for("notes/broken.md") and "Broken description" not in rendered
    counted = [path for path in root.rglob("*") if path.is_file() and ".runs" not in path.relative_to(root).parts]
    usage = workspace.usage()
    assert usage.files == len(counted) == 7
    assert usage.tokens == sum(TokenEstimate.count(path.read_text(encoding="utf-8")) for path in counted)


def test_grep_hides_superseded_entries_and_journals(tmp_path: Path) -> None:
    """D-15: the workspace grep ignores superseded.jsonl and .runs/, so stale facts and journals never come back as matches."""
    root = workspace_root(tmp_path)
    write_jsonl(root / "superseded.jsonl", [entry_record(9, "STALE-SUPERSEDED-FACT Acme was 5 USD")])
    write_jsonl(root / ".runs" / "20261014T090000Z-0a0b0c0d.jsonl", [{"event": "run_started", "at": "2026-10-14T09:00:00Z", "run": "20261014T090000Z-0a0b0c0d", "task": "STALE-SUPERSEDED-FACT in a journal"}])
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [tool_call("grep", {"pattern": "STALE-SUPERSEDED-FACT"}), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    (found,) = _results(tree)
    assert found.strip() == "No matches found.", found


# ---------------------------------------------------------------- S4 review: edit_file caps (R-11)


EDIT_CAPS = (
    pytest.param("max_file_tokens", {"max_file_tokens": 50}, None, id="note-over-max-file-tokens"),
    pytest.param("max_tokens", {"max_tokens": 200, "max_file_tokens": 150}, "o" * 400, id="workspace-over-max-tokens"),
)


@pytest.mark.parametrize(("cap", "limits", "other"), EDIT_CAPS)
def test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing(tmp_path: Path, cap: str, limits: dict[str, int], other: str | None) -> None:
    """R-11, INV-19, INV-32, AC-17: under FULL, an edit that would grow the note past max_file_tokens, or the workspace past max_tokens, is refused with the quota line and changes no byte; a small edit afterwards still works."""
    from vidbyte.lib.enums import InfiniteMemoryPreset

    root = workspace_root(tmp_path)
    note = root / "notes" / "prices.md"
    note.parent.mkdir(parents=True)
    note.write_text("Acme Pro is 49 USD per seat.\n", encoding="utf-8", newline="\n")
    if other is not None:
        # 100 tokens in another note, so an edited note under max_file_tokens still takes the workspace past max_tokens.
        (root / "notes" / "other.md").write_text(other, encoding="utf-8", newline="\n")
    agent = build_agent(tmp_path, workspace={"preset": InfiniteMemoryPreset.FULL, **limits})
    # The grown note is about 128 tokens: over 50, under 150, and about 228 with other.md beside it.
    grown = "49 USD per seat, " + "with the yearly plan billed up front " * 13
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    tree = ScriptedTree(
        {
            ROOT: [
                observe(watch, tool_call("edit_file", {"path": "notes/prices.md", "old_text": "49 USD per seat.", "new_text": grown})),
                observe(watch, tool_call("edit_file", {"path": "notes/prices.md", "old_text": "Acme Pro", "new_text": "Acme Pro plan"})),
                observe(watch, reply("done")),
            ]
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    refused, edited = _results(tree)
    assert is_error(refused), f"the edit over {cap} was applied: {refused}"
    assert template_regex(prompt_text("memory_rejected_prompt")).search(refused) and template_regex(prompt_text("quota_line")).search(refused), refused
    assert cap in refused or int_token(limits[cap]).search(refused), f"the refusal names neither {cap} nor its value: {refused}"
    assert states[0] == states[1], f"the refused edit over {cap} changed the workspace"
    assert not is_error(edited), edited
    assert note.read_text(encoding="utf-8") == "Acme Pro plan is 49 USD per seat.\n"


# ---------------------------------------------------------------- S4 review: failed disk writes (R-8)


def _failing_write(tool_name: str, bad: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The file name the tool's write replaces, a call whose new text ends with `bad`, and a clean call of the same tool."""
    if tool_name == "remember":
        return "entries.jsonl", {"kind": "fact", "text": f"Globex Team costs 59 USD per seat{bad}"}, {"kind": "fact", "text": "Initech costs 30 USD per seat"}
    if tool_name == "write_note":
        return "prices.md", {"path": "notes/prices.md", "text": f"Globex Team is 59 USD per seat.{bad}\n"}, {"path": "notes/prices.md", "text": "Initech is 30 USD per seat.\n"}
    return "prices.md", {"path": "notes/prices.md", "old_text": "49", "new_text": f"52{bad}"}, {"path": "notes/prices.md", "old_text": "Acme Pro", "new_text": "Acme Pro plan"}


@pytest.mark.parametrize("fault", ("replace-fails", "lone-surrogate"))
@pytest.mark.parametrize("tool_name", ("remember", "write_note", "edit_file"))
def test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str, fault: str) -> None:
    """R-8, INV-32, INV-19, spec 12.4: when the atomic replace fails (OSError) or the text cannot be encoded as UTF-8 (ValueError), remember, write_note and edit_file return a refusal with the quota line, leave no temp file or other change, and the same tool works on the next call."""
    from vidbyte.lib.enums import InfiniteMemoryPreset

    root = workspace_root(tmp_path)
    note = root / "notes" / "prices.md"
    note.parent.mkdir(parents=True)
    note.write_text("Acme Pro is 49 USD per seat.\n", encoding="utf-8", newline="\n")
    agent = build_agent(tmp_path, workspace={"preset": InfiniteMemoryPreset.FULL})
    # A lone surrogate is what a provider's escaped "\ud83d" decodes to; UTF-8 cannot encode it.
    target, failing, clean = _failing_write(tool_name, " \ud83d" if fault == "lone-surrogate" else "")
    fired: list[str] = []
    if fault == "replace-fails":
        # Fault injection on the filesystem seam, allowed for this R-8 case only: the first os.replace onto
        # the tool's target raises, as it does on Windows while another process holds that file open.
        real_replace = os.replace

        def replace_once(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
            if not fired and Path(destination).name == target:
                fired.append(str(destination))
                raise PermissionError(13, "Access is denied", str(destination))
            real_replace(source, destination, *args, **kwargs)

        monkeypatch.setattr(os, "replace", replace_once)
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    tree = ScriptedTree({ROOT: [observe(watch, tool_call(tool_name, failing)), observe(watch, tool_call(tool_name, clean)), observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    if fault == "replace-fails":
        assert fired, f"precondition: the injected failure never reached a replace of {target}"
    refused, accepted = _results(tree)
    assert is_error(refused), ascii(refused[:300])
    assert template_regex(prompt_text("memory_rejected_prompt")).search(refused) and template_regex(prompt_text("quota_line")).search(refused), f"{tool_name} let the failed write out as a raw error: {ascii(refused[:300])}"
    leftovers = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.tmp"))
    assert not leftovers, f"the failed write left temp files behind: {leftovers}"
    assert states[0] == states[1], "the refused call changed the workspace"
    assert not is_error(accepted), f"{tool_name} stopped working after the refusal: {accepted}"


def test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files(tmp_path: Path) -> None:
    """R-8, INV-32, INV-19, INV-20: write_note("notes/standup 10:30.md") either saves exactly that note, where the filesystem allows a colon, or is refused with the quota line and leaves every byte as it was; on NTFS the colon names a data stream, so a careless write leaves a stray file."""
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path)
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    args = {"path": "notes/standup 10:30.md", "text": "Standup summary.", "description": "Standup summary"}
    tree = ScriptedTree({ROOT: [observe(watch, tool_call("write_note", args)), observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    (content,) = _results(tree)
    if is_error(content):
        assert template_regex(prompt_text("memory_rejected_prompt")).search(content) and template_regex(prompt_text("quota_line")).search(content), f"the failed write escaped as a raw error: {ascii(content[:300])}"
        assert states[0] == states[1], f"the refused call left files behind: {sorted(set(states[1]) - set(states[0]))}"
    else:
        assert template_regex(prompt_text("note_saved_prompt")).search(content), content
        assert (root / "notes" / "standup 10:30.md").read_text(encoding="utf-8") == "Standup summary."


# ---------------------------------------------------------------- S4 review: EC-18 guidance (R-6)


EC18_PASTES = (
    pytest.param("\n".join(f"2026-10-15 ERROR worker {index} failed: connection reset by peer at stage {index % 7}" for index in range(200)), id="multi-line-log"),
    pytest.param(("Worker failure detail from the overnight batch " * 8).strip(), id="one-line-over-the-cap"),
)
ADVICE = re.compile(r"pointer|note", re.IGNORECASE)


@pytest.mark.parametrize("paste", EC18_PASTES)
def test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer(tmp_path: Path, paste: str) -> None:
    """R-6, EC-18, INV-17, INV-32: a pasted multi-line log, or one line over max_entry_tokens, is refused with the quota line and changes nothing, and the problem text itself tells the model to store a pointer or a note instead."""
    assert not ADVICE.search(paste), "precondition: the paste holds no advice word, so an echo of it cannot pass"
    root = workspace_root(tmp_path)
    agent = build_agent(tmp_path)
    states: list[dict[str, bytes]] = []
    watch = _recorder(root, states)
    tree = ScriptedTree({ROOT: [observe(watch, tool_call("remember", {"kind": "fact", "text": paste})), observe(watch, reply("done"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    (content,) = _results(tree)
    assert is_error(content), content[:300]
    assert template_regex(prompt_text("memory_rejected_prompt")).search(content) and template_regex(prompt_text("quota_line")).search(content), content[:300]
    assert states[0] == states[1], "the refused paste changed the workspace"
    # Only the problem text counts: strip the rejection template's and the quota line's own words first.
    problem = content
    for template in (prompt_text("memory_rejected_prompt"), prompt_text("quota_line")):
        for literal, _, _, _ in Formatter().parse(template):
            if literal.strip():
                problem = problem.replace(literal, " ")
    assert ADVICE.search(problem), f"the refusal does not tell the model to store a pointer or a note: {ascii(problem[:300])}"
