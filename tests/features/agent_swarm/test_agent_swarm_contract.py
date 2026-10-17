"""FILE: tests/features/agent_swarm/test_agent_swarm_contract.py

PURPOSE: Pins AgentSwarm's static contract:
- the public import paths, exports and the regenerated public-API contract, plus enum values;
- the record and settings shapes of section 8.5 (frozen, slotted, documented fields, api_keys hidden);
- the ten-leaf agent_swarm prompt family with its format fields, and the prompt text rules (no digits, no infinite_memory role or workflow words, no examples; 4-5 sentence descriptions);
- the agent_swarm_member runtime type and its refusal outside a swarm;
- the exact tools and message schema each agent's model is offered, and the order of each agent's system prompt;
- settings validation, boundaries and defaults (including a search tool named isDone), and API-key secrecy;
- the tool-result cap and the history trim every member's model call goes through;
- the per-kind field table of AgentSwarmEvent and the sequence rules of AgentSwarmResult;
- the complexity budget, no polling, and the entry points' type checks.
ROLE IN CODEBASE: Contract layer of tests/features/agent_swarm/ (spec AC-11, AC-12, AC-13, AC-14, AC-17, AC-21; INV-21, INV-22, INV-23, INV-24, INV-28; EC-26, EC-33, EC-34, EC-35; FR-1, FR-3, FR-9, FR-12, FR-13, FR-14; NFR-2, NFR-3, NFR-4, NFR-5; D-10; sections 8.4, 8.5, 9.1, 9.2, 9.3; S4 review R-2, R-5).
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError (or, for the budget test, on the missing package folder) and the rest of the suite still collects. Tool offers and system prompts are read from what the scripted runner receives on each agent's first call, never from the swarm's internals.
FUNCTION INVENTORY: test_public_names_import_from_every_documented_path (AC-17, FR-14); test_records_and_settings_are_frozen_slotted_dataclasses_with_the_documented_fields (section 8.5, NFR-5); test_enum_values_are_the_documented_lowercase_strings (section 8.5); test_prompt_family_has_exactly_the_ten_documented_leaves_with_their_fields (W-2, INV-28); test_prompt_leaves_hold_no_digits_roles_or_examples (INV-22, NFR-4, NG-10); test_runtime_type_refuses_outside_a_swarm_without_calling_a_model (AC-12, INV-24, EC-35); test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_of_its_peers (AC-13, INV-21, FR-3, D-13); test_each_system_prompt_is_own_prompt_then_swarm_prompt_then_agentic_loop_prompt (AC-14, FR-9); test_invalid_settings_are_refused_naming_the_field_and_creating_nothing (AC-11, EC-33, INV-18, FR-12); test_a_search_tool_named_isdone_is_refused_naming_the_reserved_names (EC-33, FR-3, section 9.3, R-2); test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call (EC-26, D-10, A-5; mutants M21, M22); test_boundary_settings_are_accepted_with_documented_defaults (FR-1, section 9.3); test_api_keys_never_appear_in_reprs_events_model_calls_or_errors (AC-21, INV-23, EC-34, NFR-5); test_event_records_enforce_the_per_kind_field_table (section 9.1); test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended (section 9.1, FR-15); test_new_modules_stay_inside_the_complexity_budget_and_never_sleep (NFR-2, NFR-3, section 8.4); test_entry_points_refuse_anything_but_their_documented_types (section 9.2).
COMMON MODIFICATION PATTERNS: When the spec adds a prompt leaf, add it to LEAF_FIELDS with its format fields. When a setting gains a bound, add one row to INVALID_SETTINGS with the field the error must name.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare tool descriptions or refusals to hand-written text; they come from the prompt catalog. 3. Do not loosen the exact tool-name set to a subset check; INV-21 is an exact list.
KNOWN EDGE CASES: A refusal's field may be named with an index suffix by a converter (AgentSwarmSettings.agents[1]), so field checks use startswith. The swarm segment of a system prompt is located between the member's own prompt and the agentic-loop prompt and must fully match the system_prompt template; a template that ends in a field would otherwise match too little. The trim test counts the history budget in characters with TOKEN_ESTIMATE_CHARS_PER_TOKEN, the four-characters-per-token estimate the constants module states and the trim uses; its search count is one cut result more than that budget holds, plus one, and the cut ceiling allows a one-percent truncation notice.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6.1, 6.2, 8.4, 8.5, 9.1, 9.2, 9.3 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm/test_agent_swarm_contract.py -q
"""

from __future__ import annotations

import ast
import collections.abc
import dataclasses
import importlib
import json
import math
import re
import string
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.features.agent_swarm.agent_swarm_fixtures import (
    FAKE_OPENAI_KEY,
    MODEL,
    PROMPTS,
    EventLog,
    ScriptedSwarm,
    SearchTool,
    build_settings,
    build_swarm,
    error_text,
    member,
    prompt_text,
    reply,
    run_swarm,
    seen_text,
    send,
    snapshot,
    template_regex,
    tool_call,
    tool_results,
    workplace_path,
)
from vidbyte import BaseAgent

REPO_ROOT = Path(__file__).resolve().parents[3]
NAMES = ("builder", "tester")
THREE = ("builder", "tester", "reviewer")
ROOT_NAMES = {"AgentSwarm", "AgentSwarmMember", "AgentSwarmSettings", "AgentSwarmEventKind", "AgentSwarmStopReason"}
PACKAGE_NAMES = {"AgentSwarm", "AgentSwarmSettings", "AgentSwarmRuntime", "AgentSwarmEvents", "AgentSwarmWorkplace", "AgentSwarmMemberRuntime"}
SWARM_TOOLS = {"bash", "grep", "read_lines", "write_text", "patch_file", "message", "isDone"}

# The ten leaves of spec section 8.5 / 12.3 rows 8-17 and the str.format fields each one takes.
LEAF_FIELDS: dict[str, set[str]] = {
    "system_prompt": {"name", "agents"},
    "message_tool_description": set(),
    "message_to_description": set(),
    "message_text_description": set(),
    "message_sent": {"recipient"},
    "message_unknown_recipient": {"recipient", "agents"},
    "message_stopped_recipient": {"recipient"},
    "message_blank_text": set(),
    "inbox": {"messages"},
    "inbox_message": {"sender", "text"},
}
DESCRIPTION_LEAVES = ("message_tool_description", "message_to_description", "message_text_description")
# The role and workflow vocabulary of the infinite_memory prompt family (every word below occurs there), which NG-10 keeps out of the swarm prompt (Prompt 1: "dont want to influence the same biases as the InfiniteMemoryAgent").
ROLE_WORDS = (r"\bgenerators?\b", r"\bverifiers?\b", r"\bsubagents?\b", r"\blaunch_subagent\b", r"\bdelegat\w*", r"\bscarcest\b")
# A sentence ends at . ! or ? (optionally followed by a closing quote, bracket or backtick) and then whitespace.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]`]*\s+")

# The eleven new modules of section 8.4: the package's seven, the toolset, and the lib enums, constants and records.
PACKAGE_MODULES = ("__init__.py", "swarm.py", "settings.py", "runtime.py", "events.py", "workplace.py", "member.py")
BUDGET_MODULES = (
    *(f"vidbyte/agents/agent_swarm/{name}" for name in PACKAGE_MODULES),
    "vidbyte/tools/toolsets/agent_swarm.py",
    "vidbyte/lib/enums/agent_swarm.py",
    "vidbyte/lib/constants/agent_swarm.py",
    "vidbyte/lib/dataclasses/agent_swarm.py",
)


# ---------------------------------------------------------------- exports, enums, catalog


def test_public_names_import_from_every_documented_path() -> None:
    """AC-17, FR-14: every documented import path works and yields the same objects; the enums are exported, the registry and linear-loop set know the runtime, and the contract lists the five root names."""
    import vidbyte
    import vidbyte.agents
    import vidbyte.tools.toolsets
    from vidbyte import AgentSwarm, AgentSwarmEventKind, AgentSwarmMember, AgentSwarmSettings, AgentSwarmStopReason
    from vidbyte.agents import agent_swarm as package
    from vidbyte.agents.agent_swarm.member import AgentSwarmMemberAgent, AgentSwarmMessageTool, AgentSwarmTurnMiddleware
    from vidbyte.agents.base import _LINEAR_LOOP_RUNTIMES
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmEventCallback, AgentSwarmResult
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember as record_member
    from vidbyte.lib.enums import AgentRuntimeType
    from vidbyte.lib.enums.agent_swarm import AgentSwarmEventKind as enum_kind
    from vidbyte.lib.enums.agent_swarm import AgentSwarmStopReason as enum_stop
    from vidbyte.lib.registries.runtimes import RuntimeRegistry
    from vidbyte.middleware.base import AgentMiddleware
    from vidbyte.tools.base import BaseTool
    from vidbyte.tools.catalog import Tools
    from vidbyte.tools.toolsets import AgentSwarmTools

    # The package exports exactly its six names, and vidbyte.agents re-exports the same objects.
    assert sorted(package.__all__) == sorted(PACKAGE_NAMES)
    for name in PACKAGE_NAMES:
        assert getattr(vidbyte.agents, name) is getattr(package, name), name
        assert name in vidbyte.agents.__all__, name
    assert AgentSwarm is package.AgentSwarm and AgentSwarmSettings is package.AgentSwarmSettings
    assert AgentSwarmMember is record_member and AgentSwarmEventKind is enum_kind and AgentSwarmStopReason is enum_stop
    # Q-10 default: the root exports the five names and no other AgentSwarm name.
    assert {name for name in vidbyte.__all__ if name.startswith("AgentSwarm")} == ROOT_NAMES
    enums_package = importlib.import_module("vidbyte.lib.enums")
    assert {"AgentSwarmEventKind", "AgentSwarmStopReason"} <= set(enums_package.__all__)
    assert "AgentSwarmTools" in vidbyte.tools.toolsets.__all__ and issubclass(AgentSwarmTools, Tools)
    # FR-13: the member loop is a registered linear-loop runtime; the member parts subclass the SDK bases.
    assert issubclass(package.AgentSwarmMemberRuntime, AgentRuntime)
    assert RuntimeRegistry.resolve(AgentRuntimeType.AGENT_SWARM_MEMBER) is package.AgentSwarmMemberRuntime
    assert AgentRuntimeType.AGENT_SWARM_MEMBER in _LINEAR_LOOP_RUNTIMES
    assert issubclass(AgentSwarmMemberAgent, BaseAgent) and AgentSwarmMemberAgent.session_persistence_supported is False
    assert issubclass(AgentSwarmMessageTool, BaseTool) and issubclass(AgentSwarmTurnMiddleware, AgentMiddleware)
    assert AgentSwarmTurnMiddleware.fail_closed is True, "EC-16 (c): the turn middleware keeps the default fail_closed"
    # Section 8.5: the callback alias is Callable[[AgentSwarmEvent], None | Awaitable[None]].
    assert typing.get_origin(AgentSwarmEventCallback) is collections.abc.Callable
    parameters = typing.get_args(AgentSwarmEventCallback)[0]
    assert len(parameters) == 1 and (parameters[0] is AgentSwarmEvent or getattr(parameters[0], "__forward_arg__", "") == "AgentSwarmEvent")
    assert AgentSwarmResult.__module__ == "vidbyte.lib.dataclasses.agent_swarm"
    contract = json.loads((REPO_ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert ROOT_NAMES <= set(contract["exports"]), "the regenerated public-API contract must list the five root exports"


def test_records_and_settings_are_frozen_slotted_dataclasses_with_the_documented_fields() -> None:
    """Section 8.5, NFR-5: the three records and the settings are frozen, slotted dataclasses whose fields are exactly the documented ones in order, and api_keys is hidden from the repr."""
    from vidbyte import AgentSwarmMember, AgentSwarmSettings
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmResult

    expected = {
        AgentSwarmMember: ["name", "system_prompt", "provider", "model_name"],
        AgentSwarmEvent: ["sequence", "kind", "agent", "elapsed_ms", "peer", "message_id", "text", "tool_name", "tool_status", "stop_reason"],
        AgentSwarmResult: ["stop_reason", "events", "replies", "event_error_types"],
        AgentSwarmSettings: ["agents", "workplace", "api_keys", "search_tool", "on_event", "max_turns", "timeout_seconds"],
    }
    for record, names in expected.items():
        assert dataclasses.is_dataclass(record), record.__name__
        assert [item.name for item in dataclasses.fields(record)] == names, record.__name__
        assert record.__dataclass_params__.frozen is True, f"{record.__name__} is not frozen"
        assert "__slots__" in record.__dict__, f"{record.__name__} is not slotted"
    hidden = {item.name for item in dataclasses.fields(AgentSwarmSettings) if not item.repr}
    assert hidden == {"api_keys"}


def test_enum_values_are_the_documented_lowercase_strings() -> None:
    """Section 8.5: each new enum is a str enum whose values are exactly the documented lowercase names, and the runtime type has its value."""
    from vidbyte import AgentSwarmEventKind, AgentSwarmStopReason
    from vidbyte.lib.enums import AgentRuntimeType

    expected: dict[type, set[str]] = {
        AgentSwarmEventKind: {"agent_started", "tool_called", "message_sent", "message_delivered", "agent_idle", "agent_woke", "agent_failed", "swarm_ended"},
        AgentSwarmStopReason: {"quiet", "max_turns", "timeout", "failed"},
    }
    for enum_type, values in expected.items():
        assert {item.value for item in enum_type} == values, enum_type.__name__
        assert all(isinstance(item, str) and item.value == item.name.lower() for item in enum_type), enum_type.__name__
    assert AgentRuntimeType("agent_swarm_member") is AgentRuntimeType.AGENT_SWARM_MEMBER


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_prompt_family_has_exactly_the_ten_documented_leaves_with_their_fields() -> None:
    """W-2, INV-28: Prompt.AGENT_SWARM_* is exactly the ten leaves, each backed by non-blank catalog text whose str.format fields are exactly the documented ones."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    members = {item.name: item.value for item in Prompt if item.name.startswith("AGENT_SWARM_")}
    assert members == {f"AGENT_SWARM_{leaf.upper()}": f"agent_swarm.{leaf}" for leaf in LEAF_FIELDS}
    catalog = Prompts()
    assert set(catalog.family("agent_swarm")) == set(LEAF_FIELDS)
    for leaf, fields in LEAF_FIELDS.items():
        text = catalog.get(Prompt[f"AGENT_SWARM_{leaf.upper()}"])
        assert text.strip(), f"{leaf} is blank"
        assert _fields(text) == fields, f"{leaf} takes {_fields(text)}, the spec documents {fields}"
        # Rendering with exactly the documented fields never raises.
        text.format(**{name: "X" for name in fields})


def test_prompt_leaves_hold_no_digits_roles_or_examples() -> None:
    """INV-22, NFR-4, NG-10, section 12.3 rows 8-11: no leaf states a number, a role or a workflow; each description is 4-5 general sentences without examples; the swarm prompt says what AC-14 needs."""
    from vidbyte.prompts import Prompts

    family = Prompts().family("agent_swarm")
    assert set(family) == set(LEAF_FIELDS)
    for leaf, text in family.items():
        assert not re.search(r"\d", text), f"{leaf} holds a digit"
        for word in ROLE_WORDS:
            assert not re.search(word, text, re.IGNORECASE), f"{leaf} uses the role or workflow word {word!r}"
    for leaf in DESCRIPTION_LEAVES:
        sentences = [part for part in SENTENCE_BREAK.split(family[leaf].strip()) if part.strip()]
        assert 4 <= len(sentences) <= 5, f"{leaf} has {len(sentences)} sentences"
        assert not re.search(r"\be\.g\.|\bi\.e\.|\bfor (?:example|instance)\b|\bexamples?\b", family[leaf], re.IGNORECASE), f"{leaf} gives an example"
    system = family["system_prompt"]
    assert "agent swarm" in system.lower() and "folder" in system.lower() and "message" in system.lower()
    assert "isDone" in system


def test_runtime_type_refuses_outside_a_swarm_without_calling_a_model() -> None:
    """AC-12, INV-24, EC-35: a plain BaseAgent cannot build the agent_swarm_member runtime; _runtime() raises the documented ConfigurationError and arun wraps it as the cause, with no model call."""
    import asyncio

    # Imported so that, before the feature exists, this test fails on the missing package rather than on BaseAgent's unknown-runtime refusal.
    from vidbyte.agents.agent_swarm import AgentSwarmMemberRuntime  # noqa: F401
    from vidbyte.lib.errors import AgentExecutionError, ConfigurationError

    prefix = "The 'agent_swarm_member' runtime is only available through AgentSwarm"
    plain = BaseAgent(name="loner", system_prompt="Work alone.", provider="openai", model_name=MODEL, runtime="agent_swarm_member")
    with pytest.raises(ConfigurationError) as refused:
        plain._runtime()
    assert str(refused.value).startswith(prefix)
    assert "AgentSwarm(AgentSwarmSettings(" in str(refused.value) and "arun(" in str(refused.value)
    assert refused.value.details == {"received_swarm_runtime": "NoneType"}

    scripted = ScriptedSwarm({})
    with scripted.install():
        with pytest.raises(AgentExecutionError) as wrapped:
            asyncio.run(run_swarm(plain))
    assert isinstance(wrapped.value.__cause__, ConfigurationError)
    assert str(wrapped.value.__cause__).startswith(prefix)
    assert scripted.calls == []


# ---------------------------------------------------------------- what each agent is offered


@pytest.mark.asyncio
@pytest.mark.parametrize("search", ["no-search-tool", "with-search-tool"])
async def test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_of_its_peers(tmp_path: Path, search: str) -> None:
    """AC-13, INV-21, FR-3, D-13: each agent's first call offers exactly the swarm tools, isDone, and the search tool only when given; message takes one of the other agents' names and a text."""
    tool = SearchTool("web_search") if search == "with-search-tool" else None
    expected = SWARM_TOOLS | ({"web_search"} if tool is not None else set())
    scripted = ScriptedSwarm({name: [reply(f"{name} done.")] for name in THREE})
    fields: dict[str, Any] = {"search_tool": tool} if tool is not None else {}
    with scripted.install():
        await run_swarm(build_swarm(tmp_path, THREE, **fields))

    for name in THREE:
        call = scripted.first_call(name)
        assert sorted(call.tools) == sorted(expected), f"{name} was offered {call.tools}"
        assert len(call.tools) == len(set(call.tools)), f"{name} holds a tool twice: {call.tools}"
        schema = call.tool_schemas["message"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["properties"]) == {"to", "text"} and set(schema["required"]) == {"to", "text"}
        assert schema["properties"]["to"]["type"] == "string" and schema["properties"]["text"]["type"] == "string"
        assert sorted(schema["properties"]["to"]["enum"]) == sorted(other for other in THREE if other != name)
        assert schema["properties"]["to"]["description"].strip() == prompt_text("message_to_description").strip()
        assert schema["properties"]["text"]["description"].strip() == prompt_text("message_text_description").strip()
        assert call.tool_descriptions["message"].strip() == prompt_text("message_tool_description").strip()


@pytest.mark.asyncio
async def test_each_system_prompt_is_own_prompt_then_swarm_prompt_then_agentic_loop_prompt(tmp_path: Path) -> None:
    """AC-14, FR-9: each system string holds the member's own prompt verbatim (braces kept), then exactly one rendering of the swarm prompt naming it and its peers, then the agentic-loop prompt; the swarm part differs between agents only by names and has no digits."""
    from vidbyte.prompts.agentic_loop import agentic_loop_prompt

    own = {**{name: PROMPTS[name] for name in NAMES}, "reviewer": 'You review code. Reply with {"ok": true} and never {name}.'}
    agents = tuple(member(name, system_prompt=own[name]) for name in THREE)
    scripted = ScriptedSwarm({name: [reply(f"{name} done.")] for name in THREE})
    with scripted.install():
        await run_swarm(build_swarm(tmp_path, THREE, agents=agents))

    loop_text = agentic_loop_prompt().strip()
    normalized: dict[str, str] = {}
    for name in THREE:
        system = scripted.first_call(name).system
        start = system.find(own[name])
        assert start >= 0, f"{name}'s own prompt is not in its system string verbatim"
        own_end = start + len(own[name])
        loop_at = system.find(loop_text, own_end)
        assert loop_at >= 0, f"the agentic-loop prompt does not follow {name}'s own prompt"
        segment = system[own_end:loop_at].strip()
        # Between the two sits exactly one rendering of the swarm prompt, naming this agent.
        assert template_regex(prompt_text("system_prompt"), name=name).fullmatch(segment), f"{name}'s swarm segment is not the system_prompt template: {segment!r}"
        for peer in THREE:
            if peer != name:
                assert peer in segment, f"{name}'s swarm segment does not name {peer}"
        assert not re.search(r"\d", segment)
        normalized[name] = re.sub("|".join(THREE), "<agent>", segment)
    assert len(set(normalized.values())) == 1, normalized


# ---------------------------------------------------------------- settings


def _member_fields(**override: Any) -> dict[str, Any]:
    return {"name": "builder", "system_prompt": PROMPTS["builder"], "provider": "openai", "model_name": MODEL, **override}


def _bad_member(**override: Any) -> Callable[[Path], Any]:
    def build(tmp_path: Path) -> Any:
        from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember

        return AgentSwarmMember(**_member_fields(**override))

    return build


def _bad_settings(**override: Any) -> Callable[[Path], Any]:
    def build(tmp_path: Path) -> Any:
        values = {key: (value(tmp_path) if callable(value) and key in ("agents", "workplace") else value) for key, value in override.items()}
        return build_settings(tmp_path, NAMES, **values)

    return build


def _a_file(tmp_path: Path) -> Path:
    path = tmp_path / "workplace.txt"
    path.write_text("a file, not a folder", encoding="utf-8")
    return path


INVALID_SETTINGS = [
    pytest.param(_bad_member(name="build er"), "AgentSwarmMember.name", id="name-with-a-space"),
    pytest.param(_bad_member(name="_builder"), "AgentSwarmMember.name", id="name-starting-with-underscore"),
    pytest.param(_bad_member(name="b" * 65), "AgentSwarmMember.name", id="name-of-sixty-five-characters"),
    pytest.param(_bad_member(name="büilder"), "AgentSwarmMember.name", id="name-with-a-non-ascii-letter"),
    pytest.param(_bad_member(name="builder\n"), "AgentSwarmMember.name", id="name-with-a-trailing-newline"),
    pytest.param(_bad_member(name=""), "AgentSwarmMember.name", id="empty-name"),
    pytest.param(_bad_member(system_prompt="   "), "AgentSwarmMember.system_prompt", id="blank-system-prompt"),
    pytest.param(_bad_member(provider="not-a-provider"), "AgentSwarmMember.provider", id="unknown-provider"),
    pytest.param(_bad_member(model_name="  "), "AgentSwarmMember.model_name", id="blank-model-name"),
    pytest.param(_bad_member(provider="anthropic", model_name="gpt-4.1"), "AgentSwarmMember.model_name", id="model-the-provider-cannot-run"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"),)), "AgentSwarmSettings.agents", id="one-agent"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"), member("builder"))), "AgentSwarmSettings.agents", id="two-agents-with-one-name"),
    pytest.param(_bad_settings(agents=lambda tmp: tuple(member(f"a{index}") for index in range(101))), "AgentSwarmSettings.agents", id="one-hundred-and-one-agents"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"), "tester")), "AgentSwarmSettings.agents", id="an-entry-that-is-not-a-member"),
    pytest.param(_bad_settings(max_turns=1), "AgentSwarmSettings.max_turns", id="max-turns-below-the-agent-count"),
    pytest.param(_bad_settings(max_turns=True), "AgentSwarmSettings.max_turns", id="max-turns-true"),
    pytest.param(_bad_settings(timeout_seconds=0), "AgentSwarmSettings.timeout_seconds", id="timeout-zero"),
    pytest.param(_bad_settings(timeout_seconds=-1.0), "AgentSwarmSettings.timeout_seconds", id="timeout-negative"),
    pytest.param(_bad_settings(timeout_seconds=math.nan), "AgentSwarmSettings.timeout_seconds", id="timeout-nan"),
    pytest.param(_bad_settings(timeout_seconds=math.inf), "AgentSwarmSettings.timeout_seconds", id="timeout-infinite"),
    pytest.param(_bad_settings(timeout_seconds=604800.5), "AgentSwarmSettings.timeout_seconds", id="timeout-over-one-week"),
    pytest.param(_bad_settings(on_event="print"), "AgentSwarmSettings.on_event", id="on-event-not-callable"),
    pytest.param(_bad_settings(search_tool=SearchTool("bash")), "AgentSwarmSettings.search_tool", id="search-tool-named-bash"),
    pytest.param(_bad_settings(search_tool=SearchTool("message")), "AgentSwarmSettings.search_tool", id="search-tool-named-message"),
    pytest.param(_bad_settings(search_tool="web_search"), "AgentSwarmSettings.search_tool", id="search-tool-not-a-tool"),
    pytest.param(_bad_settings(workplace=_a_file), "AgentSwarmSettings.workplace", id="workplace-is-a-file"),
]


@pytest.mark.parametrize(("build", "field"), INVALID_SETTINGS)
def test_invalid_settings_are_refused_naming_the_field_and_creating_nothing(tmp_path: Path, build: Callable[[Path], Any], field: str) -> None:
    """AC-11, EC-33, INV-18, FR-12: each invalid member or setting raises ConfigurationError naming Record.field in the message and in details["field"], and leaves the disk as it was."""
    # Imported so that, before the feature exists, every case fails on the missing package, not inside a builder.
    from vidbyte.agents.agent_swarm import AgentSwarmSettings  # noqa: F401
    from vidbyte.lib.errors import ConfigurationError

    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(ConfigurationError) as refused:
        build(tmp_path)
    assert str(refused.value.details["field"]).startswith(field), error_text(refused.value)
    assert field in str(refused.value), error_text(refused.value)
    after = sorted(path.name for path in tmp_path.iterdir())
    assert after == before or (field.endswith("workplace") and after == ["workplace.txt"])
    assert not workplace_path(tmp_path).exists()


def test_a_search_tool_named_isdone_is_refused_naming_the_reserved_names(tmp_path: Path) -> None:
    """EC-33, FR-3, section 9.3 (r4, S4 R-2): a search tool named like the loop's own isDone is refused with ConfigurationError on AgentSwarmSettings.search_tool, the message lists the reserved names and isDone, and nothing is created."""
    from vidbyte.agents.agent_swarm import AgentSwarmSettings  # noqa: F401
    from vidbyte.lib.constants.agent_swarm import AGENT_SWARM_RESERVED_TOOL_NAMES
    from vidbyte.lib.errors import ConfigurationError
    from vidbyte.tools._internal import IS_DONE_TOOL_NAME

    with pytest.raises(ConfigurationError) as refused:
        build_settings(tmp_path, NAMES, search_tool=SearchTool(IS_DONE_TOOL_NAME))
    assert refused.value.details["field"] == "AgentSwarmSettings.search_tool", error_text(refused.value)
    message = str(refused.value)
    assert all(name in message for name in (*AGENT_SWARM_RESERVED_TOOL_NAMES, IS_DONE_TOOL_NAME)), message
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call(tmp_path: Path) -> None:
    """EC-26, D-10, A-5: every search result the model reads is cut near AGENT_SWARM_TOOL_RESULT_MAX_CHARS, far below its raw size, and once the cut results outgrow AGENT_SWARM_HISTORY_MAX_TOKENS the oldest drop out of what the next model call is sent."""
    from vidbyte.lib.constants.agent_swarm import (
        AGENT_SWARM_HISTORY_MAX_TOKENS,
        AGENT_SWARM_TOOL_RESULT_MAX_CHARS,
    )
    from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN
    from vidbyte.tools.types import ToolCall, ToolResult

    # Every bound comes from the constants; the history budget is counted with the SDK's characters-per-token estimate.
    raw_chars = 3 * AGENT_SWARM_TOOL_RESULT_MAX_CHARS
    budget_chars = AGENT_SWARM_HISTORY_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN
    cut_ceiling = AGENT_SWARM_TOOL_RESULT_MAX_CHARS + AGENT_SWARM_TOOL_RESULT_MAX_CHARS // 100
    searches = budget_chars // AGENT_SWARM_TOOL_RESULT_MAX_CHARS + 2

    class HugeSearch(SearchTool):
        async def execute(self, call: ToolCall) -> ToolResult:
            self.queries.append(str(call.arguments.get("query", "")))
            return ToolResult.success(self.name, "x" * raw_chars)

    search = HugeSearch()
    scripted = ScriptedSwarm({"builder": [*(tool_call("web_search", {"query": f"q{index}"}) for index in range(searches)), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES, search_tool=search)
    with scripted.install():
        await run_swarm(swarm)

    builder_calls = scripted.calls_by("builder")
    assert len(search.queries) == searches and len(builder_calls) == searches + 1
    for call in builder_calls:
        for name, content in tool_results(call):
            if name == "web_search":
                assert len(content) <= cut_ceiling, f"a {len(content)}-character search result reached the model; the cap is {AGENT_SWARM_TOOL_RESULT_MAX_CHARS}"
    last = builder_calls[-1]
    kept = [content for name, content in tool_results(last) if name == "web_search"]
    assert 0 < len(kept) < searches, f"the last call kept {len(kept)} of {searches} search results: the history was not trimmed"
    total = sum(len(str(message.get("content") or "")) for message in last.messages)
    assert total <= budget_chars, f"the last call sent {total} characters of history; the budget is {budget_chars}"
    assert last.system == builder_calls[0].system
    scripted.assert_complete()


def test_boundary_settings_are_accepted_with_documented_defaults(tmp_path: Path) -> None:
    """FR-1, section 9.3: boundary values pass, defaults are 500 turns and one hour, the workplace is stored as a resolved Path, the provider as an enum, and the constants hold their documented values."""
    from vidbyte.lib.constants import agent_swarm as constants
    from vidbyte.lib.enums import ModelProvider

    settings = build_settings(tmp_path, NAMES)
    assert (settings.max_turns, settings.timeout_seconds, settings.search_tool, settings.on_event) == (500, 3600.0, None, None)
    assert isinstance(settings.agents, tuple) and settings.agents == (member("builder"), member("tester"))
    assert settings.agents[0].provider is ModelProvider.OPENAI
    assert isinstance(settings.workplace, Path) and settings.workplace == workplace_path(tmp_path).resolve()
    assert build_settings(tmp_path, NAMES, workplace=str(tmp_path / "as-text")).workplace == (tmp_path / "as-text").resolve()
    hundred = tuple(member(f"a{index}") for index in range(100))
    assert len(build_settings(tmp_path, agents=hundred, max_turns=100).agents) == 100
    edge_names = (member("b" * 64), member("1-a_b"))
    build_settings(tmp_path, agents=edge_names, max_turns=2, timeout_seconds=604800.0)
    build_settings(tmp_path, NAMES, timeout_seconds=0.001, search_tool=SearchTool("web_search"), on_event=print)
    mixed = (member("builder"), member("reviewer", provider="anthropic", model_name="claude-sonnet-5"))
    assert build_settings(tmp_path, agents=mixed).agents[1].provider is ModelProvider.ANTHROPIC
    assert list(tmp_path.iterdir()) == []
    assert (constants.AGENT_SWARM_MIN_AGENTS, constants.AGENT_SWARM_MAX_AGENTS) == (2, 100)
    assert constants.AGENT_SWARM_NAME_PATTERN == r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
    assert (constants.AGENT_SWARM_DEFAULT_MAX_TURNS, constants.AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS, constants.AGENT_SWARM_MAX_TIMEOUT_SECONDS) == (500, 3600.0, 604800.0)
    assert (constants.AGENT_SWARM_HISTORY_MAX_TOKENS, constants.AGENT_SWARM_TOOL_RESULT_MAX_CHARS) == (90_000, 100_000)
    assert (constants.AGENT_SWARM_MESSAGE_TOOL_NAME, constants.AGENT_SWARM_MESSAGE_TO_ARGUMENT, constants.AGENT_SWARM_MESSAGE_TEXT_ARGUMENT) == ("message", "to", "text")
    assert constants.AGENT_SWARM_RESERVED_TOOL_NAMES == ("bash", "grep", "read_lines", "write_text", "patch_file", "message")


@pytest.mark.asyncio
async def test_api_keys_never_appear_in_reprs_events_model_calls_or_errors(tmp_path: Path) -> None:
    """AC-21, INV-23, EC-34, NFR-5: with api_keys set, no key text reaches a repr, an event, a model call or a refusal; a mixed swarm missing one provider's key is refused naming AgentSwarmSettings.api_keys."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    secret = "SwarmFakeKey"
    log = EventLog()
    settings = build_settings(tmp_path, NAMES, api_keys=[FAKE_OPENAI_KEY], on_event=log.callback)
    swarm = AgentSwarm(settings)
    for text in (repr(settings), str(settings), repr(swarm), repr(AgentSwarmRuntime(settings, workplace_path(tmp_path)))):
        assert secret not in text
    scripted = ScriptedSwarm({"builder": [send("tester", "c2f.py is ready."), reply("Sent.")], "tester": [reply("First pass."), reply("Done.")]})
    with scripted.install():
        result = await run_swarm(swarm)
    assert result.stop_reason is AgentSwarmStopReason.QUIET
    assert all(secret not in repr(event) for event in result.events)
    assert all(secret not in repr(event) for event in log.received)
    assert scripted.calls and all(secret not in seen_text(call) for call in scripted.calls)

    for fields in ({"max_turns": 1}, {"timeout_seconds": 0}, {"agents": (member("builder"),)}, {"on_event": "print"}):
        with pytest.raises(ConfigurationError) as refused:
            build_settings(tmp_path, NAMES, api_keys=[FAKE_OPENAI_KEY], **fields)
        assert secret not in error_text(refused.value) and secret not in repr(refused.value)
    mixed = (member("builder"), member("reviewer", provider="anthropic", model_name="claude-sonnet-5"))
    with pytest.raises(ConfigurationError) as missing:
        build_settings(tmp_path, agents=mixed, api_keys=[FAKE_OPENAI_KEY])
    assert missing.value.details["field"] == "AgentSwarmSettings.api_keys"
    assert "AgentSwarmSettings.api_keys" in str(missing.value) and secret not in error_text(missing.value)


# ---------------------------------------------------------------- records


def _event(kind: str, **fields: Any) -> Any:
    from vidbyte import AgentSwarmEventKind
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent

    values: dict[str, Any] = {"sequence": 5, "agent": "builder", "elapsed_ms": 0, **fields}
    # "raw:<value>" passes the kind as its value string instead of the enum member, which the record must refuse.
    member_or_text: Any = kind.removeprefix("raw:") if kind.startswith("raw:") else AgentSwarmEventKind(kind)
    return AgentSwarmEvent(kind=member_or_text, **values)


def _status(name: str) -> Any:
    from vidbyte.lib.dataclasses.tools import ToolStatus

    return ToolStatus(name)


def _stop(name: str) -> Any:
    from vidbyte import AgentSwarmStopReason

    return AgentSwarmStopReason(name)


VALID_EVENTS: list[tuple[str, dict[str, Any]]] = [
    ("agent_started", {"sequence": 1}),
    ("tool_called", {"tool_name": "bash", "tool_status": "success"}),
    ("message_sent", {"peer": "tester", "message_id": 5, "text": "c2f.py is ready."}),
    ("message_delivered", {"agent": "tester", "peer": "builder", "message_id": 4}),
    ("agent_idle", {"text": ""}),
    ("agent_idle", {"text": "Done."}),
    ("agent_woke", {}),
    ("agent_failed", {"text": "ProviderRequestError: openai returned 503"}),
    ("swarm_ended", {"agent": "", "stop_reason": "quiet"}),
]

INVALID_EVENTS = [
    pytest.param("agent_started", {"sequence": 0}, "sequence", id="sequence-zero"),
    pytest.param("agent_started", {"sequence": True}, "sequence", id="sequence-bool"),
    pytest.param("agent_started", {"elapsed_ms": -1}, "elapsed_ms", id="elapsed-negative"),
    pytest.param("agent_started", {"elapsed_ms": 1.5}, "elapsed_ms", id="elapsed-float"),
    pytest.param("agent_started", {"elapsed_ms": True}, "elapsed_ms", id="elapsed-bool"),
    pytest.param("raw:agent_started", {}, "kind", id="kind-as-its-value-string"),
    pytest.param("agent_started", {"agent": ""}, "agent", id="started-without-agent"),
    pytest.param("agent_started", {"peer": "tester"}, "peer", id="started-with-peer"),
    pytest.param("tool_called", {"tool_name": "", "tool_status": "success"}, "tool_name", id="tool-without-name"),
    pytest.param("tool_called", {"tool_name": "bash"}, "tool_status", id="tool-without-status"),
    pytest.param("message_sent", {"peer": "tester", "message_id": 4, "text": "hi"}, "message_id", id="sent-id-not-its-sequence"),
    pytest.param("message_sent", {"peer": "tester", "message_id": 5, "text": "   "}, "text", id="sent-blank-text"),
    pytest.param("message_sent", {"message_id": 5, "text": "hi"}, "peer", id="sent-without-recipient"),
    pytest.param("message_delivered", {"agent": "tester", "peer": "builder", "message_id": 5}, "message_id", id="delivered-id-not-earlier"),
    pytest.param("message_delivered", {"agent": "tester", "peer": "builder", "message_id": 0}, "message_id", id="delivered-id-zero"),
    pytest.param("message_delivered", {"agent": "tester", "peer": "builder", "message_id": 4, "text": "hi"}, "text", id="delivered-with-text"),
    pytest.param("agent_idle", {"tool_name": "bash"}, "tool_name", id="idle-with-tool-name"),
    pytest.param("agent_woke", {"text": "woke"}, "text", id="woke-with-text"),
    pytest.param("agent_failed", {"text": ""}, "text", id="failed-without-cause"),
    pytest.param("agent_failed", {"text": "boom", "stop_reason": "failed"}, "stop_reason", id="failed-with-stop-reason"),
    pytest.param("swarm_ended", {"agent": "builder", "stop_reason": "quiet"}, "agent", id="ended-with-agent"),
    pytest.param("swarm_ended", {"agent": ""}, "stop_reason", id="ended-without-stop-reason"),
]


def _coerce(fields: dict[str, Any]) -> dict[str, Any]:
    # Statuses and stop reasons are written as values in the tables above; records take enum members.
    values = dict(fields)
    if isinstance(values.get("tool_status"), str):
        values["tool_status"] = _status(values["tool_status"])
    if isinstance(values.get("stop_reason"), str):
        values["stop_reason"] = _stop(values["stop_reason"])
    return values


@pytest.mark.parametrize(("kind", "fields", "field"), INVALID_EVENTS)
def test_event_records_enforce_the_per_kind_field_table(kind: str, fields: dict[str, Any], field: str) -> None:
    """Section 9.1: every documented event shape builds; a missing required field, a set field the kind does not list, or a bad number raises ConfigurationError naming AgentSwarmEvent.<field>."""
    from vidbyte.lib.errors import ConfigurationError

    for valid_kind, valid_fields in VALID_EVENTS:
        built = _event(valid_kind, **_coerce(valid_fields))
        assert built.kind.value == valid_kind
        assert all(getattr(built, name) == value for name, value in _coerce(valid_fields).items())
    with pytest.raises(ConfigurationError) as refused:
        _event(kind, **_coerce(fields))
    assert refused.value.details["field"] == f"AgentSwarmEvent.{field}", error_text(refused.value)


def _events(*shapes: tuple[str, dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(_event(kind, sequence=index, **_coerce(fields)) for index, (kind, fields) in enumerate(shapes, start=1))


def _reply(sender: str) -> Any:
    from vidbyte.lib.dataclasses.agents import AgentMessage

    return AgentMessage(sender=sender, recipient="user", content=f"{sender} done.")


QUIET_RUN = (("agent_started", {}), ("agent_started", {"agent": "tester"}), ("agent_idle", {}), ("agent_idle", {"agent": "tester"}), ("swarm_ended", {"agent": "", "stop_reason": "quiet"}))

INVALID_RESULTS = [
    pytest.param(lambda: {"events": ()}, ("events",), id="no-events"),
    pytest.param(lambda: {"events": tuple(_events(*QUIET_RUN)[index] for index in (0, 1, 3, 4))}, ("events",), id="a-gap-in-the-sequence"),
    pytest.param(lambda: {"events": _events(*QUIET_RUN[:-1])}, ("events",), id="no-swarm-ended"),
    pytest.param(lambda: {"events": _events(QUIET_RUN[0], QUIET_RUN[4], QUIET_RUN[2])}, ("events",), id="swarm-ended-not-last"),
    pytest.param(lambda: {"events": _events(QUIET_RUN[0], QUIET_RUN[4], QUIET_RUN[4])}, ("events",), id="two-swarm-ended"),
    pytest.param(lambda: {"stop_reason": _stop("max_turns")}, ("events", "stop_reason"), id="stop-reason-differs-from-swarm-ended"),
    pytest.param(lambda: {"stop_reason": "quiet"}, ("stop_reason",), id="stop-reason-as-text"),
    pytest.param(lambda: {"replies": ("builder done.",)}, ("replies",), id="a-reply-that-is-not-an-agent-message"),
    pytest.param(lambda: {"event_error_types": ("",)}, ("event_error_types",), id="blank-error-type"),
    pytest.param(lambda: {"event_error_types": ("Callback\nBoom",)}, ("event_error_types",), id="two-line-error-type"),
]


@pytest.mark.parametrize(("override", "fields"), INVALID_RESULTS)
def test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended(override: Callable[[], dict[str, Any]], fields: tuple[str, ...]) -> None:
    """Section 9.1, FR-15: a result holds events numbered 1..N ending in its one SWARM_ENDED with the same stop reason, AgentMessage replies, and one-line error type names; anything else raises ConfigurationError naming the field."""
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmResult
    from vidbyte.lib.errors import ConfigurationError

    valid = {"stop_reason": _stop("quiet"), "events": _events(*QUIET_RUN), "replies": (_reply("builder"), _reply("tester")), "event_error_types": ("CallbackBoom",)}
    built = AgentSwarmResult(**{**valid, "events": list(valid["events"])})
    assert isinstance(built.events, tuple) and len(built.events) == 5
    with pytest.raises(ConfigurationError) as refused:
        AgentSwarmResult(**{**valid, **override()})
    assert refused.value.details["field"] in {f"AgentSwarmResult.{name}" for name in fields}, error_text(refused.value)


# ---------------------------------------------------------------- budget and entry points


def _lines_after_header(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    first = tree.body[0] if tree.body else None
    header_end = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else 0
    return len(source.splitlines()) - int(header_end or 0)


def _sleep_calls(path: Path) -> list[int]:
    # Every call whose callee is named sleep (asyncio.sleep, time.sleep, or a bare imported sleep).
    found: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else callee.id if isinstance(callee, ast.Name) else ""
            if name == "sleep":
                found.append(node.lineno)
    return found


def test_new_modules_stay_inside_the_complexity_budget_and_never_sleep() -> None:
    """NFR-2, NFR-3, section 8.4: the package has its seven modules and no more, each of the eleven new modules is at most 400 lines after its header, and no swarm module sleeps or polls."""
    package = REPO_ROOT / "vidbyte" / "agents" / "agent_swarm"
    assert package.is_dir(), "vidbyte/agents/agent_swarm does not exist"
    assert sorted(path.name for path in package.glob("*.py")) == sorted(PACKAGE_MODULES)
    for relative in BUDGET_MODULES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is missing"
        assert _lines_after_header(path) <= 400, f"{relative} is over 400 lines after its header"
    for relative in (*BUDGET_MODULES[: len(PACKAGE_MODULES)], "vidbyte/tools/toolsets/agent_swarm.py"):
        assert _sleep_calls(REPO_ROOT / relative) == [], f"{relative} sleeps (NFR-2: no polling)"


def test_entry_points_refuse_anything_but_their_documented_types(tmp_path: Path) -> None:
    """Section 9.2: AgentSwarm takes only an AgentSwarmSettings, AgentSwarmRuntime only an AgentSwarmSettings and a Path; each refusal is a ConfigurationError and touches no disk."""
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    settings = build_settings(tmp_path, NAMES)
    for bad in (object(), None, {"agents": NAMES, "workplace": str(workplace_path(tmp_path))}):
        with pytest.raises(ConfigurationError):
            AgentSwarm(bad)
    with pytest.raises(ConfigurationError):
        AgentSwarmRuntime(object(), workplace_path(tmp_path))
    with pytest.raises(ConfigurationError):
        AgentSwarmRuntime(settings, str(workplace_path(tmp_path)))
    assert snapshot(tmp_path) == {} and list(tmp_path.iterdir()) == []
