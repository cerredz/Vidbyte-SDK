"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_resume.py

PURPOSE: Proves the run journal and resume: records in order as fsynced JSON lines, resume continuing the newest unfinished run without re-running finished pairs, refusals before any model call, torn and malformed journals, cancellation leaving a resumable journal, the reserved-name check before the journal starts, and the API key never reaching disk.
ROLE IN CODEBASE: Journal and resume layer of tests/features/infinite_memory_agent/ (spec AC-19..AC-23, AC-41; INV-7, INV-25..INV-28, INV-31; EC-1, EC-26..EC-29; NFR-3; T-2, T-3). Exercises vidbyte/agents/infinite/journal.py, vidbyte/agents/infinite/agent.py (resume, aresume) and vidbyte/agents/infinite/runtime.py.
ARCHITECTURE NOTE: Starting states for resume are journals written by hand in the section 9.1 shape (spec section 13 allows this), so the tests pin the documented on-disk contract rather than whatever the implementation happens to write. Cancellation uses a generator runner that waits on a Signal nobody sets, and the test cancels the asyncio task running arun.
FUNCTION INVENTORY: test_journal_records_the_run_in_order_as_json_lines (AC-19, INV-25); test_resume_replays_finished_pairs_and_reruns_interrupted_ones (AC-20, INV-26..INV-28, EC-26); test_a_rerun_generator_hears_about_its_own_finished_children (INV-28); test_resume_refuses_unsafe_unknown_finished_or_missing_runs_before_any_model_call (AC-21, EC-28, EC-29, T-2); test_resume_skips_a_torn_final_journal_line (AC-22, EC-27, D-25); test_resume_rejects_a_malformed_middle_journal_line (AC-22, EC-27); test_cancelling_a_run_mid_pair_leaves_a_resumable_journal (AC-23, INV-31); test_a_run_time_tool_named_like_a_run_bound_tool_fails_before_the_journal_starts (AC-41, EC-1, INV-7); test_every_journal_record_is_fsynced_before_the_next_one_is_written (NFR-3, INV-25); test_api_key_stays_out_of_the_settings_repr_the_journal_and_the_workspace (T-3).
COMMON MODIFICATION PATTERNS: Build a new starting state with write_journal and the *_record helpers; keep run ids well-formed (INFINITE_RUN_ID_PATTERN) unless the case is about a bad id.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not simulate a crash with a runner VidbyteSdkError; the pair catches it (spec section 13). 3. Do not sleep while waiting for the generator to start; await the Signal it sets.
KNOWN EDGE CASES: BaseAgent.generate_reply wraps an Exception raised inside a run in AgentExecutionError (vidbyte/agents/base.py), so AC-41 accepts the ConfigurationError either raised directly or as the cause of that wrapper; see the S2 report. A torn line has no trailing newline, which is what makes it torn.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2, 6.3, 9.1, 10 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_resume.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    RUN_B,
    TASK,
    ModelCall,
    ScriptedTree,
    Signal,
    build_agent,
    build_settings,
    card_record,
    entry_record,
    events,
    finished_cards,
    generator,
    int_token,
    is_error,
    journal_paths,
    journal_records,
    launch,
    pair_finished_record,
    pair_key,
    pair_started_record,
    prompt_text,
    read_jsonl,
    reply,
    run_finished_record,
    run_started_record,
    simple_pair,
    snapshot,
    task,
    template_regex,
    tool_result,
    workspace_root,
    write_journal,
    write_jsonl,
)
from vidbyte import tool
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError

RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
CARD_FIELDS = {"name", "key", "status", "verdict", "summary", "review", "entries", "dropped", "files"}


def _error_text(error: BaseException) -> str:
    return f"{error} {json.dumps(getattr(error, 'details', None), default=str)}"


def _utc(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp)
    assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0, f"{stamp} is not UTC"
    return parsed


def _finished_line_regex(name: str, status: str, verdict: str) -> re.Pattern[str]:
    from vidbyte.lib.constants.infinite import INFINITE_FINISHED_PAIR_LINE

    return template_regex(INFINITE_FINISHED_PAIR_LINE, name=name, status=status, verdict=verdict)


def _finished_cards_in(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["key"]: record["card"] for record in records if record["event"] == "pair_finished"}


def _line_at(text: str, start: int) -> str:
    end = text.find("\n", start)
    return text[start : end if end >= 0 else len(text)]


# ---------------------------------------------------------------- AC-19


def test_journal_records_the_run_in_order_as_json_lines(tmp_path: Path) -> None:
    """AC-19, INV-25, section 9.1: run_started (task), pair_started and pair_finished (key, card), run_finished (stop reason), one JSON line each, UTC stamps."""
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("alpha")), reply("ROOT-FINAL")], **simple_pair("alpha", "ALPHA-SUMMARY")})
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    (path,) = journal_paths(workspace_root(tmp_path))
    lines = path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert events(records) == ["run_started", "pair_started", "pair_finished", "run_finished"]
    assert records[0]["run"] == path.stem and RUN_ID.match(path.stem) and records[0]["task"] == TASK
    assert records[1]["key"] == records[2]["key"] == pair_key("alpha")
    card = records[2]["card"]
    assert set(card) == CARD_FIELDS
    assert (card["name"], card["key"], card["status"], card["verdict"], card["summary"]) == ("alpha", pair_key("alpha"), "done", "passed", "ALPHA-SUMMARY")
    assert records[3]["stop_reason"] == answer.metadata["stop_reason"] == "final_response"
    stamps = [_utc(record["at"]) for record in records]
    assert stamps == sorted(stamps)


# ---------------------------------------------------------------- AC-20, INV-28


def test_resume_replays_finished_pairs_and_reruns_interrupted_ones(tmp_path: Path) -> None:
    """AC-20, INV-26..INV-28, EC-26: resume() picks the newest unfinished run, briefs the root in short lines, replays alpha without running it, re-runs beta, and finishes that same journal."""
    root = workspace_root(tmp_path)
    older_run = "20261014T090000Z-0a0b0c0d"
    older = write_journal(root, older_run, [run_started_record(older_run, "OLDER-TASK from yesterday", at="2026-10-14T09:00:00Z")])
    older_bytes = older.read_bytes()
    alpha_card = card_record("alpha", summary="ALPHA-SUMMARY-FULL-TEXT", review="ALPHA-REVIEW-FULL-TEXT", entries=[3])
    newer = write_journal(
        root,
        RUN_A,
        [run_started_record(RUN_A, "ORIGINAL-TASK compare competitor prices"), pair_started_record(pair_key("alpha")), pair_finished_record(alpha_card), pair_started_record(pair_key("beta-survey"))],
    )
    write_jsonl(root / "entries.jsonl", [entry_record(index, f"Earlier fact {index}", by="root/alpha/gen", verified_by="root/alpha/ver") for index in (1, 2, 3)])
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("alpha"), task("beta-survey")), reply("RESUMED-FINAL")], **simple_pair("beta-survey", "BETA-SUMMARY")})
    with tree.install():
        answer = agent.resume()
    tree.assert_complete()
    assert answer.content == "RESUMED-FINAL"
    briefing = tree.first_call(ROOT).prompt
    assert template_regex(prompt_text("resume_prompt")).search(briefing)
    assert "ORIGINAL-TASK compare competitor prices" in briefing and "OLDER-TASK" not in briefing
    line = _finished_line_regex("alpha", "done", "passed").search(briefing)
    assert line, f"no finished-pair line for alpha in: {briefing}"
    assert int_token(3).search(_line_at(briefing, line.start())), "the finished-pair line must carry alpha's entry ids"
    assert "ALPHA-SUMMARY-FULL-TEXT" not in briefing and "ALPHA-REVIEW-FULL-TEXT" not in briefing
    assert "beta-survey" in briefing
    assert generator("alpha") not in tree.agents_called()
    relaunched = tool_result(tree.calls_by(ROOT)[1], "launch_subagent")
    assert not is_error(relaunched)
    assert "ALPHA-SUMMARY-FULL-TEXT" in relaunched and template_regex(prompt_text("replayed_label")).search(relaunched)
    assert "BETA-SUMMARY" in relaunched
    assert journal_paths(root) == sorted([older, newer]) and older.read_bytes() == older_bytes
    records = read_jsonl(newer)
    assert events(records).count("run_started") == 1 and events(records)[-1] == "run_finished"
    assert _finished_cards_in(records)[pair_key("beta-survey")]["summary"] == "BETA-SUMMARY"


def test_a_rerun_generator_hears_about_its_own_finished_children(tmp_path: Path) -> None:
    """INV-28: a re-run generator's first message holds one finished-pair line per child of its own that finished earlier in the run."""
    root = workspace_root(tmp_path)
    child = card_record("child-scan", key="root/a/gen/child-scan", summary="CHILD-SUMMARY-FULL-TEXT")
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), pair_started_record(pair_key("a")), pair_started_record("root/a/gen/child-scan"), pair_finished_record(child)])
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")], **simple_pair("a", "A-SUMMARY")})
    with tree.install():
        agent.resume()
    tree.assert_complete()
    first = tree.first_call(generator("a")).prompt
    assert _finished_line_regex("child-scan", "done", "passed").search(first), first
    assert "CHILD-SUMMARY-FULL-TEXT" not in first


# ---------------------------------------------------------------- AC-21


def _all_finished(root: Path) -> str | None:
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), run_finished_record()])
    return None


def _path_escape(root: Path) -> str | None:
    # A well-shaped unfinished journal sits where "../x" would lead from .runs/, so following the path would resume it.
    write_jsonl(root / "x.jsonl", [run_started_record(RUN_A, "ESCAPED-TASK")])
    return "../x"


def _unknown_id(root: Path) -> str | None:
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK)])
    return "20991231T235959Z-0123abcd"


def _finished_id(root: Path) -> str | None:
    write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), run_finished_record()])
    write_journal(root, RUN_B, [run_started_record(RUN_B, TASK)])
    return RUN_A


def _no_runs(root: Path) -> str | None:
    return None


@pytest.mark.parametrize(
    "prepare",
    (
        pytest.param(_all_finished, id="all-runs-finished"),
        pytest.param(_path_escape, id="path-escape"),
        pytest.param(_unknown_id, id="unknown-well-formed-id"),
        pytest.param(_finished_id, id="finished-id"),
        pytest.param(_no_runs, id="no-runs-at-all"),
    ),
)
def test_resume_refuses_unsafe_unknown_finished_or_missing_runs_before_any_model_call(tmp_path: Path, prepare: Callable[[Path], str | None]) -> None:
    """AC-21, INV-27, EC-28, EC-29, T-2: each case raises ConfigurationError, calls no runner, and leaves every journal untouched."""
    root = workspace_root(tmp_path)
    root.mkdir(parents=True)
    run_id = prepare(root)
    agent = build_agent(tmp_path)
    before = snapshot(root, include_runs=True)
    tree = ScriptedTree({})
    with tree.install(), pytest.raises(ConfigurationError):
        agent.resume(run_id)
    assert tree.calls == []
    assert snapshot(root, include_runs=True) == before


# ---------------------------------------------------------------- AC-22


def test_resume_skips_a_torn_final_journal_line(tmp_path: Path) -> None:
    """AC-22, EC-27, D-25: a final line cut mid-JSON is ignored; the run resumes and its run_finished is a whole JSON line."""
    root = workspace_root(tmp_path)
    torn = '{"event": "pair_fini'
    path = write_journal(root, RUN_A, [run_started_record(RUN_A, "TORN-TASK compare prices"), pair_started_record(pair_key("alpha"))], torn_tail=torn)
    agent = build_agent(tmp_path)
    tree = ScriptedTree({ROOT: [reply("RESUMED")]})
    with tree.install():
        answer = agent.resume()
    tree.assert_complete()
    assert answer.content == "RESUMED"
    briefing = tree.first_call(ROOT).prompt
    assert "TORN-TASK compare prices" in briefing and "alpha" in briefing
    lines = path.read_text(encoding="utf-8").splitlines()
    unreadable = []
    for line in lines:
        try:
            json.loads(line)
        except ValueError:
            unreadable.append(line)
    assert unreadable in ([], [torn]), f"only the torn fragment may stay unreadable: {unreadable}"
    readable = [json.loads(line) for line in lines if line not in unreadable]
    assert events(readable) == ["run_started", "pair_started", "run_finished"]


def test_resume_rejects_a_malformed_middle_journal_line(tmp_path: Path) -> None:
    """AC-22, EC-27: a malformed line before the last one raises ConfigurationError naming its line number, before any model call."""
    root = workspace_root(tmp_path)
    path = write_journal(root, RUN_A, [run_started_record(RUN_A, TASK), pair_started_record(pair_key("alpha"))])
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("{not json\n")
        handle.write(json.dumps(pair_started_record(pair_key("beta"))) + "\n")
    agent = build_agent(tmp_path)
    tree = ScriptedTree({})
    with tree.install(), pytest.raises(ConfigurationError) as refused:
        agent.resume()
    assert tree.calls == []
    assert int_token(3).search(_error_text(refused.value)), _error_text(refused.value)


# ---------------------------------------------------------------- AC-23


@pytest.mark.asyncio
async def test_cancelling_a_run_mid_pair_leaves_a_resumable_journal(tmp_path: Path) -> None:
    """AC-23, INV-31: cancelling arun while a generator waits propagates CancelledError, writes no run_finished, and aresume() relaunches the pair."""
    agent = build_agent(tmp_path)
    started = Signal("alpha's generator started")
    never = Signal("a release that never comes")

    cancelled: list[str] = []

    async def hold(call: ModelCall) -> object:
        started.set()
        try:
            await never.wait(call.agent)
        except asyncio.CancelledError:
            cancelled.append(call.agent)
            raise
        return reply("unreachable")

    first = ScriptedTree({ROOT: [launch(task("alpha"))], generator("alpha"): [hold]})
    with first.install():
        running = asyncio.create_task(agent.arun(TASK))
        await started.wait("the test")
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    first.assert_complete()
    assert cancelled == [generator("alpha")], "cancelling the root must cancel the running generator"
    root = workspace_root(tmp_path)
    assert events(journal_records(root)) == ["run_started", "pair_started"]
    second = ScriptedTree({ROOT: [launch(task("alpha")), reply("RESUMED-DONE")], **simple_pair("alpha", "ALPHA-SUMMARY")})
    with second.install():
        answer = await agent.aresume()
    second.assert_complete()
    assert answer.content == "RESUMED-DONE"
    assert "alpha" in second.first_call(ROOT).prompt
    records = journal_records(root)
    assert events(records).count("run_started") == 1 and events(records)[-1] == "run_finished"
    assert finished_cards(root)[pair_key("alpha")]["summary"] == "ALPHA-SUMMARY"


# ---------------------------------------------------------------- AC-41


@tool(name="remember")
def foreign_remember(text: str) -> str:
    """An MCP-style tool that happens to be named like a run-bound tool."""
    return text


def _configuration_error(raised: BaseException) -> ConfigurationError | None:
    current: BaseException | None = raised
    while current is not None:
        if isinstance(current, ConfigurationError):
            return current
        current = current.__cause__ or current.__context__
    return None


def test_a_run_time_tool_named_like_a_run_bound_tool_fails_before_the_journal_starts(tmp_path: Path) -> None:
    """AC-41, EC-1, INV-7: a root catalog tool named remember makes run() raise ConfigurationError naming it and the reserved list; no runner call, no journal."""
    from vidbyte.lib.constants.infinite import INFINITE_RESERVED_TOOL_NAMES

    agent = build_agent(tmp_path)
    agent.add_tool(foreign_remember)
    tree = ScriptedTree({})
    with tree.install(), pytest.raises(VidbyteSdkError) as raised:
        agent.run(TASK)
    refusal = _configuration_error(raised.value)
    assert refusal is not None, f"expected a ConfigurationError, got {raised.value!r}"
    text = _error_text(refusal)
    assert all(name in text for name in INFINITE_RESERVED_TOOL_NAMES), text
    assert tree.calls == []
    assert journal_paths(workspace_root(tmp_path)) == []


# ---------------------------------------------------------------- NFR-3, T-3


def test_every_journal_record_is_fsynced_before_the_next_one_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-3, INV-25, D-25: os.fsync runs once the journal holds 1, 2, 3, and 4 records, so no record waits for a later one."""
    import vidbyte.agents.infinite.journal as journal_module

    agent = build_agent(tmp_path)
    root = workspace_root(tmp_path)
    real_fsync = os.fsync
    seen: list[int] = []

    def spy(descriptor: int) -> None:
        real_fsync(descriptor)
        seen.append(sum(len([line for line in path.read_bytes().splitlines() if line.strip()]) for path in journal_paths(root)))

    monkeypatch.setattr(os, "fsync", spy)
    if hasattr(journal_module, "fsync"):
        monkeypatch.setattr(journal_module, "fsync", spy)
    tree = ScriptedTree({ROOT: [launch(task("alpha")), reply("done")], **simple_pair("alpha", "ALPHA-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert len(journal_records(root)) == 4
    assert {1, 2, 3, 4} <= set(seen), f"journal sizes seen at fsync time: {seen}"


def test_api_key_stays_out_of_the_settings_repr_the_journal_and_the_workspace(tmp_path: Path) -> None:
    """T-3: the API key is not in the settings repr, the journal, or any workspace file after a run with one pair."""
    from vidbyte.agents.infinite import InfiniteMemoryAgent

    secret = "sk-live-SECRET-0123456789"
    settings = build_settings(tmp_path, api_keys=[secret])
    assert secret not in repr(settings)
    agent = InfiniteMemoryAgent(settings)
    tree = ScriptedTree({ROOT: [launch(task("alpha")), reply("done")], **simple_pair("alpha", "ALPHA-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    files = snapshot(workspace_root(tmp_path), include_runs=True)
    assert any(name.startswith(".runs/") for name in files)
    leaked = [name for name, content in files.items() if secret.encode() in content]
    assert not leaked, f"the API key reached {leaked}"
