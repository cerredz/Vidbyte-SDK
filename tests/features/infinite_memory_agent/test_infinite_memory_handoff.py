"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_handoff.py

PURPOSE: Proves InfiniteMemoryAgent.run_handoff: the nine sections of a finished run and the exact file it saves, the placeholder for a journal written before the answer was stored, the run_id errors that write nothing, the section and line caps on a huge answer and a long Files list, the refusal of a hand-edited journal in both run_handoff and resume, which entries and cards each section lists, a lone surrogate in the answer, and a note replaced by a symlink loop.
ROLE IN CODEBASE: Handoff layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-events/spec.md (AC-16, AC-18, AC-19, AC-33; INV-22..INV-24, INV-26, INV-37; EC-15, EC-17, EC-19, EC-20, EC-21, EC-24, EC-33, EC-35; FR-14; D-11, D-14, D-19, D-26). Exercises InfiniteMemoryAgent.run_handoff in vidbyte/agents/infinite/agent.py, InfiniteHandoff in vidbyte/context/handoff/infinite.py, the journal's run_finished answer and files, and the workspace readers run_entries and descriptions.
ARCHITECTURE NOTE: Runs are scripted with ScriptedTree, or their journals are written by hand with the pack's record builders (the old run_finished shape for AC-18). run_handoff is always called inside an empty ScriptedTree, so any model call would fail the test. Expected section bodies are built from InfiniteHandoff's own wording attributes, which the spec fixes (section 9.1), and from cut/line in infinite_events_fixtures.py for the caps.
FUNCTION INVENTORY: test_a_finished_run_gives_nine_sections_and_a_byte_exact_file_without_a_model_call (AC-16, INV-22, INV-23, D-19); test_an_old_journal_without_an_answer_uses_the_placeholder_and_resume_is_unchanged (AC-18, EC-21, INV-26); test_a_bad_unknown_or_missing_run_id_is_refused_and_writes_nothing (AC-19, INV-22); test_a_huge_answer_and_a_long_files_list_are_cut_to_the_section_caps (AC-33, INV-37, EC-24, EC-33, D-26); test_a_hand_edited_run_finished_record_is_refused_with_its_line (EC-20, INV-26); test_a_malformed_entries_line_refuses_the_handoff_and_writes_nothing (EC-19, INV-22); test_the_handoff_lists_this_runs_live_entries_by_kind_and_every_card_in_finishing_order (INV-24, D-11); test_a_lone_surrogate_in_the_roots_answer_becomes_a_question_mark_in_the_handoff_and_its_file (EC-17, INV-23); test_a_note_replaced_by_a_symlink_loop_keeps_one_name_and_breaks_no_handoff_or_event (EC-35, FR-14, D-23). _handoff calls run_handoff with no model allowed; _files_record copies the files.jsonl shape.
COMMON MODIFICATION PATTERNS: A new handoff rule gets one test that builds the run (scripted or hand-written), calls _handoff, and compares one section with text built from InfiniteHandoff's wording attributes.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare the handoff file with text read in text mode; compare bytes, because Windows would turn "\\n" into "\\r\\n". 3. Do not hard-code the handoff sentences; read them from InfiniteHandoff's class attributes, which spec section 9.1 names.
KNOWN EDGE CASES: The spec allows NO_ANSWER to be either the whole Outcome or the answer inside OUTCOME, so AC-18 checks that the Outcome holds the task and the placeholder rather than one exact body. journal_paths globs .runs/*.jsonl, so the handoff file never counts as a journal. AC-33 adds files.jsonl records after the run in the shape the workspace writes, because creating 30 notes through the model would only repeat AC-31.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 6.1, 6.2, 6.3, 9.1, 9.2 and 13; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_handoff.py -q
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    FACT,
    GEN_SUMMARY,
    HANDOFF_LINE_MAX,
    HANDOFF_OUTCOME_MAX,
    HANDOFF_SECTION_MAX,
    HANDOFF_TEXT_MAX,
    HANDOFF_TITLES,
    MARKER,
    NOTE_DESCRIPTION,
    NOTE_PATH,
    PAIR,
    ROOT_ANSWER,
    ac2_tree,
    cut,
    line,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    RUN_B,
    TASK,
    ScriptedTree,
    build_agent,
    card_record,
    entry_record,
    fail,
    finished_cards,
    generator,
    journal_paths,
    journal_records,
    launch,
    pair_finished_record,
    pair_key,
    pair_started_record,
    reply,
    run_finished_record,
    run_started_record,
    simple_pair,
    snapshot,
    task,
    tool_call,
    verifier,
    workspace_root,
    write_journal,
    write_jsonl,
)
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError, VidbyteSdkError

HANDOFF_SUFFIX = ".handoff.md"


def _handoff(agent: Any, run_id: str | None = None) -> Any:
    """run_handoff with every model call refused, so a call that reaches a model fails the test."""
    quiet = ScriptedTree({})
    with quiet.install():
        handoff = agent.run_handoff(run_id) if run_id is not None else agent.run_handoff()
    assert quiet.calls == []
    return handoff


def _files_record(path: str, description: str, run_id: str) -> dict[str, str]:
    # One files.jsonl line in the shape InfiniteWorkspace.write_note writes.
    return {"path": path, "description": description, "by": "root", "run": run_id, "at": "2026-10-16T08:15:00+00:00"}


# ---------------------------------------------------------------- AC-16, AC-18, AC-19


def test_a_finished_run_gives_nine_sections_and_a_byte_exact_file_without_a_model_call(tmp_path: Path) -> None:
    """AC-16, INV-22, INV-23, D-19: after the AC-2 run, run_handoff twice returns an InfiniteHandoff with the nine titles and the expected bodies, writes .runs/<run_id>.handoff.md as to_context_text() in UTF-8 with no \\r, leaves identical bytes both times, and changes no other workspace file."""
    from vidbyte.context.handoff.base import Handoff
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    agent = build_agent(tmp_path)
    tree = ac2_tree()
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    root = workspace_root(tmp_path)
    run_id = answer.metadata["infinite_run_id"]
    target = root / ".runs" / f"{run_id}{HANDOFF_SUFFIX}"
    before = snapshot(root, include_runs=True)
    handoff = _handoff(agent, run_id)
    first = target.read_bytes()
    again = _handoff(agent, run_id)
    assert target.read_bytes() == first == handoff.to_context_text().encode("utf-8")
    assert b"\r" not in first
    assert (again.title, again.sections) == (handoff.title, handoff.sections)
    after = snapshot(root, include_runs=True)
    assert {name: data for name, data in after.items() if not name.endswith(HANDOFF_SUFFIX)} == before
    assert [name for name in after if name.endswith(HANDOFF_SUFFIX)] == [f".runs/{run_id}{HANDOFF_SUFFIX}"]

    assert type(handoff) is InfiniteHandoff and isinstance(handoff, Handoff) and handoff.is_filled
    assert handoff.section_titles() == HANDOFF_TITLES and tuple(handoff.default_sections()) == HANDOFF_TITLES
    assert (handoff.title, handoff.metadata) == (InfiniteHandoff.TITLE.format(run_id=run_id), {"filled": True, "run_id": run_id})
    assert InfiniteHandoff.DEFAULT_TITLE == "InfiniteMemory handoff" and type(handoff.fill(handoff.sections)) is InfiniteHandoff
    (entry_id,) = finished_cards(root)[pair_key(PAIR)]["entries"]
    empty = InfiniteHandoff.EMPTY
    assert handoff.sections == {
        "Outcome": InfiniteHandoff.OUTCOME.format(task=TASK, stop_reason="final_response", answer=ROOT_ANSWER),
        "Work done": InfiniteHandoff.CARD_LINE.format(key=pair_key(PAIR), status="done", verdict="passed", text=GEN_SUMMARY),
        "Decisions": empty,
        "Facts": InfiniteHandoff.ENTRY_LINE.format(id=entry_id, text=FACT),
        "Lessons": empty,
        "Open questions": empty,
        "Files": InfiniteHandoff.FILE_LINE.format(path=NOTE_PATH, description=NOTE_DESCRIPTION),
        "Unverified or failed work": empty,
        "How to continue": InfiniteHandoff.NEW_RUN,
    }


def test_an_old_journal_without_an_answer_uses_the_placeholder_and_resume_is_unchanged(tmp_path: Path) -> None:
    """AC-18, EC-21, INV-26: a finished journal in the pre-change shape (run_finished without answer or files) gives an Outcome holding the task and NO_ANSWER and the new-run advice, and resume() still picks the sibling unfinished run and finishes it."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    old = write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), pair_started_record(pair_key("a")), pair_finished_record(card_record("a", summary="A-SUMMARY")), run_finished_record()])
    write_journal(root, RUN_B, [run_started_record(RUN_B, TASK), pair_started_record(pair_key("b"))])
    old_bytes = old.read_bytes()
    handoff = _handoff(agent, RUN_A)
    outcome = handoff.sections["Outcome"]
    assert TASK in outcome and InfiniteHandoff.NO_ANSWER in outcome, outcome
    assert handoff.sections["Work done"] == InfiniteHandoff.CARD_LINE.format(key=pair_key("a"), status="done", verdict="passed", text="A-SUMMARY")
    assert handoff.sections["How to continue"] == InfiniteHandoff.NEW_RUN
    assert old.read_bytes() == old_bytes

    tree = ScriptedTree({ROOT: [launch(task("b")), reply("RESUMED-B")], **simple_pair("b", "B-SUMMARY")})
    with tree.install():
        resumed = agent.resume()
    tree.assert_complete()
    assert (resumed.content, resumed.metadata["infinite_run_id"]) == ("RESUMED-B", RUN_B)
    assert old.read_bytes() == old_bytes


def test_a_bad_unknown_or_missing_run_id_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    """AC-19, INV-22: run_handoff("../x"), a well-formed id with no journal, and run_handoff() on a workspace with no runs each raise ConfigurationError for field run_id, and no handoff file is written anywhere."""
    listed, empty = tmp_path / "listed", tmp_path / "empty"
    listed.mkdir()
    empty.mkdir()
    agent = build_agent(listed)
    write_journal(workspace_root(listed), RUN_A, [run_started_record(RUN_A, TASK), run_finished_record()])
    blank = build_agent(empty)
    for target, run_id in ((agent, "../x"), (agent, RUN_B), (blank, None), (blank, RUN_A)):
        with pytest.raises(ConfigurationError) as refused:
            _handoff(target, run_id)
        assert refused.value.details.get("field") == "run_id", (run_id, refused.value.details)
    assert list(tmp_path.rglob(f"*{HANDOFF_SUFFIX}")) == []


# ---------------------------------------------------------------- AC-33, EC-20


def test_a_huge_answer_and_a_long_files_list_are_cut_to_the_section_caps(tmp_path: Path) -> None:
    """AC-33, INV-37, EC-24, EC-33, D-26: a 300,000-character answer is stored whole in the journal with the root's note in files, Outcome is exactly 239,000 characters ending with the marker, a Files list over 15,900 characters is cut to exactly 15,900 with the marker, a 2,000-character file line is cut to 1,000, and the whole text stays within 366,500."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    answer = "".join(f"Vendor {index:05d}: list price {index % 97} USD per seat, checked on the public page.\n" for index in range(4_000))
    answer = (answer * 2)[:300_000]
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [tool_call("write_note", {"path": "notes/root.md", "text": "Root summary of the pricing work.\n", "description": "Root pricing summary"}), reply(answer)]})
    with tree.install():
        result = agent.run(TASK)
    tree.assert_complete()
    root = workspace_root(tmp_path)
    run_id = result.metadata["infinite_run_id"]
    finished = journal_records(root)[-1]
    assert (finished["event"], finished["answer"], finished["files"]) == ("run_finished", answer, ["notes/root.md"])

    files_file = root / "files.jsonl"
    created = [json.loads(text) for text in files_file.read_text(encoding="utf-8").splitlines() if text.strip()]
    extra = [_files_record("notes/vendor-00.md", "Vendor 0 pricing notes: " + "d" * 1_976, run_id)]
    extra += [_files_record(f"notes/vendor-{index:02d}.md", f"Vendor {index} pricing notes: " + "d" * 576, run_id) for index in range(1, 30)]
    write_jsonl(files_file, [*created, *extra])
    handoff = _handoff(agent, run_id)

    sections = handoff.sections
    expected_outcome = cut(InfiniteHandoff.OUTCOME.format(task=TASK, stop_reason="final_response", answer=answer), HANDOFF_OUTCOME_MAX)
    assert sections["Outcome"] == expected_outcome and len(expected_outcome) == HANDOFF_OUTCOME_MAX and expected_outcome.endswith(MARKER)
    lines = [line(InfiniteHandoff.FILE_LINE.format(path=record["path"], description=record["description"]), HANDOFF_LINE_MAX) for record in [*created, *extra]]
    assert lines[1].endswith(MARKER) and len(lines[1]) == HANDOFF_LINE_MAX
    expected_files = cut("\n".join(lines), HANDOFF_SECTION_MAX)
    assert sections["Files"] == expected_files and len(expected_files) == HANDOFF_SECTION_MAX and expected_files.endswith(MARKER)
    for title, body in sections.items():
        assert len(body) <= (HANDOFF_OUTCOME_MAX if title == "Outcome" else HANDOFF_SECTION_MAX), title
        if title not in ("Outcome", "How to continue"):
            assert all(len(text) <= HANDOFF_LINE_MAX for text in body.split("\n")), title
    text = handoff.to_context_text()
    assert len(text) <= HANDOFF_TEXT_MAX
    assert (root / ".runs" / f"{run_id}{HANDOFF_SUFFIX}").read_bytes() == text.encode("utf-8")


@pytest.mark.parametrize(
    "finished",
    [{"answer": 42}, {"answer": "Done.", "files": ["notes/a.md", 7]}],
    ids=["answer-not-text", "files-not-all-text"],
)
def test_a_hand_edited_run_finished_record_is_refused_with_its_line(tmp_path: Path, finished: dict[str, Any]) -> None:
    """EC-20, INV-26: a run_finished record whose answer is not a string or whose files are not all strings refuses the journal with its line number in run_handoff and in resume's scan, and no handoff file is written."""
    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), {**run_finished_record(), **finished}])
    with pytest.raises(ConfigurationError) as in_handoff:
        _handoff(agent, RUN_A)
    quiet = ScriptedTree({})
    with quiet.install(), pytest.raises(ConfigurationError) as in_resume:
        agent.resume()
    for refused in (in_handoff.value, in_resume.value):
        assert refused.details.get("line") == 2, refused.details
    assert quiet.calls == [] and list(root.rglob(f"*{HANDOFF_SUFFIX}")) == []
    assert [path.name for path in journal_paths(root)] == [f"{RUN_A}.jsonl"]


def test_a_malformed_entries_line_refuses_the_handoff_and_writes_nothing(tmp_path: Path) -> None:
    """EC-19, INV-22: when entries.jsonl holds a line that is not an entry, run_handoff raises the workspace's ToolExecutionError naming the file and line, and no handoff file is written."""
    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), run_finished_record()])
    write_jsonl(root / "entries.jsonl", [entry_record(1, "Acme charges 49 USD per seat", run=RUN_A)])
    with (root / "entries.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("{this is not an entry\n")
    with pytest.raises(ToolExecutionError) as refused:
        _handoff(agent, RUN_A)
    assert refused.value.details == {"file": "entries.jsonl", "line": 2}
    assert list(root.rglob(f"*{HANDOFF_SUFFIX}")) == []


# ---------------------------------------------------------------- INV-24


def test_the_handoff_lists_this_runs_live_entries_by_kind_and_every_card_in_finishing_order(tmp_path: Path) -> None:
    """INV-24, D-11: entries from another run and superseded entries are left out, each kind section lists this run's live entries in id order, Work done has one line per finished card at every depth in finishing order, and Unverified lists the unchecked card, the card with a failed verdict, and the failed card with their reviews."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(1, "Acme listed 45 USD per seat in 2025", kind="fact", run=RUN_A), entry_record(2, "Prefer yearly prices", kind="decision", run=RUN_A)])
    first_decision, decision, lesson = "Compare monthly list prices", "Compare monthly list prices in USD", "Pricing pages hide enterprise tiers"
    unsure_review, rejected_review, broken_error = "Looks fine to me.", "The prices have no sources.\nVERDICT: failed", "provider is down"
    nested = generator("ok")
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("remember", {"kind": "decision", "text": first_decision}),
                tool_call("remember", {"kind": "decision", "text": decision, "supersedes": 3}),
                tool_call("remember", {"kind": "lesson", "text": lesson}),
                launch(task("ok")),
                launch(task("unsure")),
                launch(task("rejected")),
                launch(task("broken")),
                reply("done"),
            ],
            generator("ok"): [launch(task("deep")), reply("OK-SUMMARY")],
            verifier("ok"): [reply("Checked.\nVERDICT: passed")],
            **simple_pair("deep", "DEEP-SUMMARY", parent=nested),
            **simple_pair("unsure", "UNSURE-SUMMARY", review=unsure_review),
            **simple_pair("rejected", "REJECTED-SUMMARY", review=rejected_review),
            generator("broken"): [fail(VidbyteSdkError(broken_error))],
        }
    )
    with tree.install():
        result = agent.run(TASK)
    tree.assert_complete()
    handoff = _handoff(agent, result.metadata["infinite_run_id"])
    sections = handoff.sections
    assert sections["Decisions"] == InfiniteHandoff.ENTRY_LINE.format(id=4, text=decision)
    assert sections["Lessons"] == InfiniteHandoff.ENTRY_LINE.format(id=5, text=lesson)
    assert (sections["Facts"], sections["Open questions"]) == (InfiniteHandoff.EMPTY, InfiniteHandoff.EMPTY)
    def card(key: str, status: str, verdict: str, text: str) -> str:
        # Every list line is collapsed and cut (INV-37), so a card with an empty summary loses its trailing space.
        return line(InfiniteHandoff.CARD_LINE.format(key=key, status=status, verdict=verdict, text=text), HANDOFF_LINE_MAX)

    assert sections["Work done"] == "\n".join(
        [
            card("root/ok/gen/deep", "done", "passed", "DEEP-SUMMARY"),
            card(pair_key("ok"), "done", "passed", "OK-SUMMARY"),
            card(pair_key("unsure"), "done", "unchecked", "UNSURE-SUMMARY"),
            card(pair_key("rejected"), "done", "failed", "REJECTED-SUMMARY"),
            card(pair_key("broken"), "failed", "unchecked", ""),
        ]
    )
    assert sections["Unverified or failed work"] == "\n".join(
        [
            card(pair_key("unsure"), "done", "unchecked", unsure_review),
            card(pair_key("rejected"), "done", "failed", rejected_review),
            card(pair_key("broken"), "failed", "unchecked", broken_error),
        ]
    )


# ---------------------------------------------------------------- EC-17, EC-35


def test_a_lone_surrogate_in_the_roots_answer_becomes_a_question_mark_in_the_handoff_and_its_file(tmp_path: Path) -> None:
    """EC-17, INV-23: a root whose final answer holds "\\ud800" still gets its handoff: the Outcome shows "?" in its place, the saved file's bytes decode as UTF-8 and equal to_context_text() encoded as UTF-8, and the journal keeps the original answer."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    answer = "Prices checked \ud800 done."
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [reply(answer)]})
    with tree.install():
        run_id = agent.run(TASK).metadata["infinite_run_id"]
    tree.assert_complete()
    root = workspace_root(tmp_path)
    handoff = _handoff(agent, run_id)
    assert handoff.sections["Outcome"] == InfiniteHandoff.OUTCOME.format(task=TASK, stop_reason="final_response", answer="Prices checked ? done.")
    saved = (root / ".runs" / f"{run_id}{HANDOFF_SUFFIX}").read_bytes()
    assert saved == handoff.to_context_text().encode("utf-8")
    assert "Prices checked ? done." in saved.decode("utf-8")
    assert journal_records(root)[-1]["answer"] == answer


def test_a_note_replaced_by_a_symlink_loop_keeps_one_name_and_breaks_no_handoff_or_event(tmp_path: Path) -> None:
    """EC-35, FR-14, D-23: after bash replaces a recorded note with a two-link symlink loop, InfiniteWorkspace.relative returns one workspace-relative name for it instead of raising (the path as given where Path.resolve raises on a loop), run_handoff succeeds for the run that wrote the note, listing it under that name with its description, and for a later run that never touched it, and a file_written event naming the note is still delivered."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.context.handoff.infinite import InfiniteHandoff
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteFileChange

    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    run_ids: list[str] = []
    for script in ([tool_call("write_note", {"path": NOTE_PATH, "text": "Acme is 49 USD per seat.\n", "description": NOTE_DESCRIPTION}), reply("noted")], [reply("nothing to note")]):
        tree = ScriptedTree({ROOT: script})
        with tree.install():
            run_ids.append(agent.run(TASK).metadata["infinite_run_id"])
        tree.assert_complete()
    # Swap the note for a link loop, as a bash call could.
    note, partner = root / NOTE_PATH, root / "notes" / "partner.md"
    note.unlink()
    try:
        os.symlink(partner, note)
    except OSError:
        pytest.skip("this host cannot create symbolic links (Windows without the symlink privilege)")
    os.symlink(note, partner)

    # Python 3.11 and 3.12 (the CI matrix) raise RuntimeError resolving the loop, so the path comes back as given;
    # 3.13 stopped raising and resolves it to the loop's other link, which is still one name inside the workspace.
    named = agent.workspace.relative(NOTE_PATH)
    assert (named == NOTE_PATH) if sys.version_info < (3, 13) else (named in (NOTE_PATH, "notes/partner.md"))
    wrote, untouched = (_handoff(agent, run_id) for run_id in run_ids)
    assert wrote.sections["Files"] == InfiniteHandoff.FILE_LINE.format(path=named, description=NOTE_DESCRIPTION)
    assert untouched.sections["Files"] == InfiniteHandoff.EMPTY
    seen: list[Any] = []
    events = InfiniteEvents(seen.append, run_ids[1])
    memory = InfiniteAgentMemory(agent.workspace, key="root", role=InfiniteAgentRole.ROOT, run_id=run_ids[1], depth=0, events=events)
    events.file_written(memory, NOTE_PATH, InfiniteFileChange.APPENDED, "More.\n", None)
    assert [(event.kind.value, event.details.path) for event in seen] == [("file_written", named)]
