"""FILE: tests/features/browser_agent/test_browser_agent_contract.py

PURPOSE: Pins BrowserAgent's static contract: public import paths and the regenerated public-API contract, enum values and the two added members, the fixed string constants, the 19-leaf prompt family with its placeholders and no digits, the runtime registry entry and its refusal outside BrowserAgent, the session opt-out, the exact methods the runtime overrides, the two run-bound tools' schemas and descriptions, server naming by role, and the complexity budget.
ROLE IN CODEBASE: Contract layer of tests/features/browser_agent/ (spec AC-17 static half, AC-20, AC-24, AC-25, AC-28; INV-22, INV-26, INV-27; NFR-1, NFR-3, NFR-5; FR-20, FR-22; sections 8.5, 9.1 and 12.3). Exercises vidbyte/agents/browser/, vidbyte/lib/enums/browser.py, vidbyte/lib/constants/browser.py, vidbyte/lib/registries/runtimes.py, vidbyte/agents/base.py's _LINEAR_LOOP_RUNTIMES and the browser_agent prompt family.
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError and the rest of the pack still collects. Tool offers are read from what the scripted runner receives on the orchestrator's first call, not from the agent's internals.
FUNCTION INVENTORY: test_public_names_import_from_every_documented_path (AC-24); test_enum_values_and_added_members_are_the_documented_strings (section 8.5, D-2, D-28); test_fixed_string_constants_are_the_documented_values (section 9.1); test_prompt_family_has_exactly_the_nineteen_leaves_with_their_placeholders_and_no_digits (AC-25, INV-26, NFR-5); test_runtime_type_resolves_and_refuses_outside_its_agent (AC-20, INV-22, INV-27, FR-20); test_session_refuses_the_agent (AC-20, D-21); test_runtime_overrides_exactly_the_five_documented_methods (NFR-3); test_run_episode_and_patch_goal_schemas_follow_the_documented_contract (section 8.5 tool contracts, AC-17 static half, INV-19); test_run_episode_is_internal_so_it_does_not_spend_the_orchestrators_tool_budget (section 8.5 "internal"); test_named_servers_names_every_server_by_role_in_role_order (D-7, section 12.3 row 10); test_new_package_stays_inside_the_complexity_budget (AC-28, NFR-1, NFR-5, section 12.4).
COMMON MODIFICATION PATTERNS: When the spec adds a prompt leaf, add it to EXPECTED_LEAVES with its placeholders. When the spec adds a module, raise MAX_MODULES only if section 8.4 changes.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see browser_agent_fixtures.py). 2. Do not compare tool descriptions to hand-written text; descriptions come from the prompt catalog. 3. Do not loosen the exact override set or the exact leaf set to subset checks.
KNOWN EDGE CASES: The internal isDone tool is added to every BaseAgent's catalog by the loop, so the orchestrator's offered set includes it (INV-5 lists it). Server indexes in role names are not fixed to 0- or 1-based by the spec, so the naming test checks the template shape and consecutive numbering within a role.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 8.4, 8.5, 9.1 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_contract.py -q
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import re
import string
from pathlib import Path

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    DONE_WHEN,
    NAME,
    RECHECK,
    TASK,
    FakeBrowserServers,
    ScriptedModel,
    action_server,
    build_agent,
    build_settings,
    card,
    fetch_server,
    installed,
    reply,
    search_server,
    template_regex,
    tool_call,
    verdict,
    worker,
)
from vidbyte import BaseAgent
from vidbyte.lib.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / "vidbyte" / "agents" / "browser"
MAX_MODULES = 10
MAX_LINES_AFTER_HEADER = 400

# The 19 leaves of spec section 9.1, in its order, with the placeholders each one takes.
EXPECTED_LEAVES: dict[str, set[str]] = {
    "orchestrator_system_prompt": set(),
    "worker_system_prompt": set(),
    "episode_prompt": {"index", "task", "done_when"},
    "done_when_system_prompt": set(),
    "recheck_system_prompt": set(),
    "recheck_prompt": {"goal", "done_when", "progress"},
    "goal_card": {"goal", "done_when", "plan", "progress", "blockers", "verdict", "gap", "last_episode"},
    "result_card": {"index", "outcome", "summary", "facts", "urls", "evidence"},
    "run_episode_description": set(),
    "run_episode_task_description": set(),
    "run_episode_done_when_description": set(),
    "patch_goal_description": set(),
    "patch_goal_section_description": set(),
    "patch_goal_text_description": set(),
    "patch_refused": {"problem"},
    "progress_full": set(),
    "continue_prompt": {"verdict", "gap"},
    "stuck_summary": {"reason"},
    "stalled_output": {"card"},
}

# NFR-3: the only AgentRuntime methods BrowserAgentRuntime may redefine.
OVERRIDES = {"__init__", "arun", "_continue_finish_attempt", "_after_tool_iteration", "_budget_stop"}


def _placeholders(template: str) -> set[str]:
    return {re.split(r"[!:.\[]", name, maxsplit=1)[0] for _, name, _, _ in string.Formatter().parse(template) if name}


def _one_episode_run(**fields: object) -> ScriptedModel:
    agent = build_agent(**fields)
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", {"task": "Open https://www.seedcamp.com/apply and read the deadline.", "done_when": "The deadline is read."}), reply("Seedcamp closes 30 November.")],
            worker(1): [card("done", "Seedcamp closes 30 November.")],
            RECHECK: [verdict("done", "Nothing is missing.")],
        }
    )
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    return model


# ---------------------------------------------------------------- exports and vocabularies


def test_public_names_import_from_every_documented_path() -> None:
    """AC-24: the four root names import from vidbyte, BrowserAgentRuntime from vidbyte.agents and vidbyte.agents.browser, the five enums from vidbyte.lib.enums, and the contract lists the root names."""
    import vidbyte
    from vidbyte import BrowserAgent, BrowserAgentSettings, BrowserEvent, BrowserServerSettings
    from vidbyte.agents import BrowserAgent as agents_agent
    from vidbyte.agents import BrowserAgentRuntime
    from vidbyte.agents import BrowserAgentSettings as agents_settings
    from vidbyte.agents import BrowserServerSettings as agents_server
    from vidbyte.agents.browser import BrowserAgent as package_agent
    from vidbyte.agents.browser import BrowserAgentRuntime as package_runtime
    from vidbyte.agents.browser import BrowserAgentSettings as package_settings
    from vidbyte.agents.browser import BrowserServerSettings as package_server
    from vidbyte.lib.dataclasses.browser import BrowserEvent as record_event
    from vidbyte.lib.enums import BrowserEpisodeOutcome, BrowserEventKind, BrowserGoalSection, BrowserToolRole, BrowserVerdict

    assert BrowserAgent is agents_agent is package_agent
    assert BrowserAgentSettings is agents_settings is package_settings
    assert BrowserServerSettings is agents_server is package_server
    assert BrowserAgentRuntime is package_runtime
    assert BrowserEvent is record_event
    assert issubclass(BrowserAgent, BaseAgent)
    root_names = {"BrowserAgent", "BrowserAgentSettings", "BrowserServerSettings", "BrowserEvent"}
    assert root_names <= set(vidbyte.__all__)
    assert {"BrowserAgent", "BrowserAgentRuntime", "BrowserAgentSettings", "BrowserServerSettings"} <= set(importlib.import_module("vidbyte.agents").__all__)
    enums_package = importlib.import_module("vidbyte.lib.enums")
    enum_names = {cls.__name__ for cls in (BrowserToolRole, BrowserEpisodeOutcome, BrowserGoalSection, BrowserVerdict, BrowserEventKind)}
    assert enum_names <= set(enums_package.__all__), "every public enum is in vidbyte.lib.enums.__all__"
    contract = json.loads((REPO_ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert root_names <= set(contract["exports"]), "the regenerated public-API contract must list the new root exports"


def test_enum_values_and_added_members_are_the_documented_strings() -> None:
    """Section 8.5, D-2, D-28: each new enum is a str enum with exactly the documented lowercase values; GOAL_STALLED and BROWSER are added in place."""
    from vidbyte.lib.dataclasses.agents import AgentStopReason
    from vidbyte.lib.enums import AgentRuntimeType, BrowserEpisodeOutcome, BrowserEventKind, BrowserGoalSection, BrowserToolRole, BrowserVerdict

    expected: dict[type, set[str]] = {
        BrowserToolRole: {"action", "search", "fetch"},
        BrowserEpisodeOutcome: {"done", "stuck", "blocked", "ready_to_submit"},
        BrowserGoalSection: {"plan", "progress", "blockers"},
        BrowserVerdict: {"continue", "done", "stalled"},
        BrowserEventKind: {"run_started", "goal_set", "episode_started", "episode_finished", "goal_patched", "goal_rechecked", "recipe_recorded", "context_rebuilt", "run_finished", "run_stopped"},
    }
    for enum_type, values in expected.items():
        assert {member.value for member in enum_type} == values, enum_type.__name__
        assert all(isinstance(member, str) and member.value == member.name.lower() for member in enum_type), enum_type.__name__
    assert AgentStopReason("goal_stalled") is AgentStopReason.GOAL_STALLED
    assert AgentRuntimeType("browser") is AgentRuntimeType.BROWSER


def test_fixed_string_constants_are_the_documented_values() -> None:
    """Section 9.1: tool names, argument names, the card's primitive id, the screenshot marker, and the name templates are fixed strings other code and tests bind to."""
    from vidbyte.lib.constants import browser as names

    assert names.BROWSER_EPISODE_TOOL_NAME == "run_episode"
    assert names.BROWSER_PATCH_TOOL_NAME == "patch_goal"
    assert set(names.BROWSER_RESERVED_TOOL_NAMES) == {"run_episode", "patch_goal"}
    assert (names.BROWSER_EPISODE_TASK_ARGUMENT, names.BROWSER_EPISODE_DONE_WHEN_ARGUMENT) == ("task", "done_when")
    assert (names.BROWSER_PATCH_SECTION_ARGUMENT, names.BROWSER_PATCH_TEXT_ARGUMENT) == ("section", "text")
    assert names.BROWSER_GOAL_PRIMITIVE_ID == "browser_goal_card"
    assert names.BROWSER_SCREENSHOT_MARKER == "screenshot"
    assert names.BROWSER_SERVER_NAME_TEMPLATE == "browser-{role}-{index}"
    assert names.BROWSER_EPISODE_AGENT_NAME == "{name}-episode-{index}"
    assert names.BROWSER_RECHECK_AGENT_NAME == "{name}-recheck"
    assert names.BROWSER_DONE_WHEN_AGENT_NAME == "{name}-done-when"
    assert isinstance(names.BROWSER_GOAL_TITLE, str) and names.BROWSER_GOAL_TITLE.strip()
    assert isinstance(names.BROWSER_CARD_CUT_MARKER, str) and names.BROWSER_CARD_CUT_MARKER.strip()


def test_prompt_family_has_exactly_the_nineteen_leaves_with_their_placeholders_and_no_digits() -> None:
    """AC-25, INV-26, NFR-5: Prompt.BROWSER_AGENT_* is exactly the 19 leaves of section 9.1, each non-blank, using exactly its documented placeholders, and no leaf contains a digit."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    members = {member.name: member.value for member in Prompt if member.name.startswith("BROWSER_AGENT_")}
    assert members == {f"BROWSER_AGENT_{leaf.upper()}": f"browser_agent.{leaf}" for leaf in EXPECTED_LEAVES}
    catalog = Prompts()
    family = catalog.family("browser_agent")
    assert set(family) == set(EXPECTED_LEAVES)
    for leaf, placeholders in EXPECTED_LEAVES.items():
        text = catalog.get(Prompt[f"BROWSER_AGENT_{leaf.upper()}"])
        assert text.strip(), f"{leaf} is blank"
        assert _placeholders(text) == placeholders, f"{leaf} uses {sorted(_placeholders(text))}, the spec gives {sorted(placeholders)}"
        assert not re.search(r"[0-9]", text), f"{leaf} states a number: {re.findall(r'.{0,30}[0-9].{0,30}', text)}"
    descriptor = json.loads((REPO_ROOT / "vidbyte" / "prompts" / "prompts" / "browser_agent" / "browser_agent.json").read_text(encoding="utf-8"))
    assert descriptor["key"] == "browser_agent"
    assert set(descriptor["prompts"]) == set(EXPECTED_LEAVES)


# ---------------------------------------------------------------- runtime, registry, sessions


def test_runtime_type_resolves_and_refuses_outside_its_agent() -> None:
    """AC-20, INV-22, INV-27, FR-20: the registry maps BROWSER to BrowserAgentRuntime and keeps the other three; a plain BaseAgent or a fork cannot build the runtime."""
    from vidbyte.agents import BrowserAgentRuntime
    from vidbyte.agents.base import _LINEAR_LOOP_RUNTIMES
    from vidbyte.agents.infinite import InfiniteMemoryRuntime
    from vidbyte.agents.jev.runtime import JevRuntime
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.lib.enums import AgentRuntimeType
    from vidbyte.lib.registries.runtimes import RuntimeRegistry

    assert RuntimeRegistry.resolve(AgentRuntimeType.BROWSER) is BrowserAgentRuntime
    assert RuntimeRegistry.resolve(AgentRuntimeType.LINEAR) is AgentRuntime
    assert RuntimeRegistry.resolve(AgentRuntimeType.JEV) is JevRuntime
    assert RuntimeRegistry.resolve(AgentRuntimeType.INFINITE_MEMORY) is InfiniteMemoryRuntime
    assert set(_LINEAR_LOOP_RUNTIMES) == {AgentRuntimeType.LINEAR, AgentRuntimeType.JEV, AgentRuntimeType.INFINITE_MEMORY, AgentRuntimeType.BROWSER}
    prefix = "The 'browser' runtime is only available through BrowserAgent"
    plain = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1", runtime="browser")
    with pytest.raises(ConfigurationError) as refused:
        plain._runtime()
    assert str(refused.value).startswith(prefix), str(refused.value)
    with pytest.raises(ConfigurationError) as forked:
        build_agent().fork()._runtime()
    assert str(forked.value).startswith(prefix), str(forked.value)


def test_session_refuses_the_agent() -> None:
    """AC-20, D-21: Session refuses a BrowserAgent with the SessionError it raises for opted-out agent types."""
    from vidbyte import Session, SessionError
    from vidbyte.agents.browser import BrowserAgent

    assert BrowserAgent.session_persistence_supported is False
    with pytest.raises(SessionError, match="does not support durable session persistence"):
        Session(build_agent())


def test_runtime_overrides_exactly_the_five_documented_methods() -> None:
    """NFR-3: BrowserAgentRuntime redefines only __init__, arun, _continue_finish_attempt, _after_tool_iteration and _budget_stop of AgentRuntime."""
    from vidbyte.agents.browser import BrowserAgentRuntime
    from vidbyte.agents.runtime import AgentRuntime

    redefined = {name for name, value in vars(BrowserAgentRuntime).items() if callable(value) or isinstance(value, (staticmethod, classmethod, property))}
    overridden = {name for name in redefined if hasattr(AgentRuntime, name)}
    assert overridden == OVERRIDES, f"overrides beyond NFR-3: {sorted(overridden - OVERRIDES)}; missing: {sorted(OVERRIDES - overridden)}"
    assert issubclass(BrowserAgentRuntime, AgentRuntime)


# ---------------------------------------------------------------- what the orchestrator is offered


def test_run_episode_and_patch_goal_schemas_follow_the_documented_contract() -> None:
    """Section 8.5 tool contracts, AC-17 static half, INV-19: run_episode takes exactly task and done_when, patch_goal a section enum and text, all descriptions come from leaves, and nothing offers to submit."""
    from vidbyte.agents.browser import BrowserAgentSettings
    from vidbyte.lib.enums import BrowserGoalSection
    from vidbyte.prompts import Prompts

    model = _one_episode_run()
    first = model.first_call(NAME)
    episode = first.tool_schemas["run_episode"]
    assert episode["type"] == "object"
    assert set(episode["properties"]) == {"task", "done_when"}
    assert set(episode["required"]) == {"task", "done_when"}
    assert episode.get("additionalProperties") is False
    assert episode["properties"]["task"]["type"] == "string" and episode["properties"]["done_when"]["type"] == "string"
    patch = first.tool_schemas["patch_goal"]
    assert set(patch["properties"]) == {"section", "text"}
    assert set(patch["required"]) == {"section", "text"}
    assert set(patch["properties"]["section"]["enum"]) == {section.value for section in BrowserGoalSection}
    assert patch["properties"]["text"]["type"] == "string"
    from vidbyte.lib.enums.prompts import Prompt

    catalog = Prompts()
    described = {
        ("run_episode", None): "RUN_EPISODE_DESCRIPTION",
        ("run_episode", "task"): "RUN_EPISODE_TASK_DESCRIPTION",
        ("run_episode", "done_when"): "RUN_EPISODE_DONE_WHEN_DESCRIPTION",
        ("patch_goal", None): "PATCH_GOAL_DESCRIPTION",
        ("patch_goal", "section"): "PATCH_GOAL_SECTION_DESCRIPTION",
        ("patch_goal", "text"): "PATCH_GOAL_TEXT_DESCRIPTION",
    }
    for (tool_name, argument), leaf in described.items():
        text = first.tool_descriptions[tool_name] if argument is None else first.tool_schemas[tool_name]["properties"][argument].get("description", "")
        expected = catalog.get(Prompt[f"BROWSER_AGENT_{leaf}"])
        assert template_regex(expected).fullmatch(text.strip()), f"{tool_name}.{argument or 'description'} is not its catalog leaf: {text!r}"
    # INV-19: no settings field and no run_episode argument offers to submit.
    assert not [f.name for f in dataclasses.fields(BrowserAgentSettings) if "submit" in f.name.lower()]
    assert not [name for name in episode["properties"] if "submit" in name.lower()]


def test_run_episode_is_internal_so_it_does_not_spend_the_orchestrators_tool_budget() -> None:
    """Section 8.5: run_episode is internal, so an orchestrator loop with max_tool_calls=1 still runs two episodes and finishes with its own answer."""
    from vidbyte.agents.settings import AgentLoopSettings

    agent = build_agent(loop=AgentLoopSettings(max_iterations=10, max_tool_calls=1))
    episode_args = {"task": "Open https://www.seedcamp.com/apply.", "done_when": "The page is open."}
    model = ScriptedModel(
        {
            NAME: [tool_call("run_episode", episode_args), tool_call("run_episode", episode_args), reply("Both pages were opened.")],
            worker(1): [card("done", "Opened.")],
            worker(2): [card("done", "Opened again.")],
            RECHECK: [verdict("done", "Nothing is missing.")],
        }
    )
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    assert result.content == "Both pages were opened."
    assert agent.response.stop_reason == "final_response"
    assert [episode.index for episode in agent.response.episodes] == [1, 2]


def test_named_servers_names_every_server_by_role_in_role_order() -> None:
    """D-7, section 12.3 row 10: named_servers yields (name, role, server) for every server in action, search, fetch order, named from BROWSER_SERVER_NAME_TEMPLATE with consecutive indexes per role."""
    from vidbyte.agents.browser import BrowserServerSettings
    from vidbyte.agents.browser.tools import BrowserAgentTools
    from vidbyte.lib.constants.browser import BROWSER_SERVER_NAME_TEMPLATE
    from vidbyte.lib.enums import BrowserToolRole

    second_action = BrowserServerSettings(command=("fake-second-browser",))
    settings = build_settings(action_servers=(action_server(), second_action), search_servers=(search_server(),), fetch_servers=(fetch_server(),), done_when=DONE_WHEN)
    named = BrowserAgentTools.named_servers(settings)
    assert [role for _, role, _ in named] == [BrowserToolRole.ACTION, BrowserToolRole.ACTION, BrowserToolRole.SEARCH, BrowserToolRole.FETCH]
    assert [server for _, _, server in named] == [settings.action_servers[0], second_action, settings.search_servers[0], settings.fetch_servers[0]]
    names = [name for name, _, _ in named]
    assert len(set(names)) == len(names)
    base = int(names[0].rsplit("-", 1)[1])
    assert base in (0, 1)
    expected = [
        BROWSER_SERVER_NAME_TEMPLATE.format(role="action", index=base),
        BROWSER_SERVER_NAME_TEMPLATE.format(role="action", index=base + 1),
        BROWSER_SERVER_NAME_TEMPLATE.format(role="search", index=base),
        BROWSER_SERVER_NAME_TEMPLATE.format(role="fetch", index=base),
    ]
    assert names == expected


# ---------------------------------------------------------------- complexity budget


def _lines_after_header(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    first = tree.body[0] if tree.body else None
    header_end = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else 0
    return len(source.splitlines()) - int(header_end or 0)


def test_new_package_stays_inside_the_complexity_budget() -> None:
    """AC-28, NFR-1, NFR-5, section 12.4: at most 10 modules in vidbyte/agents/browser, each at most 400 lines after its header; no prompt formats a cap and no code deletes stored messages by hand."""
    assert PACKAGE.is_dir(), "vidbyte/agents/browser does not exist"
    modules = sorted(PACKAGE.glob("*.py"))
    assert 0 < len(modules) <= MAX_MODULES, [path.name for path in modules]
    for path in modules:
        assert _lines_after_header(path) <= MAX_LINES_AFTER_HEADER, f"{path.name} is over {MAX_LINES_AFTER_HEADER} lines after its header"
        source = path.read_text(encoding="utf-8")
        assert "format(max_" not in source, f"{path.name} formats a cap into prompt text"
        assert "del messages" not in source, f"{path.name} deletes stored messages instead of using the compaction engine"
    for relative in ("vidbyte/lib/enums/browser.py", "vidbyte/lib/constants/browser.py", "vidbyte/lib/dataclasses/browser.py"):
        assert (REPO_ROOT / relative).is_file(), f"{relative} is missing"
