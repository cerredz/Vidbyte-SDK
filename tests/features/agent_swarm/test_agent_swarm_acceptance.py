"""FILE: tests/features/agent_swarm/test_agent_swarm_acceptance.py

PURPOSE: Proves the caller-visible story of AgentSwarm end to end: the spec's section 4 snippet runs as written and prints exactly what the spec says, a swarm whose agents each end one turn without messages ends QUIET with one reply per agent (after a plain reply, an isDone, or an empty reply, with the default or an exact turn budget), and every agent's model receives the goal verbatim as the prompt of every call inside one append-only conversation.
ROLE IN CODEBASE: Acceptance layer of tests/features/agent_swarm/ (spec AC-1, AC-4; INV-1, INV-2, INV-3, INV-10, INV-11; EC-9, EC-11, EC-36; FR-2, FR-7, FR-15; G-1, G-3, G-4). Start here when a caller reports a regression; the narrower modules pin each rule.
ARCHITECTURE NOTE: Only the model runner is scripted (ScriptedSwarm at BaseAgent._runner_for_model); the agent loop, middleware, catalog, file tools and filesystem are real and live under tmp_path. Every run is also checked by assert_event_invariants, the pack's oracle.
FUNCTION INVENTORY: test_section_4_snippet_prints_one_line_per_event_then_quiet_true_swarm_ended_and_one_reply_per_agent (AC-1); test_agents_that_end_their_first_turn_without_messages_end_quiet_with_one_reply_each (AC-4, EC-9, EC-11, EC-36); test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation (INV-1, INV-2, INV-3, FR-2).
COMMON MODIFICATION PATTERNS: Keep the section 4 snippet byte-for-byte as the spec prints it; if the spec's snippet changes, paste the new one.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not edit the snippet to make it easier to test; chdir into tmp_path and guard asyncio.run instead.
KNOWN EDGE CASES: The snippet assigns a loop variable named `reply`, so its scripted swarm is built by a module helper instead of with reply() inside the test body. Whether tester's message arrives before or after its first turn ends depends on scheduling; either way tester makes exactly two model calls, so the script is exact.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 4, 6.1, 6.2 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_acceptance.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    ENDED,
    IDLE,
    TOOL_CALLED,
    EventLog,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    assert_no_stray_tasks,
    build_swarm,
    finish,
    guard_asyncio_run,
    of_kind,
    only,
    reply,
    run_swarm,
    send,
    tool_call,
)

NAMES = ("builder", "tester")
C2F_SOURCE = 'import sys\n\n\ndef c2f(celsius: float) -> float:\n    return celsius * 9 / 5 + 32\n\n\nif __name__ == "__main__":\n    print(c2f(float(sys.argv[1])))\n'


def _snippet_swarm() -> ScriptedSwarm:
    # builder writes the tool and tells tester; tester ends one turn, is woken (or continues at once) and reports.
    return ScriptedSwarm(
        {
            "builder": [
                tool_call("write_text", {"path": "c2f.py", "content": C2F_SOURCE}),
                send("tester", "c2f.py is ready; please test it."),
                reply("Wrote c2f.py."),
            ],
            "tester": [reply("Waiting for the code."), reply("Tests pass.")],
        }
    )


def test_section_4_snippet_prints_one_line_per_event_then_quiet_true_swarm_ended_and_one_reply_per_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, G-1, G-4: the section 4 snippet prints one show line per event in sequence order, then quiet, True, swarm_ended, then one line per agent."""
    monkeypatch.chdir(tmp_path)
    guard_asyncio_run(monkeypatch)
    scripted = _snippet_swarm()
    with scripted.install():
        # ---- spec section 4, as printed ----
        import asyncio

        from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings
        from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent

        def show(event: AgentSwarmEvent) -> None:
            # Called once per event, in order, while the swarm runs.
            print(event.sequence, event.kind.value, event.agent, event.peer)

        swarm = AgentSwarm(
            AgentSwarmSettings(
                agents=(
                    AgentSwarmMember(name="builder", system_prompt="You write the code.", provider="openai", model_name="gpt-4.1"),
                    AgentSwarmMember(name="tester", system_prompt="You write and run the tests.", provider="openai", model_name="gpt-4.1"),
                ),
                workplace="swarm-workplace",  # one folder both agents share; created if missing, never deleted
                on_event=show,
            )
        )

        result = asyncio.run(swarm.arun("Build a Celsius-to-Fahrenheit command-line tool with tests."))
        print(result.stop_reason.value)                          # quiet
        print(result.events[-1].sequence == len(result.events))  # True
        print(result.events[-1].kind.value)                      # swarm_ended
        for reply in result.replies:
            print(reply.sender, reply.content)  # each agent's reply from its last turn
        # ---- end of section 4 ----

    lines = capsys.readouterr().out.splitlines()
    # print(a, b, c, d) joins with single spaces, so an empty peer leaves a trailing space.
    event_lines = [" ".join((str(event.sequence), event.kind.value, event.agent, event.peer)) for event in result.events]
    assert lines[:2] == ["1 agent_started builder ", "2 agent_started tester "]
    assert lines == [*event_lines, "quiet", "True", "swarm_ended", "builder Wrote c2f.py.", "tester Tests pass."]
    assert_event_invariants(result, NAMES, max_turns=500)
    assert (tmp_path / "swarm-workplace" / "c2f.py").read_text(encoding="utf-8") == C2F_SOURCE
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", ["default-budget", "budget-equals-agents"])
@pytest.mark.parametrize("ending", ["reply", "isdone", "empty-reply"])
async def test_agents_that_end_their_first_turn_without_messages_end_quiet_with_one_reply_each(tmp_path: Path, ending: str, budget: str) -> None:
    """AC-4, EC-9, EC-11, EC-36: no messages means QUIET after one turn each, one reply per agent in member order, and SWARM_ENDED last."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_DEFAULT_MAX_TURNS

    texts = {"builder": "Builder done.", "tester": "Tester done."} if ending != "empty-reply" else {"builder": "", "tester": ""}
    scripted = ScriptedSwarm({name: [finish(text) if ending == "isdone" else reply(text)] for name, text in texts.items()})
    log = EventLog()
    max_turns = len(NAMES) if budget == "budget-equals-agents" else AGENT_SWARM_DEFAULT_MAX_TURNS
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback, max_turns=max_turns)
    with scripted.install():
        result = await run_swarm(swarm)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert [(item.sender, item.content) for item in result.replies] == [("builder", texts["builder"]), ("tester", texts["tester"])]
    assert result.events[-1].kind.value == ENDED and result.events[-1].stop_reason is AgentSwarmStopReason.QUIET
    # Two starts, one idle each (carrying the turn's reply, empty included), the end: nothing else, and no TOOL_CALLED for isDone.
    assert len(result.events) == 5
    assert {name: only(result.events, IDLE, name).text for name in NAMES} == texts
    assert of_kind(result.events, TOOL_CALLED) == []
    assert_event_invariants(result, NAMES, max_turns=max_turns, log=log)
    scripted.assert_complete()
    assert_no_stray_tasks()


@pytest.mark.asyncio
async def test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation(tmp_path: Path) -> None:
    """INV-1, INV-2, INV-3, FR-2: the goal (braces, unicode, edge whitespace kept) is every call's prompt; each agent's history only grows and its system string never changes."""
    from vidbyte import AgentSwarmStopReason

    goal = '  Build a {"unit": "°F"} converter — naïve café ✓\nwith tests.  '
    log = EventLog()
    tester_idle = log.signal(IDLE, "tester")
    scripted = ScriptedSwarm(
        {
            "builder": [
                tool_call("write_text", {"path": "c2f.py", "content": C2F_SOURCE}),
                after(tester_idle, send("tester", "c2f.py is ready.")),
                reply("Builder done."),
            ],
            "tester": [reply("Waiting."), tool_call("read_lines", {"path": "c2f.py"}), reply("Tester done.")],
        }
    )
    swarm = build_swarm(tmp_path, NAMES, on_event=log.callback)
    with scripted.install():
        result = await run_swarm(swarm, goal)

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    for name in NAMES:
        calls = scripted.calls_by(name)
        assert len(calls) == 3
        # INV-1: the goal is the prompt of every call, exactly as passed, and never repeated as a message.
        assert all(call.prompt == goal for call in calls)
        assert all(goal not in str(message.get("content")) for call in calls for message in call.messages)
        # INV-2, INV-3: one conversation that only grows, under one unchanging system string.
        assert calls[0].messages == []
        for earlier, later in zip(calls, calls[1:]):
            assert later.messages[: len(earlier.messages)] == earlier.messages
            assert len(later.messages) > len(earlier.messages)
            assert later.system == earlier.system
    # tester's second turn still holds its first turn's reply before the delivered message.
    assert scripted.calls_by("tester")[1].messages[0] == {"role": "assistant", "content": "Waiting."}
    assert_event_invariants(result, NAMES, max_turns=500, log=log)
    scripted.assert_complete()
