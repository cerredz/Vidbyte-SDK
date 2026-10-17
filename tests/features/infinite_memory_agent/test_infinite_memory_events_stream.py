"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py

PURPOSE: Proves the live event stream of an InfiniteMemory run as a caller sees it: the spec section 4 snippet's exact output, the exact kinds, envelopes, summaries, and details of a one-pair run, the root's memory_saved, durable-before-announced delivery, a raising or coroutine-returning sink changing nothing, the default with no sink, token totals, tools that stay quiet, the run id on every reply, and runs refused before their journal.
ROLE IN CODEBASE: Event-stream layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-events/spec.md (AC-1, AC-2, AC-3, AC-4, AC-13, AC-15, AC-20, AC-23, AC-25, AC-26, AC-29; INV-1, INV-4, INV-5, INV-7, INV-9..INV-13, INV-21, INV-31, INV-36; EC-2, EC-5, EC-32; NFR-2). Exercises vidbyte/agents/infinite/events.py through runtime.py, launch.py, and memory.py.
ARCHITECTURE NOTE: Only the model runner is scripted (ScriptedTree). The sink is a plain list.append or a small function defined in the test; InfiniteEvents, the records, the workspace, and the journal are real. A sink never asserts: InfiniteEvents catches what it raises, so it records what it saw and the test asserts after the run. Two runs are compared through run_view and calls_view, which replace the run id, stamps, tmp folder, and call ids with placeholders (proved equal for two identical runs without a sink before this file was written).
FUNCTION INVENTORY: test_section_4_snippet_prints_the_two_run_events_and_the_nine_handoff_titles (AC-1); test_a_one_pair_run_delivers_seven_events_in_order_with_their_envelopes_summaries_and_details (AC-2, AC-13, INV-11, INV-12, INV-16, D-18); test_the_roots_entry_is_announced_once_by_memory_saved_before_its_next_model_call (AC-3, INV-17); test_a_sink_that_always_raises_changes_nothing_and_each_failure_is_logged_once_without_text (AC-4, INV-7); test_each_event_is_delivered_after_the_change_it_reports_is_on_disk (AC-26, INV-4); test_a_sink_that_returns_a_coroutine_has_it_closed_and_logged_as_a_type_error (AC-29a, INV-36, EC-32); test_a_sink_that_returns_a_task_it_scheduled_is_not_a_failure (AC-29b, INV-36); test_without_a_sink_the_journal_gains_only_answer_and_files_and_nothing_is_logged (AC-20, INV-9); test_without_a_sink_no_event_method_builds_an_event_or_logs (NFR-2, INV-9); test_token_totals_come_from_the_scripted_usage_and_match_get_usage (AC-23, INV-31, D-18); test_bash_grep_and_read_lines_deliver_no_event_and_no_event_carries_their_output_or_secrets (AC-25, INV-10); test_every_reply_names_its_journal_in_infinite_run_id (AC-15, INV-21, INV-29); test_a_run_refused_before_its_journal_delivers_no_event (EC-5, INV-1); test_a_keyboard_interrupt_raised_by_the_sink_is_not_swallowed (INV-7, EC-2). _compare_with_list_sink runs the AC-2 script with a list sink beside another sink.
COMMON MODIFICATION PATTERNS: A new stream-level rule gets one test that runs a ScriptedTree with seen.append as the sink and ends with assert_portable(seen). Keep summaries compared with line(...) from infinite_events_fixtures.py so the expected text follows the spec's cut rule.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert inside a sink. 3. Do not edit the section 4 snippet to make it easier to test; chdir into tmp_path instead. 4. Do not compare raw journals of two runs; compare run_view output, because run ids and stamps differ.
KNOWN EDGE CASES: The snippet assigns names `reply` and `events`, so its scripted tree is built by a module helper and this file imports neither fixture name. The fixture's DEFAULT_USAGE has no total_tokens, so the AC-23 script sets total_tokens on every step; without it the rollup's total_tokens is None (S2 report). The scripted model is unpriced (cost_complete is False), so every cost_usd in a scripted run is None, never 0.0. Bash needs a POSIX bash or Git for Windows bash.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 4, 6.1, 6.2, 9.1 and 13; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py -q
"""

from __future__ import annotations

import asyncio
import dataclasses
import gc
import inspect
import logging
import warnings
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    AC2_KINDS,
    EVENTS_LOGGER,
    FACT,
    GEN_SUMMARY,
    NOTE_DESCRIPTION,
    NOTE_PATH,
    NOTE_TEXT,
    PAIR,
    PASSED,
    ROOT_ANSWER,
    SUMMARY_MAX,
    TEXT_MAX,
    ac2_tree,
    assert_portable,
    calls_view,
    cut,
    event_warnings,
    kinds,
    line,
    one,
    run_view,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    RUN_B,
    SYSTEM_PROMPT,
    TASK,
    ModelCall,
    ScriptedTree,
    build_agent,
    entry_record,
    finished_cards,
    generator,
    is_error,
    journal_paths,
    journal_records,
    launch,
    observe,
    pair_key,
    read_jsonl,
    run_started_record,
    task,
    tool_call,
    tool_result,
    verifier,
    workspace_root,
    write_journal,
    write_jsonl,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import reply as answer_with
from vidbyte import tool
from vidbyte.lib.errors import VidbyteSdkError

SNIPPET_ANSWER = "Acme is cheapest at 49 USD per seat."
# The three lines spec section 4 says the snippet prints, each ending with a line break.
SNIPPET_LINES = (
    "run_started root Run started: Compare the list prices of our five competitors.",
    "run_finished root Run finished (final_response): Acme is cheapest at 49 USD per seat.",
    "('Outcome', 'Work done', 'Decisions', 'Facts', 'Lessons', 'Open questions', 'Files', 'Unverified or failed work', 'How to continue')",
)
SNIPPET_OUTPUT = "".join(f"{text}\n" for text in SNIPPET_LINES)


@tool(name="remember")
def foreign_remember(text: str) -> str:
    """An MCP-style tool that happens to be named like a run-bound tool."""
    return text


def _root_answers_at_once() -> ScriptedTree:
    return ScriptedTree({ROOT: [answer_with(SNIPPET_ANSWER)]})


def _usage(input_tokens: int, output_tokens: int) -> dict[str, int]:
    # Scripted usage with its total, because the rollup's total_tokens stays None without one.
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}


def _texts(value: Any) -> list[str]:
    # Every text leaf of an asdict() value, nested dicts and tuples included.
    if isinstance(value, dict):
        return [text for item in value.values() for text in _texts(item)]
    if isinstance(value, tuple):
        return [text for item in value for text in _texts(item)]
    return [value] if isinstance(value, str) else []


def _compare_with_list_sink(base: Path) -> tuple[list[Any], str, Any, ScriptedTree]:
    """Runs the AC-2 script under `base` with a list sink; returns the events, the run id, the reply, and the tree."""
    base.mkdir()
    seen: list[Any] = []
    agent = build_agent(base, on_event=seen.append)
    tree = ac2_tree()
    with tree.install():
        listed = agent.run(TASK)
    tree.assert_complete()
    return seen, listed.metadata["infinite_run_id"], listed, tree


# ---------------------------------------------------------------- AC-1, AC-2, AC-3


def test_section_4_snippet_prints_the_two_run_events_and_the_nine_handoff_titles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, INV-1, INV-2, INV-21, INV-23: the section 4 snippet, run as printed for a root that answers at once, prints exactly the three documented lines and saves the handoff file it names."""
    monkeypatch.chdir(tmp_path)
    tree = _root_answers_at_once()
    with tree.install():
        # ---- spec section 4, as printed ----
        from vidbyte import InfiniteEvent, InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings

        events: list[InfiniteEvent] = []
        agent = InfiniteMemoryAgent(
            InfiniteMemoryAgentSettings(
                name="analyst",
                system_prompt="You research markets and report sourced findings.",
                provider="openai",
                model_name="gpt-4.1",
                root_dir=".",
                workspace=InfiniteWorkspaceSettings(root="memory"),
                on_event=events.append,  # a plain (not async) callable, called once per event, in order; an error it raises never stops the run
            )
        )
        reply = agent.run("Compare the list prices of our five competitors.")
        run_id = reply.metadata["infinite_run_id"]  # the journal id, also given to resume()

        for event in events:
            print(event.kind.value, event.agent_key, event.summary)

        handoff = agent.run_handoff(run_id)  # no model call; also saved as memory/.runs/<run_id>.handoff.md
        print(handoff.section_titles())
        # ---- end of snippet ----
    tree.assert_complete()
    assert capsys.readouterr().out == SNIPPET_OUTPUT
    assert (tmp_path / "memory" / ".runs" / f"{run_id}.handoff.md").is_file()


def test_a_one_pair_run_delivers_seven_events_in_order_with_their_envelopes_summaries_and_details(tmp_path: Path) -> None:
    """AC-2, AC-13, INV-11, INV-12, INV-16, D-18: the AC-2 script delivers exactly seven events in order, each with the documented envelope, template summary, and details, all carrying the reply's run id."""
    from vidbyte.lib.dataclasses.infinite import InfiniteCommittedEntry
    from vidbyte.lib.enums.infinite import (
        InfiniteAgentRole,
        InfiniteEntryKind,
        InfiniteFileChange,
        InfiniteMemoryPreset,
        InfiniteResultStatus,
        InfiniteVerdict,
    )

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == AC2_KINDS
    run_id = answer.metadata["infinite_run_id"]
    assert {event.run_id for event in seen} == {run_id}
    at_root = ("root", InfiniteAgentRole.ROOT, 0)
    at_generator = (f"{pair_key(PAIR)}/gen", InfiniteAgentRole.GENERATOR, 1)
    assert [(event.agent_key, event.role, event.depth) for event in seen] == [at_root, at_root, at_generator, at_generator, at_generator, at_root, at_root]
    assert [event.summary for event in seen] == [
        line(f"Run started: {TASK}", SUMMARY_MAX),
        line(f"root launched {PAIR}: Find the list prices for {PAIR}.", SUMMARY_MAX),
        f"{PAIR}/gen proposed s1 (fact): {FACT}",
        f"{PAIR}/gen created {NOTE_PATH}: {NOTE_DESCRIPTION}",
        f"{PAIR}/gen: done: {GEN_SUMMARY}",
        f"{PAIR}: passed, 1 memories saved, 0 dropped, 1 files",
        f"Run finished (final_response): {ROOT_ANSWER}",
    ]

    started = one(seen, "run_started").details
    assert (started.task, started.model, started.preset, started.max_depth, started.max_parallel, started.max_agents, started.max_iterations) == (TASK, "gpt-4.1", InfiniteMemoryPreset.SPARSE, 20, 20, 1_000, 500)
    assert (started.extras, started.extras_omitted, started.seeds, started.seeds_omitted) == ((), 0, (), 0)
    launched = one(seen, "subagent_launched").details
    assert (launched.name, launched.key, launched.parent, launched.depth, launched.goal) == (PAIR, pair_key(PAIR), "root", 1, f"Find the list prices for {PAIR}.")
    assert (launched.done_criteria, launched.done_criteria_omitted, launched.context, launched.tools) == (("Every price has a source URL",), 0, (), ())
    staged = one(seen, "memory_staged").details
    assert (staged.key, staged.kind, staged.text, staged.supersedes) == ("s1", InfiniteEntryKind.FACT, FACT, None)
    written = one(seen, "file_written").details
    assert (written.path, written.change, written.added_chars, written.excerpt, written.description) == (NOTE_PATH, InfiniteFileChange.CREATED, len(NOTE_TEXT), NOTE_TEXT, NOTE_DESCRIPTION)
    produced = one(seen, "generator_finished").details
    assert (produced.status, produced.stop_reason, produced.summary, produced.tool_calls) == (InfiniteResultStatus.DONE, "final_response", GEN_SUMMARY, 2)
    assert isinstance(produced.duration_ms, int) and produced.duration_ms >= 0

    card = finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]
    finished = one(seen, "subagent_finished").details
    assert (finished.name, finished.key, finished.status, finished.verdict, finished.review) == (PAIR, pair_key(PAIR), InfiniteResultStatus.DONE, InfiniteVerdict.PASSED, cut(card["review"], TEXT_MAX))
    assert finished.committed == (InfiniteCommittedEntry(staged_key="s1", entry_id=card["entries"][0], kind=InfiniteEntryKind.FACT, text=FACT),)
    assert (finished.committed_omitted, finished.dropped, finished.dropped_omitted, finished.files, finished.files_omitted) == (0, (), 0, (NOTE_PATH,), 0)
    ended = one(seen, "run_finished").details
    assert (ended.stop_reason, ended.answer, ended.pairs, ended.agents) == ("final_response", ROOT_ANSWER, 1, 2)
    # The scripted model is unpriced, so the cost is unknown everywhere: None, never 0.0 (D-18).
    assert agent.get_usage().cost_complete is False
    assert (produced.cost_usd, finished.cost_usd, ended.cost_usd) == (None, None, None)
    assert_portable(seen)


def test_the_roots_entry_is_announced_once_by_memory_saved_before_its_next_model_call(tmp_path: Path) -> None:
    """AC-3, INV-17, D-15: the root's remember gives one memory_saved with the entry's id, kind, text, tags, refs, and supersedes before the root's next call; the pair's entry is reported only in subagent_finished."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteEntryKind

    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(7, "Compare annual list prices", kind="decision")])
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    kinds_at_next_call: list[list[str]] = []

    def look(call: ModelCall) -> None:
        kinds_at_next_call.append(kinds(seen))

    decision = {"kind": "decision", "text": "Compare monthly list prices only", "tags": ["pricing", "scope"], "refs": ["notes/plan.md"], "supersedes": 7}
    tree = ScriptedTree(
        {
            ROOT: [tool_call("remember", decision), observe(look, launch(task(PAIR))), answer_with("done")],
            generator(PAIR): [tool_call("remember", {"kind": "fact", "text": FACT}), answer_with(GEN_SUMMARY)],
            verifier(PAIR): [answer_with(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds_at_next_call == [["run_started", "memory_saved"]]
    saved = one(seen, "memory_saved")
    assert (saved.agent_key, saved.role, saved.depth) == ("root", InfiniteAgentRole.ROOT, 0)
    details = saved.details
    assert (details.id, details.kind, details.text, details.tags, details.refs, details.supersedes) == (8, InfiniteEntryKind.DECISION, decision["text"], ("pricing", "scope"), ("notes/plan.md",), 7)
    assert saved.summary == f"Memory #8 (decision): {decision['text']}"
    assert [entry["id"] for entry in read_jsonl(root / "entries.jsonl")] == [8, 9]
    finished = one(seen, "subagent_finished").details
    assert [(item.entry_id, item.text) for item in finished.committed] == [(9, FACT)]
    assert_portable(seen)


# ---------------------------------------------------------------- AC-4, AC-26, AC-29: the sink never changes the run


def test_a_sink_that_always_raises_changes_nothing_and_each_failure_is_logged_once_without_text(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-4, INV-7, D-3: with a sink that raises RuntimeError on every call, the reply, the workspace and journal (run id and stamps replaced), and every model call equal the list-sink run's; each event is attempted and logged once at WARNING with the run id, kind, and RuntimeError only."""
    caplog.set_level(logging.WARNING, logger=EVENTS_LOGGER)
    seen, listed_id, listed, listed_tree = _compare_with_list_sink(tmp_path / "listed")
    assert event_warnings(caplog) == [], "a list sink must not log"
    raising_base = tmp_path / "raising"
    raising_base.mkdir()
    attempted: list[str] = []

    def broken(event: Any) -> None:
        attempted.append(event.kind.value)
        raise RuntimeError("SINK-BROKE-7731: the dashboard is offline")

    agent = build_agent(raising_base, on_event=broken)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    run_id = answer.metadata["infinite_run_id"]
    assert answer.content == listed.content
    assert run_view(workspace_root(raising_base), raising_base, run_id) == run_view(workspace_root(tmp_path / "listed"), tmp_path / "listed", listed_id)
    assert calls_view(tree, raising_base, run_id) == calls_view(listed_tree, tmp_path / "listed", listed_id)
    assert attempted == kinds(seen), "every later event must still reach the sink"
    logged = event_warnings(caplog)
    assert [record.getMessage() for record in logged] == [f"infinite_event_failed run_id={run_id} kind={kind} error_type=RuntimeError" for kind in kinds(seen)]
    assert all(record.levelno == logging.WARNING and record.exc_info is None and not record.exc_text for record in logged), "the log must not carry the exception or its traceback"


def test_each_event_is_delivered_after_the_change_it_reports_is_on_disk(tmp_path: Path) -> None:
    """AC-26, INV-4: a sink that reads the disk finds the run_started, pair_started, pair_finished, and run_finished records, the saved entry, and the written note (with its files.jsonl line) already there when each event arrives."""
    root = workspace_root(tmp_path)
    checks: list[tuple[str, bool]] = []

    def inspect_disk(event: Any) -> None:
        journal = root / ".runs" / f"{event.run_id}.jsonl"
        records = [(record["event"], record.get("key")) for record in read_jsonl(journal)] if journal.is_file() else []
        kind = event.kind.value
        if kind == "run_started":
            checks.append((kind, records[:1] == [("run_started", None)]))
        elif kind == "subagent_launched":
            checks.append((kind, ("pair_started", event.details.key) in records))
        elif kind == "memory_saved":
            checks.append((kind, event.details.id in [entry["id"] for entry in read_jsonl(root / "entries.jsonl")]))
        elif kind == "file_written":
            described = [record["path"] for record in read_jsonl(root / "files.jsonl")]
            checks.append((kind, NOTE_TEXT in (root / event.details.path).read_text(encoding="utf-8") and event.details.path in described))
        elif kind == "subagent_finished":
            checks.append((kind, ("pair_finished", event.details.key) in records))
        elif kind == "run_finished":
            checks.append((kind, records[-1:] == [("run_finished", None)]))

    agent = build_agent(tmp_path, on_event=inspect_disk)
    tree = ScriptedTree(
        {
            ROOT: [tool_call("remember", {"kind": "decision", "text": "Compare monthly list prices only"}), launch(task(PAIR)), answer_with(ROOT_ANSWER)],
            generator(PAIR): [tool_call("remember", {"kind": "fact", "text": FACT}), tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}), answer_with(GEN_SUMMARY)],
            verifier(PAIR): [answer_with(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert checks == [(kind, True) for kind in ("run_started", "memory_saved", "subagent_launched", "file_written", "subagent_finished", "run_finished")]


def test_a_sink_that_returns_a_coroutine_has_it_closed_and_logged_as_a_type_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-29 (a), INV-36, EC-32, D-27: every coroutine a plain sink returns is closed, never awaited, so no never-awaited warning appears; each event logs one TypeError warning, and the run equals the list-sink run."""
    caplog.set_level(logging.WARNING, logger=EVENTS_LOGGER)
    seen, listed_id, listed, _ = _compare_with_list_sink(tmp_path / "listed")
    base = tmp_path / "coroutine"
    base.mkdir()
    received: list[Any] = []
    returned: list[Any] = []

    async def forward(event: Any) -> None:
        received.append(event)

    def sink(event: Any) -> Any:
        coroutine = forward(event)
        returned.append(coroutine)
        return coroutine

    agent = build_agent(base, on_event=sink)
    tree = ac2_tree()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with tree.install():
            answer = agent.run(TASK)
        states = [inspect.getcoroutinestate(coroutine) for coroutine in returned]
        returned.clear()
        gc.collect()
    tree.assert_complete()
    run_id = answer.metadata["infinite_run_id"]
    assert states == [inspect.CORO_CLOSED] * len(seen), states
    assert received == [], "a returned coroutine must never be awaited"
    assert not [warning for warning in caught if "never awaited" in str(warning.message)]
    assert [record.getMessage() for record in event_warnings(caplog)] == [f"infinite_event_failed run_id={run_id} kind={kind} error_type=TypeError" for kind in kinds(seen)]
    assert answer.content == listed.content
    assert run_view(workspace_root(base), base, run_id) == run_view(workspace_root(tmp_path / "listed"), tmp_path / "listed", listed_id)


def test_a_sink_that_returns_a_task_it_scheduled_is_not_a_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-29 (b), INV-36: a sink that schedules its coroutine and returns the task is a working hand-off: the events logger logs nothing and the run equals the list-sink run."""
    caplog.set_level(logging.WARNING, logger=EVENTS_LOGGER)
    _, listed_id, listed, _ = _compare_with_list_sink(tmp_path / "listed")
    base = tmp_path / "scheduled"
    base.mkdir()
    received: list[Any] = []
    tasks: list[asyncio.Future[None]] = []

    async def forward(event: Any) -> None:
        received.append(event)

    def sink(event: Any) -> asyncio.Future[None]:
        tasks.append(asyncio.ensure_future(forward(event)))
        return tasks[-1]

    agent = build_agent(base, on_event=sink)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    run_id = answer.metadata["infinite_run_id"]
    assert len(tasks) == len(AC2_KINDS), "the sink was not called once per event"
    assert event_warnings(caplog) == []
    assert answer.content == listed.content
    assert run_view(workspace_root(base), base, run_id) == run_view(workspace_root(tmp_path / "listed"), tmp_path / "listed", listed_id)


# ---------------------------------------------------------------- AC-20, AC-23, AC-25


def test_without_a_sink_the_journal_gains_only_answer_and_files_and_nothing_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-20, INV-9, INV-26, D-11: with on_event left at None, each journal record has exactly its documented keys (run_finished adds answer and files), the events module logs nothing, and the reply carries infinite_run_id."""
    caplog.set_level(logging.DEBUG, logger=EVENTS_LOGGER)
    agent = build_agent(tmp_path)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    root = workspace_root(tmp_path)
    records = journal_records(root)
    assert [(record["event"], sorted(record)) for record in records] == [
        ("run_started", ["at", "event", "run", "task"]),
        ("pair_started", ["at", "event", "key"]),
        ("pair_finished", ["at", "card", "event", "key"]),
        ("run_finished", ["answer", "at", "event", "files", "stop_reason"]),
    ]
    assert (records[-1]["answer"], records[-1]["files"]) == (ROOT_ANSWER, []), "the root wrote no file in this script"
    assert event_warnings(caplog) == []
    assert answer.metadata["infinite_run_id"] == journal_paths(root)[0].stem


def test_without_a_sink_no_event_method_builds_an_event_or_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """NFR-2, INV-9: with on_event=None, each of the 14 public InfiniteEvents methods, one per event kind, returns before it reads its arguments, so no InfiniteEvent is built and the events module logs nothing."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.lib.dataclasses.infinite import InfiniteEvent
    from vidbyte.lib.enums.infinite import InfiniteEventKind

    built: list[InfiniteEvent] = []
    validate = InfiniteEvent.__post_init__

    def counted(event: InfiniteEvent) -> None:
        # Count each envelope built, then run the record's own checks unchanged.
        built.append(event)
        validate(event)

    monkeypatch.setattr(InfiniteEvent, "__post_init__", counted)
    caplog.set_level(logging.DEBUG, logger=EVENTS_LOGGER)
    events = InfiniteEvents(None, RUN_A)
    public = sorted(name for name, _ in inspect.getmembers(InfiniteEvents, inspect.isfunction) if not name.startswith("_"))
    assert public == sorted(kind.value for kind in InfiniteEventKind)
    # A method that got past its no-sink return would either trip over a placeholder inside its shield, which logs a warning, or build an event, which is counted.
    for name in public:
        method = getattr(events, name)
        method(*(object() for _ in inspect.signature(method).parameters))
    assert built == []
    assert event_warnings(caplog) == []


def test_token_totals_come_from_the_scripted_usage_and_match_get_usage(tmp_path: Path) -> None:
    """AC-23, INV-31, D-18: generator_finished counts the generator's scripted tokens, subagent_finished the generator's plus the verifier's, and run_finished equals agent.get_usage().total_tokens."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [tool_call("launch_subagent", {"tasks": [task(PAIR)]}, usage=_usage(1_000, 100)), answer_with(ROOT_ANSWER, usage=_usage(2_000, 200))],
            generator(PAIR): [
                tool_call("remember", {"kind": "fact", "text": FACT}, usage=_usage(200, 20)),
                tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}, usage=_usage(300, 30)),
                answer_with(GEN_SUMMARY, usage=_usage(400, 40)),
            ],
            verifier(PAIR): [answer_with(PASSED, usage=_usage(50, 5))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert one(seen, "generator_finished").details.tokens == 220 + 330 + 440
    assert one(seen, "subagent_finished").details.tokens == 220 + 330 + 440 + 55
    total = one(seen, "run_finished").details.tokens
    assert total == agent.get_usage().total_tokens == 1_100 + 2_200 + 990 + 55
    assert_portable(seen)


def test_bash_grep_and_read_lines_deliver_no_event_and_no_event_carries_their_output_or_secrets(tmp_path: Path) -> None:
    """AC-25, INV-10: bash, grep, and read_lines calls by the root and by a pair deliver no event; no event carries their output, the API key, the system prompt, or the tmp folder's absolute path."""
    secret = "sk-live-EVENTS-SECRET-0123456789"
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append, api_keys=[secret])
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("bash", {"command": "echo BASH-OUT-7731 > memory/bash-notes.md && echo BASH-OUT-7731"}),
                tool_call("grep", {"pattern": "BASH-OUT"}),
                tool_call("read_lines", {"path": "bash-notes.md"}),
                launch(task(PAIR)),
                answer_with(ROOT_ANSWER),
            ],
            generator(PAIR): [tool_call("bash", {"command": "echo GEN-BASH-7731"}), tool_call("grep", {"pattern": "BASH-OUT"}), answer_with(GEN_SUMMARY)],
            verifier(PAIR): [tool_call("read_lines", {"path": "bash-notes.md"}), answer_with(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    root_calls = tree.calls_by(ROOT)
    assert "BASH-OUT-7731" in tool_result(root_calls[1], "bash") and not is_error(tool_result(root_calls[3], "read_lines")), "the tools must really run for this test to mean anything"
    assert kinds(seen) == ["run_started", "subagent_launched", "generator_finished", "subagent_finished", "run_finished"]
    texts = [text for event in seen for text in _texts(dataclasses.asdict(event))]
    forbidden = ("BASH-OUT-7731", "GEN-BASH-7731", secret, SYSTEM_PROMPT, str(tmp_path), tmp_path.as_posix())
    assert not [(needle, text) for needle in forbidden for text in texts if needle in text]
    assert_portable(seen)


# ---------------------------------------------------------------- AC-15, EC-5, EC-2


def test_every_reply_names_its_journal_in_infinite_run_id(tmp_path: Path) -> None:
    """AC-15, INV-21, INV-29: run(), arun(), and resume(<id>) on one agent each return infinite_run_id equal to their journal's stem (the resume's equals the id passed), and stop_reason keeps its value."""
    root = workspace_root(tmp_path)
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK)])
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [answer_with("FIRST"), answer_with("SECOND"), answer_with("RESUMED")]})
    with tree.install():
        known = set(journal_paths(root))
        first = agent.run(TASK)
        (first_path,) = set(journal_paths(root)) - known
        known = set(journal_paths(root))
        second = asyncio.run(agent.arun(TASK))
        (second_path,) = set(journal_paths(root)) - known
        resumed = agent.resume(RUN_A)
    tree.assert_complete()
    for reply_, path in ((first, first_path), (second, second_path), (resumed, root / ".runs" / f"{RUN_A}.jsonl")):
        assert reply_.metadata["infinite_run_id"] == path.stem
        assert reply_.metadata["stop_reason"] == read_jsonl(path)[-1]["stop_reason"] == "final_response"
    assert resumed.metadata["infinite_run_id"] == RUN_A


def test_a_run_refused_before_its_journal_delivers_no_event(tmp_path: Path) -> None:
    """EC-5, INV-1: a malformed, unknown, or missing resume id and a reserved tool name each refuse the run before a journal opens, and the sink receives nothing."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({})
    with tree.install():
        for run_id in ("../x", RUN_B, None):
            with pytest.raises(VidbyteSdkError):
                agent.resume(run_id)
        agent.add_tool(foreign_remember)
        with pytest.raises(VidbyteSdkError):
            agent.run(TASK)
    assert seen == []
    assert tree.calls == [] and journal_paths(workspace_root(tmp_path)) == []


def test_a_keyboard_interrupt_raised_by_the_sink_is_not_swallowed(tmp_path: Path) -> None:
    """INV-7, EC-2, D-3: the shield catches Exception only, so a KeyboardInterrupt raised by the sink on run_started stops the run before any model call and leaves it unfinished."""
    delivered: list[str] = []

    def interrupt(event: Any) -> None:
        delivered.append(event.kind.value)
        raise KeyboardInterrupt

    agent = build_agent(tmp_path, on_event=interrupt)
    tree = ScriptedTree({})
    with tree.install(), pytest.raises(KeyboardInterrupt):
        agent.run(TASK)
    assert delivered[:1] == ["run_started"]
    assert tree.calls == []
    assert "run_finished" not in [record["event"] for record in journal_records(workspace_root(tmp_path))]
