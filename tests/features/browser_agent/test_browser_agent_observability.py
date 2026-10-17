"""FILE: tests/features/browser_agent/test_browser_agent_observability.py

PURPOSE: Proves what a developer can watch and trust: events arrive in order with consecutive sequence numbers, a sink's Exception is recorded and never breaks the run while a BaseException propagates, every run ends with exactly one run_finished or run_stopped, event details are one short line, usage is one rollup that counts every agent and fails closed on an unpriced call, keys never reach tools, events, the response, or a model, and the run-start checks (reserved MCP tool names, an ACTION role with no tools, duplicate tool names across servers) refuse before any model call, while each server starts under its role name with only its own env and timeout.
ROLE IN CODEBASE: Observability and boundary layer of tests/features/browser_agent/ (spec AC-3, AC-18, AC-19, AC-21 run-start half, AC-30; INV-3, INV-20, INV-21, INV-25, INV-28; EC-6, EC-7, EC-8, EC-20, EC-33; D-7, D-18, D-19; T-1, T-3, T-5; FR-17, FR-18, FR-19). Exercises vidbyte/agents/browser/events.py, usage.py, response.py, tools.py and the runtime's run-start checks through BrowserAgent.run / arun.
ARCHITECTURE NOTE: EventLog is the developer's on_event sink; it records every event and the orchestrator call count at the moment it arrived. Usage is read from the reply metadata, agent.response and agent.get_usage() and compared as UsageRollup values; the tracker and ledger are real.
FUNCTION INVENTORY: test_a_raising_sink_is_recorded_and_never_breaks_the_run (AC-18, INV-20, EC-20); test_a_base_exception_from_the_sink_propagates (INV-20, D-18); test_a_max_iterations_stop_ends_with_run_stopped (EC-33, INV-20); test_event_details_are_one_line_within_their_cap (section 8.5 BrowserEvent, section 12.3 row 11); test_usage_is_one_rollup_that_counts_every_agent (AC-19, INV-21, FR-18); test_an_unpriced_call_raises_usage_accounting_error (AC-19, INV-21, D-19, INV-20 / S4 R-4); test_keys_never_reach_tools_events_the_response_or_any_model_call (AC-3, INV-3, T-1, T-3, T-5); test_attached_tools_carry_no_server_key (AC-3, INV-3, S4 R-20); test_servers_start_under_their_role_names_with_their_own_env_and_timeout (D-7, FR-4, T-5, EC-28); test_a_reserved_name_on_an_mcp_tool_is_refused_before_any_model_call (AC-21, EC-7, INV-25); test_an_action_server_without_tools_is_refused_before_any_model_call (AC-30, EC-8); test_duplicate_tool_names_across_servers_fail_the_attach_all_or_nothing (EC-6, INV-28).
COMMON MODIFICATION PATTERNS: Add a usage scenario as one more parametrize row with its per-agent usage and expected totals. Take caps from vidbyte.lib.constants.browser.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not put a real key anywhere; FIRECRAWL_KEY and MODEL_KEY are fakes. 3. Do not catch the run's exception broadly and pass; find the documented error type in the raised chain.
KNOWN EDGE CASES: A run-start refusal may reach the caller wrapped by BaseAgent's own error handling, so the checks walk the cause chain with find_error. Server indexes in role names are not fixed to 0- or 1-based by the spec, so names are matched by shape.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 6.3, 8.1, 10 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_observability.py -q
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    ACTION_COMMAND,
    ACTION_TOOLS,
    DONE_WHEN_AGENT,
    FETCH_COMMAND,
    FIRECRAWL_KEY,
    MODEL_KEY,
    NAME,
    RECHECK,
    SEARCH_COMMAND,
    TASK,
    EventLog,
    FakeBrowserServers,
    ScriptedModel,
    build_agent,
    card,
    criteria,
    error_text,
    fetch_server,
    find_error,
    forever,
    installed,
    reply,
    search_server,
    seen_text,
    text_result,
    tool_call,
    verdict,
    worker,
)
from vidbyte.lib.errors import ConfigurationError, McpAttachmentError, ToolRegistrationError, UsageAccountingError

FINAL = "FINAL-ANSWER: Seedcamp closes 30 November."
EPISODE = {"task": "Open https://seedcamp.com/apply and read the application deadline.", "done_when": "The deadline is read from the page."}
DONE = verdict("done", "Nothing is missing.")
SERVER_NAME = re.compile(r"^browser-(action|search|fetch)-\d+$")


class SinkStop(BaseException):
    """A BaseException a sink raises; it must reach the caller like a cancellation would."""


def _one_episode(**usage: Mapping[str, int]) -> dict[str, list[Any]]:
    return {
        NAME: [tool_call("run_episode", EPISODE, usage=usage.get("orchestrator")), reply(FINAL, usage=usage.get("orchestrator"))],
        worker(1): [tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}, usage=usage.get("worker")), card("done", "Seedcamp closes 30 November.", usage=usage.get("worker"))],
        RECHECK: [verdict("done", "Nothing is missing.", usage=usage.get("recheck"))],
    }


# ---------------------------------------------------------------- events (INV-20)


def test_a_raising_sink_is_recorded_and_never_breaks_the_run() -> None:
    """AC-18, INV-20, EC-20: a sink that raises ValueError on episode_started does not stop the run; event_errors is ["ValueError"] and every event reached the sink in order with sequence numbers 1..n, from run_started to run_finished."""
    log = EventLog(raise_on="episode_started", error=ValueError)
    agent = build_agent(on_event=log)
    model = ScriptedModel(_one_episode())
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    assert result.content == FINAL
    assert agent.response.event_errors == ["ValueError"]
    assert [event.sequence for event in log.events] == list(range(1, len(log.events) + 1))
    kinds = log.kinds()
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    assert kinds.count("run_started") == 1 and kinds.count("run_finished") == 1 and "run_stopped" not in kinds
    assert kinds.index("goal_set") < kinds.index("episode_started") < kinds.index("episode_finished") < kinds.index("goal_rechecked")
    assert [event.episode for event in log.of("episode_started")] == [1]


def test_a_base_exception_from_the_sink_propagates() -> None:
    """INV-20, D-18: a BaseException raised by the sink is not swallowed; it reaches the caller, and the run's servers are still closed."""
    log = EventLog(raise_on="episode_started", error=SinkStop)
    agent = build_agent(on_event=log)
    model = ScriptedModel(_one_episode())
    servers = FakeBrowserServers()
    with installed(model, servers), pytest.raises(SinkStop):
        agent.run(TASK)
    assert worker(1) not in model.agents_called(), "the episode ran after its sink raised a BaseException"
    assert servers.instances and all(transport.closed for transport in servers.instances)


def test_a_max_iterations_stop_ends_with_run_stopped() -> None:
    """EC-33, INV-20: when the orchestrator loop reaches max_iterations the run returns with that stop reason and its last event is run_stopped."""
    from vidbyte.agents.settings import AgentLoopSettings

    log = EventLog()
    agent = build_agent(loop=AgentLoopSettings(max_iterations=2), on_event=log)
    model = ScriptedModel({NAME: [forever(tool_call("firecrawl_search", {"query": "seed accelerators"}))]})
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    assert len(model.calls_by(NAME)) == 2
    assert agent.response.stop_reason == "max_iterations"
    kinds = log.kinds()
    assert kinds[-1] == "run_stopped" and "run_finished" not in kinds
    assert [event.sequence for event in log.events] == list(range(1, len(log.events) + 1))


def test_event_details_are_one_line_within_their_cap() -> None:
    """Section 8.5 BrowserEvent, section 12.3 row 11: even for a long, multi-line episode task, every event detail is one line of at most BROWSER_EVENT_DETAIL_MAX_CHARS."""
    from vidbyte.lib.constants.browser import BROWSER_EVENT_DETAIL_MAX_CHARS

    long_task = "Open each of these pages:\n" + "\n".join(f"https://directory.example/page-{index}" for index in range(80))
    log = EventLog()
    agent = build_agent(on_event=log)
    model = ScriptedModel({NAME: [tool_call("run_episode", {"task": long_task, "done_when": "Every page\nis open."}), reply(FINAL)], worker(1): [card("done", "Opened every page.\n" * 40)], RECHECK: [DONE]})
    with installed(model, FakeBrowserServers()):
        agent.run(long_task)
    model.assert_complete()
    assert log.events
    for event in log.events:
        assert "\n" not in event.detail and "\r" not in event.detail, f"{event.kind} detail spans lines"
        assert len(event.detail) <= BROWSER_EVENT_DETAIL_MAX_CHARS, f"{event.kind} detail has {len(event.detail)} characters"


# ---------------------------------------------------------------- usage (INV-21)


@pytest.mark.parametrize(
    ("done_when", "expected"),
    (
        pytest.param(True, (5, 2_430, 243), id="done-when-given"),
        pytest.param(False, (6, 2_480, 248), id="done-when-derived"),
    ),
)
def test_usage_is_one_rollup_that_counts_every_agent(done_when: bool, expected: tuple[int, int, int]) -> None:
    """AC-19, INV-21, FR-18: the reply's usage_rollup, agent.response.usage and agent.get_usage() are the same rollup, and it counts the orchestrator's, the worker's, the recheck's and the done-when agent's calls."""
    usage = {
        "orchestrator": {"input_tokens": 1_000, "output_tokens": 100},
        "worker": {"input_tokens": 200, "output_tokens": 20},
        "recheck": {"input_tokens": 30, "output_tokens": 3},
    }
    scripts = _one_episode(**usage)
    fields: dict[str, Any] = {}
    if not done_when:
        scripts[DONE_WHEN_AGENT] = [criteria("Twenty programs are listed.", usage={"input_tokens": 50, "output_tokens": 5})]
        fields["done_when"] = ()
    agent = build_agent(**fields)
    model = ScriptedModel(scripts)
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    rollup = result.metadata["usage_rollup"]
    assert rollup == agent.response.usage == agent.get_usage()
    assert (rollup.model_call_count, rollup.input_tokens, rollup.output_tokens) == expected


def test_an_unpriced_call_raises_usage_accounting_error() -> None:
    """AC-19, INV-21, D-19, INV-20 (S4 R-4): a run in which one model call reports a model with no price raises UsageAccountingError naming it, instead of returning, and its last event is run_stopped, never run_finished."""
    log = EventLog()
    agent = build_agent(on_event=log)
    model = ScriptedModel({NAME: [reply(FINAL, model="not-in-the-pricebook")], RECHECK: [DONE]})
    with installed(model, FakeBrowserServers()), pytest.raises(UsageAccountingError) as raised:
        agent.run(TASK)
    assert "not-in-the-pricebook" in error_text(raised.value)
    # A run that raises instead of returning has not finished.
    assert log.kinds()[-1] == "run_stopped", log.kinds()
    assert "run_finished" not in log.kinds()


# ---------------------------------------------------------------- keys (INV-3) and servers (D-7)


def test_keys_never_reach_tools_events_the_response_or_any_model_call() -> None:
    """AC-3, INV-3, T-1, T-3, T-5: with a server key in env and a model key in api_keys, neither appears in repr(agent.tools), any event, agent.response, or anything any model call carried; the server key reaches only its own server."""
    log = EventLog()
    agent = build_agent(api_keys=[MODEL_KEY], on_event=log)
    model = ScriptedModel(
        {
            NAME: [tool_call("firecrawl_search", {"query": "seed accelerators"}), tool_call("run_episode", EPISODE), reply(FINAL)],
            worker(1): [tool_call("browser_navigate", {"url": "https://seedcamp.com/apply"}), card("done", "Seedcamp closes 30 November.")],
            RECHECK: [DONE],
        }
    )
    servers = FakeBrowserServers()
    with installed(model, servers):
        agent.run(TASK)
    model.assert_complete()
    exposed = [repr(agent.tools), repr(agent.response), str(agent.response), *(repr(event) for event in log.events), *(seen_text(call) for call in model.calls)]
    for text in exposed:
        assert FIRECRAWL_KEY not in text and MODEL_KEY not in text
    (search,) = servers.instances_for(SEARCH_COMMAND)
    assert search.env.get("FIRECRAWL_API_KEY") == FIRECRAWL_KEY, "positive control: the key must reach its own server"
    for command in (ACTION_COMMAND, FETCH_COMMAND):
        (other,) = servers.instances_for(command)
        assert FIRECRAWL_KEY not in other.env.values(), f"the SEARCH key reached {command}"


@pytest.mark.asyncio
async def test_attached_tools_carry_no_server_key() -> None:
    """AC-3, INV-3, S4 R-20: while the servers are still attached, no tool on the agent, bridged ones included, carries the server key in its repr or its spec (name, description, parameters, schema, metadata)."""
    agent = build_agent()
    model = ScriptedModel({NAME: [reply(FINAL)], RECHECK: [DONE]})
    servers = FakeBrowserServers()
    with installed(model, servers):
        try:
            await agent.arun(TASK)
            # Read the tools before closing: a closed server's bridged
            # tools leave the catalog, which makes the check vacuous.
            attached = list(agent.tools)
            names = {tool.spec().name for tool in attached}
            texts = [repr(tool) + repr(tool.spec()) for tool in attached]
        finally:
            await agent.close_mcp_servers()
    model.assert_complete()
    # Positive controls: the bridged tools were read, and the key
    # really sits in the SEARCH server's env.
    assert {"firecrawl_search", "fetch_markdown", *ACTION_TOOLS} <= names, names
    (search,) = servers.instances_for(SEARCH_COMMAND)
    assert search.env.get("FIRECRAWL_API_KEY") == FIRECRAWL_KEY
    for text in texts:
        assert FIRECRAWL_KEY not in text


@pytest.mark.asyncio
async def test_servers_start_under_their_role_names_with_their_own_env_and_timeout() -> None:
    """D-7, FR-4, T-5, EC-28: each configured server starts once under a browser-<role>-<n> name, with only its own env and its own request timeout."""
    from vidbyte.lib.constants.browser import BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS

    agent = build_agent(search_servers=(search_server(timeout=45.0),), fetch_servers=(fetch_server(env={"FETCH_REGION": "eu"}),))
    model = ScriptedModel({NAME: [reply(FINAL)], RECHECK: [DONE]})
    servers = FakeBrowserServers()
    with installed(model, servers):
        try:
            await agent.arun(TASK)
            names = sorted(handle.name for handle in agent.mcp_servers())
        finally:
            await agent.close_mcp_servers()
    model.assert_complete()
    assert len(names) == 3 and all(SERVER_NAME.match(name) for name in names), names
    assert sorted(SERVER_NAME.match(name).group(1) for name in names) == ["action", "fetch", "search"]
    (action,), (search,), (fetch,) = (servers.instances_for(command) for command in (ACTION_COMMAND, SEARCH_COMMAND, FETCH_COMMAND))
    assert search.request_timeout == 45.0
    assert action.request_timeout == fetch.request_timeout == BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS
    assert fetch.env == {"FETCH_REGION": "eu"}
    assert "FETCH_REGION" not in action.env and "FETCH_REGION" not in search.env
    assert "FIRECRAWL_API_KEY" not in action.env and "FIRECRAWL_API_KEY" not in fetch.env


# ---------------------------------------------------------------- run-start refusals


def test_a_reserved_name_on_an_mcp_tool_is_refused_before_any_model_call() -> None:
    """AC-21, EC-7, INV-25: a FETCH server exposing a tool named patch_goal makes the run raise ConfigurationError naming the tool and the reserved names before any model call."""
    servers = FakeBrowserServers()
    servers.add(FETCH_COMMAND, "patch_goal", lambda args: text_result("shadowed"))
    model = ScriptedModel({})
    agent = build_agent()
    with installed(model, servers), pytest.raises(Exception) as raised:
        agent.run(TASK)
    refusal = find_error(raised.value, ConfigurationError)
    assert refusal is not None, f"no ConfigurationError in {raised.value!r}"
    text = error_text(refusal)
    assert "patch_goal" in text and "run_episode" in text, text
    assert model.calls == [], "a model was called before the reserved-name check"


def test_an_action_server_without_tools_is_refused_before_any_model_call() -> None:
    """AC-30, EC-8: an ACTION server whose bridge exposes no tools makes the run raise ConfigurationError naming the ACTION role before any model call."""
    servers = FakeBrowserServers()
    servers.serve(ACTION_COMMAND, {})
    model = ScriptedModel({})
    agent = build_agent()
    with installed(model, servers), pytest.raises(Exception) as raised:
        agent.run(TASK)
    refusal = find_error(raised.value, ConfigurationError)
    assert refusal is not None, f"no ConfigurationError in {raised.value!r}"
    assert re.search("action", error_text(refusal), re.IGNORECASE), error_text(refusal)
    assert model.calls == []


def test_duplicate_tool_names_across_servers_fail_the_attach_all_or_nothing() -> None:
    """EC-6, INV-28: two servers exposing the same tool name make the run fail naming the tool, with every started server closed and none left attached."""
    servers = FakeBrowserServers()
    servers.add(SEARCH_COMMAND, "fetch_markdown", lambda args: text_result("duplicate"))
    model = ScriptedModel({})
    agent = build_agent()
    with installed(model, servers), pytest.raises(Exception) as raised:
        agent.run(TASK)
    failure = find_error(raised.value, McpAttachmentError) or find_error(raised.value, ToolRegistrationError)
    assert failure is not None, f"neither McpAttachmentError nor ToolRegistrationError in {raised.value!r}"
    assert "fetch_markdown" in error_text(failure)
    assert all(transport.closed for transport in servers.instances), "a server was left running"
    assert agent.mcp_servers() == ()
    assert model.calls == []
