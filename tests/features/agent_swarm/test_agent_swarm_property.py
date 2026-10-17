"""FILE: tests/features/agent_swarm/test_agent_swarm_property.py

PURPOSE: Runs many seeded random swarms and checks, on every one, that the event record and what each agent's model actually received agree with each other and with the spec's invariants: valid and refused sends, tool calls, turn ends of both kinds, random scheduler yields inside model calls and inside an async or sync on_event callback, a tight turn budget, and one agent failing mid-turn.
ROLE IN CODEBASE: Property layer of tests/features/agent_swarm/ (spec INV-1 to INV-10, INV-13 to INV-15, INV-17, NFR-1; D-4, D-5, D-6; EC-2, EC-3, EC-4, EC-7, EC-8, EC-9). The narrow modules pin each rule with a hand-built schedule; this module searches the schedules nobody wrote by hand.
ARCHITECTURE NOTE: Each agent is a RandomAgent behaviour with its own random.Random seeded by "<seed>-<name>", so the k-th decision of an agent depends only on the seed and k, never on how the agents interleave; whatever interleaving asyncio produces, every assertion below must hold. The oracle (assert_event_invariants) checks the events alone; the reconciliation helpers then check the events against the transcripts the scripted runner recorded.
FUNCTION INVENTORY: RandomAgent (seeded model behaviour); _plan (agents, budgets and callback mode for a seed); _run (one seeded swarm); _assert_transcripts_match_events (reconciliation); test_random_schedules_keep_every_event_invariant_and_end_quiet; test_random_schedules_under_a_tight_turn_budget_end_quiet_or_max_turns_by_the_rules; test_random_schedules_with_one_failing_agent_contain_the_failure.
COMMON MODIFICATION PATTERNS: To widen the search, add seeds; to add an action, add one branch to RandomAgent.__call__ and, when it can change an event, one check to _assert_transcripts_match_events.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not make a RandomAgent decision depend on what its call contains (delivered text, peers' progress): decisions must be a function of the seed and the call count only, or a failure cannot be replayed from its seed. 3. Do not call bash here; a subprocess makes the interleaving depend on the machine.
KNOWN EDGE CASES: A send accepted for an agent just before it fails stays undelivered and is legal; a send after AGENT_FAILED is refused with the stopped-recipient text. The failing agent is forced to keep calling tools until its failing call, so the failure always happens inside its first turn.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6.1, 8.5 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_property.py -q
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    DELIVERED,
    FAILED,
    IDLE,
    SENT,
    TOOL_CALLED,
    EventLog,
    ModelCall,
    ScriptedSwarm,
    Step,
    assert_event_invariants,
    assert_no_stray_tasks,
    build_swarm,
    fail,
    finish,
    is_error,
    message_tool_calls,
    of_kind,
    prompt_text,
    provider_error,
    renderings,
    reply,
    run_swarm,
    seen_text,
    send,
    template_regex,
    tool_call,
    tool_results,
    user_messages,
    yield_to_loop,
)

POOL = ("builder", "tester", "reviewer", "docs")
GOAL = "Build a {small} note-taking tool, together, in the shared folder."
# Tool steps a turn may take before the agent is made to end it; keeps every run finite.
MAX_TOOL_STEPS_PER_TURN = 4
MAX_VALID_SENDS = 3


class RandomAgent:
    """A seeded model: each call it ends its turn (plain reply or isDone) or calls one tool (a valid send, a refused send, a failing read, or a write)."""

    def __init__(self, seed: int, name: str, peers: tuple[str, ...], *, fail_at: int | None = None) -> None:
        self.random = random.Random(f"{seed}-{name}")
        self.name = name
        self.peers = peers
        self.fail_at = fail_at
        self.sends_left = self.random.randint(0, MAX_VALID_SENDS)
        self.calls = 0
        self.steps_this_turn = 0
        self.turn_ends = 0
        self.sends = 0
        self.writes = 0

    async def __call__(self, call: ModelCall) -> Step:
        self.calls += 1
        # Shake the interleaving: hand the event loop to other agents a random number of times first.
        await yield_to_loop(self.random.randint(0, 3))
        if self.fail_at is not None and self.calls >= self.fail_at:
            return fail(provider_error(f"openai returned 503 for {self.name}"))
        must_work = self.fail_at is not None
        if not must_work and (self.steps_this_turn >= MAX_TOOL_STEPS_PER_TURN or self.random.random() < 0.35):
            self.steps_this_turn = 0
            self.turn_ends += 1
            text = f"{self.name} ended turn {self.turn_ends}."
            return finish(text) if self.random.random() < 0.3 else reply(text)
        self.steps_this_turn += 1
        roll = self.random.random()
        if self.sends_left > 0 and roll < 0.5:
            self.sends_left -= 1
            self.sends += 1
            peer = self.random.choice(self.peers)
            return send(peer, f"[{self.name}->{peer} #{self.sends}]")
        if roll < 0.65:
            to, text = self.random.choice(((self.name, "note to self"), ("nobody", "hello?"), (self.random.choice(self.peers), "   ")))
            return send(to, text)
        if roll < 0.8:
            return tool_call("read_lines", {"path": f"missing-{self.name}.txt"})
        self.writes += 1
        return tool_call("write_text", {"path": f"notes/{self.name}-{self.writes}.md", "content": f"{self.name} note {self.writes}\n", "create_parents": True})


@dataclass(frozen=True)
class Plan:
    names: tuple[str, ...]
    log_mode: str
    log_yields: int
    extra_turns: int
    failing: str | None
    fail_at: int


def _plan(seed: int) -> Plan:
    # Everything about the run except the agents' own decisions comes from one seed-level stream.
    chooser = random.Random(f"plan-{seed}")
    count = chooser.randint(2, len(POOL))
    names = tuple(POOL[:count])
    return Plan(
        names=names,
        log_mode=chooser.choice(("sync", "async")),
        log_yields=chooser.randint(0, 2),
        extra_turns=chooser.randint(0, 2),
        failing=chooser.choice(names),
        fail_at=chooser.randint(1, 3),
    )


async def _run(tmp_path: Path, seed: int, *, max_turns: int | None, with_failure: bool) -> tuple[Any, ScriptedSwarm, dict[str, RandomAgent], EventLog, Plan]:
    plan = _plan(seed)
    agents = {
        name: RandomAgent(seed, name, tuple(peer for peer in plan.names if peer != name), fail_at=plan.fail_at if with_failure and name == plan.failing else None)
        for name in plan.names
    }
    scripted = ScriptedSwarm(behaviours=agents)
    log = EventLog(mode=plan.log_mode, yields=plan.log_yields)
    fields: dict[str, Any] = {"on_event": log.callback}
    if max_turns is not None:
        fields["max_turns"] = max_turns
    swarm = build_swarm(tmp_path, plan.names, **fields)
    with scripted.install():
        result = await run_swarm(swarm, GOAL)
    return result, scripted, agents, log, plan


def _assert_transcripts_match_events(result: Any, scripted: ScriptedSwarm, agents: dict[str, RandomAgent], *, failed: str | None) -> None:
    """Reconciles result.events with what every model call carried (INV-1 to INV-8, INV-17, AC-19)."""
    events = list(result.events)
    names = tuple(agents)
    last = {name: scripted.last_call(name) for name in names}
    stopped = prompt_text("message_stopped_recipient")
    sent_ok = prompt_text("message_sent")
    for name in names:
        calls = scripted.calls_by(name)
        # INV-1, INV-2, INV-3: the goal is every call's prompt; one system string; one conversation that only grows.
        assert all(call.prompt == GOAL for call in calls), name
        assert len({call.system for call in calls}) == 1, f"{name}'s system string changed"
        assert calls[0].messages == []
        for earlier, later in zip(calls, calls[1:]):
            assert later.messages[: len(earlier.messages)] == earlier.messages, f"{name}'s history was edited"
        # AC-19: one TOOL_CALLED per non-isDone tool result, in order, carrying its status.
        transcript_tools = [(tool, "error" if is_error(content) else "success") for tool, content in tool_results(last[name]) if tool != "isDone"]
        recorded_tools = [(event.tool_name, event.tool_status.value) for event in of_kind(events, TOOL_CALLED, name)]
        assert recorded_tools == transcript_tools, name
        # INV-4, INV-8: every accepted send is one MESSAGE_SENT with the same recipient and text, in order; every refusal sent nothing.
        calls_made = message_tool_calls(last[name])
        accepted = [(args["to"], args["text"]) for args, content in calls_made if not is_error(content)]
        assert [(event.peer, event.text) for event in of_kind(events, SENT, name)] == accepted, name
        for args, content in calls_made:
            if not is_error(content):
                assert template_regex(sent_ok, recipient=args["to"]).search(content), content
            elif args["to"] in agents and args["to"] != name and args["text"].strip():
                # A well-formed send to a peer is refused only because that peer has failed (EC-7).
                assert args["to"] == failed, f"{name}'s send to {args['to']} was refused: {content}"
                assert template_regex(stopped, recipient=failed).search(content), content
        # INV-14: one AGENT_IDLE per turn the model ended.
        assert len(of_kind(events, IDLE, name)) == agents[name].turn_ends, name
    delivered_ids = [event.message_id for event in of_kind(events, DELIVERED)]
    for recipient in names:
        inbox = "\n".join(user_messages(last[recipient]))
        positions: list[int] = []
        for event in of_kind(events, DELIVERED, recipient):
            sent = next(item for item in events if item.sequence == event.message_id)
            # INV-5, INV-6: a delivered text reaches its recipient once, labeled with its sender, after everything delivered before it.
            assert inbox.count(sent.text) == 1, (recipient, sent.text)
            assert renderings(prompt_text("inbox_message"), inbox, sender=sent.agent, text=sent.text) == 1, (recipient, sent.text)
            positions.append(inbox.index(sent.text))
        assert positions == sorted(positions), f"{recipient} received messages out of acceptance order"
    for event in of_kind(events, SENT):
        # INV-5: no text reaches an agent it was not sent to, and an undelivered text reaches nobody.
        for other in names:
            if other in (event.agent, event.peer):
                continue
            assert event.text not in seen_text(last[other]), (event.text, other)
        if event.sequence not in delivered_ids:
            assert event.text not in "\n".join(user_messages(last[event.peer])), event.text


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(16))
async def test_random_schedules_keep_every_event_invariant_and_end_quiet(tmp_path: Path, seed: int) -> None:
    """INV-1 to INV-15, NFR-1: with the default budget every seeded swarm ends QUIET, its events pass the oracle, and the events and transcripts agree."""
    from vidbyte import AgentSwarmStopReason

    result, scripted, agents, log, plan = await _run(tmp_path, seed, max_turns=None, with_failure=False)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, plan
    assert_event_invariants(result, plan.names, max_turns=500, log=log)
    _assert_transcripts_match_events(result, scripted, agents, failed=None)
    # INV-5: on QUIET every accepted message was delivered.
    assert len(of_kind(result.events, DELIVERED)) == len(of_kind(result.events, SENT))
    scripted.assert_complete()
    assert_no_stray_tasks()


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(16, 28))
async def test_random_schedules_under_a_tight_turn_budget_end_quiet_or_max_turns_by_the_rules(tmp_path: Path, seed: int) -> None:
    """INV-9, INV-10, EC-8, EC-9: with max_turns between the agent count and two more, turns never exceed it and the stop reason follows the rule the oracle replays."""
    from vidbyte import AgentSwarmStopReason

    plan = _plan(seed)
    max_turns = len(plan.names) + plan.extra_turns
    result, scripted, agents, log, plan = await _run(tmp_path, seed, max_turns=max_turns, with_failure=False)

    assert result.stop_reason in (AgentSwarmStopReason.QUIET, AgentSwarmStopReason.MAX_TURNS), plan
    assert_event_invariants(result, plan.names, max_turns=max_turns, log=log)
    _assert_transcripts_match_events(result, scripted, agents, failed=None)
    scripted.assert_complete()
    assert_no_stray_tasks()


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(28, 36))
async def test_random_schedules_with_one_failing_agent_contain_the_failure(tmp_path: Path, seed: int) -> None:
    """INV-17, EC-7, EC-12: one agent's provider error inside its first turn fails only that agent, names the cause, and refuses later sends to it; the others end QUIET."""
    from vidbyte import AgentSwarmStopReason

    result, scripted, agents, log, plan = await _run(tmp_path, seed, max_turns=None, with_failure=True)

    assert result.stop_reason is AgentSwarmStopReason.QUIET, plan
    assert_event_invariants(result, plan.names, max_turns=500, log=log)
    failures = of_kind(result.events, FAILED)
    assert [event.agent for event in failures] == [plan.failing]
    assert failures[0].text.startswith("ProviderRequestError") and f"503 for {plan.failing}" in failures[0].text
    assert len(scripted.calls_by(plan.failing)) == plan.fail_at
    assert [item.sender for item in result.replies] == [name for name in plan.names if name != plan.failing]
    _assert_transcripts_match_events(result, scripted, agents, failed=plan.failing)
    scripted.assert_complete()
    assert_no_stray_tasks()
