"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py

PURPOSE: Proves the events that launches, pairs, memory tools, and note writes deliver: batch_rejected for a batch the launch tool refuses, replay before launch in task order, structured drops (verifier, unchecked, rule) whose card text stays byte-identical, file_written for append and edit, one tool_refused per refused memory tool call, caps and omitted counts on long texts and lists, nested keys and depths, a generator that raises, one relative path per note, a lone surrogate, and no event at all for a middleware denial.
ROLE IN CODEBASE: Launch-and-memory layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-events/spec.md (AC-7..AC-12, AC-14, AC-22, AC-28, AC-31, AC-34..AC-36; INV-12, INV-15..INV-20, INV-28, INV-34; EC-13, EC-16, EC-17, EC-25, EC-26, EC-34, EC-37; D-8, D-23). Exercises vidbyte/agents/infinite/launch.py, memory.py, and events.py, and InfiniteWorkspace.relative.
ARCHITECTURE NOTE: Only the model runner is scripted. Expected caps come from cut/line in infinite_events_fixtures.py, which restate spec INV-12 without calling OutputText. The sibling-commit case (AC-10 b) needs pair a to commit before pair b's verifier answers; the sink itself is the hook: it sets a Signal when pair a's subagent_finished arrives, which is after a's commit and card are on disk (INV-4), so the order is forced without polling or sleeps.
FUNCTION INVENTORY: test_a_batch_the_launch_tool_refuses_delivers_exactly_one_batch_rejected (AC-7, INV-15); test_a_replayed_name_and_a_new_name_are_announced_in_task_order_before_the_new_pair_runs (AC-8, INV-15, EC-26, D-16); test_drop_entry_is_announced_and_listed_in_the_finished_pair_with_the_card_text_unchanged (AC-9, INV-18, INV-28, D-8); test_a_pair_without_a_verdict_reports_every_staged_entry_dropped_as_unchecked (AC-10 a, INV-17, INV-28); test_an_entry_a_sibling_committed_first_is_reported_dropped_with_the_rule_message (AC-10 b, INV-17, INV-28); test_appending_then_editing_a_note_delivers_two_file_written_events (AC-11, INV-19, D-20); test_each_memory_tool_refusal_delivers_one_tool_refused_with_the_reason_the_model_saw (AC-12, INV-20); test_long_texts_and_lists_are_cut_to_their_caps_with_the_marker (AC-14, INV-12, INV-34); test_a_nested_launch_names_its_launcher_and_the_nested_agents_by_key_and_depth (AC-22, INV-11, D-5); test_a_generator_that_raises_has_no_generator_finished_and_its_entries_drop_as_unchecked (AC-28, EC-13, INV-16); test_large_settings_and_long_lists_stay_bounded_with_honest_omitted_counts (AC-31, INV-33, INV-34, EC-25); test_two_spellings_of_one_note_are_one_relative_path_in_events_and_the_handoff (AC-34, EC-16, D-23, INV-28); test_a_lone_surrogate_in_a_generator_reply_becomes_a_question_mark_in_events_only (AC-35, EC-17); test_middleware_denials_deliver_no_event_and_the_run_still_finishes (AC-36, EC-37). _remember, _label, _extra_tools, and _summaries are small builders.
COMMON MODIFICATION PATTERNS: A new event emitted by a pair or a memory tool gets one test here that scripts the call, asserts the exact kinds list, and checks the details against the journaled card or the tool result the model saw.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert inside a sink; the AC-10 b sink only sets a Signal and records. 3. Do not compare the card's dropped strings with text built from the events alone; compare them with the literal INV-28 shapes or with a run that has no sink.
KNOWN EDGE CASES: A middleware denial reaches the model wrapped in the runtime's tool-error envelope, so AC-36 looks for "Tool denied by middleware:" inside the tool result, as the pack's delegation tests do. Context items that are paths are not checked for existence by the launch tool, so AC-14's 30 context paths need no files. The scripted extras in AC-31 come in through settings.tools, whose order the root's catalog keeps, but the test only relies on which names appear.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 6.1, 6.2, 6.3, 9.1 and 13; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    FACT,
    GEN_SUMMARY,
    LABEL_MAX,
    LINE_MAX,
    MARKER,
    PAIR,
    PASSED,
    SUMMARY_MAX,
    TEXT_MAX,
    assert_portable,
    cut,
    kinds,
    line,
    of_kind,
    one,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    TASK,
    ModelCall,
    ScriptedTree,
    Signal,
    after,
    build_agent,
    events,
    fail,
    finished_cards,
    generator,
    is_error,
    journal_paths,
    journal_records,
    launch,
    observe,
    pair_key,
    prompt_text,
    reply,
    simple_pair,
    task,
    template_regex,
    tool_call,
    tool_result,
    verifier,
    workspace_root,
)
from vidbyte import tool
from vidbyte.lib.errors import VidbyteSdkError

UNCHECKED_NOTE = "not committed, because the verdict is unchecked"
VERIFIER_NOTE = "dropped by the verifier"


def _remember(text: str) -> object:
    return tool_call("remember", {"kind": "fact", "text": text})


def _label(agent_key: str) -> str:
    # Spec section 9.1: {agent} in a summary is "root" or the key's last two segments.
    return "root" if agent_key == "root" else "/".join(agent_key.split("/")[-2:])


def _summaries(seen: list[Any], kind: str) -> list[str]:
    return [event.summary for event in of_kind(seen, kind)]


def _extra_tools(count: int, length: int) -> tuple[Any, ...]:
    # Developer tools with long, distinct names, passed through settings.tools.
    def lookup(topic: str) -> str:
        """Look up a topic in the company wiki."""
        return topic

    return tuple(tool(name=f"extra-{index}-".ljust(length, "x"))(lookup) for index in range(count))


# ---------------------------------------------------------------- AC-7, AC-8


def test_a_batch_the_launch_tool_refuses_delivers_exactly_one_batch_rejected(tmp_path: Path) -> None:
    """AC-7, INV-15: two tasks with one name give exactly one batch_rejected from the root, naming launch_subagent and the problem the model read, with no subagent_launched and no journal record for the call."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("twin"), task("twin")), reply("done")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "batch_rejected", "run_finished"]
    rejected = seen[1]
    assert (rejected.agent_key, rejected.role, rejected.depth) == ("root", InfiniteAgentRole.ROOT, 0)
    assert rejected.details.tool == "launch_subagent"
    result = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    assert is_error(result) and "twin" in rejected.details.problem and len(rejected.details.problem) <= TEXT_MAX
    assert template_regex(prompt_text("launch_rejected_prompt"), problem=rejected.details.problem).search(result), (rejected.details.problem, result)
    assert rejected.summary == line(f"launch_subagent refused for root: {rejected.details.problem}", SUMMARY_MAX)
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "run_finished"]
    assert_portable(seen)


def test_a_replayed_name_and_a_new_name_are_announced_in_task_order_before_the_new_pair_runs(tmp_path: Path) -> None:
    """AC-8, INV-15, EC-26, D-16: relaunching finished `a` beside new `b` gives subagent_replayed(a) with its recorded status and verdict, then subagent_launched(b), both before b's generator reports; `a` gets no second generator_finished or subagent_finished."""
    from vidbyte.lib.enums.infinite import InfiniteResultStatus, InfiniteVerdict

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("a")), launch(task("a"), task("b")), reply("done")], **simple_pair("a", "A-SUMMARY"), **simple_pair("b", "B-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == [
        "run_started",
        "subagent_launched",
        "generator_finished",
        "subagent_finished",
        "subagent_replayed",
        "subagent_launched",
        "generator_finished",
        "subagent_finished",
        "run_finished",
    ]
    replayed = one(seen, "subagent_replayed")
    assert (replayed.agent_key, replayed.details.name, replayed.details.key) == ("root", "a", pair_key("a"))
    assert (replayed.details.status, replayed.details.verdict) == (InfiniteResultStatus.DONE, InfiniteVerdict.PASSED)
    assert replayed.summary == "root: a already finished; its result is reused"
    assert [event.details.name for event in of_kind(seen, "subagent_launched")] == ["a", "b"]
    assert [event.agent_key for event in of_kind(seen, "generator_finished")] == [f"{pair_key('a')}/gen", f"{pair_key('b')}/gen"]
    assert [event.details.key for event in of_kind(seen, "subagent_finished")] == [pair_key("a"), pair_key("b")]
    assert_portable(seen)


# ---------------------------------------------------------------- AC-9, AC-10: structured drops


def test_drop_entry_is_announced_and_listed_in_the_finished_pair_with_the_card_text_unchanged(tmp_path: Path) -> None:
    """AC-9, INV-18, INV-28, D-8: the verifier's drop_entry("s1") gives one memory_dropped from the verifier (key, text, verifier reason, note), the same item in subagent_finished.dropped, and a card string byte-identical to a run without a sink."""
    from vidbyte.lib.dataclasses.infinite import InfiniteDroppedEntry
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteDropReason

    wrong = "Acme is free for everyone"

    def script() -> ScriptedTree:
        return ScriptedTree(
            {
                ROOT: [launch(task(PAIR)), reply("done")],
                generator(PAIR): [_remember(wrong), _remember(FACT), reply(GEN_SUMMARY)],
                verifier(PAIR): [tool_call("drop_entry", {"id": "s1"}), reply("Dropped the wrong entry.\nVERDICT: passed")],
            }
        )

    watched, quiet = tmp_path / "watched", tmp_path / "quiet"
    watched.mkdir()
    quiet.mkdir()
    seen: list[Any] = []
    for base, fields in ((watched, {"on_event": seen.append}), (quiet, {})):
        agent = build_agent(base, **fields)
        tree = script()
        with tree.install():
            agent.run(TASK)
        tree.assert_complete()
    assert kinds(seen) == ["run_started", "subagent_launched", "memory_staged", "memory_staged", "generator_finished", "memory_dropped", "subagent_finished", "run_finished"]
    dropped = one(seen, "memory_dropped")
    assert (dropped.agent_key, dropped.role, dropped.depth) == (f"{pair_key(PAIR)}/ver", InfiniteAgentRole.VERIFIER, 1)
    item = InfiniteDroppedEntry(key="s1", text=wrong, reason=InfiniteDropReason.VERIFIER, note=VERIFIER_NOTE)
    assert (dropped.details.key, dropped.details.text, dropped.details.reason, dropped.details.note) == (item.key, item.text, item.reason, item.note)
    assert dropped.summary == f"{PAIR}/ver dropped s1: {wrong}"
    finished = one(seen, "subagent_finished").details
    assert (finished.dropped, finished.dropped_omitted) == ((item,), 0)
    assert [(entry.staged_key, entry.text) for entry in finished.committed] == [("s2", FACT)]
    watched_card = finished_cards(workspace_root(watched))[pair_key(PAIR)]
    quiet_card = finished_cards(workspace_root(quiet))[pair_key(PAIR)]
    assert watched_card["dropped"] == quiet_card["dropped"] == [f"s1 ({wrong}): {VERIFIER_NOTE}"]
    assert_portable(seen)


def test_a_pair_without_a_verdict_reports_every_staged_entry_dropped_as_unchecked(tmp_path: Path) -> None:
    """AC-10 (a), INV-17, INV-28: a verifier with no VERDICT line gives subagent_finished(unchecked) whose dropped lists each staged entry with the unchecked reason and note, and the card strings keep their INV-28 shape."""
    from vidbyte.lib.dataclasses.infinite import InfiniteDroppedEntry
    from vidbyte.lib.enums.infinite import InfiniteDropReason, InfiniteVerdict

    second = "Globex charges 59 USD per seat"
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [_remember(FACT), _remember(second), reply(GEN_SUMMARY)],
            verifier(PAIR): [reply("Looks fine to me, nothing to add.")],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    finished = one(seen, "subagent_finished").details
    assert finished.verdict is InfiniteVerdict.UNCHECKED
    assert finished.committed == () and finished.committed_omitted == 0
    assert finished.dropped == tuple(InfiniteDroppedEntry(key=key, text=text, reason=InfiniteDropReason.UNCHECKED, note=UNCHECKED_NOTE) for key, text in (("s1", FACT), ("s2", second)))
    card = finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]
    assert card["dropped"] == [f"s1 ({FACT}): {UNCHECKED_NOTE}", f"s2 ({second}): {UNCHECKED_NOTE}"]
    assert one(seen, "subagent_finished").summary == f"{PAIR}: unchecked, 0 memories saved, 2 dropped, 0 files"
    assert_portable(seen)


def test_an_entry_a_sibling_committed_first_is_reported_dropped_with_the_rule_message(tmp_path: Path) -> None:
    """AC-10 (b), INV-17, INV-28: when sibling a commits the shared text first, b's staged copy is in b's dropped with the rule reason and the rule's message as note, and b's card string is "<key> (<text>): <note>"."""
    from vidbyte.lib.enums.infinite import InfiniteDropReason, InfiniteVerdict

    shared = "Initech charges 30 USD per seat"
    seen: list[Any] = []
    a_finished = Signal("pair a's subagent_finished")
    b_staged = Signal("pair b staged its entry")

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
            generator("b"): [_remember(shared), observe(staged, reply("B-SUMMARY"))],
            verifier("a"): [after(b_staged, reply(PASSED))],
            verifier("b"): [after(a_finished, reply(PASSED))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    by_key = {event.details.key: event.details for event in of_kind(seen, "subagent_finished")}
    assert [(item.staged_key, item.text) for item in by_key[pair_key("a")].committed] == [("s1", shared)]
    late = by_key[pair_key("b")]
    assert late.verdict is InfiniteVerdict.PASSED and late.committed == ()
    (item,) = late.dropped
    assert (item.key, item.text, item.reason) == ("s1", shared, InfiniteDropReason.RULE)
    entry_id = finished_cards(workspace_root(tmp_path))[pair_key("a")]["entries"][0]
    assert f"#{entry_id}" in item.note
    card = finished_cards(workspace_root(tmp_path))[pair_key("b")]
    assert card["dropped"] == [f"{item.key} ({item.text}): {item.note}"]
    assert_portable(seen)


# ---------------------------------------------------------------- AC-11, AC-12: notes and refusals


def test_appending_then_editing_a_note_delivers_two_file_written_events(tmp_path: Path) -> None:
    """AC-11, INV-19, D-20: under FULL, appending to an existing note and then editing it give file_written(appended, the appended length, the text cut to 500 with its line breaks) and file_written(edited, len(new_text), new_text), with an empty description."""
    from vidbyte.lib.enums.infinite import InfiniteFileChange

    root = workspace_root(tmp_path)
    seen: list[Any] = []
    agent = build_agent(tmp_path, workspace={"preset": "full"}, on_event=seen.append)
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "notes" / "plan.md").write_text("Plan v1: compare list prices.\n", encoding="utf-8", newline="\n")
    appended = "".join(f"Finding {index}: Globex lists Team at {50 + index} USD per seat.\n" for index in range(20))
    new_text = "Plan v2: compare monthly list prices only."
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("write_note", {"path": "notes/plan.md", "text": appended}),
                tool_call("edit_file", {"path": "notes/plan.md", "old_text": "Plan v1: compare list prices.", "new_text": new_text}),
                reply("done"),
            ]
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert not is_error(tool_result(tree.calls_by(ROOT)[2], "edit_file"))
    assert kinds(seen) == ["run_started", "file_written", "file_written", "run_finished"]
    written = [event.details for event in of_kind(seen, "file_written")]
    assert [(item.path, item.change, item.added_chars, item.excerpt, item.description) for item in written] == [
        ("notes/plan.md", InfiniteFileChange.APPENDED, len(appended), cut(appended, TEXT_MAX), ""),
        ("notes/plan.md", InfiniteFileChange.EDITED, len(new_text), new_text, ""),
    ]
    assert len(written[0].excerpt) == TEXT_MAX and written[0].excerpt.endswith(MARKER) and "\n" in written[0].excerpt
    assert _summaries(seen, "file_written") == ["root appended notes/plan.md", "root edited notes/plan.md"]
    assert_portable(seen)


def test_each_memory_tool_refusal_delivers_one_tool_refused_with_the_reason_the_model_saw(tmp_path: Path) -> None:
    """AC-12, INV-20: remember past its quota, write_note outside the workspace, edit_file with no match, and drop_entry of an unknown key each give exactly one tool_refused from the acting agent, whose problem is in the refusal the model read; none gives a memory or file event."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    root = workspace_root(tmp_path)
    seen: list[Any] = []
    agent = build_agent(tmp_path, workspace={"preset": "full", "max_entries_per_agent": 1}, on_event=seen.append)
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "notes" / "plan.md").write_text("Plan v1: compare list prices.\n", encoding="utf-8", newline="\n")
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("remember", {"kind": "decision", "text": "Compare monthly list prices only"}),
                tool_call("remember", {"kind": "fact", "text": "Globex charges 59 USD per seat"}),
                tool_call("write_note", {"path": "../outside.md", "text": "Escaped.", "description": "Outside"}),
                tool_call("edit_file", {"path": "notes/plan.md", "old_text": "NO-SUCH-PASSAGE", "new_text": "x"}),
                launch(task(PAIR)),
                reply("done"),
            ],
            generator(PAIR): [reply(GEN_SUMMARY)],
            verifier(PAIR): [tool_call("drop_entry", {"id": "s9"}), reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "memory_saved", "tool_refused", "tool_refused", "tool_refused", "subagent_launched", "generator_finished", "tool_refused", "subagent_finished", "run_finished"]
    root_calls = tree.calls_by(ROOT)
    seen_by_model = [
        tool_result(root_calls[2], "remember"),
        tool_result(root_calls[3], "write_note"),
        tool_result(root_calls[4], "edit_file"),
        tool_result(tree.calls_by(verifier(PAIR))[1], "drop_entry"),
    ]
    refused = of_kind(seen, "tool_refused")
    assert [event.details.tool for event in refused] == ["remember", "write_note", "edit_file", "drop_entry"]
    assert [(event.agent_key, event.role) for event in refused] == [("root", InfiniteAgentRole.ROOT)] * 3 + [(f"{pair_key(PAIR)}/ver", InfiniteAgentRole.VERIFIER)]
    for event, content in zip(refused, seen_by_model, strict=True):
        assert is_error(content), content
        assert event.details.problem.strip() and len(event.details.problem) <= TEXT_MAX
        assert event.details.problem in content, (event.details.problem, content)
        assert event.summary == line(f"{event.details.tool} refused for {_label(event.agent_key)}: {event.details.problem}", SUMMARY_MAX)
    assert not (tmp_path / "project" / "outside.md").exists()
    assert_portable(seen)


# ---------------------------------------------------------------- AC-14, AC-31: caps and omitted counts


def test_long_texts_and_lists_are_cut_to_their_caps_with_the_marker(tmp_path: Path) -> None:
    """AC-14, INV-12, INV-34: a 3,000-char task, a 5,000-char goal, 15 criteria of 1,000 chars, 10,000-char prompts, 30 context paths, and a 10,000-char answer are cut to 500/500/5x120/120/5x64/500 with the marker and honest omitted counts; multi-line fields keep their line breaks and every summary is one line of at most 280."""
    long_task = "Compare the list prices of our five competitors.\nUse the public pricing pages.\n" + "t" * 2_920
    goal = "Find every list price.\nInclude the currency.\n" + "g" * 4_957
    criteria = [f"Criterion {index}: every price\nhas a source URL. " + "c" * 960 for index in range(15)]
    prompt = "Research the vendor.\nWrite down each price.\n" + "p" * 9_955
    context = [f"notes/context/file-{index:02d}-".ljust(80, "n") + ".md" for index in range(30)]
    answer = "Acme is cheapest.\nGlobex is second.\n" + "a" * 9_964
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    card = task(PAIR, goal=goal, criteria=criteria, gen=prompt, ver=prompt, context=context)
    tree = ScriptedTree({ROOT: [launch(card), reply(answer)], generator(PAIR): [reply(GEN_SUMMARY)], verifier(PAIR): [reply(PASSED)]})
    with tree.install():
        agent.run(long_task)
    tree.assert_complete()
    started = one(seen, "run_started")
    assert started.details.task == cut(long_task, TEXT_MAX) and "\n" in started.details.task
    assert started.summary == line(f"Run started: {long_task}", SUMMARY_MAX)
    launched = one(seen, "subagent_launched")
    details = launched.details
    assert details.goal == cut(goal, TEXT_MAX) and "\n" in details.goal
    assert details.done_criteria == tuple(cut(item, LINE_MAX) for item in criteria[:5]) and details.done_criteria_omitted == 10
    assert all("\n" in item for item in details.done_criteria)
    assert (details.generator_prompt, details.verifier_prompt) == (cut(prompt, LINE_MAX), cut(prompt, LINE_MAX))
    assert details.context == tuple(cut(item, LABEL_MAX) for item in context[:5]) and details.context_omitted == 25
    assert launched.summary == line(f"root launched {PAIR}: {goal}", SUMMARY_MAX)
    finished = one(seen, "run_finished").details
    assert finished.answer == cut(answer, TEXT_MAX) and "\n" in finished.answer
    for value, cap in ((started.details.task, TEXT_MAX), (details.goal, TEXT_MAX), *((item, LINE_MAX) for item in details.done_criteria), (details.generator_prompt, LINE_MAX), *((item, LABEL_MAX) for item in details.context), (finished.answer, TEXT_MAX)):
        assert len(value) == cap and value.endswith(MARKER), (cap, value[-20:])
    assert_portable(seen)


def test_large_settings_and_long_lists_stay_bounded_with_honest_omitted_counts(tmp_path: Path) -> None:
    """AC-31, INV-33, INV-34, EC-25: with limits at 10_000 / 10**9 / 10**6, 7 extras of 100 chars, and a generator that writes 7 notes twice each and stages 7 entries while its verifier drops one, run_started shows the limits and 5 cut extras (2 omitted) and subagent_finished shows 5 files (2 omitted), 5 committed (1 omitted), and 1 dropped, with full counts in its summary."""
    from vidbyte.agents.settings.loop import AgentLoopSettings
    from vidbyte.lib.enums.infinite import InfiniteDropReason

    extras = _extra_tools(7, 100)
    caps = {name: 10**9 for name in ("max_files", "max_tokens", "max_file_tokens", "max_entry_tokens", "max_entries_per_agent")}
    seen: list[Any] = []
    agent = build_agent(
        tmp_path,
        workspace=caps,
        tools=extras,
        max_depth=10_000,
        max_parallel=10_000,
        max_agents=10**9,
        loop=AgentLoopSettings(max_iterations=10**6),
        on_event=seen.append,
    )
    writes = []
    for index in range(1, 8):
        writes.append(tool_call("write_note", {"path": f"./notes/n{index}.md", "text": f"Note {index}, first part.\n", "description": f"Pricing note {index}"}))
        writes.append(tool_call("write_note", {"path": f"notes/n{index}.md", "text": f"Note {index}, second part.\n"}))
    facts = [f"Vendor {index} charges {40 + index} USD per seat" for index in range(1, 8)]
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [*writes, *(_remember(text) for text in facts), reply(GEN_SUMMARY)],
            verifier(PAIR): [tool_call("drop_entry", {"id": "s3"}), reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    started = one(seen, "run_started").details
    assert (started.max_depth, started.max_parallel, started.max_agents, started.max_iterations) == (10_000, 10_000, 10**9, 10**6)
    names = {cut(extra.spec().name, LABEL_MAX) for extra in extras}
    assert len(started.extras) == 5 and set(started.extras) <= names and started.extras_omitted == 2
    assert all(len(name) == LABEL_MAX and name.endswith(MARKER) for name in started.extras)
    finished = one(seen, "subagent_finished")
    details = finished.details
    assert (details.files, details.files_omitted) == (tuple(f"notes/n{index}.md" for index in range(1, 6)), 2)
    assert [item.staged_key for item in details.committed] == ["s1", "s2", "s4", "s5", "s6"] and details.committed_omitted == 1
    assert [(item.key, item.reason) for item in details.dropped] == [("s3", InfiniteDropReason.VERIFIER)] and details.dropped_omitted == 0
    assert finished.summary == f"{PAIR}: passed, 6 memories saved, 1 dropped, 7 files"
    assert_portable(seen)


# ---------------------------------------------------------------- AC-22, AC-28


def test_a_nested_launch_names_its_launcher_and_the_nested_agents_by_key_and_depth(tmp_path: Path) -> None:
    """AC-22, INV-11, INV-16, D-5: when a's generator launches b, b's subagent_launched comes from root/a/gen at depth 1 with key root/a/gen/b, parent root/a/gen, depth 2, and b's generator reports as root/a/gen/b/gen at depth 2, all between a's launch and a's finish."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    nested = generator("a")
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("a")), reply("done")],
            generator("a"): [launch(task("b")), reply("A-SUMMARY")],
            verifier("a"): [reply(PASSED)],
            generator("b", nested): [_remember(FACT), reply("B-SUMMARY")],
            verifier("b", nested): [reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    outer, inner = of_kind(seen, "subagent_launched")
    assert (outer.agent_key, outer.details.key, outer.details.parent, outer.details.depth) == ("root", "root/a", "root", 1)
    assert (inner.agent_key, inner.role, inner.depth) == ("root/a/gen", InfiniteAgentRole.GENERATOR, 1)
    assert (inner.details.key, inner.details.parent, inner.details.depth) == ("root/a/gen/b", "root/a/gen", 2)
    deep = [event for event in seen if event.agent_key == "root/a/gen/b/gen"]
    assert kinds(deep) == ["memory_staged", "generator_finished"]
    assert {(event.role, event.depth) for event in deep} == {(InfiniteAgentRole.GENERATOR, 2)}
    finishes = {event.details.key: event for event in of_kind(seen, "subagent_finished")}
    assert finishes["root/a/gen/b"].agent_key == "root/a/gen" and finishes["root/a"].agent_key == "root"
    order = [seen.index(event) for event in (outer, inner, *deep, finishes["root/a/gen/b"], finishes["root/a"])]
    assert order == sorted(order), kinds(seen)
    assert_portable(seen)


def test_a_generator_that_raises_has_no_generator_finished_and_its_entries_drop_as_unchecked(tmp_path: Path) -> None:
    """AC-28, EC-13, INV-16: a generator whose runner raises an SDK error after staging gets no generator_finished; its subagent_finished is failed/unchecked with the card's error review cut to 500 and the staged entry dropped as unchecked."""
    from vidbyte.lib.dataclasses.infinite import InfiniteDroppedEntry
    from vidbyte.lib.enums.infinite import InfiniteDropReason, InfiniteResultStatus, InfiniteVerdict

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    error = "provider is down: " + "upstream 503 " * 60
    tree = ScriptedTree({ROOT: [launch(task(PAIR)), reply("done")], generator(PAIR): [_remember(FACT), fail(VidbyteSdkError(error))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "subagent_launched", "memory_staged", "subagent_finished", "run_finished"]
    card = finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]
    assert "provider is down" in card["review"] and len(card["review"]) > TEXT_MAX
    finished = one(seen, "subagent_finished").details
    assert (finished.status, finished.verdict) == (InfiniteResultStatus.FAILED, InfiniteVerdict.UNCHECKED)
    assert finished.review == cut(card["review"], TEXT_MAX) and len(finished.review) == TEXT_MAX
    assert finished.dropped == (InfiniteDroppedEntry(key="s1", text=FACT, reason=InfiniteDropReason.UNCHECKED, note=UNCHECKED_NOTE),)
    assert_portable(seen)


# ---------------------------------------------------------------- AC-34, AC-35, AC-36


def test_two_spellings_of_one_note_are_one_relative_path_in_events_and_the_handoff(tmp_path: Path) -> None:
    """AC-34, EC-16, D-23, INV-28: creating ./notes/a.md and appending to notes/a.md give two file_written events for notes/a.md, subagent_finished.files == ("notes/a.md",), a card that keeps both spellings, and one Files line with the description in the handoff."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff
    from vidbyte.lib.enums.infinite import InfiniteFileChange

    description = "Acme pricing notes"
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task(PAIR)), reply("done")],
            generator(PAIR): [
                tool_call("write_note", {"path": "./notes/a.md", "text": "First finding.\n", "description": description}),
                tool_call("write_note", {"path": "notes/a.md", "text": "Second finding.\n"}),
                reply(GEN_SUMMARY),
            ],
            verifier(PAIR): [reply(PASSED)],
        }
    )
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    written = [event.details for event in of_kind(seen, "file_written")]
    assert [(item.path, item.change) for item in written] == [("notes/a.md", InfiniteFileChange.CREATED), ("notes/a.md", InfiniteFileChange.APPENDED)]
    assert one(seen, "subagent_finished").details.files == ("notes/a.md",)
    assert finished_cards(workspace_root(tmp_path))[pair_key(PAIR)]["files"] == ["./notes/a.md", "notes/a.md"]
    handoff = agent.run_handoff(answer.metadata["infinite_run_id"])
    assert handoff.sections["Files"] == InfiniteHandoff.FILE_LINE.format(path="notes/a.md", description=description)
    assert_portable(seen)


def test_a_lone_surrogate_in_a_generator_reply_becomes_a_question_mark_in_events_only(tmp_path: Path) -> None:
    """AC-35, EC-17, INV-12: a generator reply holding "\\ud800" gives generator_finished.details.summary with "?" in its place, every event encodes as UTF-8, and the journal keeps the original card as ASCII JSON."""
    surrogate = "Prices: Acme \ud800 Globex"
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task(PAIR)), reply("done")], generator(PAIR): [reply(surrogate)], verifier(PAIR): [reply(PASSED)]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    produced = one(seen, "generator_finished")
    assert produced.details.summary == "Prices: Acme ? Globex"
    assert produced.summary == f"{PAIR}/gen: done: Prices: Acme ? Globex"
    assert_portable(seen)
    root = workspace_root(tmp_path)
    (journal,) = journal_paths(root)
    assert journal.read_bytes().isascii()
    assert finished_cards(root)[pair_key(PAIR)]["summary"] == surrogate


def test_middleware_denials_deliver_no_event_and_the_run_still_finishes(tmp_path: Path) -> None:
    """AC-36, EC-37, INV-15: a root batch over max_parallel=2 and a generator's launch past max_depth=1 are denied by DelegationLimitsMiddleware with results naming the limit; neither call gives any event or pair_started, and the run ends with run_finished."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, max_parallel=2, max_depth=1, on_event=seen.append)
    tree = ScriptedTree(
        {
            ROOT: [launch(task("x"), task("y"), task("z")), launch(task("a")), reply("done")],
            generator("a"): [launch(task("b")), reply("A-SUMMARY")],
            verifier("a"): [reply(PASSED)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    over_parallel = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    over_depth = tool_result(tree.calls_by(generator("a"))[1], "launch_subagent")
    assert "Tool denied by middleware:" in over_parallel and "max_parallel" in over_parallel, over_parallel
    assert "Tool denied by middleware:" in over_depth and "max_depth" in over_depth, over_depth
    assert kinds(seen) == ["run_started", "subagent_launched", "generator_finished", "subagent_finished", "run_finished"]
    assert one(seen, "subagent_launched").details.key == pair_key("a")
    records = journal_records(workspace_root(tmp_path))
    assert events(records) == ["run_started", "pair_started", "pair_finished", "run_finished"]
    assert_portable(seen)
