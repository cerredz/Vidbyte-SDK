"""FILE: tests/features/agent_swarm/test_agent_swarm_stop.py

PURPOSE: Pins the swarm-wide token budget and what each model call records. Every model response records one model_called with its billed input, output and cached tokens and the loop's model call count, and the budget grows by the reported total (total_tokens when reported, else input plus output). The response that brings the total to max_tokens stops the swarm in its own block: swarm_stopping follows its model_called, parked agents are released, responses already in flight are answered but run no tool, a member inside a long tool call finishes it and is released at its next model call, a message sent after the decision is recorded sent then undelivered, a model call refused after the decision records no history_trimmed, a compact request still pending at the decision makes no summary call, and no member makes another model call. A model error records model_error before a retry that the test installs at the member's middleware seam (AgentSwarm installs none, spec r4 INV-23), and a provider that reports no usage records zeros and never spends the budget.
ROLE IN CODEBASE: Budget and stop layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-8, AC-9, AC-10; EC-4, EC-7, EC-8, EC-9, EC-12; INV-12, INV-13, INV-14, INV-15, INV-22, INV-23, INV-24, INV-32; S4 review R-7, R-9). Exercises AgentSwarmRuntime.record_model_call, record_model_error, the stop block, and AgentSwarmObserverMiddleware's before_model_call, after_model_response and on_model_error.
ARCHITECTURE NOTE: The scripted runner's usage mapping is the only source of token counts, and it reaches the swarm through the loop's own UsageTracker, so every count asserted here is the one the OpenAI usage parser reads. Interleavings are forced with Signals and a blocking FakeTavily; the FakeTavily is released from an on_event hook when swarm_stopping is delivered, so the search provably returns after the decision.
FUNCTION INVENTORY: _next_own (the next event of the same agent); test_a_model_response_records_its_tokens_and_the_budget_grows_by_the_reported_total (AC-8, INV-15, INV-22); test_the_response_that_crosses_max_tokens_stops_the_swarm_in_its_own_block_and_runs_nothing_more (AC-9, EC-12, INV-12, INV-13); test_a_member_inside_a_long_tool_call_finishes_it_and_is_released_before_its_next_model_call (EC-7); test_a_message_sent_after_the_stop_is_recorded_sent_then_undelivered (EC-4); test_a_model_call_refused_after_the_stop_records_no_history_trimmed (INV-13, INV-24, R-9); test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction (INV-13, INV-32, R-7); test_the_first_response_crossing_the_budget_leaves_no_further_paid_call (EC-9); test_a_retried_model_error_records_model_error_and_the_agent_keeps_working (AC-10, INV-23); test_a_provider_that_reports_no_usage_records_zeros_and_never_spends_the_budget (EC-8).
COMMON MODIFICATION PATTERNS: A new budget rule gets one test that scripts usage on each step, sets max_tokens just at and just past the expected total, and asserts the stop reason and the swarm_stopping position.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not read token counts back from the swarm's internals; read them from model_called events and the stop reason. 3. Do not wait on time; every wait here is a Signal, a blocking FakeTavily, or a scripted step.
KNOWN EDGE CASES: A response that arrives after the decision still records its model_called (it was paid for) and then aborts, so its tool calls never run. Agents released by the stop record agent_released in the order their tasks resume, so only same-agent orderings are pinned. The EC-9 test lets the other members' first calls wait for swarm_stopping, so it holds whether their first call was dispatched before the decision (answered after it, running nothing) or refused at before_model_call.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1 (INV-12 to INV-15, INV-22, INV-23), 6.2, 6.3 and 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_stop.py -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    COMPACTION,
    DELIVERED,
    FAILED,
    IDLE,
    MODEL_CALLED,
    MODEL_ERROR,
    RELEASED,
    SENT,
    STOPPING,
    TAVILY_TOOL,
    TOOL_CALLED,
    TRIMMED,
    UNDELIVERED,
    EventLog,
    FakeTavily,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    build_swarm,
    calls,
    compact,
    describe,
    error_line,
    fail,
    install_model_retry,
    of_kind,
    only,
    provider_error,
    reply,
    run_swarm,
    search,
    send,
    snapshot,
    tool_call,
    web_search_fields,
    workplace_path,
)

NAMES = ("builder", "tester")
THREE = ("builder", "tester", "reviewer")
NOTE = "c2f.py is ready; please run your tests against it."
# OpenAI Responses usage with every field the parser reads: total_tokens differs from input plus output on purpose.
BUILDER_USAGE = {"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1300, "input_tokens_details": {"cached_tokens": 1000}}
SMALL = {"input_tokens": 4, "output_tokens": 1}


def _next_own(events: Any, event: Any) -> Any:
    # The first event after `event` that names the same agent.
    return next(item for item in events[event.sequence :] if item.agent == event.agent)


def _release_on_stopping(log: EventLog, fake: FakeTavily) -> None:
    # Lets a blocked Tavily call return only once swarm_stopping has been delivered.
    log.hook(lambda event: fake.release.set() if event.kind.value == STOPPING else None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("max_tokens", "expected"), [pytest.param(1305, "max_tokens", id="budget-equal-to-the-total"), pytest.param(1306, "quiet", id="budget-one-above-the-total")])
async def test_a_model_response_records_its_tokens_and_the_budget_grows_by_the_reported_total(tmp_path: Path, max_tokens: int, expected: str) -> None:
    """AC-8, INV-15, INV-22: builder's model_called carries the billed input, output and cached tokens and model_calls 1; the budget counts builder's total_tokens (1300, not 1280) plus tester's input plus output (5), so a budget of exactly 1305 ends MAX_TOKENS and 1306 ends QUIET."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    scripted = ScriptedSwarm({"builder": [reply("Builder done.", usage=BUILDER_USAGE)], "tester": [reply("Tester done.", usage=SMALL)]})
    swarm = build_swarm(tmp_path, NAMES, max_tokens=max_tokens, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    builder = only(result.events, MODEL_CALLED, "builder")
    assert (builder.input_tokens, builder.output_tokens, builder.cached_tokens, builder.model_calls) == (1200, 80, 1000, 1)
    tester = only(result.events, MODEL_CALLED, "tester")
    assert (tester.input_tokens, tester.output_tokens, tester.cached_tokens, tester.model_calls) == (4, 1, 0, 1)
    assert result.stop_reason is AgentSwarmStopReason(expected), describe(result.events)
    if expected == "max_tokens":
        # The decision is made in the block of the response that reached the budget.
        stopping = only(result.events, STOPPING)
        assert result.events[stopping.sequence - 2].kind.value == MODEL_CALLED
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_response_that_crosses_max_tokens_stops_the_swarm_in_its_own_block_and_runs_nothing_more(tmp_path: Path) -> None:
    """AC-9, EC-12, INV-12, INV-13, INV-14: tester's reply (5 tokens) parks it; builder's tool-call response (995 tokens) is the run's second response and reaches max_tokens=1000, so swarm_stopping max_tokens is the very next event; tester is released, builder's tool never runs, reviewer's call that was in flight is answered but runs no tool, every member ends agent_released with its reply kept (builder's and reviewer's marked middleware_abort), and no further model call is made."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    tester_idle, stopping = log.signal(IDLE, "tester"), log.signal(STOPPING, "")
    scripted = ScriptedSwarm(
        {
            "tester": [reply("Tester done.", usage=SMALL)],
            "builder": [after(tester_idle, tool_call("write_text", {"path": "late.txt", "content": "x"}, usage={"input_tokens": 900, "output_tokens": 95}))],
            "reviewer": [after(stopping, tool_call("write_text", {"path": "reviewer.txt", "content": "r"}))],
        }
    )
    swarm = build_swarm(tmp_path, THREE, max_tokens=1000, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    events = result.events
    crossing = of_kind(events, MODEL_CALLED)[1]
    assert crossing.agent == "builder" and of_kind(events, MODEL_CALLED)[0].agent == "tester"
    decided = events[crossing.sequence]
    assert (decided.kind.value, decided.stop_reason) == (STOPPING, AgentSwarmStopReason.MAX_TOKENS), describe(events)
    # The in-flight call was answered after the decision, and nothing any agent asked for afterwards ran.
    assert only(events, MODEL_CALLED, "reviewer").sequence > decided.sequence
    assert of_kind(events, TOOL_CALLED) == []
    assert not (workplace_path(tmp_path) / "late.txt").exists() and not (workplace_path(tmp_path) / "reviewer.txt").exists()
    assert sorted(event.agent for event in of_kind(events, RELEASED)) == sorted(THREE)
    assert all(event.sequence > decided.sequence for event in of_kind(events, RELEASED))
    assert of_kind(events, FAILED) == []
    # EC-12: a loop the observer aborted after the decision is a release, and its reply is kept marked middleware_abort.
    stops = {item.sender: item.metadata.get("stop_reason") for item in result.replies}
    assert set(stops) == set(THREE) and stops["builder"] == stops["reviewer"] == "middleware_abort", stops
    assert_event_invariants(result, THREE, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_member_inside_a_long_tool_call_finishes_it_and_is_released_before_its_next_model_call(tmp_path: Path) -> None:
    """EC-7, INV-13: reviewer is inside a Tavily search when builder's response reaches the budget; the search returns after swarm_stopping, reviewer's tool_called is recorded, no compaction runs, and its next model call is refused, so it ends agent_released after one model call."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    fake = FakeTavily(block=True)
    log = EventLog()
    _release_on_stopping(log, fake)
    scripted = ScriptedSwarm(
        {
            "reviewer": [search("celsius to fahrenheit")],
            "tester": [reply("Tester done.")],
            "builder": [after(fake.entered, reply("Builder done.", usage={"input_tokens": 990, "output_tokens": 10}))],
        }
    )
    swarm = build_swarm(tmp_path, THREE, max_tokens=1000, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    assert fake.problems == [] and fake.queries == ["celsius to fahrenheit"]
    stopping = only(result.events, STOPPING)
    searched = only(result.events, TOOL_CALLED, "reviewer")
    assert (searched.tool_name, searched.tool_status) == (TAVILY_TOOL, ToolStatus.SUCCESS)
    assert stopping.sequence < searched.sequence
    assert _next_own(result.events, searched).kind.value == RELEASED, describe(result.events)
    assert len(scripted.calls_by("reviewer")) == 1
    assert_event_invariants(result, THREE, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_message_sent_after_the_stop_is_recorded_sent_then_undelivered(tmp_path: Path) -> None:
    """EC-4, INV-6, INV-13: builder's one response holds a Tavily search and then a message; the search returns after tester's response reached the budget, so the message is a success recorded as message_sent then, at once, message_undelivered with the same id, nothing is delivered, and builder ends agent_released."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    fake = FakeTavily(block=True)
    log = EventLog()
    _release_on_stopping(log, fake)
    scripted = ScriptedSwarm(
        {
            "builder": [calls(search("c2f rounding"), send("tester", NOTE))],
            "tester": [after(fake.entered, reply("Tester done.", usage={"input_tokens": 990, "output_tokens": 10}))],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, max_tokens=1000, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    events = result.events
    sent = only(events, SENT, "builder")
    follower = events[sent.sequence]
    assert sent.sequence > only(events, STOPPING).sequence
    assert (follower.kind.value, follower.agent, follower.peer, follower.message_id) == (UNDELIVERED, "tester", "builder", sent.message_id)
    assert of_kind(events, DELIVERED) == []
    assert [(event.tool_name, event.tool_status) for event in of_kind(events, TOOL_CALLED, "builder")] == [(TAVILY_TOOL, ToolStatus.SUCCESS), ("message", ToolStatus.SUCCESS)]
    assert of_kind(events, RELEASED, "builder")[0].sequence > follower.sequence
    assert len(scripted.calls_by("builder")) == 1
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_model_call_refused_after_the_stop_records_no_history_trimmed(tmp_path: Path) -> None:
    """INV-13, INV-24 (S4 R-9): builder sends itself a 300,000-character note, so from its second call on its history is over AGENT_SWARM_HISTORY_MAX_TOKENS and the trim leaves out the send's call and result (one history_trimmed before the stop, two dropped); its second response is a Tavily search that returns only after tester's response reached the budget, and the observer refuses its next model call, so after swarm_stopping builder records the search's tool_called and agent_released only, and no history_trimmed for a call that is never sent."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    fake = FakeTavily(block=True)
    log = EventLog()
    _release_on_stopping(log, fake)
    scripted = ScriptedSwarm(
        {
            "builder": [send("builder", "n" * 300_000), search("c2f rounding")],
            "tester": [after(fake.entered, reply("Tester done.", usage={"input_tokens": 990, "output_tokens": 10}))],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, max_tokens=1000, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    events = result.events
    stopping = only(events, STOPPING)
    # The history was over the cap before the stop, so the refused call's history, one search longer, would be trimmed too.
    assert [(event.sequence < stopping.sequence, event.messages_dropped) for event in of_kind(events, TRIMMED, "builder")[:1]] == [(True, 2)], describe(events)
    assert [(event.kind.value, event.tool_name, event.tool_status) for event in events[stopping.sequence :] if event.agent == "builder"] == [(TOOL_CALLED, TAVILY_TOOL, ToolStatus.SUCCESS), (RELEASED, "", None)], describe(events)
    assert len(scripted.calls_by("builder")) == 2 and fake.problems == []
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction(tmp_path: Path) -> None:
    """INV-13, INV-32 (S4 R-7): builder reads two sixty-thousand-character files, so its older history is over AGENT_SWARM_COMPACTION_TARGET_TOKENS and a compaction would have something to summarize, then one response calls compact and a Tavily search; the search returns only after tester's response reached the budget, so the request is still pending when that iteration ends after swarm_stopping. No compaction is due after the decision: builder makes no model call after swarm_stopping (no summary call, its next loop call refused), records no compaction, and its events after the stop are the search's tool_called and agent_released."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    root = workplace_path(tmp_path)
    root.mkdir()
    for name in ("old1", "old2"):
        (root / f"{name}.txt").write_text(name.upper() + "-" + "o" * 60_000, encoding="utf-8", newline="")
    fake = FakeTavily(block=True)
    log = EventLog()
    _release_on_stopping(log, fake)
    scripted = ScriptedSwarm(
        {
            "builder": [tool_call("read_lines", {"path": "old1.txt"}), tool_call("read_lines", {"path": "old2.txt"}), calls(compact(), search("c2f rounding"))],
            "tester": [after(fake.entered, reply("Tester done.", usage={"input_tokens": 990, "output_tokens": 10}))],
        }
    )
    calls_at_stop: list[int] = []
    log.hook(lambda event: calls_at_stop.append(len(scripted.calls_by("builder"))) if event.kind.value == STOPPING else None)
    swarm = build_swarm(tmp_path, NAMES, max_tokens=1000, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    events = result.events
    stopping = only(events, STOPPING)
    # The compact request was made and answered before the decision, so it was pending when the search returned.
    assert [(event.tool_name, event.tool_status, event.sequence < stopping.sequence) for event in of_kind(events, TOOL_CALLED, "builder")] == [
        ("read_lines", ToolStatus.SUCCESS, True),
        ("read_lines", ToolStatus.SUCCESS, True),
        ("compact", ToolStatus.SUCCESS, True),
        (TAVILY_TOOL, ToolStatus.SUCCESS, False),
    ], describe(events)
    assert calls_at_stop == [3] and len(scripted.calls_by("builder")) == 3, f"builder's model calls: {calls_at_stop} at the stop, {len(scripted.calls_by('builder'))} in all"
    assert of_kind(events, COMPACTION) == [], describe(events)
    assert [(event.kind.value, event.tool_name) for event in events[stopping.sequence :] if event.agent == "builder"] == [(TOOL_CALLED, TAVILY_TOOL), (RELEASED, "")], describe(events)
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_the_first_response_crossing_the_budget_leaves_no_further_paid_call(tmp_path: Path) -> None:
    """EC-9, INV-13: builder's first response reaches max_tokens; swarm_stopping is the next event, every other model_called comes after it, no tool runs, nobody fails, and all three members end agent_released."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    stopping = log.signal(STOPPING, "")
    scripted = ScriptedSwarm(
        {
            "builder": [reply("Builder done.", usage={"input_tokens": 50, "output_tokens": 50})],
            "tester": [after(stopping, tool_call("write_text", {"path": "t.txt", "content": "t"}))],
            "reviewer": [after(stopping, tool_call("write_text", {"path": "r.txt", "content": "r"}))],
        }
    )
    swarm = build_swarm(tmp_path, THREE, max_tokens=100, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.MAX_TOKENS, describe(result.events)
    events = result.events
    first = of_kind(events, MODEL_CALLED)[0]
    assert first.agent == "builder" and events[first.sequence].kind.value == STOPPING, describe(events)
    assert all(event.sequence > first.sequence + 1 for event in of_kind(events, MODEL_CALLED)[1:])
    assert of_kind(events, TOOL_CALLED) == [] and of_kind(events, FAILED) == []
    assert sorted(event.agent for event in of_kind(events, RELEASED)) == sorted(THREE)
    assert snapshot(workplace_path(tmp_path)) == {}
    assert scripted.unscripted == [] and scripted.problems == []
    assert_event_invariants(result, THREE, max_turns=swarm.settings.max_turns, log=log)


@pytest.mark.asyncio
async def test_a_retried_model_error_records_model_error_and_the_agent_keeps_working(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-10, INV-23 (spec r4): builder's first model attempt raises a provider error that a retry middleware installed by this test (install_model_retry, at the member's middleware seam) retries, because AgentSwarm installs no retry of its own and without one the first error fails the member; one model_error with "<Type>: <message>" is recorded before the retry, the retried call records model_called with model_calls 2, builder does not fail, and the swarm ends QUIET."""
    from vidbyte import AgentSwarmStopReason

    retried = install_model_retry(monkeypatch)
    error = provider_error("openai returned 503: try again")
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [fail(error), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, describe(result.events)
    assert retried == ["builder"]
    model_error = only(result.events, MODEL_ERROR, "builder")
    assert model_error.text == error_line(error)
    called = only(result.events, MODEL_CALLED, "builder")
    assert model_error.sequence < called.sequence and called.model_calls == 2
    assert of_kind(result.events, FAILED) == []
    assert scripted.calls_by("builder")[1].messages == scripted.calls_by("builder")[0].messages
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Tester done.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_provider_that_reports_no_usage_records_zeros_and_never_spends_the_budget(tmp_path: Path) -> None:
    """EC-8, INV-15, INV-22: when no response carries usage, every model_called holds zero tokens with a model call count of at least one, and even max_tokens=1 is never reached, so the swarm ends QUIET."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    scripted = ScriptedSwarm(
        {
            "builder": [tool_call("write_text", {"path": "notes.md", "content": "n"}, usage={}), reply("Builder done.", usage={})],
            "tester": [reply("Tester done.", usage={})],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, max_tokens=1, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, describe(result.events)
    called = of_kind(result.events, MODEL_CALLED)
    assert len(called) == 3
    assert all((event.input_tokens, event.output_tokens, event.cached_tokens) == (0, 0, 0) and event.model_calls >= 1 for event in called)
    assert [event.model_calls for event in of_kind(result.events, MODEL_CALLED, "builder")] == [1, 2]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
