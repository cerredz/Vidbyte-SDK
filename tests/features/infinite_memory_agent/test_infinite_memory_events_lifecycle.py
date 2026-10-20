"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_events_lifecycle.py

PURPOSE: Proves how an InfiniteMemory run's event stream opens and ends when the run does not finish normally: a cancelled run ends with run_stopped(cancelled) and its resume opens with run_resumed, a runner error ends with run_stopped(failed), a KeyboardInterrupt ends with run_stopped(cancelled), each run stays resumable, the handoff of a cancelled run says it is unfinished and how to resume it, and a resumed run counts its pairs at every depth.
ROLE IN CODEBASE: Lifecycle layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-events/spec.md (AC-5, AC-6, AC-17, AC-27; INV-1..INV-3, INV-6, INV-27; D-9, D-14; the section 9.1 run_resumed and run_finished counts). Exercises the try/except BaseException that vidbyte/agents/infinite/runtime.py wraps around the run, InfiniteEvents.run_stopped/run_resumed in vidbyte/agents/infinite/events.py, and InfiniteMemoryAgent.run_handoff for an unfinished journal.
ARCHITECTURE NOTE: Cancellation copies the pack's existing pattern (test_infinite_memory_resume.py): the generator's runner sets a Signal and then waits on one nobody sets, the test cancels the asyncio task running arun, and nothing sleeps. The KeyboardInterrupt case runs arun inside asyncio.run in a plain test, so even an interrupt that crossed a task boundary would surface as the exception pytest.raises expects instead of aborting the pytest session.
FUNCTION INVENTORY: test_a_cancelled_run_ends_with_run_stopped_and_its_resume_opens_with_run_resumed (AC-5, INV-2, INV-6, INV-27); test_the_handoff_of_a_cancelled_run_says_it_is_unfinished_and_how_to_resume (AC-17, INV-22, INV-24, D-14); test_a_resumed_run_counts_finished_and_interrupted_pairs_at_every_depth (section 9.1, INV-2); test_a_root_runner_error_ends_the_stream_with_run_stopped_failed_and_the_run_stays_resumable (AC-6, INV-3, INV-6); test_a_keyboard_interrupt_in_arun_ends_the_stream_with_run_stopped_cancelled (AC-27, INV-3). _cancel_while_alpha_waits runs the shared cancellation.
COMMON MODIFICATION PATTERNS: A new way for a run to stop gets one test that collects events with seen.append, triggers the stop, and checks that the last event is run_stopped with its reason and error_type and that the journal has no run_finished.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not wait for the generator with a sleep; await the Signal it sets. 3. Do not raise KeyboardInterrupt inside a pytest-asyncio test body; run it through asyncio.run so a regression cannot end the pytest session.
KNOWN EDGE CASES: BaseAgent.generate_reply wraps an Exception from the runtime in AgentExecutionError, so AC-6 compares the caller's exception with a run without events instead of naming its type, while run_stopped names the RuntimeError the runtime itself saw. str(CancelledError()) is empty, so the cancelled run_stopped has an empty message.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 6.1, 6.2, 6.3 and 9.1; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_events_lifecycle.py -q
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    assert_portable,
    kinds,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    RUN_A,
    TASK,
    ModelCall,
    ScriptedTree,
    Signal,
    build_agent,
    card_record,
    events,
    fail,
    generator,
    journal_paths,
    journal_records,
    launch,
    pair_finished_record,
    pair_key,
    pair_started_record,
    reply,
    run_started_record,
    simple_pair,
    task,
    workspace_root,
    write_journal,
)
from vidbyte.lib.errors import VidbyteSdkError

RUNNER_ERROR = "provider exploded mid-run"


async def _cancel_while_alpha_waits(agent: Any) -> None:
    """Starts arun, waits until pair alpha's generator is running, cancels the run, and checks CancelledError propagates."""
    started = Signal("alpha's generator started")
    never = Signal("a release that never comes")

    async def hold(call: ModelCall) -> object:
        started.set()
        await never.wait(call.agent)
        return reply("unreachable")

    tree = ScriptedTree({ROOT: [launch(task("alpha"))], generator("alpha"): [hold]})
    with tree.install():
        running = asyncio.create_task(agent.arun(TASK))
        await started.wait("the test")
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    tree.assert_complete()


# ---------------------------------------------------------------- AC-5, AC-17


@pytest.mark.asyncio
async def test_a_cancelled_run_ends_with_run_stopped_and_its_resume_opens_with_run_resumed(tmp_path: Path) -> None:
    """AC-5, INV-2, INV-6, INV-27 (and derived-events AC-12, INV-15): a run cancelled mid-pair announces the pair's subagent_aborted and then ends its stream with run_stopped(cancelled, CancelledError), its journal holds exactly run_started and pair_started, and aresume() opens with run_resumed naming the interrupted pair and ends with run_finished, all under one run id."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteStopCause

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    await _cancel_while_alpha_waits(agent)
    first = list(seen)
    assert kinds(first) == ["run_started", "subagent_launched", "subagent_aborted", "run_stopped"]
    stopped = first[-1]
    assert (stopped.agent_key, stopped.role, stopped.depth) == ("root", InfiniteAgentRole.ROOT, 0)
    assert (stopped.details.reason, stopped.details.error_type, stopped.details.message) == (InfiniteStopCause.CANCELLED, "CancelledError", "")
    assert stopped.summary == "Run stopped (cancelled): CancelledError; resume it to continue"
    root = workspace_root(tmp_path)
    assert events(journal_records(root)) == ["run_started", "pair_started"]
    (journal,) = journal_paths(root)

    second = ScriptedTree({ROOT: [launch(task("alpha")), reply("RESUMED-DONE")], **simple_pair("alpha", "ALPHA-SUMMARY")})
    with second.install():
        answer = await agent.aresume()
    second.assert_complete()
    resumed = seen[len(first) :]
    assert kinds(resumed) == ["run_resumed", "subagent_launched", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "run_finished"]
    opening = resumed[0].details
    assert (opening.task, opening.finished, opening.interrupted, opening.interrupted_omitted) == (TASK, 0, (pair_key("alpha"),), 0)
    assert resumed[0].summary == "Run resumed: 0 tasks done earlier, 1 will run again"
    assert {event.run_id for event in seen} == {journal.stem} == {answer.metadata["infinite_run_id"]}
    assert events(journal_records(root))[-1] == "run_finished"
    assert_portable(seen)


@pytest.mark.asyncio
async def test_the_handoff_of_a_cancelled_run_says_it_is_unfinished_and_how_to_resume(tmp_path: Path) -> None:
    """AC-17, INV-22, INV-24, D-14: after the AC-5 cancellation, run_handoff(run_id) makes no model call, changes no journal byte, and its Outcome, Unverified, and How to continue sections give the not-finished text, the interrupted pair, and agent.resume("<run_id>"); run_handoff() with no id picks the same run."""
    from vidbyte.context.handoff.infinite import InfiniteHandoff

    agent = build_agent(tmp_path)
    await _cancel_while_alpha_waits(agent)
    (journal,) = journal_paths(workspace_root(tmp_path))
    before = journal.read_bytes()
    quiet = ScriptedTree({})
    with quiet.install():
        handoff = agent.run_handoff(journal.stem)
        newest = agent.run_handoff()
    assert quiet.calls == []
    assert journal.read_bytes() == before
    sections = handoff.sections
    assert sections["Outcome"] == InfiniteHandoff.UNFINISHED.format(task=TASK)
    assert sections["Work done"] == InfiniteHandoff.EMPTY
    assert sections["Unverified or failed work"] == InfiniteHandoff.INTERRUPTED_LINE.format(key=pair_key("alpha"))
    assert sections["How to continue"] == InfiniteHandoff.RESUME.format(run_id=journal.stem)
    assert f'agent.resume("{journal.stem}")' in sections["How to continue"]
    assert newest.metadata["run_id"] == journal.stem and newest.sections == sections


def test_a_resumed_run_counts_finished_and_interrupted_pairs_at_every_depth(tmp_path: Path) -> None:
    """Section 9.1, INV-2: resuming a hand-written journal in which root/a started, its nested pair root/a/gen/b finished, and root/a/gen/c started gives run_resumed finished=1 and interrupted naming both unfinished keys at their depths, and run_finished pairs=1 and agents=6, because these counts cover every depth, not only the root's own pairs."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)
    nested_done, nested_cut = "root/a/gen/b", "root/a/gen/c"
    write_journal(
        workspace_root(tmp_path),
        RUN_A,
        [
            run_started_record(RUN_A, TASK),
            pair_started_record("root/a"),
            pair_started_record(nested_done),
            pair_finished_record(card_record("b", key=nested_done, summary="B-SUMMARY")),
            pair_started_record(nested_cut),
        ],
    )
    tree = ScriptedTree({ROOT: [reply("Finished after the resume.")]})
    with tree.install():
        agent.resume()
    tree.assert_complete()
    assert kinds(seen) == ["run_resumed", "run_finished"]
    resumed, finished = seen
    assert (resumed.run_id, resumed.details.finished, resumed.details.interrupted, resumed.details.interrupted_omitted) == (RUN_A, 1, ("root/a", nested_cut), 0)
    assert (finished.run_id, finished.details.pairs, finished.details.agents) == (RUN_A, 1, 6)
    assert_portable(seen)


# ---------------------------------------------------------------- AC-6, AC-27


def test_a_root_runner_error_ends_the_stream_with_run_stopped_failed_and_the_run_stays_resumable(tmp_path: Path) -> None:
    """AC-6, INV-3, INV-6: a RuntimeError from the root's runner reaches the caller exactly as without events, the stream ends run_started, run_stopped(failed, RuntimeError, its message), the journal has no run_finished, and resume() accepts the run."""
    from vidbyte.lib.enums.infinite import InfiniteStopCause

    quiet_base, watched_base = tmp_path / "quiet", tmp_path / "watched"
    quiet_base.mkdir()
    watched_base.mkdir()
    quiet = build_agent(quiet_base)
    with ScriptedTree({ROOT: [fail(RuntimeError(RUNNER_ERROR))]}).install(), pytest.raises(VidbyteSdkError) as without_events:
        quiet.run(TASK)
    seen: list[Any] = []
    agent = build_agent(watched_base, on_event=seen.append)
    with ScriptedTree({ROOT: [fail(RuntimeError(RUNNER_ERROR))]}).install(), pytest.raises(VidbyteSdkError) as with_events:
        agent.run(TASK)
    assert type(with_events.value) is type(without_events.value)
    assert str(with_events.value) == str(without_events.value)
    assert type(with_events.value.__cause__) is type(without_events.value.__cause__)
    assert kinds(seen) == ["run_started", "run_stopped"]
    stopped = seen[-1].details
    assert (stopped.reason, stopped.error_type, stopped.message) == (InfiniteStopCause.FAILED, "RuntimeError", RUNNER_ERROR)
    assert seen[-1].summary == "Run stopped (failed): RuntimeError; resume it to continue"
    assert events(journal_records(workspace_root(watched_base))) == ["run_started"]
    run_id = seen[0].run_id
    tree = ScriptedTree({ROOT: [reply("RESUMED")]})
    with tree.install():
        resumed = agent.resume(run_id)
    tree.assert_complete()
    assert (resumed.content, resumed.metadata["infinite_run_id"]) == ("RESUMED", run_id)
    assert kinds(seen)[2:] == ["run_resumed", "run_finished"]
    assert_portable(seen)


def test_a_keyboard_interrupt_in_arun_ends_the_stream_with_run_stopped_cancelled(tmp_path: Path) -> None:
    """AC-27, INV-3: a KeyboardInterrupt raised by the root's runner inside arun propagates, and the last event is run_stopped(cancelled, KeyboardInterrupt) with the journal left unfinished."""
    from vidbyte.lib.enums.infinite import InfiniteStopCause

    seen: list[Any] = []
    agent = build_agent(tmp_path, on_event=seen.append)

    async def main() -> None:
        await agent.arun(TASK)

    with ScriptedTree({ROOT: [fail(KeyboardInterrupt())]}).install(), pytest.raises(KeyboardInterrupt):
        asyncio.run(main())
    assert kinds(seen) == ["run_started", "run_stopped"]
    stopped = seen[-1].details
    assert (stopped.reason, stopped.error_type) == (InfiniteStopCause.CANCELLED, "KeyboardInterrupt")
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started"]
