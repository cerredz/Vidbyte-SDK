"""FILE: tests/features/agent_swarm/test_agent_swarm_acceptance.py

PURPOSE: Proves the caller-visible story of AgentSwarm end to end: the spec's section 4 snippet runs as written (three members, no per-member prompt, Tavily web search) and prints exactly what the spec says, three members are created then started in order holding the search tool right before isDone, a swarm whose agents each end one turn without messages ends QUIET with one reply per agent, and every agent's model receives the goal verbatim as the prompt of every call inside one append-only conversation.
ROLE IN CODEBASE: Acceptance layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-1, AC-2, AC-7; INV-1, INV-4, INV-14, INV-17, INV-38; FR-1). Start here when a caller reports a regression; the narrower modules pin each rule.
ARCHITECTURE NOTE: Only the model runner is scripted (ScriptedSwarm at BaseAgent._runner_for_model) and the Tavily HTTP call is faked (FakeTavily); the agent loop, middleware, catalog, file tools and filesystem are real and live under tmp_path. Every run is also checked by assert_event_invariants, the pack's oracle.
FUNCTION INVENTORY: test_the_section_4_snippet_runs_as_written (AC-1); test_three_members_are_created_then_started_in_order_with_the_search_tool_before_isdone (AC-2); test_agents_that_end_their_first_turn_without_messages_end_quiet_with_one_reply_each (AC-7, INV-14); test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation (INV-4).
COMMON MODIFICATION PATTERNS: Keep the section 4 snippet byte-for-byte as the spec prints it; if the spec's snippet changes, paste the new one.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not edit the snippet to make it easier to test; chdir into tmp_path and guard asyncio.run instead. 3. Do not let the snippet's Tavily tool reach the network; FakeTavily is installed around it.
KNOWN EDGE CASES: Whether ben's message arrives before or after its first turn ends depends on scheduling; either way ben makes exactly two model calls, so the script is exact. The snippet's api_keys entry is the literal "sk-proj-...", which the provider-key matcher accepts as an OpenAI key. The two agents of the one-turn test interleave freely, so its event list is compared as a sorted multiset after the fixed start.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 4, 6.1 and 6.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_acceptance.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    ENDED,
    IDLE,
    MODEL_CALLED,
    RELEASED,
    STOPPING,
    TAVILY_TOOL,
    TOOL_CALLED,
    EventLog,
    FakeTavily,
    ScriptedSwarm,
    after,
    assert_event_invariants,
    assert_no_stray_tasks,
    build_swarm,
    finish,
    guard_asyncio_run,
    of_kind,
    only,
    pairs,
    reply,
    run_swarm,
    search,
    send,
    shared_system_prompt,
    start_pairs,
    tool_call,
    web_search_fields,
)

NAMES = ("builder", "tester")
SNIPPET_NAMES = ("ada", "ben", "cleo")
C2F_SOURCE = 'import sys\n\n\ndef c2f(celsius: float) -> float:\n    return celsius * 9 / 5 + 32\n\n\nif __name__ == "__main__":\n    print(c2f(float(sys.argv[1])))\n'


def _snippet_swarm() -> ScriptedSwarm:
    # ada writes the tool and tells ben; ben ends one turn, is woken (or continues at once) and reports; cleo checks the formula on the web.
    return ScriptedSwarm(
        {
            "ada": [
                tool_call("write_text", {"path": "c2f.py", "content": C2F_SOURCE}),
                send("ben", "c2f.py is ready; please test it."),
                reply("Wrote c2f.py."),
            ],
            "ben": [reply("Waiting for the code."), reply("Tests pass.")],
            "cleo": [search("celsius to fahrenheit formula"), reply("Formula checked.")],
        }
    )


def test_the_section_4_snippet_runs_as_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, INV-1: the section 4 snippet builds its settings, every member's first call carries the shared section template then the loop prompt, and it prints one line per event and then the stop reason, the event count and the reply count."""
    from vidbyte.prompts.agentic_loop import agentic_loop_prompt

    monkeypatch.chdir(tmp_path)
    guard_asyncio_run(monkeypatch)
    scripted = _snippet_swarm()
    fake = FakeTavily()
    with scripted.install(), fake.install():
        # ---- spec section 4, as printed ----
        import asyncio

        from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings

        settings = AgentSwarmSettings(
            agents=(
                AgentSwarmMember(name="ada", provider="openai", model_name="gpt-4.1"),
                AgentSwarmMember(name="ben", provider="openai", model_name="gpt-4.1"),
                AgentSwarmMember(name="cleo", provider="openai", model_name="gpt-4.1"),
            ),
            workplace="swarm-workplace",          # created if missing, never cleaned
            api_keys=["sk-proj-..."],             # matched to each member's provider
            web_search="tavily",                  # AgentSwarmWebSearch value; None means no web search
            web_search_api_key="tvly-...",
            on_event=lambda event: print(event.sequence, event.kind.value, event.agent, event.peer, event.text),
        )

        result = asyncio.run(AgentSwarm(settings).arun("Build a Celsius-to-Fahrenheit command-line tool with tests."))
        print(result.stop_reason.value, len(result.events), len(result.replies))
        # ---- end of section 4 ----

    lines = capsys.readouterr().out.splitlines()
    # print(a, b, c, d, e) joins with single spaces, so an empty peer or text leaves its separator.
    event_lines = [" ".join((str(event.sequence), event.kind.value, event.agent, event.peer, event.text)) for event in result.events]
    assert lines == [*event_lines, f"quiet {len(result.events)} 3"]
    assert [item.sender for item in result.replies] == list(SNIPPET_NAMES)
    workplace = (tmp_path / "swarm-workplace").resolve()
    loop_text = agentic_loop_prompt().strip()
    for name in SNIPPET_NAMES:
        system = scripted.first_call(name).system
        loop_at = system.find(loop_text)
        # The "System prompt:" label is written by BaseContext.build_context_fixed (vidbyte/lib/dataclasses/context.py), shared by every agent.
        assert loop_at > 0 and system[:loop_at].strip() == "System prompt:\n" + shared_system_prompt(name, SNIPPET_NAMES, workplace, search_tool=TAVILY_TOOL), f"{name}'s first call does not carry the shared template"
    assert fake.queries == ["celsius to fahrenheit formula"]
    assert_event_invariants(result, SNIPPET_NAMES, max_turns=settings.max_turns)
    assert (workplace / "c2f.py").read_text(encoding="utf-8") == C2F_SOURCE
    scripted.assert_complete()


@pytest.mark.asyncio
async def test_three_members_are_created_then_started_in_order_with_the_search_tool_before_isdone(tmp_path: Path) -> None:
    """AC-2, INV-17, INV-38: after workplace_prepared come agent_created for each member in settings order, then agent_started for each; each catalog is the swarm tools, then tavily_search, then the loop's isDone."""
    log = EventLog()
    scripted = ScriptedSwarm({name: [reply(f"{name} done.")] for name in SNIPPET_NAMES})
    swarm = build_swarm(tmp_path, SNIPPET_NAMES, on_event=log.callback, **web_search_fields())
    with scripted.install():
        result = await run_swarm(swarm)

    assert pairs(result.events[:7]) == start_pairs(SNIPPET_NAMES)
    for name in SNIPPET_NAMES:
        tools = scripted.first_call(name).tools
        assert tools[-2:] == (TAVILY_TOOL, "isDone") and tools.index("compact") == len(tools) - 3, f"{name} holds {tools}"
    assert_event_invariants(result, SNIPPET_NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", ["default-budget", "budget-equals-agents"])
@pytest.mark.parametrize("ending", ["reply", "isdone", "empty-reply"])
async def test_agents_that_end_their_first_turn_without_messages_end_quiet_with_one_reply_each(tmp_path: Path, ending: str, budget: str) -> None:
    """AC-7, INV-14 (r5 AC-4 kept): no messages means QUIET after one turn each, one reply per agent in member order, each agent released after swarm_stopping, and swarm_ended last."""
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
    # The fixed start; one model call and one idle each (carrying the turn's reply, empty included); the stop, one release each, the end: nothing else, and no tool_called for isDone.
    expected = [*start_pairs(NAMES), *((kind, name) for name in NAMES for kind in (MODEL_CALLED, IDLE, RELEASED)), (STOPPING, ""), (ENDED, "")]
    assert pairs(result.events[:5]) == start_pairs(NAMES)
    assert sorted(pairs(result.events)) == sorted(expected) and len(result.events) == 13
    assert {name: only(result.events, IDLE, name).text for name in NAMES} == texts
    assert of_kind(result.events, TOOL_CALLED) == []
    assert_event_invariants(result, NAMES, max_turns=max_turns, log=log)
    scripted.assert_complete()
    assert_no_stray_tasks()


@pytest.mark.asyncio
async def test_every_agent_gets_the_goal_verbatim_as_the_prompt_of_every_call_in_one_conversation(tmp_path: Path) -> None:
    """INV-4 (r5 INV-1..INV-3 kept): the goal (braces, unicode, edge whitespace kept) is every call's prompt and never a message; each agent's history only grows and its system string never changes."""
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
        # INV-4: the goal is the prompt of every call, exactly as passed, and never repeated as a message.
        assert all(call.prompt == goal for call in calls)
        assert all(goal not in str(message.get("content")) for call in calls for message in call.messages)
        # One conversation that only grows, under one unchanging system string.
        assert calls[0].messages == []
        for earlier, later in zip(calls, calls[1:]):
            assert later.messages[: len(earlier.messages)] == earlier.messages
            assert len(later.messages) > len(earlier.messages)
            assert later.system == earlier.system
    # tester's second turn still holds its first turn's reply before the delivered message.
    assert scripted.calls_by("tester")[1].messages[0] == {"role": "assistant", "content": "Waiting."}
    assert_event_invariants(result, NAMES, max_turns=swarm.settings.max_turns, log=log)
    scripted.assert_complete()
