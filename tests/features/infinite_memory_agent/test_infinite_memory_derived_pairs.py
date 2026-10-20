"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py

PURPOSE: Proves the derived events of pairs and launches: memory_committed per committed entry after it is on disk, rule and unchecked drops under the right agent, verifier_started and verifier_finished with their counts and usage, the quota fields equal to the quota line the model read, the batch offset, index, size, attempt, and tree counters on subagent_launched and subagent_finished, batch_finished totals (and none for a batch of replays or a pipeline that raises), subagent_aborted for a cancellation, a defect in the pair's own commit step, and an interrupt raised by the sink, the original error class on a child's failed card, and in_flight counting each pair once.
ROLE IN CODEBASE: Pair-and-launch layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-derived-events/spec.md (AC-3, AC-4, AC-5, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14; INV-3, INV-4, INV-9, INV-10, INV-15, INV-16; EC-2, EC-5, EC-10, EC-16, EC-20, EC-24, EC-25, EC-26, EC-27; FR-1, FR-2, FR-4, FR-5, FR-8..FR-12; D-6..D-10, D-16, D-18, D-20, D-22). Exercises vidbyte/agents/infinite/launch.py, memory.py, journal.py, and events.py.
ARCHITECTURE NOTE: Only the model runner is scripted; the workspace, journal, ParallelPipeline, and disk are real. Two seams are touched on purpose and nowhere else: the AC-13 tests wrap InfiniteWorkspace.commit_entry so that one call raises RuntimeError after delegating every other call to the real method, because spec section 13 names that the one way pair-owned code can raise past its card; and the EC-10 sink raises KeyboardInterrupt, which is the scenario itself. Sinks only record (the AC-3 sink also sets a Signal, and the INV-4 sink reads entries.jsonl at delivery time); every assertion runs after the run.
FUNCTION INVENTORY: test_each_committed_entry_is_announced_in_staged_order_after_it_is_on_disk (AC-5, FR-2, INV-4, INV-9, D-18); test_an_entry_a_sibling_committed_first_is_dropped_by_rule_while_the_rest_commit (AC-3, FR-1, EC-20, INV-15); test_unchecked_entries_drop_under_the_last_agent_that_ran (AC-4 a, b; D-18, D-20); test_verifier_started_and_finished_carry_the_staged_count_the_notes_the_verdict_and_the_usage (FR-9, FR-10, D-6); test_each_quota_carrying_event_equals_the_quota_line_the_model_read (AC-9, FR-4); test_a_batch_beside_a_replay_announces_its_offset_index_counters_and_verdict_totals (AC-10, EC-5, D-7, D-9); test_a_pair_launched_again_after_a_resume_counts_a_second_attempt_and_continues_the_offset (AC-11, EC-16, D-8, D-16); test_a_cancelled_flat_generator_announces_its_abort_before_run_stopped (AC-12, INV-3, INV-15); test_an_error_in_the_pairs_own_commit_step_is_announced_and_the_run_goes_on (AC-13, EC-2, EC-26, INV-10); test_an_aborted_pair_re_raises_the_very_error_it_announced (INV-3, D-10); test_a_sink_interrupt_while_an_abort_is_announced_propagates_in_place_of_the_error (INV-3's exception); test_an_aborted_pair_with_a_long_key_carries_the_key_its_launch_carried (EC-24); test_a_child_agents_error_becomes_the_card_and_names_its_original_class (AC-14, EC-27, D-22); test_in_flight_counts_each_pair_once_and_never_goes_below_zero (INV-16, D-9, EC-10, EC-25); test_an_interrupt_the_sink_raises_on_subagent_finished_gives_one_abort_in_the_commit_phase (EC-10, INV-3, INV-10). _remember, _usage, _pair, _quota, _flaky_commit, and _cancel_while_alpha_waits are small builders.
COMMON MODIFICATION PATTERNS: A new pair or launch event gets one test here that scripts the pair, asserts the exact kinds list (or the pair's own subsequence when sibling pairs interleave), and checks its details against the journal, entries.jsonl, or the text the model read.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert inside a sink. 3. Do not pin the interleaving of two sibling pairs' events; pin each pair's own order and the batch's closing event. 4. Do not mock the journal, the pipeline, or the workspace beyond the one commit_entry fault the spec names.
KNOWN EDGE CASES: The scripted model is unpriced, so every cost_usd is None; scripted usage needs total_tokens for a token count (the fixture's DEFAULT_USAGE has none and counts 0). A KeyboardInterrupt raised inside a pair's task leaves the loop at once, and asyncio then cancels the root's task, so EC-10's run_stopped names CancelledError. The verifier_started summary's {files} could mean the notes written or the notes shown, which the spec does not settle, so that one summary accepts both counts (test-plan OPEN ITEM).
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-derived-events/spec.md sections 6.1, 6.2, 6.3, 8.1, 9.1, 9.2 and 13; docs/spec/infinite-memory-derived-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py -q
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    FACT,
    GEN_SUMMARY,
    LABEL_MAX,
    NOTE_DESCRIPTION,
    NOTE_PATH,
    NOTE_TEXT,
    PAIR,
    PASSED,
    assert_portable,
    cut,
    kinds,
    of_kind,
    one,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    TASK,
    ModelCall,
    ScriptedTree,
    Signal,
    after,
    build_agent,
    build_settings,
    card_record,
    entry_record,
    events,
    fail,
    finished_cards,
    generator,
    is_error,
    journal_records,
    launch,
    observe,
    pair_finished_record,
    pair_key,
    pair_started_record,
    prompt_text,
    read_jsonl,
    reply,
    run_started_record,
    simple_pair,
    task,
    tool_call,
    tool_result,
    verifier,
    workspace_root,
    write_journal,
    write_jsonl,
)

SECOND = "Globex charges 59 USD per seat"
UNCHECKED_NOTE = "not committed, because the verdict is unchecked"
FAILED_REVIEW = "Two prices have no source.\nVERDICT: failed"
FAULT = "entries disk controller fault"


def _remember(text: str, kind: str = "fact", supersedes: int | None = None) -> Any:
    args: dict[str, Any] = {"kind": kind, "text": text}
    if supersedes is not None:
        args["supersedes"] = supersedes
    return tool_call("remember", args)


def _usage(input_tokens: int, output_tokens: int) -> dict[str, int]:
    # Scripted usage with its total, because the rollup's total_tokens stays None without one.
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}


def _pair(seen: list[Any], name: str) -> list[Any]:
    """The events of root-level pair `name`: its launch and end (by details.key) and every event of its two agents."""
    key = pair_key(name)
    own = ("subagent_launched", "subagent_finished", "subagent_aborted")
    return [event for event in seen if (event.kind.value in own and event.details.key == key) or event.agent_key.startswith(f"{key}/")]


def _quota(content: str) -> tuple[int, int, int, int]:
    """The four numbers of the quota line in a tool result, read with the catalog's quota_line template."""
    template = prompt_text("quota_line").strip()
    pattern = re.escape(template)
    for name in ("entries_left", "entries_max", "files_left", "files_max"):
        pattern = pattern.replace(re.escape("{" + name + "}"), rf"(?P<{name}>\d+)")
    found = re.search(pattern, content)
    assert found, f"no quota line in {content!r}"
    return (int(found["entries_left"]), int(found["entries_max"]), int(found["files_left"]), int(found["files_max"]))


def _flaky_commit(monkeypatch: pytest.MonkeyPatch, fail_on: int, error: BaseException) -> list[int]:
    """Spec section 13's one seam: the `fail_on`-th InfiniteWorkspace.commit_entry call raises `error`; every other call runs the real method."""
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace

    real = InfiniteWorkspace.commit_entry
    calls: list[int] = []

    def commit_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(len(calls) + 1)
        if len(calls) == fail_on:
            raise error
        return real(self, *args, **kwargs)

    monkeypatch.setattr(InfiniteWorkspace, "commit_entry", commit_entry)
    return calls


# ---------------------------------------------------------------- AC-5, AC-3, AC-4: commits and drops


def test_each_committed_entry_is_announced_in_staged_order_after_it_is_on_disk(tmp_path: Path) -> None:
    """AC-5, FR-2, INV-4, INV-9, D-18: a pair that commits three entries, one superseding seeded #7, gives exactly three memory_committed events after verifier_finished and before subagent_finished, in staged order, each from the verifier, with the id entries.jsonl holds for its text, its staged key, kind, text, and supersedes, and each delivered only once its entry was in entries.jsonl."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteEntryKind

    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(7, "Acme charges 39 USD per seat")])
    decision = "Compare monthly list prices only"
    on_disk: list[tuple[int, bool]] = []
    seen: list[Any] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "memory_committed":
            on_disk.append((event.details.id, event.details.id in {record["id"] for record in read_jsonl(root / "entries.jsonl")}))

    agent = build_agent(tmp_path, on_event=sink)
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [_remember(FACT, supersedes=7), _remember(SECOND), _remember(decision, kind="decision"), reply(GEN_SUMMARY)],
            verifier(PAIR): [reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == [
        "run_started",
        "subagent_launched",
        "memory_staged",
        "memory_staged",
        "memory_staged",
        "generator_finished",
        "verifier_started",
        "verifier_finished",
        "memory_committed",
        "memory_committed",
        "memory_committed",
        "subagent_finished",
        "batch_finished",
        "run_finished",
    ]
    records = {record["text"]: record for record in read_jsonl(root / "entries.jsonl")}
    committed = of_kind(seen, "memory_committed")
    expected = [("s1", FACT, InfiniteEntryKind.FACT, 7), ("s2", SECOND, InfiniteEntryKind.FACT, None), ("s3", decision, InfiniteEntryKind.DECISION, None)]
    assert [(event.details.key, event.details.text, event.details.kind, event.details.supersedes) for event in committed] == expected
    assert [event.details.id for event in committed] == [records[text]["id"] for _, text, _, _ in expected]
    ver = f"{pair_key(PAIR)}/ver"
    assert all((event.agent_key, event.role, event.depth) == (ver, InfiniteAgentRole.VERIFIER, 1) for event in committed)
    assert {records[text]["verified_by"] for _, text, _, _ in expected} == {ver}
    assert on_disk == [(event.details.id, True) for event in committed], "memory_committed arrived before its entry was in entries.jsonl (INV-4)"
    assert [event.summary for event in committed] == [f"{PAIR}/ver committed {key} as memory #{records[text]['id']} ({kind.value}): {text}" for key, text, kind, _ in expected]
    card = finished_cards(root)[pair_key(PAIR)]
    assert card["entries"] == [event.details.id for event in committed], "one memory_committed per card entry (INV-9)"
    assert_portable(seen)


def test_an_entry_a_sibling_committed_first_is_dropped_by_rule_while_the_rest_commit(tmp_path: Path) -> None:
    """AC-3, FR-1, EC-20, INV-15: when sibling a commits the shared text first, pair b's events run launched, staged, staged, generator_finished, verifier_started, verifier_finished, memory_dropped (s1, rule, the rule's message as note, from b's verifier), memory_committed (s2), subagent_finished, and the batch closes once after both pairs."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteDropReason

    shared = "Initech charges 30 USD per seat"
    unique = "Hooli charges 75 USD per seat"
    seen: list[Any] = []
    a_finished = Signal("pair a's subagent_finished")
    b_staged = Signal("pair b staged both entries")

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "subagent_finished" and event.details.key == pair_key("a"):
            a_finished.set()

    def staged(call: ModelCall) -> None:
        b_staged.set()

    agent = build_agent(tmp_path, on_event=sink)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a"), task("b")), reply("done")],
            generator("a"): [_remember(shared), reply("A-SUMMARY")],
            generator("b"): [_remember(shared), _remember(unique), observe(staged, reply("B-SUMMARY"))],
            verifier("a"): [after(b_staged, reply(PASSED))],
            verifier("b"): [after(a_finished, reply(PASSED))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    late = _pair(seen, "b")
    assert kinds(late) == ["subagent_launched", "memory_staged", "memory_staged", "generator_finished", "verifier_started", "verifier_finished", "memory_dropped", "memory_committed", "subagent_finished"]
    cards = finished_cards(workspace_root(tmp_path))
    (line_text,) = cards[pair_key("b")]["dropped"]
    note = line_text.removeprefix(f"s1 ({shared}): ")
    assert note.startswith(f"This text is already recorded as #{cards[pair_key('a')]['entries'][0]}"), note
    dropped, committed = one(late, "memory_dropped"), one(late, "memory_committed")
    ver = f"{pair_key('b')}/ver"
    assert (dropped.agent_key, dropped.role, dropped.depth) == (ver, InfiniteAgentRole.VERIFIER, 1)
    assert (dropped.details.key, dropped.details.text, dropped.details.reason, dropped.details.note) == ("s1", shared, InfiniteDropReason.RULE, cut(note, LABEL_MAX))
    assert (committed.agent_key, committed.details.key, committed.details.text, committed.details.id) == (ver, "s2", unique, cards[pair_key("b")]["entries"][0])
    assert kinds(seen)[-2:] == ["batch_finished", "run_finished"] and kinds(seen).count("batch_finished") == 1
    assert_portable(seen)


@pytest.mark.parametrize("case", ["no-verdict", "blank-generator"])
def test_unchecked_entries_drop_under_the_last_agent_that_ran(tmp_path: Path, case: str) -> None:
    """AC-4 (a, b), D-18, D-20: (a) a verifier with no VERDICT line gives verifier_finished(unchecked) and then one memory_dropped(unchecked) per staged entry from the verifier; (b) a blank generator reply gives no verifier events and the drops come from the generator; both drops precede subagent_finished, and their count equals the card's dropped list (INV-9)."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteDropReason, InfiniteVerdict

    scripts: dict[str, list[Any]] = {ROOT: [launch(task(PAIR)), reply("done")]}
    if case == "no-verdict":
        scripts[generator(PAIR)] = [_remember(FACT), _remember(SECOND), reply(GEN_SUMMARY)]
        scripts[verifier(PAIR)] = [reply("Looks fine to me, nothing to add.")]
        middle = ["generator_finished", "verifier_started", "verifier_finished"]
        agent_key, role = f"{pair_key(PAIR)}/ver", InfiniteAgentRole.VERIFIER
    else:
        scripts[generator(PAIR)] = [_remember(FACT), _remember(SECOND), reply("")]
        middle = ["generator_finished"]
        agent_key, role = f"{pair_key(PAIR)}/gen", InfiniteAgentRole.GENERATOR
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(scripts)
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "subagent_launched", "memory_staged", "memory_staged", *middle, "memory_dropped", "memory_dropped", "subagent_finished", "batch_finished", "run_finished"]
    if case == "no-verdict":
        assert one(seen, "verifier_finished").details.verdict is InfiniteVerdict.UNCHECKED
    drops = of_kind(seen, "memory_dropped")
    assert [(event.agent_key, event.role, event.depth) for event in drops] == [(agent_key, role, 1)] * 2
    assert [(event.details.key, event.details.text, event.details.reason, event.details.note) for event in drops] == [("s1", FACT, InfiniteDropReason.UNCHECKED, UNCHECKED_NOTE), ("s2", SECOND, InfiniteDropReason.UNCHECKED, UNCHECKED_NOTE)]
    assert len(finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]["dropped"]) == len(drops)
    assert_portable(seen)


# ---------------------------------------------------------------- FR-9, FR-10, AC-9: the verifier's step and quotas


def test_verifier_started_and_finished_carry_the_staged_count_the_notes_the_verdict_and_the_usage(tmp_path: Path) -> None:
    """FR-9, FR-10, D-6, section 9.1: after a generator stages 2 entries and writes 7 notes, verifier_started carries staged 2, the first 5 notes in write order and files_omitted 2; a verifier that drops one entry and replies "fixed" gives verifier_finished with verdict fixed, stop reason final_response, 1 tool call, its own 33 scripted tokens, an unknown cost, and a duration; both come from the verifier."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteVerdict

    notes = [f"notes/n{index}.md" for index in range(1, 8)]
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [
                _remember(FACT),
                _remember(SECOND),
                *(tool_call("write_note", {"path": path, "text": f"Finding {path}.\n", "description": f"Notes {path}"}) for path in notes),
                reply(GEN_SUMMARY),
            ],
            verifier(PAIR): [tool_call("drop_entry", {"id": "s1"}, usage=_usage(8, 3)), reply("Dropped the unsourced entry.\nVERDICT: fixed", usage=_usage(20, 2))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    started, finished = one(seen, "verifier_started"), one(seen, "verifier_finished")
    ver = (f"{pair_key(PAIR)}/ver", InfiniteAgentRole.VERIFIER, 1)
    assert (started.agent_key, started.role, started.depth) == ver == (finished.agent_key, finished.role, finished.depth)
    assert (started.details.staged, started.details.files, started.details.files_omitted) == (2, tuple(notes[:5]), 2)
    assert started.summary in {f"{PAIR}/ver is checking 2 staged entries and {count} notes" for count in (7, 5)}, started.summary
    details = finished.details
    assert (details.verdict, details.stop_reason, details.tool_calls, details.tokens, details.cost_usd) == (InfiniteVerdict.FIXED, "final_response", 1, 33, None)
    assert isinstance(details.duration_ms, int) and details.duration_ms >= 0
    assert finished.summary == f"{PAIR}/ver: verdict fixed"
    assert kinds(seen).index("verifier_started") < kinds(seen).index("memory_dropped") < kinds(seen).index("verifier_finished")
    assert_portable(seen)


def test_each_quota_carrying_event_equals_the_quota_line_the_model_read(tmp_path: Path) -> None:
    """AC-9, FR-4: memory_saved (root remember), memory_staged (generator remember), and file_written (generator creates a note) carry entries_left, entries_max, files_left, and files_max equal to the quota line in the result the model read for that call: 24 of 25 and 10 of 10, 24 of 25 and 10 of 10, then 24 of 25 and 9 of 10."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [_remember("Compare monthly list prices only", kind="decision"), launch(task(PAIR)), reply("done")],
            generator(PAIR): [
                _remember(FACT),
                tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}),
                reply(GEN_SUMMARY),
            ],
            verifier(PAIR): [reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    read = {
        "memory_saved": _quota(tool_result(tree.calls_by(ROOT)[1], "remember")),
        "memory_staged": _quota(tool_result(tree.calls_by(generator(PAIR))[1], "remember")),
        "file_written": _quota(tool_result(tree.calls_by(generator(PAIR))[2], "write_note")),
    }
    assert read == {"memory_saved": (24, 25, 10, 10), "memory_staged": (24, 25, 10, 10), "file_written": (24, 25, 9, 10)}, "precondition: the quota lines the model read"
    for kind, numbers in read.items():
        details = one(seen, kind).details
        assert (details.entries_left, details.entries_max, details.files_left, details.files_max) == numbers, kind
    assert_portable(seen)


# ---------------------------------------------------------------- AC-10, AC-11: batches, attempts, counters


def test_a_batch_beside_a_replay_announces_its_offset_index_counters_and_verdict_totals(tmp_path: Path) -> None:
    """AC-10, EC-5, D-7, D-9: launching a, then a+b+c, then a again gives subagent_launched a (batch 0, index 0 of 1), b (batch 1, index 0 of 2, 4 agents started, 1 in flight) and c (batch 1, index 1 of 2, 6 agents, 2 in flight), all attempt 1 under max_agents 50; a replay before b; batch_finished for batch 0 (1 passed) and batch 1 (1 passed, 1 failed, 1 replayed) from the root; and no batch_finished for the batch made only of a replay."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    seen: list[Any] = []
    agent = build_agent(tmp_path, max_agents=50, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a")), launch(task("a"), task("b"), task("c")), launch(task("a")), reply("done")],
            **simple_pair("a", "A-SUMMARY"),
            **simple_pair("b", "B-SUMMARY"),
            **simple_pair("c", "C-SUMMARY", review=FAILED_REVIEW),
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    stream = kinds(seen)
    assert stream[:10] == ["run_started", "subagent_launched", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "subagent_replayed", "subagent_launched", "subagent_launched"]
    assert Counter(stream[10:18]) == Counter({"generator_finished": 2, "verifier_started": 2, "verifier_finished": 2, "subagent_finished": 2})
    assert stream[18:] == ["batch_finished", "subagent_replayed", "run_finished"]
    launched = {event.details.name: event.details for event in of_kind(seen, "subagent_launched")}
    counters = {name: (item.attempt, item.batch, item.batch_index, item.batch_size, item.agents_started, item.max_agents, item.in_flight) for name, item in launched.items()}
    assert counters == {"a": (1, 0, 0, 1, 2, 50, 1), "b": (1, 1, 0, 2, 4, 50, 1), "c": (1, 1, 1, 2, 6, 50, 2)}
    finished = of_kind(seen, "subagent_finished")
    assert [(event.details.error_type, event.details.agents_started, event.details.max_agents) for event in finished] == [("", 2, 50), ("", 6, 50), ("", 6, 50)]
    assert [event.details.in_flight for event in finished] == [0, 1, 0]
    batches = of_kind(seen, "batch_finished")
    assert [(event.agent_key, event.role, event.depth) for event in batches] == [("root", InfiniteAgentRole.ROOT, 0)] * 2
    totals = [(item.batch, item.passed, item.fixed, item.failed, item.unchecked, item.replayed) for item in (event.details for event in batches)]
    assert totals == [(0, 1, 0, 0, 0, 0), (1, 1, 0, 1, 0, 1)]
    assert all(isinstance(event.details.duration_ms, int) and event.details.duration_ms >= 0 for event in batches)
    assert [event.summary for event in batches] == ["root: batch 0 finished: 1 passed, 0 fixed, 0 failed, 0 unchecked, 0 replayed", "root: batch 1 finished: 1 passed, 0 fixed, 1 failed, 0 unchecked, 1 replayed"]
    assert_portable(seen)


def test_a_pair_launched_again_after_a_resume_counts_a_second_attempt_and_continues_the_offset(tmp_path: Path) -> None:
    """AC-11, EC-16, D-8, D-16: resuming a journal where a started and never finished and z finished, a relaunched a gives subagent_launched with attempt 2, batch 2 (the journal's start count), 6 agents started, and 1 in flight; its batch_finished says batch 2; run_finished counts the whole run's pairs (z and a both passed) and deepest 1, but this session's iterations and tool calls."""
    root = workspace_root(tmp_path)
    write_journal(
        root,
        RUN_A,
        [
            run_started_record(RUN_A, TASK),
            pair_started_record(pair_key("a")),
            pair_started_record(pair_key("z")),
            pair_finished_record(card_record("z", summary="Z-SUMMARY", review=PASSED)),
        ],
    )
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")], **simple_pair("a", "A-SUMMARY")})
    with tree.install():
        answer = agent.resume()
    tree.assert_complete()
    assert kinds(seen) == ["run_resumed", "subagent_launched", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "run_finished"]
    started = one(seen, "subagent_launched").details
    assert (started.attempt, started.batch, started.batch_index, started.batch_size, started.agents_started, started.in_flight) == (2, 2, 0, 1, 6, 1)
    assert one(seen, "batch_finished").details.batch == 2
    totals = one(seen, "run_finished").details
    assert (totals.passed, totals.fixed, totals.failed, totals.unchecked, totals.committed, totals.files, totals.deepest, totals.events_failed) == (2, 0, 0, 0, 0, 0, 1, 0)
    assert (totals.iterations, totals.tool_calls) == (answer.metadata["iteration_count"], answer.metadata["tool_call_count"]) == (2, 1)
    assert_portable(seen)


# ---------------------------------------------------------------- AC-12, AC-13, AC-14, EC-10: aborts and errors


async def _cancel_while_alpha_waits(agent: Any) -> None:
    """Starts arun, waits until pair alpha's generator has staged two entries and is waiting, cancels the run, and checks CancelledError propagates."""
    started = Signal("alpha's generator is waiting")
    never = Signal("a release that never comes")

    async def hold(call: ModelCall) -> object:
        started.set()
        await never.wait(call.agent)
        return reply("unreachable")

    tree = ScriptedTree({ROOT: [launch(task("alpha"))], generator("alpha"): [_remember(FACT), _remember(SECOND), hold]})
    with tree.install():
        running = asyncio.create_task(agent.arun(TASK))
        await started.wait("the test")
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    tree.assert_complete()


@pytest.mark.asyncio
async def test_a_cancelled_flat_generator_announces_its_abort_before_run_stopped(tmp_path: Path) -> None:
    """AC-12, INV-3, INV-15: cancelling the run while a depth-1 generator with two staged entries waits gives subagent_aborted (alpha, root/alpha, cancelled, CancelledError, phase generator, staged 2) from the root, right before run_stopped, and the CancelledError still propagates."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfinitePairPhase, InfiniteStopCause

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    await _cancel_while_alpha_waits(agent)
    assert kinds(seen) == ["run_started", "subagent_launched", "memory_staged", "memory_staged", "subagent_aborted", "run_stopped"]
    aborted = one(seen, "subagent_aborted")
    assert (aborted.agent_key, aborted.role, aborted.depth) == ("root", InfiniteAgentRole.ROOT, 0)
    details = aborted.details
    assert (details.name, details.key, details.reason, details.error_type, details.phase, details.staged) == ("alpha", pair_key("alpha"), InfiniteStopCause.CANCELLED, "CancelledError", InfinitePairPhase.GENERATOR, 2)
    assert aborted.summary == "alpha aborted (cancelled) in its generator step: CancelledError"
    assert "pair_finished" not in events(journal_records(workspace_root(tmp_path)))
    assert_portable(seen)


@pytest.mark.parametrize("fail_on", [1, 2], ids=["first-commit-fails", "second-commit-fails"])
def test_an_error_in_the_pairs_own_commit_step_is_announced_and_the_run_goes_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_on: int) -> None:
    """AC-13, EC-2, EC-26, INV-10: when the workspace commit raises RuntimeError on a passing pair's first (or second) staged entry, the entries already committed are announced, then subagent_aborted (failed, RuntimeError, phase commit, staged = entries still staged); the batch gets no batch_finished, the pair no subagent_finished or pair_finished, the root's launch_subagent result is the loop's "Tool execution failed: ..." error, and the run ends with run_finished."""
    from vidbyte.lib.enums.infinite import InfinitePairPhase, InfiniteStopCause

    calls = _flaky_commit(monkeypatch, fail_on, RuntimeError(FAULT))
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [_remember(FACT), _remember(SECOND), reply(GEN_SUMMARY)],
            verifier(PAIR): [reply(PASSED)],
        }
    )
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert len(calls) == fail_on, "precondition: the injected commit failure fired"
    commits = ["memory_committed"] * (fail_on - 1)
    assert kinds(seen) == ["run_started", "subagent_launched", "memory_staged", "memory_staged", "generator_finished", "verifier_started", "verifier_finished", *commits, "subagent_aborted", "run_finished"]
    details = one(seen, "subagent_aborted").details
    assert (details.name, details.key, details.reason, details.error_type, details.phase, details.staged) == (PAIR, pair_key(PAIR), InfiniteStopCause.FAILED, "RuntimeError", InfinitePairPhase.COMMIT, 2 - (fail_on - 1))
    result = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    assert is_error(result) and f"Tool execution failed: {FAULT}" in result, result
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "pair_started", "run_finished"]
    assert answer.content == "done"
    assert_portable(seen)


@pytest.mark.asyncio
async def test_an_aborted_pair_re_raises_the_very_error_it_announced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-3, D-10: InfinitePair.run, driven directly with a real launch tool, journal, and workspace, announces subagent_aborted for a commit that raises and then re-raises that same exception object, not a copy or a wrapper."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteTaskCard

    injected = RuntimeError(FAULT)
    _flaky_commit(monkeypatch, 1, injected)
    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []
    launch_tool = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=InfiniteEvents(seen.append, journal.run_id))
    card = InfiniteTaskCard(name=PAIR, goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    pair = InfinitePair(launch_tool, card, pair_key(PAIR))
    journal.pair_started(pair.key)
    tree = ScriptedTree({generator(PAIR): [_remember(FACT), reply(GEN_SUMMARY)], verifier(PAIR): [reply(PASSED)]})
    with tree.install(), pytest.raises(RuntimeError) as raised:
        await pair.run("")
    tree.assert_complete()
    assert raised.value is injected
    assert kinds(seen)[-1] == "subagent_aborted" and seen[-1].details.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_a_sink_interrupt_while_an_abort_is_announced_propagates_in_place_of_the_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-3 (its one exception), D-10: when the pair's own commit raises RuntimeError and the sink raises KeyboardInterrupt while handling that pair's subagent_aborted, the abort was offered once, naming RuntimeError, and the sink's KeyboardInterrupt object leaves InfinitePair.run in place of the RuntimeError."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteTaskCard

    _flaky_commit(monkeypatch, 1, RuntimeError(FAULT))
    seen: list[Any] = []
    interrupts: list[KeyboardInterrupt] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "subagent_aborted" and not interrupts:
            interrupts.append(KeyboardInterrupt("the developer pressed Ctrl-C in the sink"))
            raise interrupts[0]

    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    launch_tool = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=InfiniteEvents(sink, journal.run_id))
    card = InfiniteTaskCard(name=PAIR, goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    pair = InfinitePair(launch_tool, card, pair_key(PAIR))
    journal.pair_started(pair.key)
    tree = ScriptedTree({generator(PAIR): [_remember(FACT), reply(GEN_SUMMARY)], verifier(PAIR): [reply(PASSED)]})
    with tree.install(), pytest.raises(BaseException) as raised:
        await pair.run("")
    tree.assert_complete()
    assert kinds(seen).count("subagent_aborted") == 1 and kinds(seen)[-1] == "subagent_aborted", kinds(seen)
    assert seen[-1].details.error_type == "RuntimeError"
    assert raised.value is interrupts[0]


def test_an_aborted_pair_with_a_long_key_carries_the_key_its_launch_carried(tmp_path: Path) -> None:
    """EC-24, INV-8: for a pair whose key is 602 characters, subagent_aborted carries the same digest-shortened key as its subagent_launched, ~ + the first 16 hex digits of the key's SHA-256 + / + its last 490 characters (restated here with hashlib), and both events pass the portability check."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteTaskCard

    settings = build_settings(tmp_path, max_depth=10_000)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []
    writer = InfiniteEvents(seen.append, journal.run_id)
    launcher = "root" + "".join(f"/{name}/gen" for name in ["x" * 64] * 8 + ["y" * 39])
    launch_tool = InfiniteLaunchTool(settings, workspace, journal, key=launcher, depth=9, extras=(), events=writer)
    card = InfiniteTaskCard(name="a", goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    pair = InfinitePair(launch_tool, card, f"{launcher}/a")
    assert len(pair.key) == 602, "precondition: the pair key is over 508 characters"
    journal.pair_started(pair.key)
    writer.subagent_launched(launch_tool, card, 0, 0, 1)
    from vidbyte.lib.enums.infinite import InfinitePairPhase

    writer.subagent_aborted(pair, asyncio.CancelledError(), InfinitePairPhase.GENERATOR)
    assert kinds(seen) == ["subagent_launched", "subagent_aborted"]
    shortened = "~" + hashlib.sha256(pair.key.encode("ascii")).hexdigest()[:16] + "/" + pair.key[-490:]
    assert seen[1].details.key == seen[0].details.key == shortened
    assert_portable(seen)


def test_a_child_agents_error_becomes_the_card_and_names_its_original_class(tmp_path: Path) -> None:
    """AC-14, EC-27, D-22: generators whose runner raises ToolExecutionError and RuntimeError each end as a failed card, so their subagent_finished carries error_type ToolExecutionError and RuntimeError (the wrapper's cause, never AgentExecutionError), a passing sibling carries "", no subagent_aborted arrives, and the batch closes with 1 passed and 2 unchecked."""
    from vidbyte.lib.enums.infinite import InfiniteResultStatus, InfiniteVerdict
    from vidbyte.lib.errors import ToolExecutionError

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a"), task("b"), task("c")), reply("done")],
            generator("a"): [fail(ToolExecutionError("search backend refused the query"))],
            generator("b"): [fail(RuntimeError("runner bug"))],
            **simple_pair("c", "C-SUMMARY"),
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert "subagent_aborted" not in kinds(seen)
    finished = {event.details.key: event.details for event in of_kind(seen, "subagent_finished")}
    assert {key: details.error_type for key, details in finished.items()} == {pair_key("a"): "ToolExecutionError", pair_key("b"): "RuntimeError", pair_key("c"): ""}
    assert all((finished[pair_key(name)].status, finished[pair_key(name)].verdict) == (InfiniteResultStatus.FAILED, InfiniteVerdict.UNCHECKED) for name in ("a", "b"))
    batch = one(seen, "batch_finished").details
    assert (batch.passed, batch.fixed, batch.failed, batch.unchecked, batch.replayed) == (1, 0, 0, 2, 0)
    assert_portable(seen)


def test_in_flight_counts_each_pair_once_and_never_goes_below_zero(tmp_path: Path) -> None:
    """INV-16, D-9, EC-10, EC-25, R-17: on one InfiniteEvents with a real launch tool and journal, in_flight rises on each launch even when the sink raises on that event, falls on subagent_finished, falls on subagent_aborted only for a pair the journal has not finished, and is floored at 0: launches read 1, 2, 3, then 2 and 1 after the aborts, and subagent_finished reads 2."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteResultCard, InfiniteTaskCard
    from vidbyte.lib.enums.infinite import InfinitePairPhase, InfiniteResultStatus, InfiniteStopCause, InfiniteVerdict

    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "subagent_launched" and event.details.name == "b":
            raise ValueError("the sink rejects b's launch")

    events_writer = InfiniteEvents(sink, journal.run_id)
    launch_tool = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=events_writer)
    pairs: dict[str, Any] = {}

    def start(name: str, batch: int, index: int, size: int) -> None:
        card = InfiniteTaskCard(name=name, goal=f"Find the list prices for {name}.", done_criteria=("Every price has a source URL",), generator_prompt="Research.", verifier_prompt="Check.")
        pairs[name] = InfinitePair(launch_tool, card, pair_key(name))
        journal.pair_started(pair_key(name))
        events_writer.subagent_launched(launch_tool, card, batch, index, size)

    for index, name in enumerate(("a", "b", "c")):
        start(name, 0, index, 3)
    result = InfiniteResultCard(name="a", key=pair_key("a"), status=InfiniteResultStatus.DONE, verdict=InfiniteVerdict.PASSED, summary="A", review=PASSED, entries=(), dropped=(), files=())
    journal.pair_finished(pair_key("a"), result)
    events_writer.subagent_finished(pairs["a"], result)
    events_writer.subagent_aborted(pairs["a"], KeyboardInterrupt(), InfinitePairPhase.COMMIT)
    events_writer.subagent_aborted(pairs["c"], asyncio.CancelledError(), InfinitePairPhase.GENERATOR)
    start("d", 1, 0, 1)
    events_writer.subagent_aborted(pairs["b"], RuntimeError("defect"), InfinitePairPhase.VERIFIER)
    events_writer.subagent_aborted(pairs["d"], RuntimeError("defect"), InfinitePairPhase.VERIFIER)
    events_writer.subagent_aborted(pairs["b"], RuntimeError("defect"), InfinitePairPhase.VERIFIER)
    start("e", 2, 0, 1)
    assert kinds(seen) == ["subagent_launched"] * 3 + ["subagent_finished", "subagent_aborted", "subagent_aborted", "subagent_launched"] + ["subagent_aborted"] * 3 + ["subagent_launched"]
    assert [(event.details.name, event.details.in_flight) for event in of_kind(seen, "subagent_launched")] == [("a", 1), ("b", 2), ("c", 3), ("d", 2), ("e", 1)]
    assert one(seen, "subagent_finished").details.in_flight == 2
    aborted = [(event.details.name, event.details.reason, event.details.error_type, event.details.phase, event.details.staged) for event in of_kind(seen, "subagent_aborted")]
    assert aborted == [
        ("a", InfiniteStopCause.CANCELLED, "KeyboardInterrupt", InfinitePairPhase.COMMIT, 0),
        ("c", InfiniteStopCause.CANCELLED, "CancelledError", InfinitePairPhase.GENERATOR, 0),
        ("b", InfiniteStopCause.FAILED, "RuntimeError", InfinitePairPhase.VERIFIER, 0),
        ("d", InfiniteStopCause.FAILED, "RuntimeError", InfinitePairPhase.VERIFIER, 0),
        ("b", InfiniteStopCause.FAILED, "RuntimeError", InfinitePairPhase.VERIFIER, 0),
    ]
    assert_portable(seen)


def test_an_interrupt_the_sink_raises_on_subagent_finished_gives_one_abort_in_the_commit_phase(tmp_path: Path) -> None:
    """EC-10, INV-3, INV-10: a sink that raises KeyboardInterrupt while handling subagent_finished gets subagent_finished and then subagent_aborted (cancelled, KeyboardInterrupt, phase commit, staged 0) for the same pair, the journal already holds its pair_finished, and the very same KeyboardInterrupt object reaches the caller."""
    from vidbyte.lib.enums.infinite import InfinitePairPhase, InfiniteStopCause

    seen: list[Any] = []
    interrupts: list[KeyboardInterrupt] = []

    def sink(event: Any) -> None:
        seen.append(event)
        if event.kind.value == "subagent_finished" and not interrupts:
            interrupts.append(KeyboardInterrupt("the developer pressed Ctrl-C in the sink"))
            raise interrupts[0]

    agent = build_agent(tmp_path, on_event=sink)
    tree = ScriptedTree({ROOT: [launch(task("a"))], **simple_pair("a", "A-SUMMARY")})
    with tree.install(), pytest.raises(KeyboardInterrupt) as raised:
        agent.run(TASK)
    assert raised.value is interrupts[0]
    assert kinds(seen) == ["run_started", "subagent_launched", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "subagent_aborted", "run_stopped"]
    finished, aborted = one(seen, "subagent_finished"), one(seen, "subagent_aborted")
    assert finished.details.key == aborted.details.key == pair_key("a")
    details = aborted.details
    assert (details.reason, details.error_type, details.phase, details.staged) == (InfiniteStopCause.CANCELLED, "KeyboardInterrupt", InfinitePairPhase.COMMIT, 0)
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "pair_started", "pair_finished"]
    assert_portable(seen)
