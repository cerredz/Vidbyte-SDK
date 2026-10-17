"""FILE: tests/features/agent_swarm/test_agent_swarm_messaging.py

PURPOSE: Pins the swarm's mailbox protocol. A message to a working agent arrives after its next tool result and never blocks the sender, with or without turn budget left. Messages that waited together arrive as one labeled user message in acceptance order. A message wakes an idle agent after a plain reply or an isDone, and an agent that ends its turn with mail waiting continues at once. Two agents messaging each other never deadlock. A message accepted in the exact step that reports its recipient going idle is never lost. Refused messages queue nothing. Message text arrives whole.
ROLE IN CODEBASE: Messaging layer of tests/features/agent_swarm/ (spec AC-2, AC-3, AC-9, AC-20; EC-1, EC-2, EC-3, EC-4, EC-5, EC-6, EC-27; INV-4, INV-5, INV-6, INV-7, INV-8, INV-9; D-4, D-5; FR-4, FR-5, FR-6). Exercises AgentSwarmRuntime.post_message, collect_messages and end_turn through the real member loop, plus the message tool and the turn middleware.
ARCHITECTURE NOTE: Interleavings are forced, never timed. A BlockingSearchTool holds an agent mid-turn until a model call of another agent releases it. Gate makes two calls overlap. EventLog.signal turns a swarm state change (an agent going idle, a message being sent) into a Signal a scripted step waits on. Each test reads both views of one run: the event record and what each model was sent.
FUNCTION INVENTORY: test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender (AC-2, INV-4, INV-6, INV-9, EC-3); test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order (EC-4, INV-5, INV-6); test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply (AC-3, EC-5, INV-7, D-5); test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once (AC-20, INV-7); test_two_agents_messaging_each_other_mid_turn_never_deadlock (EC-2, INV-4); test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost (EC-1, INV-7, D-4); test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues (AC-9, EC-6, INV-8); test_message_text_reaches_the_recipient_whole_and_unformatted (EC-27, INV-5).
COMMON MODIFICATION PATTERNS: To force a new interleaving, add a Signal from EventLog.signal or a BlockingSearchTool rather than a sleep.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not gate a step on another agent's "answered" mark to wait for an idle agent; that mark fires before end_turn marks it idle (spec section 13, R-6). 3. Do not compare delivered user messages to hand-written text; build the expectation from the agent_swarm.inbox and agent_swarm.inbox_message templates.
KNOWN EDGE CASES: The lost-wake-up test sends from the on_event callback that reports tester going idle, as a separate task, and yields so that the send's synchronous part runs while that report is still being delivered. A callback that awaited post_message directly would wait on the event outbox it is already inside.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6.1, 6.2, 6.3, 8.1 (D-4, D-5) and 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_messaging.py -q
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    DELIVERED,
    FINISH_NOT_ACCEPTED,
    IDLE,
    SENT,
    TOOL_CALLED,
    WOKE,
    BlockingSearchTool,
    EventLog,
    Gate,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    build_settings,
    build_swarm,
    finish,
    is_error,
    of_kind,
    observe,
    only,
    prompt_text,
    renderings,
    reply,
    run_swarm,
    send,
    seq_of,
    template_regex,
    tool_call,
    tool_result,
    user_messages,
    workplace_path,
    yield_to_loop,
)

NAMES = ("builder", "tester")
NOTE = "c2f.py is ready; please run your tests against it."


def _assert_inbox(content: str, *expected: tuple[str, str]) -> None:
    # One delivered user message: the inbox template around one labeled rendering per (sender, text), in the given order.
    assert template_regex(prompt_text("inbox")).fullmatch(content.strip()), f"not an agent_swarm.inbox rendering: {content!r}"
    positions = []
    for sender, text in expected:
        found = list(template_regex(prompt_text("inbox_message"), sender=sender, text=text).finditer(content))
        assert len(found) == 1, f"expected one inbox_message from {sender} holding {text[:40]!r}, found {len(found)} in {content!r}"
        positions.append(found[0].start())
    assert positions == sorted(positions), f"messages are not in acceptance order: {content!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", ["budget-left", "budget-spent"])
async def test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender(tmp_path: Path, budget: str) -> None:
    """AC-2, INV-4, INV-6, INV-9, EC-3: tester's next call holds, right after its tool result, one user message from builder; builder's send returned first."""
    from vidbyte import AgentSwarmStopReason

    search = BlockingSearchTool()
    # tester sits inside its search until builder's second model call, which can only happen after builder's message call returned.
    scripted = ScriptedSwarm(
        {
            "tester": [tool_call("web_search", {"query": "celsius to fahrenheit formula"}), reply("Tests pass.")],
            "builder": [after(search.entered, send("tester", NOTE)), observe(lambda call: search.release.set(), reply("Sent."))],
        }
    )
    log = EventLog()
    max_turns = len(NAMES) if budget == "budget-spent" else 500
    swarm = build_swarm(tmp_path, NAMES, search_tool=search, on_event=log.callback, max_turns=max_turns)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert search.problems == []
    # INV-4: the sender was never held behind the busy recipient.
    assert scripted.position("builder call 2") < scripted.position("tester call 2")
    sent_reply = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(sent_reply) and template_regex(prompt_text("message_sent"), recipient="tester").search(sent_reply)
    # INV-6: after the search result comes exactly one user message, and nothing went into the system string.
    second = scripted.calls_by("tester")[1]
    assert [message["role"] for message in second.messages] == ["assistant", "tool", "user"]
    assert second.messages[1]["name"] == "web_search"
    _assert_inbox(second.messages[2]["content"], ("builder", NOTE))
    assert second.system == scripted.calls_by("tester")[0].system
    # The send precedes the tool's own event, and the delivery follows it; tester never went idle before it.
    events = result.events
    assert seq_of(events, SENT, "builder") < seq_of(events, TOOL_CALLED, "tester") < seq_of(events, DELIVERED, "tester") < seq_of(events, IDLE, "tester")
    assert of_kind(events, WOKE) == []
    assert_event_invariants(result, NAMES, max_turns=max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order(tmp_path: Path) -> None:
    """EC-4, INV-5, INV-6: two messages that wait for one delivery point arrive as one user message, each labeled, in acceptance order."""
    from vidbyte import AgentSwarmStopReason

    names = ("builder", "tester", "reviewer")
    from_builder, from_reviewer = "Builder here: c2f.py now rounds to one decimal.", "Reviewer here: please also test negative input."
    search = BlockingSearchTool()
    log = EventLog()
    builder_sent = log.signal(SENT, "builder")
    scripted = ScriptedSwarm(
        {
            "tester": [tool_call("web_search", {"query": "fahrenheit rounding"}), reply("Tester done.")],
            "builder": [after(search.entered, send("tester", from_builder)), reply("Builder done.")],
            "reviewer": [after(builder_sent, send("tester", from_reviewer)), observe(lambda call: search.release.set(), reply("Reviewer done."))],
        }
    )
    swarm = build_swarm(tmp_path, names, search_tool=search, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    second = scripted.calls_by("tester")[1]
    assert [message["role"] for message in second.messages] == ["assistant", "tool", "user"]
    _assert_inbox(second.messages[2]["content"], ("builder", from_builder), ("reviewer", from_reviewer))
    # One MESSAGE_DELIVERED per message, back to back, oldest first.
    deliveries = of_kind(result.events, DELIVERED, "tester")
    assert [event.peer for event in deliveries] == ["builder", "reviewer"]
    assert deliveries[1].sequence == deliveries[0].sequence + 1
    assert deliveries[0].message_id < deliveries[1].message_id
    assert_event_invariants(result, names, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["reply", "isdone"])
async def test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply(tmp_path: Path, ending: str) -> None:
    """AC-3, EC-5, INV-7, D-5: an idle tester is woken by builder's message; its new turn's first call ends with that message after its previous reply."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    tester_idle = log.signal(IDLE, "tester")
    scripted = ScriptedSwarm(
        {
            "tester": [finish("Waiting for code.") if ending == "isdone" else reply("Waiting for code."), reply("Tests pass.")],
            "builder": [after(tester_idle, send("tester", NOTE)), reply("Sent.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    first, second = scripted.calls_by("tester")
    # INV-2, INV-3: the same conversation continues, and the message comes after the previous reply (or after isDone's provisional refusal).
    assert second.messages[: len(first.messages)] == first.messages
    assert second.messages[-1]["role"] == "user"
    _assert_inbox(second.messages[-1]["content"], ("builder", NOTE))
    previous = second.messages[-2]
    if ending == "reply":
        assert previous == {"role": "assistant", "content": "Waiting for code."}
    else:
        assert previous["role"] == "tool" and previous["name"] == "isDone" and FINISH_NOT_ACCEPTED in previous["content"]
    # AC-3 order, with the wake recorded in the same step as the send (D-5).
    events = result.events
    idle, sent, woke, delivered = seq_of(events, IDLE, "tester"), seq_of(events, SENT, "builder"), seq_of(events, WOKE, "tester"), seq_of(events, DELIVERED, "tester")
    assert idle < sent < woke < delivered and woke == sent + 1
    assert [event.text for event in of_kind(events, IDLE, "tester")] == ["Waiting for code.", "Tests pass."]
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Sent."), ("tester", "Tests pass.")]
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once(tmp_path: Path) -> None:
    """AC-20, INV-7: a message that arrived during tester's model call is delivered when its turn ends, with AGENT_IDLE then AGENT_WOKE and no further send."""
    from vidbyte import AgentSwarmStopReason

    log = EventLog()
    builder_sent = log.signal(SENT, "builder")
    # tester's first answer is held until builder's message is accepted, so the message is already waiting when tester ends its turn.
    scripted = ScriptedSwarm(
        {
            "tester": [after(builder_sent, reply("First pass done.")), reply("Second pass done.")],
            "builder": [send("tester", NOTE), reply("Sent.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    events = result.events
    idle, woke, delivered = seq_of(events, IDLE, "tester"), seq_of(events, WOKE, "tester"), seq_of(events, DELIVERED, "tester")
    assert seq_of(events, SENT, "builder") < idle
    assert (woke, delivered) == (idle + 1, idle + 2)
    second = scripted.calls_by("tester")[1]
    assert second.messages[0] == {"role": "assistant", "content": "First pass done."}
    assert len(second.messages) == 2
    _assert_inbox(second.messages[1]["content"], ("builder", NOTE))
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_two_agents_messaging_each_other_mid_turn_never_deadlock(tmp_path: Path) -> None:
    """EC-2, INV-4: builder and tester message each other from overlapping calls; both sends return and each message is delivered once, mid-turn."""
    from vidbyte import AgentSwarmStopReason

    gate = Gate(2)
    log = EventLog(mode="async", yields=1)
    builder_sent, tester_sent = log.signal(SENT, "builder"), log.signal(SENT, "tester")
    to_tester, to_builder = "Builder: the converter takes floats.", "Tester: the tests expect integers too."
    # Each agent's second step waits until the other's message is accepted, so its next tool iteration is a delivery point for it.
    scripted = ScriptedSwarm(
        {
            "builder": [after(gate, send("tester", to_tester)), after(tester_sent, tool_call("write_text", {"path": "builder.txt", "content": "b"})), reply("Builder done.")],
            "tester": [after(gate, send("builder", to_builder)), after(builder_sent, tool_call("write_text", {"path": "tester.txt", "content": "t"})), reply("Tester done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert sorted(gate.arrived) == ["builder", "tester"]
    for name, other, text in (("builder", "tester", to_builder), ("tester", "builder", to_tester)):
        last = scripted.last_call(name)
        assert len(scripted.calls_by(name)) == 3
        assert not is_error(tool_result(scripted.calls_by(name)[1], "message"))
        assert renderings(prompt_text("inbox_message"), "\n".join(user_messages(last)), sender=other, text=text) == 1
        assert only(result.events, DELIVERED, name).peer == other
    # Both deliveries happened between tool calls; nobody had to be woken.
    assert of_kind(result.events, WOKE) == []
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost(tmp_path: Path) -> None:
    """EC-1, INV-7, D-4: a send made while tester's AGENT_IDLE is being reported is decided against tester's new state, so tester is woken and the message delivered."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime

    root = workplace_path(tmp_path)
    root.mkdir()
    log = EventLog(mode="async")
    builder_sent = log.signal(SENT, "builder")
    holder: dict[str, Any] = {}
    posted: list[asyncio.Future[str]] = []

    async def send_while_tester_goes_idle(event: Any) -> None:
        # Inside the report of tester's first AGENT_IDLE: start a send as its own task and let its synchronous part run now.
        if event.kind.value == IDLE and event.agent == "tester" and not posted:
            posted.append(asyncio.ensure_future(holder["runtime"].post_message("builder", "tester", NOTE)))
            await yield_to_loop(2)

    log.hook(send_while_tester_goes_idle)
    runtime = AgentSwarmRuntime(build_settings(tmp_path, NAMES, on_event=log.callback), root)
    holder["runtime"] = runtime
    # builder stays working until the send is accepted, so the swarm cannot end before it.
    scripted = ScriptedSwarm({"builder": [after(builder_sent, reply("Builder done."))], "tester": [reply("Waiting."), reply("Got it.")]})
    with scripted.install():
        result = await run_swarm(runtime)

    assert posted and posted[0].done()
    assert template_regex(prompt_text("message_sent"), recipient="tester").search(posted[0].result())
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    events = result.events
    assert seq_of(events, IDLE, "tester") < seq_of(events, SENT, "builder") < seq_of(events, WOKE, "tester") < seq_of(events, DELIVERED, "tester")
    second = scripted.calls_by("tester")[1]
    _assert_inbox(second.messages[-1]["content"], ("builder", NOTE))
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Builder done."), ("tester", "Got it.")]
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


REFUSALS = [
    pytest.param("builder", NOTE, "message_unknown_recipient", id="to-itself"),
    pytest.param("deployer", NOTE, "message_unknown_recipient", id="to-an-unknown-name"),
    pytest.param("all", NOTE, "message_unknown_recipient", id="to-all-is-not-a-broadcast"),
    pytest.param("tester", "   ", "message_blank_text", id="blank-text"),
    pytest.param("tester", "", "message_blank_text", id="empty-text"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("to", "text", "leaf"), REFUSALS)
async def test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues(tmp_path: Path, to: str, text: str, leaf: str) -> None:
    """AC-9, EC-6, INV-8: self, unknown, "all", blank and empty sends return the catalog refusal as a tool error; nothing is sent, queued or woken."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.dataclasses.tools import ToolStatus

    log = EventLog()
    scripted = ScriptedSwarm({"builder": [send(to, text), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    second = scripted.calls_by("builder")[1]
    refusal = tool_result(second, "message")
    assert is_error(refusal)
    if leaf == "message_unknown_recipient":
        # The refusal names the recipient it was given and the one valid recipient.
        assert template_regex(prompt_text(leaf), recipient=to).search(refusal), refusal
        assert "tester" in refusal
    else:
        assert template_regex(prompt_text(leaf)).search(refusal), refusal
    # Nothing queued: no send, no wake, no delivery, and no delivered message in builder's own history either.
    assert of_kind(result.events, SENT) == [] and of_kind(result.events, DELIVERED) == [] and of_kind(result.events, WOKE) == []
    assert user_messages(second) == []
    tool_event = only(result.events, TOOL_CALLED, "builder")
    assert (tool_event.tool_name, tool_event.tool_status) == ("message", ToolStatus.ERROR)
    # The loop continued past the refusal, and tester was never called again.
    assert len(scripted.calls_by("builder")) == 2 and len(scripted.calls_by("tester")) == 1
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_message_text_reaches_the_recipient_whole_and_unformatted(tmp_path: Path) -> None:
    """EC-27, INV-5: braces, format fields, unicode, newlines and 20,000 more characters reach the recipient and the event exactly as sent."""
    from vidbyte import AgentSwarmStopReason

    text = 'Use {"celsius": 21.5} and keep {name}, {agents} and {text} literal; naïve café ✓ 温度\nSecond line.\n' + "x" * 20_000
    log = EventLog()
    tester_idle = log.signal(IDLE, "tester")
    scripted = ScriptedSwarm({"tester": [reply("Waiting."), reply("Read it.")], "builder": [after(tester_idle, send("tester", text)), reply("Sent.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert only(result.events, SENT, "builder").text == text
    delivered = scripted.calls_by("tester")[1].messages[-1]["content"]
    assert delivered.count(text) == 1
    _assert_inbox(delivered, ("builder", text))
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()
