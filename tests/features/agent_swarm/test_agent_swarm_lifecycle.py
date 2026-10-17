"""FILE: tests/features/agent_swarm/test_agent_swarm_lifecycle.py

PURPOSE: Pins how a swarm ends and what survives a failure. A spent turn budget stops wakes and ends MAX_TURNS. The time limit cancels every agent and returns TIMEOUT, even through a slow callback. A provider error fails only its agent and names the cause. Every agent failing ends FAILED, and a failure of the last working agent ends the swarm without a hang. A tool exception is only a tool error. A turn-middleware bug fails only its agent through the fail-closed abort. Concurrent and repeated runs are refused or start fresh, and cancellation propagates. A raising on_event never stops the swarm. The event outbox delivers once, in order, and never twice at once. TOOL_CALLED carries name and status and skips isDone.
ROLE IN CODEBASE: Lifecycle layer of tests/features/agent_swarm/ (spec AC-5, AC-6, AC-7, AC-8, AC-10, AC-15, AC-19; EC-7, EC-8, EC-12, EC-13, EC-14, EC-15, EC-16, EC-17, EC-19, EC-21, EC-23, EC-30; INV-9..INV-17, INV-19; D-6, D-7, D-8; NFR-9). Exercises AgentSwarm.arun, AgentSwarmRuntime.arun and its member containment, end check and timeout, and AgentSwarmEvents.
ARCHITECTURE NOTE: Only the model runner is scripted, with one deliberate exception documented in FEATURE.md: the middleware-abort test replaces AgentSwarmRuntime.record_tool_call for one agent with a function that raises, because EC-15 and EC-16 (c) describe what a bug there must do and nothing else can make a member's run return early. Every swarm run is checked by assert_event_invariants.
FUNCTION INVENTORY: test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered (AC-5, EC-8); test_the_time_limit_cancels_every_agent_and_returns_timeout (AC-6, EC-17, INV-12, NFR-9); test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended (EC-23); test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail (AC-7, EC-7, EC-12); test_every_agent_failing_ends_failed_with_no_replies (AC-8, EC-14); test_the_last_working_agent_failing_ends_the_swarm_without_a_hang (EC-13); test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure (EC-16 b); test_a_turn_middleware_recording_bug_fails_only_that_agent_naming_the_middleware_abort (EC-15, EC-16 c); test_a_second_concurrent_arun_is_refused_and_a_later_arun_starts_fresh (AC-15, EC-30, INV-19); test_a_swarm_runtime_runs_only_once (INV-19); test_cancelling_arun_propagates_and_the_swarm_can_run_again (EC-19); test_a_raising_on_event_callback_never_stops_the_swarm (AC-10, EC-21, INV-15, INV-16); test_the_event_outbox_delivers_each_event_once_in_order_even_with_concurrent_flushes (D-6, INV-13, INV-15); test_a_flush_cancelled_mid_callback_never_repeats_that_event (EC-23, D-6); test_tool_called_events_carry_name_and_status_and_skip_isdone (AC-19).
COMMON MODIFICATION PATTERNS: A new stop condition gets one test that drives it and asserts the stop reason, the replies, and assert_event_invariants.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert exact wall-clock durations; the time-limit test only bounds the overrun loosely, and the stop reason proves the limit fired. 3. Do not add a second fault injection; drive failures through the model runner or a developer tool.
KNOWN EDGE CASES: Under the time limit the cut model call is the after(...) wait, which is cancelled, so it never records a guard problem. The concurrent-run test keeps one ScriptedSwarm across runs; the agents' scripts continue, so the third run's calls are each agent's next step, and their empty history proves a fresh conversation.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6.1, 6.2, 6.3, 8.1 (D-6, D-7, D-8) and 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_lifecycle.py -q
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    DELIVERED,
    ENDED,
    FAILED,
    IDLE,
    RUN_GUARD_SECONDS,
    SENT,
    STARTED,
    TOOL_CALLED,
    WOKE,
    EventLog,
    ScriptedSwarm,
    SearchTool,
    Signal,
    after,
    assert_event_invariants,
    assert_no_stray_tasks,
    build_settings,
    build_swarm,
    fail,
    finish,
    is_error,
    of_kind,
    observe,
    only,
    prompt_text,
    provider_error,
    reply,
    run_swarm,
    send,
    seq_of,
    template_regex,
    tool_call,
    tool_result,
    workplace_path,
    yield_to_loop,
)

NAMES = ("builder", "tester")
THREE = ("builder", "tester", "reviewer")
NOTE = "c2f.py is ready; please run your tests against it."
CAUSE = "openai returned 503: upstream overloaded"
GOAL_AGAIN = "Run the same swarm runtime a second time."


@pytest.mark.asyncio
async def test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered(tmp_path: Path) -> None:
    """AC-5, EC-8, INV-9, INV-10: with max_turns equal to the agent count, a message to an idle tester is accepted but wakes nobody, and the swarm ends MAX_TURNS."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    tester_idle = log.signal(IDLE, "tester")
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")], "builder": [after(tester_idle, send("tester", NOTE)), reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, max_turns=2, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TURNS
    # The send itself succeeded (queued); only the wake was refused.
    accepted = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(accepted) and template_regex(prompt_text("message_sent"), recipient="tester").search(accepted)
    assert only(result.events, SENT, "builder").peer == "tester"
    assert of_kind(result.events, WOKE) == [] and of_kind(result.events, DELIVERED) == []
    assert len(scripted.calls_by("tester")) == 1
    # Both agents were released normally and return their last turn's reply.
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=2, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_time_limit_cancels_every_agent_and_returns_timeout(tmp_path: Path) -> None:
    """AC-6, EC-17, INV-12, NFR-9: a model call that never answers is cut by timeout_seconds; arun returns TIMEOUT, ends with SWARM_ENDED, and leaves no task behind."""
    from vidbyte import AgentSwarmStopReason

    never = Signal("a model answer that never comes")
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [after(never, reply("Never sent."))], "tester": [reply("Tester done.")]})
    timeout = 0.5
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=timeout, on_event=log.callback)
    started = time.monotonic()
    with scripted.install():
        result = await run_swarm(swarm)
    elapsed = time.monotonic() - started

    assert result.stop_reason is AgentSwarmStopReason.TIMEOUT
    assert [(event.kind.value, event.agent) for event in result.events] == [(STARTED, "builder"), (STARTED, "tester"), (IDLE, "tester"), (ENDED, "")]
    assert result.events[-1].stop_reason is AgentSwarmStopReason.TIMEOUT
    assert result.replies == ()
    # The limit is real: the stuck call was cancelled long before its own 20-second guard could fire.
    assert elapsed < timeout + 10.0, f"arun took {elapsed:.1f} s for a {timeout} s limit"
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended(tmp_path: Path) -> None:
    """EC-23, INV-15: a callback stuck on tester's AGENT_IDLE is cut by the time limit, never called again for it, and SWARM_ENDED still reaches on_event."""
    from vidbyte import AgentSwarmStopReason

    stuck, never = Signal("a callback that never returns"), Signal("a model answer that never comes")
    log = EventLog(mode="async")

    async def hold_on_tester_idle(event: Any) -> None:
        if event.kind.value == IDLE and event.agent == "tester":
            await stuck.wait("on_event")

    log.hook(hold_on_tester_idle)
    scripted = ScriptedSwarm({"builder": [after(never, reply("Never sent."))], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=0.5, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.TIMEOUT
    assert [(event.kind.value, event.agent) for event in log.received] == [(STARTED, "builder"), (STARTED, "tester"), (IDLE, "tester"), (ENDED, "")]
    assert log.received[-1] == result.events[-1]
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=500, log=log)


@pytest.mark.asyncio
async def test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail(tmp_path: Path) -> None:
    """AC-7, EC-7, EC-12, INV-17: reviewer's provider error becomes one AGENT_FAILED naming ProviderRequestError and its text; the others end normally and a later message to reviewer is refused."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    log = EventLog()
    reviewer_failed = log.signal(FAILED, "reviewer")
    scripted = ScriptedSwarm(
        {
            "reviewer": [fail(provider_error(CAUSE))],
            "builder": [after(reviewer_failed, send("reviewer", "Please review c2f.py.")), reply("Builder done.")],
            "tester": [reply("Tester done.")],
        }
    )
    swarm = build_swarm(tmp_path, THREE, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    failure = only(result.events, FAILED, "reviewer")
    # The root cause, not BaseAgent's generic wrapper text.
    assert failure.text.startswith("ProviderRequestError")
    assert CAUSE in failure.text
    assert "failed to generate a reply" not in failure.text
    refusal = tool_result(scripted.calls_by("builder")[1], "message")
    assert is_error(refusal) and template_regex(prompt_text("message_stopped_recipient"), recipient="reviewer").search(refusal), refusal
    assert of_kind(result.events, SENT) == []
    tool_event = only(result.events, TOOL_CALLED, "builder")
    assert (tool_event.tool_name, tool_event.tool_status) == ("message", ToolStatus.ERROR)
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, THREE, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_every_agent_failing_ends_failed_with_no_replies(tmp_path: Path) -> None:
    """AC-8, EC-14: when every model call raises a provider error, the stop reason is FAILED, each agent has one AGENT_FAILED naming its own cause, and replies is empty."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    scripted = ScriptedSwarm({name: [fail(provider_error(f"openai returned 503 for {name}"))] for name in NAMES})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.FAILED
    for name in NAMES:
        failure = only(result.events, FAILED, name)
        assert failure.text.startswith("ProviderRequestError") and f"openai returned 503 for {name}" in failure.text
    assert result.replies == ()
    assert len(result.events) == 5
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_last_working_agent_failing_ends_the_swarm_without_a_hang(tmp_path: Path) -> None:
    """EC-13, INV-10: tester fails while builder is already idle; the failure runs the end check, so the swarm ends QUIET with builder's reply only."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_idle = log.signal(IDLE, "builder")
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [after(builder_idle, fail(provider_error()))]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert seq_of(result.events, IDLE, "builder") < seq_of(result.events, FAILED, "tester")
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure(tmp_path: Path) -> None:
    """EC-16 (b), INV-17: a developer search tool that raises gives tester a tool error and a TOOL_CALLED with status error; tester keeps working and nobody fails."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    search = SearchTool(error=RuntimeError("search backend down"))
    log = EventLog()
    scripted = ScriptedSwarm({"tester": [tool_call("web_search", {"query": "c2f"}), reply("Tester done.")], "builder": [reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, search_tool=search, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert of_kind(result.events, FAILED) == []
    tool_event = only(result.events, TOOL_CALLED, "tester")
    assert (tool_event.tool_name, tool_event.tool_status) == ("web_search", ToolStatus.ERROR)
    assert is_error(tool_result(scripted.calls_by("tester")[1], "web_search"))
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_turn_middleware_recording_bug_fails_only_that_agent_naming_the_middleware_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-15, EC-16 (c), INV-17: a bug in record_tool_call aborts tester's run through the fail-closed turn middleware; tester gets one AGENT_FAILED naming that stop reason, and builder ends normally."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime
    from vidbyte.lib.dataclasses.tools import ToolStatus

    # The one deliberate fault injection of the pack (FEATURE.md): record_tool_call raises for tester only.
    original = AgentSwarmRuntime.record_tool_call

    async def broken_for_tester(self: Any, *args: Any, **kwargs: Any) -> Any:
        name = args[0] if args else kwargs.get("name")
        if name == "tester":
            raise RuntimeError("event recorder broke")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AgentSwarmRuntime, "record_tool_call", broken_for_tester)
    log = EventLog()
    scripted = ScriptedSwarm(
        {
            "tester": [tool_call("read_lines", {"path": "missing.txt"})],
            "builder": [tool_call("write_text", {"path": "notes.txt", "content": "n"}), reply("Builder done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    failure = only(result.events, FAILED, "tester")
    # The early return names the run's own stop reason, not the bug's type (spec EC-16 (c)).
    assert re.search(r"middleware.abort", failure.text, re.IGNORECASE), failure.text
    assert "RuntimeError" not in failure.text
    assert len(scripted.calls_by("tester")) == 1
    assert of_kind(result.events, TOOL_CALLED, "tester") == []
    builder_tool = only(result.events, TOOL_CALLED, "builder")
    assert (builder_tool.tool_name, builder_tool.tool_status) == ("write_text", ToolStatus.SUCCESS)
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_second_concurrent_arun_is_refused_and_a_later_arun_starts_fresh(tmp_path: Path) -> None:
    """AC-15, EC-30, INV-19: arun while a run is in progress raises ConfigurationError and changes nothing; a later arun starts at sequence 1 with fresh agents and the new goal."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.errors import ConfigurationError

    entered, release = Signal("builder's first call"), Signal("the first run may finish")
    log = EventLog()
    scripted = ScriptedSwarm(
        {
            "builder": [observe(lambda call: entered.set(), after(release, reply("First run done."))), reply("Third run done.")],
            "tester": [reply("Tester first."), reply("Tester third.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        first = asyncio.ensure_future(run_swarm(swarm))
        await entered.wait("the test")
        calls_before = len(scripted.calls)
        with pytest.raises(ConfigurationError):
            await swarm.arun("A second goal, sent while the first run is busy.")
        assert len(scripted.calls) == calls_before
        release.set()
        first_result = await first
        third_result = await run_swarm(swarm, "A third goal.")

    for result in (first_result, third_result):
        assert result.stop_reason is AgentSwarmStopReason.QUIET
        assert_event_invariants(result, NAMES, max_turns=500)
    # The refused call left no trace in the first run, and the third run's events start again at 1.
    assert log.received == [*first_result.events, *third_result.events]
    assert [(item.sender, item.content) for item in third_result.replies] == [("builder", "Third run done."), ("tester", "Tester third.")]
    for name in NAMES:
        fresh = scripted.calls_by(name)[1]
        assert fresh.prompt == "A third goal." and fresh.messages == []
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_swarm_runtime_runs_only_once(tmp_path: Path) -> None:
    """INV-19, section 9.2: an AgentSwarmRuntime runs one swarm; a second arun on it raises ConfigurationError before any model call."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    root = workplace_path(tmp_path)
    root.mkdir()
    runtime = AgentSwarmRuntime(build_settings(tmp_path, NAMES), root)
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [reply("Tester done.")]})
    with scripted.install():
        result = await run_swarm(runtime)
        calls_after_first = len(scripted.calls)
        with pytest.raises(ConfigurationError):
            await runtime.arun(GOAL_AGAIN)
    assert len(scripted.calls) == calls_after_first
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert_event_invariants(result, NAMES, max_turns=500)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_cancelling_arun_propagates_and_the_swarm_can_run_again(tmp_path: Path) -> None:
    """EC-19, INV-19: cancelling arun cancels the agent runs and raises CancelledError; the in-progress flag is cleared, so the next arun runs a fresh swarm."""
    from vidbyte import AgentSwarmStopReason

    entered, never = Signal("builder's first call"), Signal("a model answer that never comes")
    scripted = ScriptedSwarm(
        {
            "builder": [observe(lambda call: entered.set(), after(never, reply("Never sent."))), reply("Second run done.")],
            "tester": [reply("Tester first."), reply("Tester second.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES)
    with scripted.install():
        task = asyncio.ensure_future(swarm.arun("A goal that gets cancelled."))
        await entered.wait("the test")
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=RUN_GUARD_SECONDS)
        assert task in done, "arun did not finish after it was cancelled"
        assert task.cancelled(), f"cancellation was swallowed: {task.exception() or task.result()!r}"
        assert_no_stray_tasks()
        result = await run_swarm(swarm, "A goal after the cancellation.")

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Second run done."), ("tester", "Tester second.")]
    assert scripted.calls_by("builder")[1].messages == []
    assert_event_invariants(result, NAMES, max_turns=500)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [SENT, ENDED])
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_a_raising_on_event_callback_never_stops_the_swarm(tmp_path: Path, mode: str, kind: str) -> None:
    """AC-10, EC-21, INV-15, INV-16: a sync or async on_event that raises on MESSAGE_SENT or SWARM_ENDED is still called once per event in order, and the swarm finishes normally."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog(mode=mode, raise_on=kind, yields=1 if mode == "async" else 0)
    scripted = ScriptedSwarm({"builder": [send("tester", NOTE), reply("Sent.")], "tester": [reply("First pass."), reply("Got it.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert result.event_error_types == ("CallbackBoom",)
    # The callback error never reached the agent that recorded the event.
    sent_reply = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(sent_reply)
    assert only(result.events, DELIVERED, "tester").peer == "builder"
    assert_event_invariants(result, NAMES, max_turns=500, log=log, error_types=("CallbackBoom",))
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_event_outbox_delivers_each_event_once_in_order_even_with_concurrent_flushes() -> None:
    """D-6, INV-13, INV-15: record numbers events 1..N at once; overlapping flushes hand each event to on_event exactly once, in order, one call at a time."""
    from vidbyte import AgentSwarmEventKind, AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmEvents

    log = EventLog(mode="async", yields=2)
    outbox = AgentSwarmEvents(log.callback)
    recorded = [outbox.record(AgentSwarmEventKind.AGENT_STARTED, "builder"), outbox.record(AgentSwarmEventKind.AGENT_STARTED, "tester")]
    flushes = [asyncio.ensure_future(outbox.flush()) for _ in range(3)]
    recorded.append(outbox.record(AgentSwarmEventKind.AGENT_IDLE, "tester", text="Tester done."))
    await yield_to_loop(1)
    recorded.append(outbox.record(AgentSwarmEventKind.AGENT_IDLE, "builder", text=""))
    flushes.append(asyncio.ensure_future(outbox.flush()))
    await asyncio.gather(*flushes)
    recorded.append(outbox.record(AgentSwarmEventKind.SWARM_ENDED, "", stop_reason=AgentSwarmStopReason.QUIET))
    await asyncio.gather(outbox.flush(), outbox.flush())

    assert [event.sequence for event in recorded] == [1, 2, 3, 4, 5]
    assert outbox.events == tuple(recorded)
    assert log.received == recorded
    assert log.max_active == 1
    assert outbox.error_types == ()
    assert all(type(event.elapsed_ms) is int for event in recorded)
    assert [event.elapsed_ms for event in recorded] == sorted(event.elapsed_ms for event in recorded)
    # Without a callback, recording and flushing still work.
    silent = AgentSwarmEvents(None)
    silent.record(AgentSwarmEventKind.AGENT_STARTED, "builder")
    await silent.flush()
    assert [event.sequence for event in silent.events] == [1]


@pytest.mark.asyncio
async def test_a_flush_cancelled_mid_callback_never_repeats_that_event() -> None:
    """EC-23, D-6: an event is marked delivered before its callback is awaited, so a flush cancelled inside that callback never hands the same event over again, and cancellation is not swallowed."""
    from vidbyte import AgentSwarmEventKind
    from vidbyte.agents.agent_swarm import AgentSwarmEvents

    entered, stuck = Signal("the callback for event 2"), Signal("a callback that never returns")
    log = EventLog(mode="async")

    async def hold_on_second(event: Any) -> None:
        if event.sequence == 2:
            entered.set()
            await stuck.wait("on_event")

    log.hook(hold_on_second)
    outbox = AgentSwarmEvents(log.callback)
    outbox.record(AgentSwarmEventKind.AGENT_STARTED, "builder")
    outbox.record(AgentSwarmEventKind.AGENT_STARTED, "tester")
    flushing = asyncio.ensure_future(outbox.flush())
    await entered.wait("the test")
    flushing.cancel()
    done, _ = await asyncio.wait({flushing}, timeout=RUN_GUARD_SECONDS)
    assert flushing in done and flushing.cancelled()
    outbox.record(AgentSwarmEventKind.AGENT_IDLE, "tester", text="Tester done.")
    await outbox.flush()

    assert [event.sequence for event in log.received] == [1, 2, 3]
    assert outbox.error_types == ()


@pytest.mark.asyncio
async def test_tool_called_events_carry_name_and_status_and_skip_isdone(tmp_path: Path) -> None:
    """AC-19, INV-21: bash and a failing read_lines each give one TOOL_CALLED with their status; the isDone that ends the turn gives none, and bash ran in the workplace."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    log = EventLog()
    scripted = ScriptedSwarm(
        {
            "tester": [tool_call("bash", {"command": "echo hello > bash-note.txt"}), tool_call("read_lines", {"path": "missing.txt"}), finish("Checked.")],
            "builder": [reply("Builder done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(event.tool_name, event.tool_status) for event in of_kind(result.events, TOOL_CALLED, "tester")] == [("bash", ToolStatus.SUCCESS), ("read_lines", ToolStatus.ERROR)]
    assert of_kind(result.events, TOOL_CALLED, "builder") == []
    assert (workplace_path(tmp_path) / "bash-note.txt").read_text(encoding="utf-8").strip() == "hello"
    assert only(result.events, IDLE, "tester").text == "Checked."
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()
