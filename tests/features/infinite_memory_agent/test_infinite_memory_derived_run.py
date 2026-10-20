"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_derived_run.py

PURPOSE: Proves the run-level derived events and guarantees: the spec section 4 snippet as printed, run_finished's session counts and whole-run card totals, events_failed on the terminal event, workspace_usage exactly when the usage level or the map's cut state changes (up and down), agent_progress every tenth root iteration with the root's own counts, handoff_written as the last event of run_handoff with its section lengths and cut titles, nothing built, scanned, or logged without a sink, nothing the model or the disk sees changed by a sink or a broken sink, and equal streams for two equal runs.
ROLE IN CODEBASE: Run layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-derived-events/spec.md (AC-1, AC-15..AC-22, AC-26; INV-1, INV-2, INV-5, INV-6, INV-13, INV-14; EC-12, EC-13, EC-14, EC-16, EC-18; FR-6, FR-7, FR-13, FR-14, FR-17; D-11..D-14, D-16, D-17). Exercises vidbyte/agents/infinite/events.py through runtime.py (_after_tool_iteration and the catch-up), agent.py (run_handoff), and workspace.py (usage, descriptions, map_omitted).
ARCHITECTURE NOTE: Only the model runner is scripted; bash, grep, the workspace, the journal, and the handoff writer are real. Counts an event must carry are read independently: usage at the root's next model call (nothing runs between the hook and that call), the omitted count from the map text the root's next call carried, totals from the journal's cards, files.jsonl, and the root result's metadata. AC-20 counts record construction with __post_init__ wrappers and attributes workspace scans to their caller's file, with a positive-control run that has a sink. _wide_tree is the one script that reaches 19 of the 22 kinds (all but run_resumed, run_stopped, and subagent_aborted, which a finished run cannot give).
FUNCTION INVENTORY: test_the_section_4_snippet_prints_the_refusal_the_commit_and_the_totals_and_its_asserts_hold (AC-1); test_run_finished_carries_this_sessions_loop_counts_and_the_whole_runs_card_totals (AC-15, D-16); test_the_terminal_event_counts_the_events_the_sink_failed_on (AC-16, D-17; finished and stopped); test_workspace_usage_arrives_exactly_when_the_level_crosses_up_or_down (AC-17, INV-13, EC-13, D-12); test_workspace_usage_arrives_when_the_map_is_cut_and_again_when_it_is_whole (AC-17, INV-13, FR-14); test_a_seeded_workspace_over_half_full_is_announced_after_the_first_root_tool_iteration_only (EC-12); test_agent_progress_arrives_every_tenth_root_iteration_with_the_roots_own_counts (AC-18, INV-14, D-11); test_agent_progress_has_no_max_iterations_when_the_loop_sets_none (EC-18); test_handoff_written_is_the_last_event_and_names_the_saved_file_and_its_sections (AC-19, INV-4, INV-15, D-14); test_handoff_written_names_the_sections_cut_at_their_caps (AC-19, D-14); test_handoff_written_arrives_for_an_unfinished_run_with_no_terminal_event (EC-14); test_without_a_sink_no_event_is_built_no_usage_is_scanned_and_nothing_is_logged (AC-20, INV-1, NFR-4, NFR-5); test_a_sink_changes_nothing_the_model_or_the_disk_sees (AC-21, INV-5); test_a_sink_that_raises_on_every_kind_changes_nothing_and_logs_each_failure_once (AC-22, INV-2); test_two_runs_of_one_script_give_equal_streams_once_ids_stamps_and_durations_are_normalized (AC-26, INV-6). _wide_tree, _snippet_tree, _note, _bash, _omitted, _run, _quiet_handoff, and _normalized are small builders.
COMMON MODIFICATION PATTERNS: A new run-level event joins _wide_tree's script and WIDE_KINDS, gets a test that pins the iterations it arrives at, and is then covered by AC-20, AC-21, AC-22, and AC-26 automatically.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert inside a sink. 3. Do not edit the section 4 snippet; chdir into tmp_path instead. 4. Do not read usage through the events module; read it from the workspace at the root's next model call.
KNOWN EDGE CASES: The scripted usage needs total_tokens for the loop's tokens_used; _USAGE sets it. The level and the map's cut state start at (0, False), so a run whose usage stays below 50 % and whose map is whole never gets workspace_usage. A KeyboardInterrupt is not used here; the abort paths live in test_infinite_memory_derived_pairs.py. Bash needs a POSIX bash or Git for Windows bash, as the rest of the pack does.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-derived-events/spec.md sections 4, 6.1, 6.2, 6.3, 9.1, 9.2 and 13; docs/spec/infinite-memory-derived-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_run.py -q
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    AC2_KINDS,
    AC7_LIMITS,
    EVENTS_LOGGER,
    FACT,
    GEN_SUMMARY,
    HANDOFF_OUTCOME_MAX,
    HANDOFF_SECTION_MAX,
    HANDOFF_TITLES,
    MARKER,
    NOTE_DESCRIPTION,
    NOTE_PATH,
    NOTE_TEXT,
    PAIR,
    PASSED,
    ROOT_ANSWER,
    ac2_tree,
    ac7_tree,
    assert_portable,
    calls_view,
    event_warnings,
    kinds,
    one,
    run_view,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    TASK,
    ModelCall,
    ScriptedTree,
    Step,
    build_agent,
    fail,
    finished_cards,
    generator,
    journal_records,
    launch,
    map_section,
    observe,
    pair_key,
    pair_started_record,
    read_jsonl,
    reply,
    run_started_record,
    simple_pair,
    task,
    tool_call,
    verifier,
    workspace_root,
    write_journal,
    write_jsonl,
)

_USAGE = {"input_tokens": 6, "output_tokens": 4, "total_tokens": 10}
_CHILD_USAGE = {"input_tokens": 600, "output_tokens": 400, "total_tokens": 1000}
_OMITTED = re.compile(r"and (\d+) more files$")
SECOND = "Globex charges 59 USD per seat"
# The wide script's settings and the 19 kinds a finished run of it with a sink gives (spec section 6.2 AC-20..AC-22, AC-26).
WIDE_FIELDS: dict[str, Any] = {"max_parallel": 2, "max_depth": 1, "workspace": {"max_files": 7}}
WIDE_KINDS = {
    "run_started",
    "run_finished",
    "batch_rejected",
    "subagent_launched",
    "subagent_replayed",
    "generator_finished",
    "subagent_finished",
    "memory_saved",
    "memory_staged",
    "memory_dropped",
    "file_written",
    "tool_refused",
    "memory_committed",
    "verifier_started",
    "verifier_finished",
    "batch_finished",
    "handoff_written",
    "workspace_usage",
    "agent_progress",
}
# The AC-7 script's stream (spec AC-7), plus the handoff this file asks for.
AC7_KINDS = ["run_started", "batch_rejected", "subagent_launched", "batch_rejected", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "run_finished"]
# The record classes an event is built from: the event itself and every details record (INV-1).
_RECORDS = re.compile(r"^Infinite\w*Details$|^InfiniteEvent$")


def _note(name: str, text: str | None = None) -> Step:
    return tool_call("write_note", {"path": f"notes/{name}.md", "text": text or f"Note {name}.\n", "description": f"Note {name}"})


def _bash(command: str) -> Step:
    return tool_call("bash", {"command": command})


def _omitted(call: ModelCall) -> int:
    """The files the root's map left out, read from the closing line of the map that call carried; 0 when the map is whole."""
    closing = map_section(call.system).rstrip().splitlines()[-1]
    found = _OMITTED.search(closing)
    return int(found.group(1)) if found else 0


def _wide_tree() -> ScriptedTree:
    """The wide script, run under WIDE_FIELDS: a root entry, a refused note, a refused batch, a denied batch, pair p (two entries, a note, one dropped by its verifier), p replayed beside q whose generator's launch is denied, then four greps and the answer."""
    return ScriptedTree(
        {
            ROOT: [
                tool_call("remember", {"kind": "decision", "text": "Compare monthly list prices only"}),
                tool_call("write_note", {"path": "../outside.md", "text": "Escaped.\n", "description": "Outside"}),
                launch(task("t"), task("t")),
                launch(task("x"), task("y"), task("z")),
                launch(task(PAIR)),
                launch(task(PAIR), task("q")),
                *(tool_call("grep", {"pattern": f"price-{index}"}) for index in range(4)),
                reply(ROOT_ANSWER),
            ],
            generator(PAIR): [
                tool_call("remember", {"kind": "fact", "text": FACT}),
                tool_call("remember", {"kind": "fact", "text": SECOND}),
                tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}),
                reply(GEN_SUMMARY),
            ],
            verifier(PAIR): [tool_call("drop_entry", {"id": "s2"}), reply(PASSED)],
            generator("q"): [launch(task("b")), reply("Q-SUMMARY")],
            verifier("q"): [reply(PASSED)],
        }
    )


SCRIPTS: dict[str, tuple[Callable[[], ScriptedTree], dict[str, Any]]] = {"ac2": (ac2_tree, {}), "ac7": (ac7_tree, dict(AC7_LIMITS)), "wide": (_wide_tree, WIDE_FIELDS)}


def _run(base: Path, script: str, on_event: Callable[[Any], object] | None) -> tuple[Any, str, ScriptedTree]:
    """Runs a named script under `base` with `on_event`, then run_handoff for its run; returns the reply, the run id, and the tree."""
    build, fields = SCRIPTS[script]
    base.mkdir(parents=True, exist_ok=True)
    agent = build_agent(base, on_event=on_event, **fields)
    tree = build()
    with tree.install():
        answer = agent.run(TASK)
        agent.run_handoff(answer.metadata["infinite_run_id"])
    tree.assert_complete()
    return answer, answer.metadata["infinite_run_id"], tree


def _quiet_handoff(agent: Any, run_id: str) -> Any:
    """run_handoff with every model call refused."""
    quiet = ScriptedTree({})
    with quiet.install():
        handoff = agent.run_handoff(run_id)
    assert quiet.calls == []
    return handoff


def _normalized(seen: list[Any], run_id: str, base: Path) -> list[tuple[Any, ...]]:
    """Each event as (kind, agent_key, role, depth, summary, details) with the run id, the tmp folder, and every duration_ms replaced (INV-6)."""

    def plain(text: str) -> str:
        text = text.replace(run_id, "<RUN>")
        for spelling in (json.dumps(str(base))[1:-1], str(base), base.as_posix()):
            text = text.replace(spelling, "<BASE>")
        return text

    rows = []
    for event in seen:
        details = {key: (0 if key == "duration_ms" else value) for key, value in dataclasses.asdict(event.details).items()}
        rows.append((event.kind.value, event.agent_key, event.role.value, event.depth, plain(event.summary), plain(json.dumps(details, default=str, sort_keys=True))))
    return rows


def _snippet_tree() -> ScriptedTree:
    """The AC-1 script: a refused batch with a repeated name, then pair p, whose generator stages FACT and writes a note and whose verifier passes."""
    return ScriptedTree(
        {
            ROOT: [launch(task("t"), task("t")), launch(task(PAIR)), reply(ROOT_ANSWER)],
            generator(PAIR): [
                tool_call("remember", {"kind": "fact", "text": FACT}),
                tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}),
                reply(GEN_SUMMARY),
            ],
            verifier(PAIR): [reply(PASSED)],
        }
    )


# ---------------------------------------------------------------- AC-1: the developer's snippet


def test_the_section_4_snippet_prints_the_refusal_the_commit_and_the_totals_and_its_asserts_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1: the section 4 snippet, run as printed in tmp_path, raises nothing, prints the tool's duplicate_task refusal, the commit of #1 by root/p/ver, and "1 1 0", every attribute it reads has the section 8.5 type, and both of its asserts hold."""
    monkeypatch.chdir(tmp_path)
    tree = _snippet_tree()
    with tree.install():
        # ---- spec section 4, as printed ----
        from vidbyte import InfiniteEventKind, InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings

        events = []
        agent = InfiniteMemoryAgent(
            InfiniteMemoryAgentSettings(
                name="analyst",
                system_prompt="You research markets and report sourced findings.",
                provider="openai",
                model_name="gpt-4.1",
                root_dir=".",
                workspace=InfiniteWorkspaceSettings(root="memory"),
                on_event=events.append,
            )
        )
        reply = agent.run("Compare the list prices of our five competitors.")
        run_id = reply.metadata["infinite_run_id"]
        agent.run_handoff(run_id)
        for event in events:
            if event.kind is InfiniteEventKind.MEMORY_COMMITTED:
                print(f"#{event.details.id} committed by {event.agent_key}: {event.details.text}")
            elif event.kind in (InfiniteEventKind.BATCH_REJECTED, InfiniteEventKind.TOOL_REFUSED):
                print(f"{event.agent_key}: {event.details.source.value} refused ({event.details.rule.value})")
        finished = next(event for event in events if event.kind is InfiniteEventKind.RUN_FINISHED)
        print(finished.details.passed, finished.details.committed, finished.details.events_failed)
        assert events[-1].kind is InfiniteEventKind.HANDOFF_WRITTEN
        assert events[-1].details.path == f".runs/{run_id}.handoff.md"
        # ---- end of snippet ----
    tree.assert_complete()
    assert capsys.readouterr().out.splitlines() == ["root: tool refused (duplicate_task)", f"#1 committed by root/{PAIR}/ver: {FACT}", "1 1 0"]
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule, InfiniteRefusalSource

    committed = next(event for event in events if event.kind is InfiniteEventKind.MEMORY_COMMITTED)
    refused = next(event for event in events if event.kind is InfiniteEventKind.BATCH_REJECTED)
    assert type(committed.details.id) is int and type(committed.details.text) is str
    assert isinstance(refused.details.source, InfiniteRefusalSource) and isinstance(refused.details.rule, InfiniteRefusalRule)
    assert all(type(value) is int for value in (finished.details.passed, finished.details.committed, finished.details.events_failed))
    assert type(events[-1].details.path) is str
    assert (tmp_path / "memory" / ".runs" / f"{run_id}.handoff.md").is_file()


# ---------------------------------------------------------------- AC-15, AC-16: the terminal event's totals


def test_run_finished_carries_this_sessions_loop_counts_and_the_whole_runs_card_totals(tmp_path: Path) -> None:
    """AC-15, D-16: a run whose root saves an entry, writes a note, launches a (passed), b (fixed, 2 entries, a note), c (failed, 1 entry), and d (no verdict), then e (passed) whose generator launches n (passed), finishes with run_finished carrying the root result's iteration and tool-call counts (5 and 4), the verdict counts 3/1/1/1 from the cards, committed 3 (card entries only), files 2 (this run's files.jsonl records), deepest 2, events_failed 0, and a duration."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("remember", {"kind": "decision", "text": "Compare monthly list prices only"}),
                _note("root"),
                launch(task("a"), task("b"), task("c"), task("d")),
                launch(task("e")),
                reply("done"),
            ],
            **simple_pair("a", "A-SUMMARY"),
            generator("b"): [tool_call("remember", {"kind": "fact", "text": FACT}), tool_call("remember", {"kind": "fact", "text": SECOND}), _note("b"), reply("B-SUMMARY")],
            verifier("b"): [reply("Fixed one source.\nVERDICT: fixed")],
            generator("c"): [tool_call("remember", {"kind": "fact", "text": "Initech charges 30 USD per seat"}), reply("C-SUMMARY")],
            verifier("c"): [reply("Two prices have no source.\nVERDICT: failed")],
            **simple_pair("d", "D-SUMMARY", review="Looks plausible."),
            generator("e"): [launch(task("n")), reply("E-SUMMARY")],
            verifier("e"): [reply(PASSED)],
            **simple_pair("n", "N-SUMMARY", parent=generator("e")),
        }
    )
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    root = workspace_root(tmp_path)
    cards = finished_cards(root)
    verdicts = [card["verdict"] for card in cards.values()]
    run_id = answer.metadata["infinite_run_id"]
    created = [record for record in read_jsonl(root / "files.jsonl") if record["run"] == run_id]
    assert (sorted(verdicts), sum(len(card["entries"]) for card in cards.values()), len(created)) == (["failed", "fixed", "passed", "passed", "passed", "unchecked"], 3, 2), "precondition: the cards and notes this script makes"
    assert kinds(seen)[-1] == "run_finished"
    details = one(seen, "run_finished").details
    assert (details.iterations, details.tool_calls) == (answer.metadata["iteration_count"], answer.metadata["tool_call_count"]) == (5, 4)
    assert (details.passed, details.fixed, details.failed, details.unchecked) == (3, 1, 1, 1)
    assert (details.committed, details.files, details.deepest, details.events_failed) == (3, 2, 2, 0)
    assert isinstance(details.duration_ms, int) and details.duration_ms >= 0
    assert_portable(seen)


@pytest.mark.parametrize("ending", ["finished", "stopped"])
def test_the_terminal_event_counts_the_events_the_sink_failed_on(tmp_path: Path, ending: str) -> None:
    """AC-16, D-17: a sink that raises ValueError on memory_staged and file_written (and, in the finished run, generator_finished) gives run_finished.events_failed 3, or run_stopped.events_failed 2 when the root's model then fails; the run's result is unchanged: the same answer, or the same AgentExecutionError."""
    from vidbyte.lib.errors import AgentExecutionError

    failing = {"memory_staged", "file_written"} | ({"generator_finished"} if ending == "finished" else set())
    seen: list[Any] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value in failing:
            raise ValueError("the dashboard rejected this event")

    agent = build_agent(tmp_path, on_event=sink)
    if ending == "finished":
        tree = ac2_tree()
        with tree.install():
            answer = agent.run(TASK)
        assert answer.content == ROOT_ANSWER
    else:
        tree = ScriptedTree({**_snippet_tree().scripts, ROOT: [launch(task(PAIR)), fail(RuntimeError("provider down"))]})
        with tree.install(), pytest.raises(AgentExecutionError):
            agent.run(TASK)
    tree.assert_complete()
    terminal = seen[-1]
    assert terminal.kind.value == ("run_finished" if ending == "finished" else "run_stopped")
    assert sum(event.kind.value in failing for event in seen) == len(failing), "precondition: each failing kind was offered once"
    assert terminal.details.events_failed == len(failing)


# ---------------------------------------------------------------- AC-17, EC-12: workspace usage


def test_workspace_usage_arrives_exactly_when_the_level_crosses_up_or_down(tmp_path: Path) -> None:
    """AC-17, INV-13, EC-13, D-12: with max_files 10 and max_tokens 100,000, five notes, a 368,000-character append, two bash files, then bash deletions give workspace_usage after root iterations 2, 5, 6, 7, 8, and 9 only, at levels 50, 75, 90, 100, 50, and 0, from the root; each carries the usage and omitted count the root's next call saw."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    seen_at: list[tuple[Any, int]] = []
    observed: dict[int, tuple[int, int, int]] = {}
    tree: ScriptedTree

    def look(call: ModelCall) -> None:
        usage = agent.workspace.usage()
        observed[len(tree.calls_by(ROOT)) - 1] = (usage.files, usage.tokens, _omitted(call))

    steps = [
        _note("a"),
        _note("b"),
        _note("c"),
        _note("d"),
        _note("e"),
        _bash("printf '%368000s' x >> memory/notes/a.md"),
        _bash("printf 'f\\n' > memory/notes/f.md && printf 'g\\n' > memory/notes/g.md"),
        _bash("printf 'Note a.\\n' > memory/notes/a.md && rm memory/notes/f.md memory/notes/g.md memory/notes/e.md memory/notes/d.md"),
        _bash("rm memory/notes/c.md memory/notes/b.md"),
        reply("done"),
    ]
    tree = ScriptedTree({ROOT: [observe(look, step) for step in steps]})
    agent = build_agent(tmp_path, workspace={"max_files": 10, "max_tokens": 100_000}, on_event=lambda event: seen_at.append((event, len(tree.calls_by(ROOT)))))
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    usages = [(event, iteration) for event, iteration in seen_at if event.kind.value == "workspace_usage"]
    assert [(iteration, event.details.level) for event, iteration in usages] == [(2, 50), (5, 75), (6, 90), (7, 100), (8, 50), (9, 0)]
    for event, iteration in usages:
        details = event.details
        assert (event.agent_key, event.role, event.depth) == ("root", InfiniteAgentRole.ROOT, 0)
        assert (details.files, details.tokens, details.map_omitted) == observed[iteration], iteration
        assert (details.max_files, details.max_tokens) == (10, 100_000)
        assert event.summary == f"Workspace is at the {details.level}% level: {details.files} of 10 files, {details.tokens} of 100000 tokens"
    assert_portable([event for event, _ in seen_at])


def test_workspace_usage_arrives_when_the_map_is_cut_and_again_when_it_is_whole(tmp_path: Path) -> None:
    """AC-17, INV-13, FR-14: 300 long-named files (far below max_files) cut the root's map, which gives workspace_usage at level 0 after iteration 1 with map_omitted equal to the "and N more files" count the root then read; deleting them gives one more at level 0 with map_omitted 0; no other iteration gives one."""
    seen_at: list[tuple[Any, int]] = []
    omitted: dict[int, int] = {}
    long_name = "competitor-pricing-page-snapshot-" + "x" * 80
    tree: ScriptedTree

    def look(call: ModelCall) -> None:
        omitted[len(tree.calls_by(ROOT)) - 1] = _omitted(call)

    steps = [_bash(f"mkdir -p memory/notes && for i in $(seq 1 300); do printf 'x' > memory/notes/n$i-{long_name}.md; done"), _bash("rm memory/notes/n*.md"), tool_call("grep", {"pattern": "price"}), reply("done")]
    tree = ScriptedTree({ROOT: [observe(look, step) for step in steps]})
    agent = build_agent(tmp_path, on_event=lambda event: seen_at.append((event, len(tree.calls_by(ROOT)))))
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert omitted[1] > 0 and omitted[2] == 0, f"precondition: the map was cut after iteration 1 only: {omitted}"
    usages = [(iteration, event.details.level, event.details.map_omitted) for event, iteration in seen_at if event.kind.value == "workspace_usage"]
    assert usages == [(1, 0, omitted[1]), (2, 0, 0)]


def test_a_seeded_workspace_over_half_full_is_announced_after_the_first_root_tool_iteration_only(tmp_path: Path) -> None:
    """EC-12, INV-13: a workspace seeded to 6 of 10 files (3 notes beside entries.jsonl, superseded.jsonl, and files.jsonl) gives one workspace_usage at level 50 after the first root tool iteration and none after the second; a run whose root answers at once gives none."""
    root = workspace_root(tmp_path)
    (root / "notes").mkdir(parents=True)
    for index in range(3):
        (root / "notes" / f"seed{index}.md").write_text(f"Seed {index}.\n", encoding="utf-8", newline="\n")
    seen_at: list[tuple[str, int, int]] = []
    tree = ScriptedTree({ROOT: [tool_call("grep", {"pattern": "seed"}), tool_call("grep", {"pattern": "price"}), reply("done")]})
    agent = build_agent(tmp_path, workspace={"max_files": 10}, on_event=lambda event: seen_at.append((event.kind.value, len(tree.calls_by(ROOT)), getattr(event.details, "level", -1))))
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert agent.workspace.usage().files == 6, "precondition: 3 seeds beside entries.jsonl, superseded.jsonl, and files.jsonl"
    assert [(iteration, level) for kind, iteration, level in seen_at if kind == "workspace_usage"] == [(1, 50)]
    at_once: list[str] = []
    again = build_agent(tmp_path, workspace={"max_files": 10}, on_event=lambda event: at_once.append(event.kind.value))
    tree = ScriptedTree({ROOT: [reply("done")]})
    with tree.install():
        again.run(TASK)
    tree.assert_complete()
    assert at_once == ["run_started", "run_finished"]


# ---------------------------------------------------------------- AC-18, EC-18: progress


def test_agent_progress_arrives_every_tenth_root_iteration_with_the_roots_own_counts(tmp_path: Path) -> None:
    """AC-18, INV-14, D-11: a root that launches one pair (whose generator makes 11 tool iterations of its own) and then greps 24 times gives agent_progress after root iterations 10 and 20 only, from the root, with model calls, tool calls, and tokens from the root's loop alone (10 tokens a call, none of the children's 1,000) and max_iterations from settings."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    seen_at: list[tuple[Any, int]] = []
    tree = ScriptedTree(
        {
            ROOT: [tool_call("launch_subagent", {"tasks": [task(PAIR)]}, usage=_USAGE), *(tool_call("grep", {"pattern": f"x{index}"}, usage=_USAGE) for index in range(24)), reply("done", usage=_USAGE)],
            generator(PAIR): [*(tool_call("grep", {"pattern": f"y{index}"}, usage=_CHILD_USAGE) for index in range(11)), reply(GEN_SUMMARY, usage=_CHILD_USAGE)],
            verifier(PAIR): [reply(PASSED, usage=_CHILD_USAGE)],
        }
    )
    agent = build_agent(tmp_path, on_event=lambda event: seen_at.append((event, len(tree.calls_by(ROOT)))))
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert answer.metadata["iteration_count"] == 26, "precondition: 25 root tool iterations and the answer"
    maximum = agent.settings.loop.max_iterations
    progress = [(event, iteration) for event, iteration in seen_at if event.kind.value == "agent_progress"]
    rows = [(iteration, event.details.iteration, event.details.model_calls, event.details.tool_calls, event.details.tokens, event.details.max_iterations) for event, iteration in progress]
    assert rows == [(10, 10, 10, 10, 100, maximum), (20, 20, 20, 20, 200, maximum)]
    assert all((event.agent_key, event.role, event.depth) == ("root", InfiniteAgentRole.ROOT, 0) for event, _ in progress)
    assert [event.summary for event, _ in progress] == ["root is at iteration 10: 10 model calls, 10 tool calls", "root is at iteration 20: 20 model calls, 20 tool calls"]
    assert_portable([event for event, _ in seen_at])


def test_agent_progress_has_no_max_iterations_when_the_loop_sets_none(tmp_path: Path) -> None:
    """EC-18: with AgentLoopSettings() (no iteration limit), the progress after root iteration 10 carries max_iterations None."""
    from vidbyte.agents.settings import AgentLoopSettings

    seen: list[Any] = []
    agent = build_agent(tmp_path, loop=AgentLoopSettings(), on_event=seen.append)
    assert agent.settings.loop.max_iterations is None, "precondition: the loop has no limit"
    tree = ScriptedTree({ROOT: [*(tool_call("grep", {"pattern": f"x{index}"}) for index in range(10)), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    progress = one(seen, "agent_progress").details
    assert (progress.iteration, progress.max_iterations) == (10, None)


# ---------------------------------------------------------------- AC-19: the handoff


def test_handoff_written_is_the_last_event_and_names_the_saved_file_and_its_sections(tmp_path: Path) -> None:
    """AC-19, INV-4, INV-15, D-14: run_handoff after the AC-2 run delivers exactly one more event, handoff_written from the root, after the file is on disk, with path .runs/<run_id>.handoff.md, the nine section lengths of the returned handoff in its fixed order, no cut section, and the template summary."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    root = workspace_root(tmp_path)
    seen: list[Any] = []
    on_disk: list[bool] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "handoff_written":
            on_disk.append((root / ".runs" / f"{event.run_id}.handoff.md").is_file())

    agent = build_agent(tmp_path, on_event=sink)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    before = len(seen)
    run_id = answer.metadata["infinite_run_id"]
    handoff = _quiet_handoff(agent, run_id)
    assert kinds(seen[before:]) == ["handoff_written"]
    event = seen[-1]
    assert (event.agent_key, event.role, event.depth, event.run_id) == ("root", InfiniteAgentRole.ROOT, 0, run_id)
    assert on_disk == [True]
    path = f".runs/{run_id}.handoff.md"
    assert (event.details.path, event.details.sections, event.details.cut, event.details.cut_omitted) == (path, tuple(len(handoff.sections[title]) for title in HANDOFF_TITLES), (), 0)
    assert len(event.details.sections) == 9
    assert event.summary == f"Handoff saved to {path}"
    assert_portable(seen)


def test_handoff_written_names_the_sections_cut_at_their_caps(tmp_path: Path) -> None:
    """AC-19, D-14: a 300,000-character answer and 30 long files.jsonl records for the run cut the Outcome to 239,000 and Files to 15,900 characters with the marker, so handoff_written lists exactly those two titles as cut, in section order."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    answer_text = "".join(f"Vendor {index:05d}: list price {index % 97} USD per seat, checked on the public page.\n" for index in range(4_000))[:300_000]
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({ROOT: [_note("root"), reply(answer_text)]})
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    run_id = answer.metadata["infinite_run_id"]
    files_file = workspace_root(tmp_path) / "files.jsonl"
    extra = [{"path": f"notes/vendor-{index:02d}.md", "description": f"Vendor {index} pricing notes: " + "d" * 576, "by": "root", "run": run_id, "at": "2026-10-16T08:15:00+00:00"} for index in range(30)]
    write_jsonl(files_file, [*read_jsonl(files_file), *extra])
    handoff = _quiet_handoff(agent, run_id)
    lengths = tuple(len(handoff.sections[title]) for title in HANDOFF_TITLES)
    assert isinstance(handoff, InfiniteHandoff) and lengths[0] == HANDOFF_OUTCOME_MAX and lengths[HANDOFF_TITLES.index("Files")] == HANDOFF_SECTION_MAX, "precondition: two sections hit their caps"
    assert handoff.sections["Outcome"].endswith(MARKER) and handoff.sections["Files"].endswith(MARKER)
    details = seen[-1].details
    assert seen[-1].kind.value == "handoff_written"
    assert (details.sections, details.cut, details.cut_omitted) == (lengths, ("Outcome", "Files"), 0)


def test_handoff_written_arrives_for_an_unfinished_run_with_no_terminal_event(tmp_path: Path) -> None:
    """EC-14, D-14: run_handoff for a run whose journal stops after a pair started (no run_finished or run_stopped on disk) writes the handoff as before and then delivers exactly one event, handoff_written from the root under that run's id, naming the file it wrote."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    root = workspace_root(tmp_path)
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), pair_started_record(pair_key("a"))])
    _quiet_handoff(agent, RUN_A)
    assert (root / ".runs" / f"{RUN_A}.handoff.md").is_file(), "precondition: the handoff file is written as before"
    assert kinds(seen) == ["handoff_written"]
    (written,) = seen
    assert (written.run_id, written.agent_key, written.depth, written.details.path) == (RUN_A, "root", 0, f".runs/{RUN_A}.handoff.md")
    assert_portable(seen)


# ---------------------------------------------------------------- AC-20, INV-1: nothing without a sink


def test_without_a_sink_no_event_is_built_no_usage_is_scanned_and_nothing_is_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """AC-20, INV-1: the wide script and run_handoff with on_event None build no InfiniteEvent or details record, never call InfiniteWorkspace.usage() or descriptions() from the events module, never call map_omitted, and log nothing; the same run with a sink does all three, so the counters can see them, and (NFR-5) scans usage at most once per root tool iteration and reads files.jsonl once, for its run_finished."""
    import vidbyte.lib.dataclasses.infinite as records
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace

    built: list[str] = []
    for name, record in vars(records).items():
        if isinstance(record, type) and _RECORDS.match(name) and hasattr(record, "__post_init__"):
            monkeypatch.setattr(record, "__post_init__", _counting(record.__post_init__, built, name))
    scans: list[tuple[str, str]] = []
    for method in ("usage", "descriptions"):
        monkeypatch.setattr(InfiniteWorkspace, method, _attributed(getattr(InfiniteWorkspace, method), scans, method))
    omitted_calls: list[str] = []
    real_omitted = InfiniteWorkspace.map_omitted
    monkeypatch.setattr(InfiniteWorkspace, "map_omitted", staticmethod(lambda text: omitted_calls.append("map_omitted") or real_omitted(text)))
    caplog.set_level(logging.DEBUG, logger=EVENTS_LOGGER)

    _run(tmp_path / "quiet", "wide", None)
    from_events = [method for method, caller in scans if caller.endswith("vidbyte/agents/infinite/events.py")]
    assert (built, from_events, omitted_calls, event_warnings(caplog)) == ([], [], [], [])

    seen: list[Any] = []
    _, _, tree = _run(tmp_path / "listened", "wide", seen.append)
    from_events = [method for method, caller in scans if caller.endswith("vidbyte/agents/infinite/events.py")]
    assert {"InfiniteEvent", "InfiniteWorkspaceUsageDetails"} <= set(built) and {"usage", "descriptions"} <= set(from_events) and omitted_calls, "positive control: with a sink, the counters see each of these"
    assert set(kinds(seen)) == WIDE_KINDS
    # NFR-5: every root call but the last asked for one tool, so the scans are bounded by those tool iterations and the one run_finished.
    root_tool_iterations = len(tree.calls_by(ROOT)) - 1
    assert (from_events.count("usage") <= root_tool_iterations, from_events.count("descriptions")) == (True, 1)


def _counting(real: Callable[..., Any], built: list[str], name: str) -> Callable[..., Any]:
    def post_init(self: Any) -> Any:
        built.append(name)
        return real(self)

    return post_init


def _attributed(real: Callable[..., Any], scans: list[tuple[str, str]], method: str) -> Callable[..., Any]:
    def scan(self: Any, *args: Any, **kwargs: Any) -> Any:
        caller = inspect.currentframe()
        assert caller is not None and caller.f_back is not None
        scans.append((method, Path(caller.f_back.f_code.co_filename).as_posix()))
        return real(self, *args, **kwargs)

    return scan


# ---------------------------------------------------------------- AC-21, AC-22, AC-26: the sink never changes the run


@pytest.mark.parametrize("script", ["ac2", "ac7", "wide"])
def test_a_sink_changes_nothing_the_model_or_the_disk_sees(tmp_path: Path, script: str) -> None:
    """AC-21, INV-5: each script run once with a list sink and once with none gives byte-identical tool results, cards, maps, prompts (every model call), journal, entries.jsonl, files.jsonl, and handoff file, once the run id, stamps, folder, and call ids are replaced; the sink run delivered the script's derived events."""
    seen: list[Any] = []
    listened, listened_id, listened_tree = _run(tmp_path / "listened", script, seen.append)
    quiet, quiet_id, quiet_tree = _run(tmp_path / "quiet", script, None)
    assert listened.content == quiet.content
    assert run_view(workspace_root(tmp_path / "listened"), tmp_path / "listened", listened_id) == run_view(workspace_root(tmp_path / "quiet"), tmp_path / "quiet", quiet_id)
    assert calls_view(listened_tree, tmp_path / "listened", listened_id) == calls_view(quiet_tree, tmp_path / "quiet", quiet_id)
    expected = {"ac2": [*AC2_KINDS, "handoff_written"], "ac7": [*AC7_KINDS, "handoff_written"]}
    if script in expected:
        assert kinds(seen) == expected[script]
    else:
        assert set(kinds(seen)) == WIDE_KINDS


def test_a_sink_that_raises_on_every_kind_changes_nothing_and_logs_each_failure_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-22, INV-2: the wide script and its handoff with a sink that raises ValueError on every event give the same reply, journal, workspace, and model calls as with no sink; every event a list sink receives is offered and logged once, naming the run id, the kind, and ValueError."""
    caplog.set_level(logging.WARNING, logger=EVENTS_LOGGER)
    listed: list[Any] = []
    _run(tmp_path / "listed", "wide", listed.append)
    assert event_warnings(caplog) == [], "a list sink must not log"
    attempted: list[str] = []

    def broken(event: Any) -> None:
        attempted.append(event.kind.value)
        raise ValueError("the dashboard is offline")

    raising, raising_id, raising_tree = _run(tmp_path / "raising", "wide", broken)
    quiet, quiet_id, quiet_tree = _run(tmp_path / "quiet", "wide", None)
    assert raising.content == quiet.content
    assert run_view(workspace_root(tmp_path / "raising"), tmp_path / "raising", raising_id) == run_view(workspace_root(tmp_path / "quiet"), tmp_path / "quiet", quiet_id)
    assert calls_view(raising_tree, tmp_path / "raising", raising_id) == calls_view(quiet_tree, tmp_path / "quiet", quiet_id)
    assert set(kinds(listed)) == WIDE_KINDS
    assert attempted == kinds(listed)
    assert [record.getMessage() for record in event_warnings(caplog)] == [f"infinite_event_failed run_id={raising_id} kind={kind} error_type=ValueError" for kind in kinds(listed)]


def test_two_runs_of_one_script_give_equal_streams_once_ids_stamps_and_durations_are_normalized(tmp_path: Path) -> None:
    """AC-26, INV-6: two runs of the wide script and its handoff on equal fresh workspaces deliver equal sequences of (kind, agent_key, role, depth, summary, details) once the run id, the folder, and every duration_ms are replaced; at is left out."""
    first: list[Any] = []
    second: list[Any] = []
    _, first_id, _ = _run(tmp_path / "one", "wide", first.append)
    _, second_id, _ = _run(tmp_path / "two", "wide", second.append)
    assert set(kinds(first)) == WIDE_KINDS
    assert _normalized(first, first_id, tmp_path / "one") == _normalized(second, second_id, tmp_path / "two")
    assert [record["event"] for record in journal_records(workspace_root(tmp_path / "one"))] == [record["event"] for record in journal_records(workspace_root(tmp_path / "two"))]
    assert_portable(first)
