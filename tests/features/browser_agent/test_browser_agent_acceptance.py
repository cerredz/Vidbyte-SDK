"""FILE: tests/features/browser_agent/test_browser_agent_acceptance.py

PURPOSE: Proves the caller-visible story of BrowserAgent end to end: the spec's section 4 snippet runs as written against the fakes and prints its event lines, the final answer, the stop reason with the episode count, and the recorded progress; every episode of one run acts on the same browser server process; sync runs get a fresh browser each and async runs on one loop share one; building the runtime has no side effects; and each run starts clean without changing an earlier run's record.
ROLE IN CODEBASE: Acceptance layer of tests/features/browser_agent/ (spec AC-1, AC-6, AC-23; INV-7, INV-23, INV-24; FR-4, FR-23; EC-22). Start here when a caller reports a regression; the narrower modules pin each rule.
ARCHITECTURE NOTE: Only the model runner (ScriptedModel at BaseAgent._runner_for_model) and the MCP stdio transport (FakeBrowserServers at vidbyte.tools.mcp.attach.McpStdioTransport) are faked. The MCP mixin, attach, client, bridge, the loop, the runtime, and the prompt catalog are real.
FUNCTION INVENTORY: test_section_4_snippet_prints_events_answer_stop_reason_and_progress (AC-1, FR-23); test_every_episode_of_one_run_uses_the_same_action_server_process (AC-6, INV-7, FR-4); test_sync_runs_get_their_own_servers_and_async_runs_on_one_loop_share_them (AC-23, EC-22, FR-4); test_building_the_runtime_has_no_side_effects (INV-23); test_each_run_starts_clean_and_never_changes_an_earlier_record (INV-24).
COMMON MODIFICATION PATTERNS: Keep the section 4 snippet byte-for-byte as the spec prints it; if the spec's snippet changes, paste the new one.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not edit the snippet to make it easier to test. 3. Do not count server processes by anything but the fake transport's instances.
KNOWN EDGE CASES: The snippet assigns a variable named `reply`, so its scripted model is built by a module helper instead of the fixture's reply() inside the test body. The snippet's model is "gpt-5.4-mini" (spec r4), which is priced; the fake replies report PRICED_MODEL, the same model, so the agent's fail-closed usage can settle (see browser_agent_fixtures.py).
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 4, 6.1 and 6.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_acceptance.py -q
"""

from __future__ import annotations

import asyncio
import copy

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    ACTION_COMMAND,
    FETCH_COMMAND,
    NAME,
    RECHECK,
    SEARCH_COMMAND,
    TASK,
    EventLog,
    FakeBrowserServers,
    ScriptedModel,
    build_agent,
    card,
    card_section,
    installed,
    reply,
    tool_call,
    verdict,
    worker,
)

FINAL_ANSWER = "FINAL-ANSWER: Seedcamp accepts applications until 30 November at https://seedcamp.com/apply."
PROGRESS_LINE = "Seedcamp - https://seedcamp.com/apply - closes 30 November"
EPISODE = {"task": "Open https://seedcamp.com/apply and read the application deadline.", "done_when": "The deadline is read from the page."}
EVENT_KINDS = {"run_started", "goal_set", "episode_started", "episode_finished", "goal_patched", "goal_rechecked", "recipe_recorded", "context_rebuilt", "run_finished", "run_stopped"}


def _snippet_script() -> ScriptedModel:
    return ScriptedModel(
        {
            NAME: [
                tool_call("run_episode", EPISODE),
                tool_call("patch_goal", {"section": "progress", "text": PROGRESS_LINE}),
                reply(FINAL_ANSWER),
            ],
            worker(1): [
                tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}),
                card("done", "Seedcamp closes 30 November.", facts=["Seedcamp closes 30 November"], urls=["https://seedcamp.com/apply"]),
            ],
            RECHECK: [verdict("done", "Nothing is missing.")],
        }
    )


def _episode_script(runs: int) -> ScriptedModel:
    """`runs` runs of: one episode that navigates, then a final answer accepted by its recheck."""
    return ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), reply(FINAL_ANSWER)] * runs,
            worker(1): [tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), card("done", "Opened the page.")] * runs,
            RECHECK: [verdict("done", "Nothing is missing.")] * runs,
        }
    )


def test_section_4_snippet_prints_events_answer_stop_reason_and_progress(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, FR-23: the section 4 snippet, run as printed with the model seam and the MCP transport faked, prints one event line per step, then the final answer, `final_response 1`, and the progress line."""
    model = _snippet_script()
    servers = FakeBrowserServers()
    with installed(model, servers):
        # ---- spec section 4, as printed ----
        from vidbyte import BrowserAgent, BrowserAgentSettings, BrowserServerSettings
        from vidbyte.tools.mcp import FirecrawlMCP, PlaywrightMCP

        agent = BrowserAgent(
            BrowserAgentSettings(
                name="vc-scout",
                system_prompt="You find seed-stage accelerator programs and record where to apply.",
                provider="openai",
                model_name="gpt-5.4-mini",
                action_servers=(BrowserServerSettings(PlaywrightMCP),),
                search_servers=(BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": "fc-your-key"}),),
                done_when=("Twenty programs are listed, each with its application URL and deadline.",),
                on_event=lambda event: print(event.kind.value, event.detail),
            )
        )
        reply = agent.run("Find twenty seed-stage accelerator programs that accept applications this quarter.")
        print(reply.content)
        print(agent.response.stop_reason, len(agent.response.episodes))
        print("\n".join(agent.response.goal.progress))
        # ---- end of snippet ----
    model.assert_complete()
    lines = capsys.readouterr().out.splitlines()
    assert lines[-3:] == [FINAL_ANSWER, "final_response 1", PROGRESS_LINE]
    event_lines = lines[:-3]
    kinds = [line.split(" ", 1)[0] for line in event_lines]
    assert kinds and set(kinds) <= EVENT_KINDS, f"a printed line is not an event line: {event_lines}"
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    assert kinds.count("run_started") == 1 and kinds.count("run_finished") == 1 and "run_stopped" not in kinds
    for kind in ("goal_set", "episode_started", "episode_finished", "goal_rechecked"):
        assert kind in kinds, f"no {kind} line was printed: {kinds}"
    assert kinds.index("episode_started") < kinds.index("episode_finished")
    # The worker really drove the ACTION server, and the snippet's key reached only the SEARCH server.
    assert servers.calls_to(ACTION_COMMAND) == [("browser_navigate", {"url": "https://seedcamp.com/apply"})]
    (search,) = servers.instances_for(SEARCH_COMMAND)
    assert search.env.get("FIRECRAWL_API_KEY") == "fc-your-key"
    (action,) = servers.instances_for(ACTION_COMMAND)
    assert "fc-your-key" not in action.env.values()


@pytest.mark.asyncio
async def test_every_episode_of_one_run_uses_the_same_action_server_process() -> None:
    """AC-6, INV-7, FR-4: one arun with two episodes builds exactly one transport per configured server, and both workers' browser calls reach the same ACTION instance."""
    agent = build_agent()
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), tool_call("run_episode", {"task": "Click Apply on the same page.", "done_when": "The form is open."}), reply(FINAL_ANSWER)],
            worker(1): [tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), card("done", "Opened the page.")],
            worker(2): [tool_call("browser_click", {"element": "Apply"}), card("done", "The form is open.")],
            RECHECK: [verdict("done", "Nothing is missing.")],
        }
    )
    servers = FakeBrowserServers()
    with installed(model, servers):
        try:
            await agent.arun(TASK)
        finally:
            await agent.close_mcp_servers()
    model.assert_complete()
    assert [len(servers.instances_for(command)) for command in (ACTION_COMMAND, SEARCH_COMMAND, FETCH_COMMAND)] == [1, 1, 1]
    assert len(servers.instances) == 3
    (action,) = servers.instances_for(ACTION_COMMAND)
    assert action.calls == [("browser_navigate", {"url": "https://seedcamp.com/apply"}), ("browser_click", {"element": "Apply"})]


def test_sync_runs_get_their_own_servers_and_async_runs_on_one_loop_share_them() -> None:
    """AC-23, EC-22, FR-4: each sync run starts and closes its own server processes; two aruns in one event loop share one set."""
    agent = build_agent()
    model = _episode_script(runs=4)
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
        first = list(servers.instances)
        assert len(first) == 3 and all(transport.closed for transport in first), "a sync run left a server running"
        agent.run(TASK)
        second = servers.instances[3:]
        assert len(second) == 3 and all(transport.closed for transport in second)
        assert not {id(t) for t in first} & {id(t) for t in second}

        async def two_runs() -> list[bool]:
            await agent.arun(TASK)
            await agent.arun(TASK)
            still_open = [not transport.closed for transport in servers.instances[6:]]
            await agent.close_mcp_servers()
            return still_open

        still_open = asyncio.run(two_runs())
    model.assert_complete()
    shared = servers.instances[6:]
    assert len(shared) == 3, f"two aruns on one loop built {len(shared)} transports, not one per server"
    assert still_open == [True, True, True], "the servers were closed between the two aruns"
    assert all(transport.closed for transport in shared)
    (action,) = [transport for transport in shared if transport.command == ACTION_COMMAND]
    assert len(action.calls) == 2, "both aruns' workers must act through the one shared ACTION process"


def test_building_the_runtime_has_no_side_effects() -> None:
    """INV-23: BaseAgent._runtime() builds a BrowserAgentRuntime without starting a process, emitting an event, calling a model, or touching the response."""
    from vidbyte.agents.browser import BrowserAgentRuntime

    model = ScriptedModel({})
    servers = FakeBrowserServers()
    log = EventLog(model)
    agent = build_agent(on_event=log)
    before = copy.deepcopy(agent.response)
    with installed(model, servers):
        runtimes = [agent._runtime(), agent._runtime()]
    assert all(isinstance(runtime, BrowserAgentRuntime) for runtime in runtimes)
    assert servers.instances == [] and model.calls == [] and log.events == []
    assert agent.response == before


def test_each_run_starts_clean_and_never_changes_an_earlier_record() -> None:
    """INV-24: a second run's first orchestrator call has no history and a card for the new task only, gets a fresh response object, and the first run's record is unchanged."""
    second_task = "List three accelerator programs in Berlin that accept applications this quarter."
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", EPISODE), tool_call("patch_goal", {"section": "progress", "text": PROGRESS_LINE}), reply(FINAL_ANSWER), reply("No Berlin program was checked yet.")],
            worker(1): [card("done", "Opened the page.")],
            RECHECK: [verdict("done", "Nothing is missing."), verdict("done", "Nothing is missing.")],
        }
    )
    agent = build_agent()
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
        first = agent.response
        snapshot = copy.deepcopy(first)
        agent.run(second_task)
    model.assert_complete()
    second_first_call = model.calls_by(NAME)[3]
    assert second_first_call.prompt == second_task
    assert second_first_call.messages == [], "the second run inherited the first run's conversation"
    section = card_section(second_first_call.system)
    assert second_task in section and TASK not in section and PROGRESS_LINE not in section
    assert agent.response is not first
    assert first == snapshot, "a record returned for an earlier run was changed"
    assert (agent.response.input, agent.response.episodes, agent.response.goal.progress) == (second_task, [], ())
