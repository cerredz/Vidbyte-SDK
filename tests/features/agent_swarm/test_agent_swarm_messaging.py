"""FILE: tests/features/agent_swarm/test_agent_swarm_messaging.py

PURPOSE: Pins the swarm's mailbox protocol. A message to a working agent arrives after its next tool result and never blocks the sender, with or without turn budget left. Messages that waited together arrive as one labeled user message in acceptance order. A message wakes an idle agent after a plain reply or an isDone, and an agent that ends its turn with mail waiting continues at once. Two agents messaging each other never deadlock. A message accepted in the exact step that reports its recipient going idle is never lost. A message to oneself is accepted and delivered like any other. Exactly two inputs are refused (an unknown or non-text name, and blank text), each as a tool error with one message_refused event and nothing queued. Message text arrives whole.
ROLE IN CODEBASE: Messaging layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-3, AC-4; EC-1, EC-2, EC-3; INV-5, INV-6, INV-7, INV-8, INV-9; D-4). Exercises AgentSwarmRuntime.post_message, collect_messages and end_turn through the real member loop, plus the message tool and the turn middleware.
ARCHITECTURE NOTE: Interleavings are forced, never timed. FakeTavily (block=True) holds an agent inside its tavily_search call until a model call of another agent releases it. Gate makes two calls overlap. EventLog.signal turns a swarm state change (an agent going idle, a message being sent) into a Signal a scripted step waits on. Each test reads both views of one run: the event record and what each model was sent.
FUNCTION INVENTORY: test_a_message_to_a_working_agent_arrives_after_its_tool_result_without_blocking_the_sender; test_messages_queued_before_one_delivery_point_arrive_together_in_acceptance_order; test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply; test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once; test_two_agents_messaging_each_other_mid_turn_never_deadlock; test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost; test_a_message_to_oneself_is_accepted_and_delivered_at_the_next_tool_iteration (AC-3, EC-2); test_a_self_message_sent_with_isdone_wakes_the_sender_at_once (EC-3); test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues (AC-4, EC-1, INV-5); test_message_text_reaches_the_recipient_whole_and_unformatted.
COMMON MODIFICATION PATTERNS: To force a new interleaving, add a Signal from EventLog.signal or a blocking FakeTavily rather than a sleep.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not gate a step on another agent's "answered" mark to wait for an idle agent; that mark fires before end_turn marks it idle. 3. Do not compare delivered user messages or refusals to hand-written text; build the expectation from the agent_swarm catalog templates.
KNOWN EDGE CASES: The lost-wake-up test sends from the on_event callback that reports tester going idle, as a separate task, and yields so that the send's synchronous part runs while that report is still being delivered. A callback that awaited post_message directly would wait on the event outbox it is already inside. A self-message sent in the same response as isDone is still queued at the turn end, because the loop skips the tool-iteration seam for a finishing response, so it wakes the sender (EC-3).
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1, 6.2, 6.3, 8.1 (D-4) and 8.5.
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
    REFUSED,
    SENT,
    TAVILY_TOOL,
    TOOL_CALLED,
    WOKE,
    EventLog,
    FakeTavily,
    Gate,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    build_settings,
    build_swarm,
    calls,
    finish,
    is_error,
    observe,
    of_kind,
    only,
    prompt_text,
    renderings,
    reply,
    run_swarm,
    search,
    send,
    seq_of,
    template_regex,
    tool_call,
    tool_result,
    user_messages,
    web_search_fields,
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
    """INV-9 (r5 AC-2 kept): tester's next call holds, right after its tool result, one user message from builder; builder's send returned first."""
    from vidbyte import AgentSwarmStopReason

    fake = FakeTavily(block=True)
    # tester sits inside its search until builder's second model call, which can only happen after builder's message call returned.
    scripted = ScriptedSwarm(
        {
            "tester": [search("celsius to fahrenheit formula"), reply("Tests pass.")],
            "builder": [after(fake.entered, send("tester", NOTE)), observe(lambda call: fake.release.set(), reply("Sent."))],
        }
    )
    log = EventLog()
    max_turns = len(NAMES) if budget == "budget-spent" else 500
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback, max_turns=max_turns, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert fake.problems == []
    # The sender was never held behind the busy recipient.
    assert scripted.position("builder call 2") < scripted.position("tester call 2")
    sent_reply = tool_result(scripted.calls_by("builder")[1], "message")
    assert not is_error(sent_reply) and template_regex(prompt_text("message_sent"), recipient="tester").search(sent_reply)
    # After the search result comes exactly one user message, and nothing went into the system string.
    second = scripted.calls_by("tester")[1]
    assert [message["role"] for message in second.messages] == ["assistant", "tool", "user"]
    assert second.messages[1]["name"] == TAVILY_TOOL
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
    """INV-8 (r5 EC-4 kept): two messages that wait for one delivery point arrive as one user message, each labeled, in acceptance order."""
    from vidbyte import AgentSwarmStopReason

    names = ("builder", "tester", "reviewer")
    from_builder, from_reviewer = "Builder here: c2f.py now rounds to one decimal.", "Reviewer here: please also test negative input."
    fake = FakeTavily(block=True)
    log = EventLog()
    builder_sent = log.signal(SENT, "builder")
    scripted = ScriptedSwarm(
        {
            "tester": [search("fahrenheit rounding"), reply("Tester done.")],
            "builder": [after(fake.entered, send("tester", from_builder)), reply("Builder done.")],
            "reviewer": [after(builder_sent, send("tester", from_reviewer)), observe(lambda call: fake.release.set(), reply("Reviewer done."))],
        }
    )
    swarm = build_swarm(tmp_path, names, on_event=log.callback, **web_search_fields())
    with scripted.install(), fake.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    second = scripted.calls_by("tester")[1]
    assert [message["role"] for message in second.messages] == ["assistant", "tool", "user"]
    _assert_inbox(second.messages[2]["content"], ("builder", from_builder), ("reviewer", from_reviewer))
    # One message_delivered per message, back to back, oldest first.
    deliveries = of_kind(result.events, DELIVERED, "tester")
    assert [event.peer for event in deliveries] == ["builder", "reviewer"]
    assert deliveries[1].sequence == deliveries[0].sequence + 1
    assert deliveries[0].message_id < deliveries[1].message_id
    assert_event_invariants(result, names, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["reply", "isdone"])
async def test_a_message_wakes_an_idle_agent_into_a_new_turn_after_its_previous_reply(tmp_path: Path, ending: str) -> None:
    """INV-9, INV-39 (r5 AC-3 kept): an idle tester is woken by builder's message; its new turn's first call ends with that message after its previous reply."""
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
    # The same conversation continues, and the message comes after the previous reply (or after isDone's provisional refusal).
    assert second.messages[: len(first.messages)] == first.messages
    assert second.messages[-1]["role"] == "user"
    _assert_inbox(second.messages[-1]["content"], ("builder", NOTE))
    previous = second.messages[-2]
    if ending == "reply":
        assert previous == {"role": "assistant", "content": "Waiting for code."}
    else:
        assert previous["role"] == "tool" and previous["name"] == "isDone" and FINISH_NOT_ACCEPTED in previous["content"]
    # The wake is recorded in the same step as the send.
    events = result.events
    idle, sent, woke, delivered = seq_of(events, IDLE, "tester"), seq_of(events, SENT, "builder"), seq_of(events, WOKE, "tester"), seq_of(events, DELIVERED, "tester")
    assert idle < sent < woke < delivered and woke == sent + 1
    assert [event.text for event in of_kind(events, IDLE, "tester")] == ["Waiting for code.", "Tests pass."]
    assert [(item.sender, item.content) for item in result.replies] == [("builder", "Sent."), ("tester", "Tests pass.")]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_an_agent_that_ends_its_turn_with_mail_waiting_continues_at_once(tmp_path: Path) -> None:
    """INV-10 (r5 AC-20 kept): a message that arrived during tester's model call is delivered when its turn ends, with agent_idle then agent_woke and no further send."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_two_agents_messaging_each_other_mid_turn_never_deadlock(tmp_path: Path) -> None:
    """INV-9 (r5 EC-2 kept): builder and tester message each other from overlapping calls; both sends return and each message is delivered once, mid-turn."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost(tmp_path: Path) -> None:
    """INV-9 (r5 EC-1 kept): a send made while tester's agent_idle is being reported is decided against tester's new state, so tester is woken and the message delivered."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarmRuntime

    root = workplace_path(tmp_path)
    root.mkdir()
    log = EventLog(mode="async")
    builder_sent = log.signal(SENT, "builder")
    holder: dict[str, Any] = {}
    posted: list[asyncio.Future[str]] = []

    async def send_while_tester_goes_idle(event: Any) -> None:
        # Inside the report of tester's first agent_idle: start a send as its own task and let its synchronous part run now.
        if event.kind.value == IDLE and event.agent == "tester" and not posted:
            posted.append(asyncio.ensure_future(holder["runtime"].post_message("builder", "tester", NOTE)))
            await yield_to_loop(2)

    log.hook(send_while_tester_goes_idle)
    settings = build_settings(tmp_path, NAMES, on_event=log.callback)
    runtime = AgentSwarmRuntime(settings, root, workplace_created=False)
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
    assert_event_invariants(result, NAMES, max_turns=settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_message_to_oneself_is_accepted_and_delivered_at_the_next_tool_iteration(tmp_path: Path) -> None:
    """AC-3, EC-2, INV-6, D-4 (reverses the r5 to-itself refusal): builder's message to itself is a success with the message_sent text, one message_sent names builder as agent and peer, and the text comes back to builder as one inbox user message right after the tool result."""
    from vidbyte import AgentSwarmStopReason

    note = "Remember: c2f must accept negative input."
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [send("builder", note), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    second = scripted.calls_by("builder")[1]
    sent_reply = tool_result(second, "message")
    assert not is_error(sent_reply) and template_regex(prompt_text("message_sent"), recipient="builder").search(sent_reply)
    assert [message["role"] for message in second.messages] == ["assistant", "tool", "user"]
    _assert_inbox(second.messages[2]["content"], ("builder", note))
    sent = only(result.events, SENT, "builder")
    assert (sent.agent, sent.peer, sent.text) == ("builder", "builder", note)
    delivered = only(result.events, DELIVERED, "builder")
    assert (delivered.peer, delivered.message_id) == ("builder", sent.message_id)
    assert sent.sequence < seq_of(result.events, TOOL_CALLED, "builder") < delivered.sequence < seq_of(result.events, IDLE, "builder")
    assert of_kind(result.events, WOKE) == [] and of_kind(result.events, REFUSED) == []
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_a_self_message_sent_with_isdone_wakes_the_sender_at_once(tmp_path: Path) -> None:
    """EC-3, INV-9, INV-10: a note to itself sent in the same response as isDone is still waiting at the turn end, so builder wakes itself at once (agent_idle, agent_woke, message_delivered) and reads its own note in one extra turn."""
    from vidbyte import AgentSwarmStopReason

    note = "Next turn: add the --round flag."
    log = EventLog()
    scripted = ScriptedSwarm({"builder": [calls(send("builder", note), finish("First pass done.")), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    events = result.events
    idle, woke, delivered = seq_of(events, IDLE, "builder"), seq_of(events, WOKE, "builder"), seq_of(events, DELIVERED, "builder")
    assert seq_of(events, SENT, "builder") < idle and (woke, delivered) == (idle + 1, idle + 2)
    second = scripted.calls_by("builder")[1]
    _assert_inbox(second.messages[-1]["content"], ("builder", note))
    assert [event.text for event in of_kind(events, IDLE, "builder")] == ["First pass done.", "Builder done."]
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


REFUSALS = [
    pytest.param("deployer", NOTE, "message_unknown_recipient", "deployer", id="to-an-unknown-name"),
    pytest.param("all", NOTE, "message_unknown_recipient", "all", id="to-all-is-not-a-broadcast"),
    pytest.param(42, NOTE, "message_unknown_recipient", "42", id="to-a-number"),
    pytest.param(None, NOTE, "message_unknown_recipient", "", id="to-null"),
    pytest.param("tester", "   ", "message_blank_text", "tester", id="blank-text"),
    pytest.param("tester", "", "message_blank_text", "tester", id="empty-text"),
    pytest.param("tester", None, "message_blank_text", "tester", id="text-not-a-string"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("to", "text", "leaf", "peer"), REFUSALS)
async def test_a_refused_message_is_a_tool_error_queues_nothing_and_the_loop_continues(tmp_path: Path, to: Any, text: Any, leaf: str, peer: str) -> None:
    """AC-4, EC-1, INV-5: unknown, non-text, "all", blank and empty sends return the catalog refusal as a tool error and record one message_refused (sender, the name as text, the reason); nothing is sent, queued or woken."""
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
    known = {"agents": ", ".join(NAMES)} if leaf == "message_unknown_recipient" else {}
    if leaf == "message_unknown_recipient" and isinstance(to, str):
        # The refusal names the recipient it was given and every agent of the swarm, the sender included.
        known["recipient"] = to
        assert template_regex(prompt_text(leaf), **known).search(refusal), refusal
        assert "tester" in refusal
    else:
        assert template_regex(prompt_text(leaf), **known).search(refusal), refusal
    refused = only(result.events, REFUSED, "builder")
    assert refused.peer == peer and refused.text.strip() and refused.text.strip() in refusal
    assert template_regex(prompt_text(leaf), **known).fullmatch(refused.text.strip()), refused.text
    # Nothing queued: no send, no wake, no delivery, and no delivered message in builder's own history either.
    assert of_kind(result.events, SENT) == [] and of_kind(result.events, DELIVERED) == [] and of_kind(result.events, WOKE) == []
    assert user_messages(second) == []
    tool_event = only(result.events, TOOL_CALLED, "builder")
    assert (tool_event.tool_name, tool_event.tool_status) == ("message", ToolStatus.ERROR)
    assert refused.sequence < tool_event.sequence
    # The loop continued past the refusal, and tester was never called again.
    assert len(scripted.calls_by("builder")) == 2 and len(scripted.calls_by("tester")) == 1
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_message_text_reaches_the_recipient_whole_and_unformatted(tmp_path: Path) -> None:
    """INV-6 (r5 EC-27 kept): braces, format fields, unicode, newlines and 20,000 more characters reach the recipient and the event exactly as sent."""
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
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
