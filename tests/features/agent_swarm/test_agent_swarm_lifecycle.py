"""FILE: tests/features/agent_swarm/test_agent_swarm_lifecycle.py

PURPOSE: Pins how a swarm ends and what each agent's ending looks like. A spent turn budget refuses wakes with wake_refused, at send time or at a turn end, and ends MAX_TURNS with each such message undelivered once. The time limit cancels every agent with agent_cancelled naming whether it was working or idle, even through a slow callback or during the start flush, and never overwrites an end already decided. A provider error fails only its agent, names the cause and records its model_error; a later message to it is a success that says it stopped and is recorded sent then undelivered. Every agent failing ends FAILED, a failure of the last working agent ends the swarm without a hang, and mail left for a failed agent is marked undelivered with its failure. An unrequested CancelledError fails only that agent. A tool exception, or a model-made tool name with a newline, is only a tool error. A turn-middleware bug exits only its agent with agent_exited naming middleware_abort. Concurrent and repeated runs are refused or start fresh, and cancellation propagates. A raising on_event never stops the swarm. The event outbox delivers once, in order, and never twice at once. Event time counts from arun. TOOL_CALLED carries name and status and skips isDone.
ROLE IN CODEBASE: Lifecycle layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-5, AC-6, AC-7, AC-23, AC-24; EC-5, EC-10, EC-11, EC-14; INV-6, INV-9, INV-10, INV-12, INV-13, INV-14, INV-16, INV-17, INV-20, INV-23, INV-28, INV-40). Exercises AgentSwarm.arun, AgentSwarmRuntime.arun with its member containment, end check, stop block and timeout, and AgentSwarmEvents.
ARCHITECTURE NOTE: Only the model runner and the Tavily HTTP call are scripted, with one deliberate exception documented in FEATURE.md: the middleware-abort test replaces AgentSwarmRuntime.record_tool_call for one agent with a function that raises, because AC-24 names that fault and nothing else makes a member's run return early. Every swarm run is checked by assert_event_invariants; the time-limit-after-the-decided-end run is checked without its callback log, which the stuck callback cuts.
FUNCTION INVENTORY: test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered (AC-6, EC-5); test_a_turn_end_with_mail_and_no_turn_left_refuses_the_wake_once_and_ends_max_turns (INV-10); test_the_time_limit_cancels_every_agent_and_returns_timeout (INV-12, INV-14); test_the_time_limit_labels_working_and_idle_agents_cancelled_and_fails_none (AC-23); test_the_time_limit_during_the_start_flush_cancels_every_member_as_working (EC-10); test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended (INV-20); test_the_time_limit_firing_after_the_end_was_decided_keeps_the_decided_stop_reason (INV-12, INV-14); test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail (AC-5, INV-6, INV-23); test_every_agent_failing_ends_failed_with_no_replies (EC-14); test_the_last_working_agent_failing_ends_the_swarm_without_a_hang; test_mail_left_for_an_agent_that_failed_is_marked_undelivered_with_its_failure (INV-14); test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure; test_a_turn_middleware_recording_bug_exits_only_that_agent_naming_the_middleware_abort (AC-24); _assert_unrequested_cancel_failed_only; three stray-CancelledError tests (EC-11); test_an_unrequested_cancel_after_the_end_was_decided_does_not_fail_the_agent; concurrency, re-run and cancellation tests (INV-40); callback and outbox tests (INV-20); test_event_time_counts_from_arun_not_from_building_the_runtime (INV-28); test_tool_called_events_carry_name_and_status_and_skip_isdone; test_a_tool_name_holding_a_newline_is_a_tool_error_not_a_failure.
COMMON MODIFICATION PATTERNS: A new stop condition gets one test that drives it and asserts the stop reason, the swarm_stopping block, each agent's terminal event, the replies, and assert_event_invariants.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert exact wall-clock durations; the time-limit tests only bound the overrun loosely, and the stop reason proves the limit fired. 3. Do not add a second fault injection; drive failures through the model runner, FakeTavily or a callback.
KNOWN EDGE CASES: Under the time limit the order in which the task group cancels member tasks is not a contract, so the agent_cancelled events recorded by the members' own cancel branches are compared as a set; the ones _stop(timeout) records for members whose task never ran are in member order (EC-10). An agent cut inside its own turn-end flush may be labeled working or idle, so only agents that were plainly parked or plainly inside a model call have their agent_state pinned. The concurrent-run test keeps one ScriptedSwarm across runs; the third run's calls are each agent's next step, and their empty history proves a fresh conversation. The clock test holds the pack's one timed wait (0.3 s between building the runtime and arun), because where the clock starts is what it tests. The stray-cancel tests give the swarm a two-second limit, so before the rule exists they fail on TIMEOUT in about two seconds each.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1, 6.2, 6.3 and 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_lifecycle.py -q
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    CANCELLED,
    DELIVERED,
    ENDED,
    EXITED,
    FAILED,
    IDLE,
    MODEL_CALLED,
    MODEL_ERROR,
    PREPARED,
    RELEASED,
    RUN_GUARD_SECONDS,
    SENT,
    STARTED,
    STOPPING,
    TAVILY_TOOL,
    TERMINAL_KINDS,
    TOOL_CALLED,
    UNDELIVERED,
    WAKE_REFUSED,
    WOKE,
    EventLog,
    FakeTavily,
    ScriptedSwarm,
    Signal,
    after,
    assert_event_invariants,
    assert_no_stray_tasks,
    build_settings,
    build_swarm,
    describe,
    error_line,
    fail,
    finish,
    is_error,
    observe,
    of_kind,
    only,
    pairs,
    prompt_text,
    provider_error,
    reply,
    run_swarm,
    search,
    send,
    seq_of,
    start_pairs,
    template_regex,
    tool_call,
    tool_result,
    web_search_fields,
    workplace_path,
    yield_to_loop,
)

NAMES = ("builder", "tester")
THREE = ("builder", "tester", "reviewer")
NOTE = "c2f.py is ready; please run your tests against it."
CAUSE = "openai returned 503: upstream overloaded"
GOAL_AGAIN = "Run the same swarm runtime a second time."


def _terminals(events: Any) -> dict[str, list[str]]:
    # Each agent's terminal events, in record order (INV-14: exactly one each).
    found: dict[str, list[str]] = {}
    for event in events:
        if event.kind.value in TERMINAL_KINDS:
            found.setdefault(event.agent, []).append(event.kind.value)
    return found


def _assert_sent_then_undelivered(events: Any, sender: str, recipient: str) -> Any:
    # INV-6, AC-5: the send to a stopped recipient is recorded, and its undelivered mark is the very next event with the same id.
    sent = only(events, SENT, sender)
    follower = events[sent.sequence]
    assert sent.peer == recipient and (follower.kind.value, follower.agent, follower.peer, follower.message_id) == (UNDELIVERED, recipient, sender, sent.message_id), describe(events)
    return sent


@pytest.mark.asyncio
async def test_a_spent_turn_budget_stops_wakes_and_ends_max_turns_with_the_message_undelivered(tmp_path: Path) -> None:
    """AC-6, EC-5, INV-9, INV-12 (r5 AC-5 kept, wake_refused and message_undelivered added): with max_turns equal to the agent count, a message to an idle tester is accepted, records message_sent then wake_refused, wakes nobody, and gets exactly one message_undelivered when the swarm ends MAX_TURNS."""
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
    sent = only(result.events, SENT, "builder")
    refused = only(result.events, WAKE_REFUSED, "tester")
    assert sent.peer == "tester" and (refused.sequence, refused.peer, refused.message_id) == (sent.sequence + 1, "builder", sent.message_id)
    undelivered = only(result.events, UNDELIVERED, "tester")
    assert (undelivered.peer, undelivered.message_id) == ("builder", sent.message_id)
    assert undelivered.sequence > only(result.events, STOPPING).sequence
    assert of_kind(result.events, WOKE) == [] and of_kind(result.events, DELIVERED) == []
    assert len(scripted.calls_by("tester")) == 1
    # Both agents were released normally and return their last turn's reply.
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=2, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_turn_end_with_mail_and_no_turn_left_refuses_the_wake_once_and_ends_max_turns(tmp_path: Path) -> None:
    """INV-10, EC-5: a message that waits for a working tester whose budget is spent gets one wake_refused when tester ends its turn, right after its agent_idle, and one message_undelivered at the stop; nobody wakes."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_sent = log.signal(SENT, "builder")
    scripted = ScriptedSwarm({"builder": [send("tester", NOTE), reply("Builder done.")], "tester": [after(builder_sent, reply("Tester done."))]})
    swarm = build_swarm(tmp_path, NAMES, max_turns=2, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TURNS, describe(result.events)
    sent = only(result.events, SENT, "builder")
    refused = only(result.events, WAKE_REFUSED, "tester")
    assert (refused.sequence, refused.peer, refused.message_id) == (seq_of(result.events, IDLE, "tester") + 1, "builder", sent.message_id)
    assert only(result.events, UNDELIVERED, "tester").message_id == sent.message_id
    assert of_kind(result.events, WOKE) == [] and of_kind(result.events, DELIVERED) == []
    assert len(scripted.calls_by("tester")) == 1
    assert_event_invariants(result, NAMES, max_turns=2, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_time_limit_cancels_every_agent_and_returns_timeout(tmp_path: Path) -> None:
    """INV-12, INV-14 (r5 AC-6 kept, its event list rewritten for v2): a model call that never answers is cut by timeout_seconds; builder is cancelled while working and tester while idle, swarm_stopping carries TIMEOUT, arun returns TIMEOUT, and no task is left behind."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.enums import AgentSwarmAgentState

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
    events = result.events
    assert pairs(events[:7]) == [*start_pairs(NAMES), (MODEL_CALLED, "tester"), (IDLE, "tester")], describe(events)
    assert sorted(pairs(events[7:9])) == [(CANCELLED, "builder"), (CANCELLED, "tester")], describe(events)
    assert pairs(events[9:]) == [(STOPPING, ""), (ENDED, "")], describe(events)
    assert {event.agent: event.agent_state for event in of_kind(events, CANCELLED)} == {"builder": AgentSwarmAgentState.WORKING, "tester": AgentSwarmAgentState.IDLE}
    assert events[-2].stop_reason is AgentSwarmStopReason.TIMEOUT and events[-1].stop_reason is AgentSwarmStopReason.TIMEOUT
    assert result.replies == ()
    # The limit is real: the stuck call was cancelled long before its own 20-second guard could fire.
    assert elapsed < timeout + 10.0, f"arun took {elapsed:.1f} s for a {timeout} s limit"
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_time_limit_labels_working_and_idle_agents_cancelled_and_fails_none(tmp_path: Path) -> None:
    """AC-23, INV-12, INV-14: the limit expires while builder and reviewer are inside model calls and tester is idle; each working agent gets agent_cancelled working, tester gets agent_cancelled idle, swarm_stopping carries timeout, no agent_failed exists, and swarm_ended is last."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.enums import AgentSwarmAgentState

    never = Signal("a model answer that never comes")
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [after(never, reply("Never sent."))], "tester": [reply("Tester done.")], "reviewer": [after(never, reply("Never sent."))]})
    swarm = build_swarm(tmp_path, THREE, timeout_seconds=0.5, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.TIMEOUT
    events = result.events
    states = {event.agent: event.agent_state for event in of_kind(events, CANCELLED)}
    assert states == {"builder": AgentSwarmAgentState.WORKING, "tester": AgentSwarmAgentState.IDLE, "reviewer": AgentSwarmAgentState.WORKING}, describe(events)
    assert of_kind(events, FAILED) == [] and of_kind(events, RELEASED) == []
    assert max(event.sequence for event in of_kind(events, CANCELLED)) < only(events, STOPPING).sequence
    assert only(events, STOPPING).stop_reason is AgentSwarmStopReason.TIMEOUT
    assert events[-1].kind.value == ENDED and result.replies == ()
    assert_no_stray_tasks()
    assert_event_invariants(result, THREE, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_time_limit_during_the_start_flush_cancels_every_member_as_working(tmp_path: Path) -> None:
    """EC-10, INV-12, INV-17, INV-20: the callback for builder's agent_started never returns, so the limit expires inside the start flush before any member task runs; _stop(timeout) records agent_cancelled working for every member in member order, then swarm_stopping, and the final flush delivers every remaining event once."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.enums import AgentSwarmAgentState

    stuck = Signal("a callback that never returns")
    log = EventLog(mode="async")

    async def hold_on_builder_started(event: Any) -> None:
        if event.kind.value == STARTED and event.agent == "builder":
            await stuck.wait("on_event")

    log.hook(hold_on_builder_started)
    scripted = ScriptedSwarm({"builder": [], "tester": []})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=0.5, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.TIMEOUT
    assert pairs(result.events) == [*start_pairs(NAMES), (CANCELLED, "builder"), (CANCELLED, "tester"), (STOPPING, ""), (ENDED, "")], describe(result.events)
    assert [event.agent_state for event in of_kind(result.events, CANCELLED)] == [AgentSwarmAgentState.WORKING, AgentSwarmAgentState.WORKING]
    assert scripted.calls == []
    # The cut callback is never called again for its event, and everything after it still arrives once.
    assert log.received == list(result.events)
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)


@pytest.mark.asyncio
async def test_the_time_limit_cuts_a_slow_callback_once_and_still_delivers_swarm_ended(tmp_path: Path) -> None:
    """INV-20 (r5 EC-23 kept, its event list rewritten for v2): a callback stuck on tester's agent_idle is cut by the time limit, never called again for it, and the cancellations, swarm_stopping and swarm_ended still reach on_event."""
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
    seen = pairs(log.received)
    assert seen[:7] == [*start_pairs(NAMES), (MODEL_CALLED, "tester"), (IDLE, "tester")], describe(log.received)
    assert sorted(seen[7:9]) == [(CANCELLED, "builder"), (CANCELLED, "tester")] and seen[9:] == [(STOPPING, ""), (ENDED, "")], describe(log.received)
    assert log.received[-1] == result.events[-1]
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)


@pytest.mark.asyncio
async def test_the_time_limit_firing_after_the_end_was_decided_keeps_the_decided_stop_reason(tmp_path: Path) -> None:
    """INV-12, INV-14 (r5 EC-18 kept, its event list rewritten for v2): the swarm decides QUIET when tester ends its turn, but the callback for tester's agent_idle never returns, so the time limit fires while tester is unwinding; the stop reason stays QUIET, one swarm_stopping carries it, every agent still has exactly one terminal event and none failed, and replies hold only released agents' last turns."""
    from vidbyte import AgentSwarmStopReason

    stuck = Signal("a callback that never returns")
    log = EventLog(mode="async")
    builder_idle = log.signal(IDLE, "builder")

    async def hold_on_tester_idle(event: Any) -> None:
        if event.kind.value == IDLE and event.agent == "tester":
            await stuck.wait("on_event")

    log.hook(hold_on_tester_idle)
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [after(builder_idle, reply("Tester done."))]})
    # end_turn decides the stop before it flushes (spec section 8.5), so QUIET is decided before the callback holds.
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=1.0, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, describe(result.events)
    events = result.events
    stopping = only(events, STOPPING)
    assert pairs(events[: stopping.sequence]) == [*start_pairs(NAMES), (MODEL_CALLED, "builder"), (IDLE, "builder"), (MODEL_CALLED, "tester"), (IDLE, "tester"), (STOPPING, "")], describe(events)
    assert stopping.stop_reason is AgentSwarmStopReason.QUIET and events[-1].stop_reason is AgentSwarmStopReason.QUIET
    terminals = _terminals(events)
    assert terminals["builder"] == [RELEASED] and len(terminals["tester"]) == 1 and terminals["tester"][0] in (RELEASED, CANCELLED), describe(events)
    assert [event.text for event in of_kind(events, IDLE)] == ["Builder done.", "Tester done."]
    assert {(item.sender, item.content) for item in result.replies} <= {("builder", "Builder done."), ("tester", "Tester done.")}
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_provider_error_fails_only_that_agent_names_its_cause_and_stops_its_mail(tmp_path: Path) -> None:
    """AC-5, INV-6, INV-14, INV-23 (r5 AC-7 kept; the stopped-recipient refusal reversed to a success): reviewer's provider error is one model_error then one agent_failed naming ProviderRequestError and its text; a later message to reviewer is a success with the message_stopped_recipient text, recorded as message_sent then message_undelivered; the others end normally."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    log = EventLog()
    reviewer_failed = log.signal(FAILED, "reviewer")
    error = provider_error(CAUSE)
    scripted = ScriptedSwarm(
        {
            "reviewer": [fail(error)],
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
    model_error = only(result.events, MODEL_ERROR, "reviewer")
    assert model_error.text == error_line(error) and model_error.sequence < failure.sequence
    stopped = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(stopped) and template_regex(prompt_text("message_stopped_recipient"), recipient="reviewer").search(stopped), stopped
    _assert_sent_then_undelivered(result.events, "builder", "reviewer")
    tool_event = only(result.events, TOOL_CALLED, "builder")
    assert (tool_event.tool_name, tool_event.tool_status) == ("message", ToolStatus.SUCCESS)
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, THREE, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_every_agent_failing_ends_failed_with_no_replies(tmp_path: Path) -> None:
    """EC-14, INV-12 (r5 AC-8 kept, its event count rewritten for v2): when every model call raises a provider error, the stop reason is FAILED, each agent has one model_error and one agent_failed naming its own cause, nobody is released, and replies is empty."""
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
        assert seq_of(result.events, MODEL_ERROR, name) < failure.sequence
    assert result.replies == ()
    assert sorted(pairs(result.events[5:9])) == sorted([(MODEL_ERROR, "builder"), (MODEL_ERROR, "tester"), (FAILED, "builder"), (FAILED, "tester")])
    assert pairs(result.events[9:]) == [(STOPPING, ""), (ENDED, "")] and len(result.events) == 11
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_last_working_agent_failing_ends_the_swarm_without_a_hang(tmp_path: Path) -> None:
    """INV-12, INV-14 (r5 EC-13 kept): tester fails while builder is already idle; the failure runs the end check, so the swarm ends QUIET, builder is released with its reply."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_idle = log.signal(IDLE, "builder")
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [after(builder_idle, fail(provider_error()))]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert seq_of(result.events, IDLE, "builder") < seq_of(result.events, FAILED, "tester") < seq_of(result.events, STOPPING) < seq_of(result.events, RELEASED, "builder")
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_mail_left_for_an_agent_that_failed_is_marked_undelivered_with_its_failure(tmp_path: Path) -> None:
    """INV-14, INV-7 (r5 M2 kept: QUIET, never MAX_TURNS): builder's message is queued for reviewer while reviewer's model call is open; that call then fails, so agent_failed is followed in the same block by message_undelivered for that message, and the swarm ends QUIET."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_sent = log.signal(SENT, "builder")
    scripted = ScriptedSwarm({"builder": [send("reviewer", "Please review c2f.py."), reply("Builder done.")], "reviewer": [after(builder_sent, fail(provider_error(CAUSE)))]})
    names = ("builder", "reviewer")
    swarm = build_swarm(tmp_path, names, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, describe(result.events)
    # The send was accepted while reviewer was working, so the message sat in reviewer's inbox until it failed.
    assert not is_error(tool_result(scripted.calls_by("builder")[1], "message"))
    sent = only(result.events, SENT, "builder")
    failure = only(result.events, FAILED, "reviewer")
    undelivered = only(result.events, UNDELIVERED, "reviewer")
    assert failure.text.startswith("ProviderRequestError")
    assert (undelivered.sequence, undelivered.peer, undelivered.message_id) == (failure.sequence + 1, "builder", sent.message_id)
    assert of_kind(result.events, DELIVERED) == []
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_event_invariants(result, names, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_an_exception_inside_a_tool_is_a_tool_error_not_a_failure(tmp_path: Path) -> None:
    """INV-14 (r5 EC-16 b kept; the developer search tool replaced by the Tavily tool, D-3): a Tavily call that raises gives tester a tool error and a tool_called with status error; tester keeps working and nobody fails."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    fake = FakeTavily(error=RuntimeError("search backend down"))
    log = EventLog()
    scripted = ScriptedSwarm({"tester": [search("c2f"), reply("Tester done.")], "builder": [reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert of_kind(result.events, FAILED) == []
    assert fake.queries == ["c2f"]
    tool_event = only(result.events, TOOL_CALLED, "tester")
    assert (tool_event.tool_name, tool_event.tool_status) == (TAVILY_TOOL, ToolStatus.ERROR)
    assert is_error(tool_result(scripted.calls_by("tester")[1], TAVILY_TOOL))
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_turn_middleware_recording_bug_exits_only_that_agent_naming_the_middleware_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-24, INV-14 (reverses r5's agent_failed for this case): a bug in record_tool_call aborts tester's run through the fail-closed turn middleware while the swarm still runs; tester gets one agent_exited with text middleware_abort, the message waiting in its inbox gets message_undelivered in the same block, and builder keeps working and ends normally."""
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
    builder_sent = log.signal(SENT, "builder")
    # tester's tool call is answered only after builder's message is in its inbox, so the abort finds mail waiting.
    scripted = ScriptedSwarm(
        {
            "tester": [after(builder_sent, tool_call("read_lines", {"path": "missing.txt"}))],
            "builder": [send("tester", NOTE), tool_call("write_text", {"path": "notes.txt", "content": "n"}), reply("Builder done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    exited = only(result.events, EXITED, "tester")
    assert exited.text == "middleware_abort", exited.text
    assert of_kind(result.events, FAILED) == []
    sent = only(result.events, SENT, "builder")
    undelivered = only(result.events, UNDELIVERED, "tester")
    assert (undelivered.sequence, undelivered.peer, undelivered.message_id) == (exited.sequence + 1, "builder", sent.message_id)
    assert len(scripted.calls_by("tester")) == 1
    assert of_kind(result.events, TOOL_CALLED, "tester") == []
    builder_tools = [(event.tool_name, event.tool_status) for event in of_kind(result.events, TOOL_CALLED, "builder")]
    assert builder_tools == [("message", ToolStatus.SUCCESS), ("write_text", ToolStatus.SUCCESS)]
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


# Stray-cancel runs are given a short time limit: without the rule they wait it out, so a red run stays quick,
# and with it the swarm ends long before half of it has passed.
CANCEL_TIMEOUT_SECONDS = 2.0


def _assert_unrequested_cancel_failed_only(result: Any, agent: str, elapsed: float) -> None:
    """EC-11: one agent_failed naming CancelledError for `agent`, the swarm ended QUIET, and arun never waited for the time limit."""
    from vidbyte import AgentSwarmStopReason

    assert result.stop_reason is AgentSwarmStopReason.QUIET, f"{result.stop_reason.value} after {elapsed:.2f} s: {describe(result.events)}"
    failure = only(result.events, FAILED, agent)
    assert failure.text.startswith("CancelledError"), failure.text
    assert elapsed < CANCEL_TIMEOUT_SECONDS / 2, f"arun took {elapsed:.2f} s, waiting toward the {CANCEL_TIMEOUT_SECONDS} s time limit"


@pytest.mark.asyncio
async def test_a_cancelled_error_raised_by_a_tool_fails_that_agent_instead_of_waiting_for_the_time_limit(tmp_path: Path) -> None:
    """EC-11, INV-14 (r5 EC-39 kept; the developer search tool replaced by the Tavily tool): a Tavily call that raises asyncio.CancelledError, which the swarm never requested, gives builder one agent_failed naming CancelledError; tester's turn still ends, and the swarm ends QUIET at once instead of at timeout_seconds."""
    fake = FakeTavily(error=asyncio.CancelledError())
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [search("c2f")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=CANCEL_TIMEOUT_SECONDS, on_event=log.callback, **web_search_fields())
    started = time.monotonic()
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)
    elapsed = time.monotonic() - started

    _assert_unrequested_cancel_failed_only(result, "builder", elapsed)
    assert fake.queries == ["c2f"]
    assert [(item.sender, item.content) for item in result.replies] == [("tester", "Tester done.")]
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_cancelled_error_raised_by_on_event_while_an_agent_works_fails_that_agent(tmp_path: Path) -> None:
    """EC-11, INV-14 (r5 EC-39 kept): an async on_event raises asyncio.CancelledError on builder's tool_called, which builder's own turn flushes; builder gets one agent_failed naming CancelledError after that event, and the swarm ends QUIET at once instead of at timeout_seconds."""
    log = EventLog(mode="async")
    tester_idle = log.signal(IDLE, "tester")

    def cancel_on_builder_tool(event: Any) -> None:
        if event.kind.value == TOOL_CALLED and event.agent == "builder":
            raise asyncio.CancelledError()

    log.hook(cancel_on_builder_tool)
    # builder calls its tool only after tester's agent_idle was delivered, so builder's own flush is the one that hands tool_called over.
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")], "builder": [after(tester_idle, tool_call("read_lines", {"path": "missing.txt"}))]})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=CANCEL_TIMEOUT_SECONDS, on_event=log.callback)
    started = time.monotonic()
    with scripted.install():
        result = await run_swarm(swarm)
    elapsed = time.monotonic() - started

    _assert_unrequested_cancel_failed_only(result, "builder", elapsed)
    assert seq_of(result.events, TOOL_CALLED, "builder") < seq_of(result.events, FAILED, "builder")
    assert [(item.sender, item.content) for item in result.replies] == [("tester", "Tester done.")]
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_cancelled_error_raised_by_on_event_on_an_idle_agent_fails_it_instead_of_waking_it(tmp_path: Path) -> None:
    """EC-11, INV-6, INV-14 (r5 EC-39 idle variant kept; the stopped-recipient refusal reversed to a success): on_event raises asyncio.CancelledError on tester's agent_idle; tester gets one agent_failed naming CancelledError, builder's later message to it is a success with the stopped-recipient text recorded sent then undelivered, no agent_woke is recorded, and the swarm ends QUIET at once."""
    log = EventLog()
    tester_idle = log.signal(IDLE, "tester")

    def cancel_on_tester_idle(event: Any) -> None:
        if event.kind.value == IDLE and event.agent == "tester":
            raise asyncio.CancelledError()

    log.hook(cancel_on_tester_idle)
    # The sync callback raises inside tester's own flush, so tester's agent_failed is recorded before builder's model call can return.
    scripted = ScriptedSwarm({"tester": [reply("Tester done.")], "builder": [after(tester_idle, send("tester", NOTE)), reply("Builder done.")]})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=CANCEL_TIMEOUT_SECONDS, on_event=log.callback)
    started = time.monotonic()
    with scripted.install():
        result = await run_swarm(swarm)
    elapsed = time.monotonic() - started

    _assert_unrequested_cancel_failed_only(result, "tester", elapsed)
    assert seq_of(result.events, IDLE, "tester") < seq_of(result.events, FAILED, "tester")
    assert of_kind(result.events, WOKE) == []
    stopped = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(stopped) and template_regex(prompt_text("message_stopped_recipient"), recipient="tester").search(stopped), stopped
    _assert_sent_then_undelivered(result.events, "builder", "tester")
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done.")]
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_an_unrequested_cancel_after_the_end_was_decided_does_not_fail_the_agent(tmp_path: Path) -> None:
    """INV-14 (r5 EC-39 guard kept: S5 mutant S5-M2): on_event raises asyncio.CancelledError on tester's agent_idle, but tester is the last working agent, so its turn end has already decided QUIET; nobody gets agent_failed, each agent has exactly one terminal event, and the swarm ends QUIET at once."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_idle = log.signal(IDLE, "builder")

    def cancel_on_tester_idle(event: Any) -> None:
        if event.kind.value == IDLE and event.agent == "tester":
            raise asyncio.CancelledError()

    log.hook(cancel_on_tester_idle)
    # tester ends its turn only after builder is idle, so tester's own turn end decides QUIET before its agent_idle is flushed (spec section 8.5).
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [after(builder_idle, reply("Tester done."))]})
    swarm = build_swarm(tmp_path, NAMES, timeout_seconds=CANCEL_TIMEOUT_SECONDS, on_event=log.callback)
    started = time.monotonic()
    with scripted.install():
        result = await run_swarm(swarm)
    elapsed = time.monotonic() - started

    assert result.stop_reason is AgentSwarmStopReason.QUIET, f"{result.stop_reason.value} after {elapsed:.2f} s: {describe(result.events)}"
    assert of_kind(result.events, FAILED) == [], describe(result.events)
    stopping = only(result.events, STOPPING)
    assert pairs(result.events[: stopping.sequence]) == [*start_pairs(NAMES), (MODEL_CALLED, "builder"), (IDLE, "builder"), (MODEL_CALLED, "tester"), (IDLE, "tester"), (STOPPING, "")], describe(result.events)
    terminals = _terminals(result.events)
    assert terminals["builder"] == [RELEASED] and len(terminals["tester"]) == 1 and terminals["tester"][0] in (RELEASED, CANCELLED), describe(result.events)
    assert result.events[-1].stop_reason is AgentSwarmStopReason.QUIET
    assert elapsed < CANCEL_TIMEOUT_SECONDS / 2, f"arun took {elapsed:.2f} s, waiting toward the {CANCEL_TIMEOUT_SECONDS} s time limit"
    assert {(item.sender, item.content) for item in result.replies} <= {("builder", "Builder done."), ("tester", "Tester done.")}
    assert_no_stray_tasks()
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_second_concurrent_arun_is_refused_and_a_later_arun_starts_fresh(tmp_path: Path) -> None:
    """INV-40 (r5 AC-15 kept): arun while a run is in progress raises ConfigurationError and changes nothing; a later arun starts at sequence 1 with fresh agents and the new goal."""
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
        assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns)
    # The refused call left no trace in the first run, and the third run's events start again at 1.
    assert log.received == [*first_result.events, *third_result.events]
    assert [(item.sender, item.content) for item in third_result.replies] == [("builder", "Third run done."), ("tester", "Tester third.")]
    for name in NAMES:
        fresh = scripted.calls_by(name)[1]
        assert fresh.prompt == "A third goal." and fresh.messages == []
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_swarm_runtime_runs_only_once(tmp_path: Path) -> None:
    """INV-40 (r5 INV-19 kept; the constructor takes workplace_created per spec 8.5): an AgentSwarmRuntime runs one swarm; a second arun on it raises ConfigurationError before any model call."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    root = workplace_path(tmp_path)
    root.mkdir()
    settings = build_settings(tmp_path, NAMES)
    runtime = AgentSwarmRuntime(settings, root, workplace_created=False)
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [reply("Tester done.")]})
    with scripted.install():
        result = await run_swarm(runtime)
        calls_after_first = len(scripted.calls)
        with pytest.raises(ConfigurationError):
            await runtime.arun(GOAL_AGAIN)
    assert len(scripted.calls) == calls_after_first
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert_event_invariants(result, NAMES, max_turns=settings.max_turns)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_cancelling_arun_propagates_and_the_swarm_can_run_again(tmp_path: Path) -> None:
    """INV-40 (r5 EC-19 kept): cancelling arun cancels the agent runs and raises CancelledError; the in-progress flag is cleared, so the next arun runs a fresh swarm."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [SENT, ENDED])
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_a_raising_on_event_callback_never_stops_the_swarm(tmp_path: Path, mode: str, kind: str) -> None:
    """INV-20 (r5 AC-10 kept): a sync or async on_event that raises on message_sent or swarm_ended is still called once per event in order, and the swarm finishes normally."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log, error_types=("CallbackBoom",))
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_event_outbox_delivers_each_event_once_in_order_even_with_concurrent_flushes() -> None:
    """INV-20 (r5 D-6 kept): record numbers events 1..N at once; overlapping flushes hand each event to on_event exactly once, in order, one call at a time."""
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
    """INV-20 (r5 EC-23 kept): an event is marked delivered before its callback is awaited, so a flush cancelled inside that callback never hands the same event over again, and cancellation is not swallowed."""
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
async def test_event_time_counts_from_arun_not_from_building_the_runtime(tmp_path: Path) -> None:
    """INV-28 (r5 D-16 kept; the first event is now workplace_prepared): elapsed_ms counts from the start of the run, so time spent between building an AgentSwarmRuntime and calling arun never shows in the events."""
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime

    root = workplace_path(tmp_path)
    root.mkdir()
    settings = build_settings(tmp_path, NAMES)
    runtime = AgentSwarmRuntime(settings, root, workplace_created=False)
    # The pack's one timed wait: what is under test is where the clock starts, which only real time between building and running can show.
    wait_seconds = 0.3
    await asyncio.sleep(wait_seconds)
    scripted = ScriptedSwarm({"builder": [reply("Builder done.")], "tester": [reply("Tester done.")]})
    with scripted.install():
        result = await run_swarm(runtime)

    first = result.events[0]
    assert (first.kind.value, first.agent) == (PREPARED, "")
    assert first.elapsed_ms < wait_seconds * 1000 / 2, f"the first event reads {first.elapsed_ms} ms after a {wait_seconds} s wait before arun: the clock started when the runtime was built"
    assert_event_invariants(result, NAMES, max_turns=settings.max_turns)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_tool_called_events_carry_name_and_status_and_skip_isdone(tmp_path: Path) -> None:
    """INV-38, INV-39 (r5 AC-19 kept): bash and a failing read_lines each give one tool_called with their status; the isDone that ends the turn gives none, and bash ran in the workplace."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_tool_name_holding_a_newline_is_a_tool_error_not_a_failure(tmp_path: Path) -> None:
    """INV-14 (r5 EC-16 b, R-8 kept): a model that calls a tool whose name holds a newline gets the loop's tool error and keeps working; tool_called records that non-blank name with status error, and nobody fails."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    odd_name = "bash\nrm"
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [tool_call(odd_name, {"command": "echo hello"}), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert of_kind(result.events, FAILED) == [], describe(result.events)
    tool_event = only(result.events, TOOL_CALLED, "builder")
    assert (tool_event.tool_name, tool_event.tool_status) == (odd_name, ToolStatus.ERROR)
    assert is_error(tool_result(scripted.calls_by("builder")[1], odd_name))
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
