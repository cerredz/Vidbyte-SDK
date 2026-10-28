"""FILE: tests/features/agent_swarm/test_agent_swarm_settings.py

PURPOSE: Pins the AgentSwarmSettings record after its move to vidbyte/lib/dataclasses: one class under every import path, members without a prompt of their own, the web-search provider and key rules, the generous limits at and just past each bound, the web-search key's secrecy, the per-provider search tool table, and the lib layering rule.
ROLE IN CODEBASE: Settings layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-19, AC-20, AC-21; INV-18, INV-19; FR-1; D-1, D-17, D-18; section 10; section 12.3 rows 4, 5 and 28).
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError or TypeError and the rest of the pack still collects. The one swarm run here drives the real Tavily tool against FakeTavily, the recording fake of the HTTP call, so the key's path from the settings to the client is observed, never assumed.
FUNCTION INVENTORY: test_agent_swarm_settings_is_one_lib_class_under_every_import_path; test_a_member_has_no_prompt_of_its_own; test_web_search_settings_without_a_key_with_a_dangling_key_or_an_unknown_provider_are_refused; test_web_search_accepts_every_provider_by_value_or_member; test_limits_refuse_just_past_each_bound_and_accept_each_bound; test_web_search_key_never_appears_in_reprs_events_model_calls_or_errors; test_each_web_search_provider_builds_its_own_tool_with_the_key_in_its_client; test_the_settings_module_imports_no_higher_layer; test_web_search_settings_and_their_swarm_create_no_folder_before_arun.
COMMON MODIFICATION PATTERNS: A new provider adds one row to SEARCH_TABLE. A new bound adds one refused and one accepted case to the limits test.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not use a real key; FAKE_TAVILY_KEY and FAKE_OPENAI_KEY are fakes of the right shape. 3. Do not let the search tool reach the network; install FakeTavily around every run that selects Tavily.
KNOWN EDGE CASES: AC-19 lets the dangling-key refusal name either web_search or web_search_api_key, so that case accepts both fields; the other two name the field that is wrong. Building 500 members validates 500 model names, which takes well under a second.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1, 6.2, 8.5, 9.3 and 10.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_settings.py -q
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    FAKE_OPENAI_KEY,
    FAKE_TAVILY_KEY,
    MODEL,
    TAVILY_TOOL,
    EventLog,
    FakeTavily,
    ScriptedSwarm,
    assert_event_invariants,
    build_settings,
    build_swarm,
    error_text,
    member,
    of_kind,
    reply,
    run_swarm,
    search,
    seen_text,
    workplace_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
NAMES = ("builder", "tester")
SECRET = "SwarmFakeKey"
# Row 28: each selectable provider, its tool class, its client class, and the tool's model-facing name.
SEARCH_TABLE = (
    ("brave", "BraveSearchTool", "BraveClient", "brave_search"),
    ("browserbase", "BrowserbaseSearchTool", "BrowserbaseClient", "browserbase_search"),
    ("exa", "ExaSearchTool", "ExaClient", "exa_search"),
    ("parallel", "ParallelSearchTool", "ParallelClient", "parallel_search"),
    ("tavily", "TavilySearchTool", "TavilyClient", "tavily_search"),
)
HIGHER_LAYERS = ("vidbyte.agents", "vidbyte.tools", "vidbyte.middleware", "vidbyte.prompts")


def _refusal(tmp_path: Path, **fields: Any) -> Any:
    from vidbyte.lib.errors import ConfigurationError

    with pytest.raises(ConfigurationError) as refused:
        build_settings(tmp_path, NAMES, **fields)
    return refused.value


def test_agent_swarm_settings_is_one_lib_class_under_every_import_path() -> None:
    """AC-21, D-1: AgentSwarmSettings from vidbyte, vidbyte.agents, vidbyte.agents.agent_swarm and vidbyte.lib.dataclasses.agent_swarm is one class defined in the lib module; AgentSwarmWebSearch comes from vidbyte and vidbyte.lib.enums; AgentSwarmMember has name, provider and model_name only."""
    import vidbyte
    import vidbyte.agents
    import vidbyte.agents.agent_swarm
    import vidbyte.lib.dataclasses.agent_swarm as records
    import vidbyte.lib.enums

    classes = {vidbyte.AgentSwarmSettings, vidbyte.agents.AgentSwarmSettings, vidbyte.agents.agent_swarm.AgentSwarmSettings, records.AgentSwarmSettings}
    assert len(classes) == 1, classes
    assert records.AgentSwarmSettings.__module__ == "vidbyte.lib.dataclasses.agent_swarm"
    assert "AgentSwarmSettings" in records.__all__
    assert vidbyte.AgentSwarmWebSearch is vidbyte.lib.enums.AgentSwarmWebSearch
    assert [item.name for item in dataclasses.fields(vidbyte.AgentSwarmMember)] == ["name", "provider", "model_name"]
    # Row 5: the old home of the settings is deleted.
    assert not (REPO_ROOT / "vidbyte" / "agents" / "agent_swarm" / "settings.py").exists()


def test_a_member_has_no_prompt_of_its_own() -> None:
    """FR-1 (reverses the r5 blank-system-prompt refusal): AgentSwarmMember takes name, provider and model_name, in that order, and a system_prompt argument is not a field at all."""
    from vidbyte import AgentSwarmMember
    from vidbyte.lib.enums import ModelProvider

    built = AgentSwarmMember("ada", "openai", MODEL)
    assert (built.name, built.provider, built.model_name) == ("ada", ModelProvider.OPENAI, MODEL)
    with pytest.raises(TypeError):
        AgentSwarmMember(name="ada", system_prompt="You write the code.", provider="openai", model_name=MODEL)


@pytest.mark.parametrize(
    ("fields", "accepted"),
    [
        pytest.param({"web_search": "tavily"}, {"AgentSwarmSettings.web_search_api_key"}, id="tavily-without-a-key"),
        pytest.param({"web_search_api_key": FAKE_TAVILY_KEY}, {"AgentSwarmSettings.web_search", "AgentSwarmSettings.web_search_api_key"}, id="a-key-without-web-search"),
        pytest.param({"web_search": "linkup", "web_search_api_key": FAKE_TAVILY_KEY}, {"AgentSwarmSettings.web_search"}, id="linkup-has-no-client"),
    ],
)
def test_web_search_settings_without_a_key_with_a_dangling_key_or_an_unknown_provider_are_refused(tmp_path: Path, fields: dict[str, Any], accepted: set[str]) -> None:
    """AC-19, INV-18, D-18: each case is a ConfigurationError naming the web-search field in the message and in details["field"], never quoting the key, and creating nothing."""
    refused = _refusal(tmp_path, **fields)
    assert refused.details["field"] in accepted, error_text(refused)
    assert refused.details["field"] in str(refused)
    assert SECRET not in error_text(refused) and SECRET not in repr(refused)
    assert list(tmp_path.iterdir()) == []


def test_web_search_accepts_every_provider_by_value_or_member(tmp_path: Path) -> None:
    """D-18, section 9.1: every AgentSwarmWebSearch member is accepted as itself or as its value string and stored as the member, with the key kept out of the repr."""
    from vidbyte import AgentSwarmWebSearch

    for provider in AgentSwarmWebSearch:
        for given in (provider, provider.value):
            settings = build_settings(tmp_path, NAMES, web_search=given, web_search_api_key=FAKE_TAVILY_KEY)
            assert settings.web_search is provider and settings.web_search_api_key == FAKE_TAVILY_KEY
            assert SECRET not in repr(settings) and SECRET not in str(settings)
    assert build_settings(tmp_path, NAMES).web_search is None
    assert list(tmp_path.iterdir()) == []


def test_limits_refuse_just_past_each_bound_and_accept_each_bound(tmp_path: Path) -> None:
    """AC-20: 501 members, max_turns=2 for three members, max_tokens=0 and a timeout past thirty days are refused naming their fields; 500 members, max_turns=3, max_tokens=1 and timeout_seconds=2_592_000.0 are accepted."""
    three = tuple(member(name) for name in ("ada", "ben", "cleo"))
    refused = {
        "AgentSwarmSettings.agents": {"agents": tuple(member(f"a{index}") for index in range(501))},
        "AgentSwarmSettings.max_turns": {"agents": three, "max_turns": 2},
        "AgentSwarmSettings.max_tokens": {"max_tokens": 0},
        "AgentSwarmSettings.timeout_seconds": {"timeout_seconds": 2_592_001.0},
    }
    for field, fields in refused.items():
        error = _refusal(tmp_path, **fields)
        assert str(error.details["field"]).startswith(field) and field in str(error), error_text(error)
    assert len(build_settings(tmp_path, agents=tuple(member(f"a{index}") for index in range(500))).agents) == 500
    assert build_settings(tmp_path, agents=three, max_turns=3).max_turns == 3
    assert build_settings(tmp_path, NAMES, max_tokens=1).max_tokens == 1
    assert build_settings(tmp_path, NAMES, timeout_seconds=2_592_000.0).timeout_seconds == 2_592_000.0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_web_search_key_never_appears_in_reprs_events_model_calls_or_errors(tmp_path: Path) -> None:
    """Section 10, D-18: the web-search key reaches the search client and nothing else: not the settings repr, an event, a model call, the result, or a refusal."""
    from vidbyte import AgentSwarm, AgentSwarmStopReason

    log = EventLog()
    settings = build_settings(tmp_path, NAMES, api_keys=[FAKE_OPENAI_KEY], web_search="tavily", web_search_api_key=FAKE_TAVILY_KEY, on_event=log.callback)
    assert SECRET not in repr(settings) and SECRET not in str(settings)
    fake = FakeTavily()
    scripted = ScriptedSwarm({"builder": [search("celsius to fahrenheit formula"), reply("Builder done.")], "tester": [reply("Tester done.")]})
    with scripted.install(), fake.install():
        result = await run_swarm(AgentSwarm(settings))

    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert fake.queries == ["celsius to fahrenheit formula"] and fake.keys == [FAKE_TAVILY_KEY]
    assert [event.tool_name for event in of_kind(result.events, "tool_called", "builder")] == [TAVILY_TOOL]
    assert all(SECRET not in repr(event) for event in result.events) and all(SECRET not in repr(event) for event in log.received)
    assert all(SECRET not in seen_text(call) for call in scripted.calls)
    assert SECRET not in repr(result)
    assert_event_invariants(result, NAMES, max_turns=settings.max_turns, log=log)
    refused = _refusal(tmp_path, web_search="linkup", web_search_api_key=FAKE_TAVILY_KEY, max_turns=1)
    assert SECRET not in error_text(refused) and SECRET not in repr(refused)


def test_each_web_search_provider_builds_its_own_tool_with_the_key_in_its_client() -> None:
    """Row 28, D-18: AgentSwarmTools.search_tool_for builds, for each provider, its own search tool around its own client holding the key, and every provider gets a fresh tool."""
    from vidbyte import AgentSwarmWebSearch
    from vidbyte.tools.builtins import operations
    from vidbyte.tools.toolsets import AgentSwarmTools

    for value, tool_class, client_class, tool_name in SEARCH_TABLE:
        tool = AgentSwarmTools.search_tool_for(AgentSwarmWebSearch(value), FAKE_TAVILY_KEY)
        assert type(tool) is getattr(operations, tool_class), f"{value} built {type(tool).__name__}"
        assert tool.name == tool_name
        client = getattr(tool, "_client", None)
        assert type(client) is getattr(operations, client_class), f"{value}'s tool holds {type(client).__name__}"
        assert getattr(client, "_api_key", None) == FAKE_TAVILY_KEY
        assert tool is not AgentSwarmTools.search_tool_for(AgentSwarmWebSearch(value), FAKE_TAVILY_KEY)
    assert {row[0] for row in SEARCH_TABLE} == {provider.value for provider in AgentSwarmWebSearch}


def test_the_settings_module_imports_no_higher_layer() -> None:
    """INV-19, A006: the lib records module, where AgentSwarmSettings now lives, imports nothing from vidbyte.agents, vidbyte.tools, vidbyte.middleware or vidbyte.prompts, not even inside a function."""
    path = REPO_ROOT / "vidbyte" / "lib" / "dataclasses" / "agent_swarm.py"
    imported: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "class AgentSwarmSettings" in path.read_text(encoding="utf-8")
    offending = [name for name in imported if name.startswith(HIGHER_LAYERS)]
    assert offending == [], f"{path.name} imports a higher layer: {offending}"


def test_web_search_settings_and_their_swarm_create_no_folder_before_arun(tmp_path: Path) -> None:
    """INV-18, section 9.3: valid web-search settings and an AgentSwarm over them create no folder before arun."""
    swarm = build_swarm(tmp_path, NAMES, web_search="tavily", web_search_api_key=FAKE_TAVILY_KEY)
    assert swarm.settings.web_search is not None and not workplace_path(tmp_path).exists()
