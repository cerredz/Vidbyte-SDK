"""FILE: tests/features/agent_swarm/test_agent_swarm_contract.py

PURPOSE: Pins AgentSwarm's static contract:
- the public import paths, exports and the regenerated public-API contract, plus enum values for the six swarm vocabularies;
- the record and settings shapes of section 8.5 (frozen, slotted, documented fields, both keys hidden);
- the twenty-three-leaf agent_swarm prompt family with its format fields, and the prompt text rules (no digits, no role or workflow words, at least six sentences per system section, six to eight per tool and parameter description, the eight thoroughness headings);
- the agent_swarm_member runtime type and its refusal outside a swarm;
- the exact tools, in order, and the message and compact schemas each agent's model is offered, and the shared sectioned system prompt;
- settings validation, boundaries and defaults, the removed search_tool and reserved names, and API-key secrecy;
- the tool-result cap and the history trim every member's model call goes through;
- the twenty-four-row per-kind field table of AgentSwarmEvent and the sequence rules of AgentSwarmResult (one swarm_stopping before swarm_ended);
- the complexity budget, no polling, and the entry points' type checks.
ROLE IN CODEBASE: Contract layer of tests/features/agent_swarm/ (docs/spec/agent-swarm-v2/spec.md AC-2, AC-21, AC-22; INV-1, INV-2, INV-3, INV-11, INV-16, INV-18, INV-21, INV-36, INV-37, INV-38; EC-34; FR-1, FR-3, NFR-2; D-17, D-18; sections 8.4, 8.5, 9.2, 12.3).
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError (or, for the budget test, on the missing module) and the rest of the suite still collects. Tool offers and system prompts are read from what the scripted runner receives on each agent's first call, never from the swarm's internals.
FUNCTION INVENTORY: test_public_names_import_from_every_documented_path; test_records_and_settings_are_frozen_slotted_dataclasses_with_the_documented_fields; test_enum_values_are_the_documented_lowercase_strings; test_prompt_family_has_exactly_the_twenty_three_documented_leaves_with_their_fields; test_prompt_leaves_hold_no_digits_roles_or_examples; test_the_thoroughness_section_has_the_eight_headings_each_six_to_eight_sentences; test_runtime_type_refuses_outside_a_swarm_without_calling_a_model; test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_naming_every_agent; test_every_member_gets_the_same_sectioned_system_prompt_then_the_agentic_loop_prompt; test_invalid_settings_are_refused_naming_the_field_and_creating_nothing; test_the_search_tool_setting_and_the_reserved_names_are_gone; test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call; test_boundary_settings_are_accepted_with_documented_defaults; test_api_keys_never_appear_in_reprs_events_model_calls_or_errors; test_event_records_enforce_the_per_kind_field_table; test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended; test_new_modules_stay_inside_the_complexity_budget_and_never_sleep; test_entry_points_refuse_anything_but_their_documented_types.
COMMON MODIFICATION PATTERNS: When the spec adds a prompt leaf, add it to LEAF_FIELDS with its format fields. When a setting gains a bound, add one row to INVALID_SETTINGS with the field the error must name. When the spec adds an event kind, add a valid shape to VALID_EVENTS and its refusals to INVALID_EVENTS.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare tool descriptions or refusals to hand-written text; they come from the prompt catalog. 3. Do not loosen the exact tool-name list to a subset or set check; INV-38 is an exact, ordered list.
KNOWN EDGE CASES: A refusal's field may be named with an index suffix by a converter (AgentSwarmSettings.agents[1]), so field checks use startswith. Names in rendered prompts are joined with ", ", the separator the runtime already uses for the unknown-recipient reply. The trim test counts the history budget in characters with TOKEN_ESTIMATE_CHARS_PER_TOKEN, the four-characters-per-token estimate the trim uses; it reads one file that is three caps long, one more time than the budget holds plus one, and the cut ceiling allows a one-percent truncation notice. Sentence counting splits at . ! or ? followed by whitespace; a thoroughness subsection is the text between its heading line and the next one.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6.1, 6.2, 8.4, 8.5, 9.2 and 12.3.
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
    TAVILY_TOOL,
    EventLog,
    ScriptedSwarm,
    build_settings,
    build_swarm,
    error_text,
    member,
    prompt_text,
    reply,
    run_swarm,
    seen_text,
    send,
    shared_system_prompt,
    snapshot,
    tool_call,
    tool_results,
    web_search_fields,
    workplace_path,
)
from vidbyte import BaseAgent

REPO_ROOT = Path(__file__).resolve().parents[3]
NAMES = ("builder", "tester")
THREE = ("builder", "tester", "reviewer")
ROOT_NAMES = {"AgentSwarm", "AgentSwarmMember", "AgentSwarmSettings", "AgentSwarmEventKind", "AgentSwarmStopReason", "AgentSwarmWebSearch"}
PACKAGE_NAMES = {"AgentSwarm", "AgentSwarmSettings", "AgentSwarmRuntime", "AgentSwarmEvents", "AgentSwarmWorkplace", "AgentSwarmMemberRuntime"}
NEW_LIB_ENUMS = {"AgentSwarmWebSearch", "AgentSwarmCompactionTrigger", "AgentSwarmAgentState", "AgentSwarmFolderState"}
# INV-38: the five workplace tools, message, compact, (the search tool,) and the loop's isDone, in this order.
SWARM_TOOLS = ("bash", "grep", "read_lines", "write_text", "patch_file", "message", "compact")
# INV-1: the nine section leaves in their fixed order; the web-search section only when web_search is set.
SECTIONS = ("system_environment", "system_tools", "system_web_search", "system_messaging", "system_turns", "system_goal", "system_instructions", "system_objective", "system_thoroughness")
# INV-2: the eight thoroughness headings, in order.
THOROUGHNESS_HEADINGS = (
    "Every part delivered",
    "Claims backed by evidence",
    "Completion proven, not declared",
    "Problems fixed, not noted",
    "The hardest requirement met as written",
    "Nothing found means nothing looked",
    "Review your own work as a strict reviewer",
    "Simplify before you stop",
)

# The twenty-three leaves of spec section 8.5 / 12.3 rows 9-27 and the str.format fields each one takes.
LEAF_FIELDS: dict[str, set[str]] = {
    "system_environment": {"name", "peers", "workplace"},
    "system_tools": set(),
    "system_web_search": {"search_tool"},
    "system_messaging": {"peers"},
    "system_turns": set(),
    "system_goal": set(),
    "system_instructions": set(),
    "system_objective": set(),
    "system_thoroughness": set(),
    "message_tool_description": set(),
    "message_to_description": {"agents"},
    "message_text_description": set(),
    "message_sent": {"recipient"},
    "message_unknown_recipient": {"recipient", "agents"},
    "message_stopped_recipient": {"recipient"},
    "message_blank_text": set(),
    "inbox": {"messages"},
    "inbox_message": {"sender", "text"},
    "compact_tool_description": set(),
    "compact_focus_description": set(),
    "compact_requested": set(),
    "compaction_summarizer_prompt": {"focus"},
    "compaction_summary_prefix": set(),
}
# The r5 message descriptions keep their no-examples rule; FR-3 adds the two compact descriptions to the six-to-eight-sentence rule.
EXAMPLE_FREE_LEAVES = ("message_tool_description", "message_to_description", "message_text_description")
DESCRIPTION_LEAVES = (*EXAMPLE_FREE_LEAVES, "compact_tool_description", "compact_focus_description")
# The role and workflow vocabulary of the infinite_memory prompt family (every word below occurs there), which NFR-2 keeps out of the swarm prompt.
ROLE_WORDS = (r"\bgenerators?\b", r"\bverifiers?\b", r"\bsubagents?\b", r"\blaunch_subagent\b", r"\bdelegat\w*", r"\bscarcest\b")
# A sentence ends at . ! or ? (optionally followed by a closing quote, bracket or backtick) and then whitespace.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]`]*\s+")

# The seven package modules of section 12.2 (settings.py deleted, compaction.py new), the toolset, the observer module, and the lib enums, constants and records.
PACKAGE_MODULES = ("__init__.py", "swarm.py", "runtime.py", "events.py", "workplace.py", "member.py", "compaction.py")
BUDGET_MODULES = (
    *(f"vidbyte/agents/agent_swarm/{name}" for name in PACKAGE_MODULES),
    "vidbyte/tools/toolsets/agent_swarm.py",
    "vidbyte/middleware/builtins/agent_swarm_observer.py",
    "vidbyte/lib/enums/agent_swarm.py",
    "vidbyte/lib/constants/agent_swarm.py",
    "vidbyte/lib/dataclasses/agent_swarm.py",
)
# INV-37: no sleep or polling in the swarm package or its middleware.
SLEEP_FREE_MODULES = (
    *(f"vidbyte/agents/agent_swarm/{name}" for name in PACKAGE_MODULES),
    "vidbyte/tools/toolsets/agent_swarm.py",
    "vidbyte/middleware/builtins/agent_swarm_observer.py",
    "vidbyte/middleware/builtins/agent_swarm_turn.py",
)


def _sentences(text: str) -> list[str]:
    return [part for part in SENTENCE_BREAK.split(text.strip()) if part.strip()]


def _thoroughness_parts(text: str) -> tuple[str, list[tuple[str, str]]]:
    # The introduction, then each "## heading" with the text up to the next heading.
    pieces = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return pieces[0], [(pieces[index].strip(), pieces[index + 1]) for index in range(1, len(pieces), 2)]


# ---------------------------------------------------------------- exports, enums, catalog


def test_public_names_import_from_every_documented_path() -> None:
    """Section 9.2, AC-21: every documented import path works and yields the same objects; the six enums are exported, the registry and linear-loop set know the runtime, the internal parts subclass the SDK bases, and the contract lists the six root names."""
    import vidbyte
    import vidbyte.agents
    import vidbyte.middleware.builtins
    import vidbyte.tools.toolsets
    from vidbyte import AgentSwarm, AgentSwarmEventKind, AgentSwarmMember, AgentSwarmSettings, AgentSwarmStopReason, AgentSwarmWebSearch
    from vidbyte.agents import agent_swarm as package
    from vidbyte.agents.agent_swarm.compaction import AgentSwarmCompactTool, AgentSwarmHandoffSummarizer
    from vidbyte.agents.agent_swarm.member import AgentSwarmMemberAgent, AgentSwarmMessageTool, AgentSwarmTurnMiddleware
    from vidbyte.agents.base import _LINEAR_LOOP_RUNTIMES
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmEventCallback, AgentSwarmResult
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember as record_member
    from vidbyte.lib.enums import AgentRuntimeType
    from vidbyte.lib.enums.agent_swarm import AgentSwarmEventKind as enum_kind
    from vidbyte.lib.enums.agent_swarm import AgentSwarmStopReason as enum_stop
    from vidbyte.lib.enums.agent_swarm import AgentSwarmWebSearch as enum_search
    from vidbyte.lib.registries.runtimes import RuntimeRegistry
    from vidbyte.middleware.base import AgentMiddleware
    from vidbyte.middleware.builtins.agent_swarm_observer import AgentSwarmObserverMiddleware, AgentSwarmTrimMiddleware
    from vidbyte.middleware.compaction.context_compaction import MessageHistoryCompactionMiddleware
    from vidbyte.tools.base import BaseTool
    from vidbyte.tools.catalog import Tools
    from vidbyte.tools.toolsets import AgentSwarmTools

    # The package exports exactly its six names, and vidbyte.agents re-exports the same objects.
    assert sorted(package.__all__) == sorted(PACKAGE_NAMES)
    for name in PACKAGE_NAMES:
        assert getattr(vidbyte.agents, name) is getattr(package, name), name
        assert name in vidbyte.agents.__all__, name
    assert AgentSwarm is package.AgentSwarm and AgentSwarmSettings is package.AgentSwarmSettings
    assert AgentSwarmMember is record_member and AgentSwarmEventKind is enum_kind and AgentSwarmStopReason is enum_stop and AgentSwarmWebSearch is enum_search
    # Row 40: the root exports the six names and no other AgentSwarm name.
    assert {name for name in vidbyte.__all__ if name.startswith("AgentSwarm")} == ROOT_NAMES
    enums_package = importlib.import_module("vidbyte.lib.enums")
    assert {"AgentSwarmEventKind", "AgentSwarmStopReason", *NEW_LIB_ENUMS} <= set(enums_package.__all__)
    assert "AgentSwarmTools" in vidbyte.tools.toolsets.__all__ and issubclass(AgentSwarmTools, Tools)
    # The member loop is a registered linear-loop runtime; the member parts subclass the SDK bases.
    assert issubclass(package.AgentSwarmMemberRuntime, AgentRuntime)
    assert RuntimeRegistry.resolve(AgentRuntimeType.AGENT_SWARM_MEMBER) is package.AgentSwarmMemberRuntime
    assert AgentRuntimeType.AGENT_SWARM_MEMBER in _LINEAR_LOOP_RUNTIMES
    assert issubclass(AgentSwarmMemberAgent, BaseAgent) and AgentSwarmMemberAgent.session_persistence_supported is False
    assert issubclass(AgentSwarmMessageTool, BaseTool) and issubclass(AgentSwarmTurnMiddleware, AgentMiddleware)
    assert issubclass(AgentSwarmCompactTool, BaseTool) and callable(getattr(AgentSwarmHandoffSummarizer, "summarize", None))
    assert issubclass(AgentSwarmObserverMiddleware, AgentMiddleware) and issubclass(AgentSwarmTrimMiddleware, MessageHistoryCompactionMiddleware)
    assert AgentSwarmTurnMiddleware.fail_closed is True and AgentSwarmObserverMiddleware.fail_closed is True, "the swarm middleware keep the default fail_closed"
    # Row 30: the swarm middleware are built only by AgentSwarm and are not re-exported from vidbyte.middleware.builtins.
    assert not {"AgentSwarmObserverMiddleware", "AgentSwarmTrimMiddleware"} & set(getattr(vidbyte.middleware.builtins, "__all__", ()))
    # Section 8.5: the callback alias is Callable[[AgentSwarmEvent], None | Awaitable[None]].
    assert typing.get_origin(AgentSwarmEventCallback) is collections.abc.Callable
    parameters = typing.get_args(AgentSwarmEventCallback)[0]
    assert len(parameters) == 1 and (parameters[0] is AgentSwarmEvent or getattr(parameters[0], "__forward_arg__", "") == "AgentSwarmEvent")
    assert AgentSwarmResult.__module__ == "vidbyte.lib.dataclasses.agent_swarm"
    contract = json.loads((REPO_ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert ROOT_NAMES <= set(contract["exports"]), "the regenerated public-API contract must list the six root exports"


def test_records_and_settings_are_frozen_slotted_dataclasses_with_the_documented_fields() -> None:
    """Section 8.5, FR-1: the three records and the settings are frozen, slotted dataclasses whose fields are exactly the documented ones in order, and both keys are hidden from the repr."""
    from vidbyte import AgentSwarmMember, AgentSwarmSettings
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmResult

    expected = {
        AgentSwarmMember: ["name", "provider", "model_name"],
        AgentSwarmEvent: [
            "sequence", "kind", "agent", "elapsed_ms", "peer", "message_id", "text", "tool_name", "tool_status", "stop_reason",
            "input_tokens", "output_tokens", "cached_tokens", "model_calls", "messages_dropped", "omitted_chars", "path",
            "compaction_trigger", "agent_state", "folder_state",
        ],
        AgentSwarmResult: ["stop_reason", "events", "replies", "event_error_types"],
        AgentSwarmSettings: ["agents", "workplace", "api_keys", "web_search", "web_search_api_key", "on_event", "max_turns", "max_tokens", "timeout_seconds"],
    }
    for record, names in expected.items():
        assert dataclasses.is_dataclass(record), record.__name__
        assert [item.name for item in dataclasses.fields(record)] == names, record.__name__
        assert record.__dataclass_params__.frozen is True, f"{record.__name__} is not frozen"
        assert "__slots__" in record.__dict__, f"{record.__name__} is not slotted"
    hidden = {item.name for item in dataclasses.fields(AgentSwarmSettings) if not item.repr}
    assert hidden == {"api_keys", "web_search_api_key"}


def test_enum_values_are_the_documented_lowercase_strings() -> None:
    """Section 8.5: each swarm enum is a str enum whose values are exactly the documented lowercase names, and the runtime type has its value."""
    from vidbyte import AgentSwarmEventKind, AgentSwarmStopReason, AgentSwarmWebSearch
    from vidbyte.lib.enums import AgentRuntimeType, AgentSwarmAgentState, AgentSwarmCompactionTrigger, AgentSwarmFolderState

    expected: dict[type, set[str]] = {
        AgentSwarmEventKind: {
            "agent_started", "tool_called", "message_sent", "message_delivered", "agent_idle", "agent_woke", "agent_failed", "swarm_ended",
            "workplace_prepared", "agent_created", "message_refused", "wake_refused", "message_undelivered", "swarm_stopping",
            "agent_released", "agent_cancelled", "agent_exited", "model_called", "model_error", "history_trimmed",
            "tool_result_truncated", "file_changed", "command_failed", "compaction",
        },
        AgentSwarmStopReason: {"quiet", "max_turns", "timeout", "failed", "max_tokens"},
        AgentSwarmWebSearch: {"brave", "browserbase", "exa", "parallel", "tavily"},
        AgentSwarmCompactionTrigger: {"tool", "auto"},
        AgentSwarmAgentState: {"working", "idle"},
        AgentSwarmFolderState: {"created", "existed"},
    }
    for enum_type, values in expected.items():
        assert {item.value for item in enum_type} == values, enum_type.__name__
        assert all(isinstance(item, str) and item.value == item.name.lower() for item in enum_type), enum_type.__name__
    assert AgentRuntimeType("agent_swarm_member") is AgentRuntimeType.AGENT_SWARM_MEMBER


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_prompt_family_has_exactly_the_twenty_three_documented_leaves_with_their_fields() -> None:
    """AC-22, INV-1: Prompt.AGENT_SWARM_* is exactly the twenty-three leaves (system_prompt gone), each backed by non-blank catalog text whose str.format fields are exactly the documented ones."""
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
    """AC-22, INV-2, INV-3, NFR-2, FR-3: no leaf states a number, a role or a workflow; every system section has at least six sentences; each tool and parameter description has six to eight; the message descriptions give no examples; the sections name the swarm and every tool."""
    from vidbyte.prompts import Prompts

    family = Prompts().family("agent_swarm")
    assert set(family) == set(LEAF_FIELDS)
    for leaf, text in family.items():
        assert not re.search(r"\d", text), f"{leaf} holds a digit"
        for word in ROLE_WORDS:
            assert not re.search(word, text, re.IGNORECASE), f"{leaf} uses the role or workflow word {word!r}"
    for leaf in SECTIONS:
        body = _thoroughness_parts(family[leaf])[0] if leaf == "system_thoroughness" else family[leaf]
        assert len(_sentences(body)) >= 6, f"{leaf} has {len(_sentences(body))} sentences; INV-2 asks for at least six"
    for leaf in DESCRIPTION_LEAVES:
        count = len(_sentences(family[leaf]))
        assert 6 <= count <= 8, f"{leaf} has {count} sentences; FR-3 asks for six to eight"
    for leaf in EXAMPLE_FREE_LEAVES:
        assert not re.search(r"\be\.g\.|\bi\.e\.|\bfor (?:example|instance)\b|\bexamples?\b", family[leaf], re.IGNORECASE), f"{leaf} gives an example"
    assert "agent swarm" in family["system_environment"].lower()
    # Row 10: the tools section names every tool the agent holds and the loop's isDone.
    for tool in (*SWARM_TOOLS, "isDone"):
        assert tool in family["system_tools"], f"system_tools does not name {tool}"


def test_the_thoroughness_section_has_the_eight_headings_each_six_to_eight_sentences() -> None:
    """INV-2, AC-22: system_thoroughness holds an introduction of at least six sentences, then exactly the eight documented ## headings in order, each with six to eight sentences."""
    intro, sections = _thoroughness_parts(prompt_text("system_thoroughness"))
    assert len(_sentences(intro)) >= 6, f"the thoroughness introduction has {len(_sentences(intro))} sentences"
    assert [heading for heading, _ in sections] == list(THOROUGHNESS_HEADINGS)
    for heading, body in sections:
        count = len(_sentences(body))
        assert 6 <= count <= 8, f"## {heading} has {count} sentences"


def test_runtime_type_refuses_outside_a_swarm_without_calling_a_model() -> None:
    """Section 13 (r5 AC-12 kept): a plain BaseAgent cannot build the agent_swarm_member runtime; _runtime() raises the documented ConfigurationError and arun wraps it as the cause, with no model call."""
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
@pytest.mark.parametrize("search", ["no-web-search", "with-web-search"])
async def test_each_agent_holds_exactly_the_swarm_tools_and_a_message_schema_naming_every_agent(tmp_path: Path, search: str) -> None:
    """INV-38, INV-11, AC-2, FR-3: each agent's first call offers exactly the swarm tools in order, the search tool only when selected and right before isDone; message takes any name (no enum) and its description names every agent; compact takes one optional focus."""
    fields = web_search_fields() if search == "with-web-search" else {}
    expected = (*SWARM_TOOLS, *((TAVILY_TOOL,) if fields else ()), "isDone")
    scripted = ScriptedSwarm({name: [reply(f"{name} done.")] for name in THREE})
    with scripted.install():
        await run_swarm(build_swarm(tmp_path, THREE, **fields))

    for name in THREE:
        call = scripted.first_call(name)
        assert call.tools == expected, f"{name} was offered {call.tools}"
        schema = call.tool_schemas["message"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert set(schema["properties"]) == {"to", "text"} and set(schema["required"]) == {"to", "text"}
        assert schema["properties"]["to"]["type"] == "string" and schema["properties"]["text"]["type"] == "string"
        assert "enum" not in schema["properties"]["to"], f"{name}'s message.to still declares an enum"
        assert schema["properties"]["to"]["description"].strip() == prompt_text("message_to_description").format(agents=", ".join(THREE)).strip()
        assert schema["properties"]["text"]["description"].strip() == prompt_text("message_text_description").strip()
        assert call.tool_descriptions["message"].strip() == prompt_text("message_tool_description").strip()
        compact = call.tool_schemas["compact"]
        assert compact["type"] == "object" and compact["additionalProperties"] is False and set(compact["properties"]) == {"focus"}
        assert compact["properties"]["focus"]["type"] == "string" and "focus" not in compact.get("required", [])
        assert compact["properties"]["focus"]["description"].strip() == prompt_text("compact_focus_description").strip()
        assert call.tool_descriptions["compact"].strip() == prompt_text("compact_tool_description").strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("search", ["no-web-search", "with-web-search"])
async def test_every_member_gets_the_same_sectioned_system_prompt_then_the_agentic_loop_prompt(tmp_path: Path, search: str) -> None:
    """INV-1, EC-34, AC-1: each system string starts with the section leaves joined by one blank line (web search only when selected), rendered with only the member's name, its peers, the workplace verbatim (braces kept) and the search tool name, then the agentic-loop prompt; no member text is added."""
    from vidbyte.prompts.agentic_loop import agentic_loop_prompt

    fields = web_search_fields() if search == "with-web-search" else {}
    workplace = tmp_path / "swarm-{work}place"
    scripted = ScriptedSwarm({name: [reply(f"{name} done.")] for name in THREE})
    with scripted.install():
        await run_swarm(build_swarm(tmp_path, THREE, workplace=workplace, **fields))

    loop_text = agentic_loop_prompt().strip()
    for name in THREE:
        expected = shared_system_prompt(name, THREE, workplace.resolve(), search_tool=TAVILY_TOOL if fields else None)
        system = scripted.first_call(name).system
        loop_at = system.find(loop_text)
        assert loop_at > 0, f"the agentic-loop prompt is missing from {name}'s system string"
        # The "System prompt:" label is written by BaseContext.build_context_fixed (vidbyte/lib/dataclasses/context.py), shared by every agent.
        assert system[:loop_at].strip() == "System prompt:\n" + expected, f"{name}'s system prompt is not the shared section template"
        assert str(workplace.resolve()) in system


# ---------------------------------------------------------------- settings


def _member_fields(**override: Any) -> dict[str, Any]:
    return {"name": "builder", "provider": "openai", "model_name": MODEL, **override}


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
    pytest.param(_bad_member(provider="not-a-provider"), "AgentSwarmMember.provider", id="unknown-provider"),
    pytest.param(_bad_member(model_name="  "), "AgentSwarmMember.model_name", id="blank-model-name"),
    pytest.param(_bad_member(provider="anthropic", model_name="gpt-4.1"), "AgentSwarmMember.model_name", id="model-the-provider-cannot-run"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"),)), "AgentSwarmSettings.agents", id="one-agent"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"), member("builder"))), "AgentSwarmSettings.agents", id="two-agents-with-one-name"),
    pytest.param(_bad_settings(agents=lambda tmp: tuple(member(f"a{index}") for index in range(501))), "AgentSwarmSettings.agents", id="five-hundred-and-one-agents"),
    pytest.param(_bad_settings(agents=lambda tmp: (member("builder"), "tester")), "AgentSwarmSettings.agents", id="an-entry-that-is-not-a-member"),
    pytest.param(_bad_settings(max_turns=1), "AgentSwarmSettings.max_turns", id="max-turns-below-the-agent-count"),
    pytest.param(_bad_settings(max_turns=True), "AgentSwarmSettings.max_turns", id="max-turns-true"),
    pytest.param(_bad_settings(max_tokens=0), "AgentSwarmSettings.max_tokens", id="max-tokens-zero"),
    pytest.param(_bad_settings(max_tokens=True), "AgentSwarmSettings.max_tokens", id="max-tokens-true"),
    pytest.param(_bad_settings(max_tokens=1.5), "AgentSwarmSettings.max_tokens", id="max-tokens-not-an-integer"),
    pytest.param(_bad_settings(timeout_seconds=0), "AgentSwarmSettings.timeout_seconds", id="timeout-zero"),
    pytest.param(_bad_settings(timeout_seconds=-1.0), "AgentSwarmSettings.timeout_seconds", id="timeout-negative"),
    pytest.param(_bad_settings(timeout_seconds=math.nan), "AgentSwarmSettings.timeout_seconds", id="timeout-nan"),
    pytest.param(_bad_settings(timeout_seconds=math.inf), "AgentSwarmSettings.timeout_seconds", id="timeout-infinite"),
    pytest.param(_bad_settings(timeout_seconds=2_592_000.5), "AgentSwarmSettings.timeout_seconds", id="timeout-over-thirty-days"),
    pytest.param(_bad_settings(on_event="print"), "AgentSwarmSettings.on_event", id="on-event-not-callable"),
    pytest.param(_bad_settings(web_search="linkup", web_search_api_key="tvly-SwarmFakeKey0000AAAA1111"), "AgentSwarmSettings.web_search", id="web-search-not-a-provider"),
    pytest.param(_bad_settings(web_search="Tavily", web_search_api_key="tvly-SwarmFakeKey0000AAAA1111"), "AgentSwarmSettings.web_search", id="web-search-wrong-case"),
    pytest.param(_bad_settings(web_search=3, web_search_api_key="tvly-SwarmFakeKey0000AAAA1111"), "AgentSwarmSettings.web_search", id="web-search-not-text"),
    pytest.param(_bad_settings(web_search="tavily"), "AgentSwarmSettings.web_search_api_key", id="web-search-without-a-key"),
    pytest.param(_bad_settings(web_search="tavily", web_search_api_key="   "), "AgentSwarmSettings.web_search_api_key", id="web-search-with-a-blank-key"),
    pytest.param(_bad_settings(workplace=_a_file), "AgentSwarmSettings.workplace", id="workplace-is-a-file"),
]


@pytest.mark.parametrize(("build", "field"), INVALID_SETTINGS)
def test_invalid_settings_are_refused_naming_the_field_and_creating_nothing(tmp_path: Path, build: Callable[[Path], Any], field: str) -> None:
    """INV-18, AC-19, AC-20: each invalid member or setting raises ConfigurationError naming Record.field in the message and in details["field"], and leaves the disk as it was."""
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


def test_the_search_tool_setting_and_the_reserved_names_are_gone(tmp_path: Path) -> None:
    """D-17, D-18 (reverses the r5 isDone-named search tool refusal): search_tool is no longer a setting, AGENT_SWARM_RESERVED_TOOL_NAMES no longer exists, and no selectable web-search tool can shadow a swarm tool or the loop's isDone."""
    from vidbyte import AgentSwarmWebSearch
    from vidbyte.lib.constants import agent_swarm as constants
    from vidbyte.tools._internal import IS_DONE_TOOL_NAME
    from vidbyte.tools.toolsets import AgentSwarmTools

    with pytest.raises(TypeError):
        build_settings(tmp_path, NAMES, search_tool=object())
    assert not hasattr(constants, "AGENT_SWARM_RESERVED_TOOL_NAMES") and "AGENT_SWARM_RESERVED_TOOL_NAMES" not in constants.__all__
    for provider in AgentSwarmWebSearch:
        name = AgentSwarmTools.search_tool_for(provider, "tvly-SwarmFakeKey0000AAAA1111").name
        assert name not in (*SWARM_TOOLS, IS_DONE_TOOL_NAME), f"{provider.value}'s search tool is named {name}"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call(tmp_path: Path) -> None:
    """INV-36, INV-25 (r5 EC-26 kept, read through read_lines now that search_tool is gone): every result the model reads is cut near AGENT_SWARM_TOOL_RESULT_MAX_CHARS, far below its raw size, and once the cut results outgrow AGENT_SWARM_HISTORY_MAX_TOKENS the oldest drop out of what the next model call is sent."""
    from vidbyte.lib.constants.agent_swarm import (
        AGENT_SWARM_HISTORY_MAX_TOKENS,
        AGENT_SWARM_TOOL_RESULT_MAX_CHARS,
    )
    from vidbyte.lib.util.text import TOKEN_ESTIMATE_CHARS_PER_TOKEN

    # Every bound comes from the constants; the history budget is counted with the SDK's characters-per-token estimate.
    raw_chars = 3 * AGENT_SWARM_TOOL_RESULT_MAX_CHARS
    budget_chars = AGENT_SWARM_HISTORY_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN
    cut_ceiling = AGENT_SWARM_TOOL_RESULT_MAX_CHARS + AGENT_SWARM_TOOL_RESULT_MAX_CHARS // 100
    reads = budget_chars // AGENT_SWARM_TOOL_RESULT_MAX_CHARS + 2
    workplace_path(tmp_path).mkdir()
    (workplace_path(tmp_path) / "huge.txt").write_text("x" * raw_chars, encoding="utf-8")

    scripted = ScriptedSwarm({"builder": [*(tool_call("read_lines", {"path": "huge.txt"}) for _ in range(reads)), reply("Builder done.")], "tester": [reply("Tester done.")]})
    swarm = build_swarm(tmp_path, NAMES)
    with scripted.install():
        await run_swarm(swarm)

    builder_calls = scripted.calls_by("builder")
    assert len(builder_calls) == reads + 1
    for call in builder_calls:
        for name, content in tool_results(call):
            if name == "read_lines":
                assert len(content) <= cut_ceiling, f"a {len(content)}-character result reached the model; the cap is {AGENT_SWARM_TOOL_RESULT_MAX_CHARS}"
    last = builder_calls[-1]
    kept = [content for name, content in tool_results(last) if name == "read_lines"]
    assert 0 < len(kept) < reads, f"the last call kept {len(kept)} of {reads} results: the history was not trimmed"
    total = sum(len(str(message.get("content") or "")) for message in last.messages)
    assert total <= budget_chars, f"the last call sent {total} characters of history; the budget is {budget_chars}"
    assert last.system == builder_calls[0].system
    scripted.assert_complete()


def test_boundary_settings_are_accepted_with_documented_defaults(tmp_path: Path) -> None:
    """Section 8.5, section 9.3: boundary values pass, defaults are 100,000 turns, ten billion tokens and one day with no web search, the workplace is stored as a resolved Path, the provider as an enum, and the constants hold their documented values."""
    from vidbyte.lib.constants import agent_swarm as constants
    from vidbyte.lib.enums import ModelProvider

    settings = build_settings(tmp_path, NAMES)
    assert (settings.max_turns, settings.max_tokens, settings.timeout_seconds, settings.web_search, settings.web_search_api_key, settings.on_event) == (100_000, 10_000_000_000, 86_400.0, None, None, None)
    assert isinstance(settings.agents, tuple) and settings.agents == (member("builder"), member("tester"))
    assert settings.agents[0].provider is ModelProvider.OPENAI
    assert isinstance(settings.workplace, Path) and settings.workplace == workplace_path(tmp_path).resolve()
    assert build_settings(tmp_path, NAMES, workplace=str(tmp_path / "as-text")).workplace == (tmp_path / "as-text").resolve()
    hundred = tuple(member(f"a{index}") for index in range(100))
    assert len(build_settings(tmp_path, agents=hundred, max_turns=100).agents) == 100
    edge_names = (member("b" * 64), member("1-a_b"))
    build_settings(tmp_path, agents=edge_names, max_turns=2, timeout_seconds=604800.0)
    build_settings(tmp_path, NAMES, timeout_seconds=0.001, on_event=print, **web_search_fields())
    mixed = (member("builder"), member("reviewer", provider="anthropic", model_name="claude-sonnet-5"))
    assert build_settings(tmp_path, agents=mixed).agents[1].provider is ModelProvider.ANTHROPIC
    assert list(tmp_path.iterdir()) == []
    assert (constants.AGENT_SWARM_MIN_AGENTS, constants.AGENT_SWARM_MAX_AGENTS) == (2, 500)
    assert constants.AGENT_SWARM_NAME_PATTERN == r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
    assert (constants.AGENT_SWARM_DEFAULT_MAX_TURNS, constants.AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS, constants.AGENT_SWARM_MAX_TIMEOUT_SECONDS) == (100_000, 86_400.0, 2_592_000.0)
    assert (constants.AGENT_SWARM_MIN_TOKENS, constants.AGENT_SWARM_DEFAULT_MAX_TOKENS) == (1, 10_000_000_000)
    assert (constants.AGENT_SWARM_HISTORY_MAX_TOKENS, constants.AGENT_SWARM_TOOL_RESULT_MAX_CHARS) == (90_000, 100_000)
    assert (constants.AGENT_SWARM_COMPACTION_TRIGGER_TOKENS, constants.AGENT_SWARM_COMPACTION_TARGET_TOKENS) == (72_000, 27_000)
    assert (constants.AGENT_SWARM_MESSAGE_TOOL_NAME, constants.AGENT_SWARM_MESSAGE_TO_ARGUMENT, constants.AGENT_SWARM_MESSAGE_TEXT_ARGUMENT) == ("message", "to", "text")
    assert (constants.AGENT_SWARM_COMPACT_TOOL_NAME, constants.AGENT_SWARM_COMPACT_FOCUS_ARGUMENT) == ("compact", "focus")


@pytest.mark.asyncio
async def test_api_keys_never_appear_in_reprs_events_model_calls_or_errors(tmp_path: Path) -> None:
    """Section 10, INV-18: with api_keys set, no key text reaches a repr, an event, a model call or a refusal; a mixed swarm missing one provider's key is refused naming AgentSwarmSettings.api_keys."""
    from vidbyte import AgentSwarmStopReason
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    secret = "SwarmFakeKey"
    log = EventLog()
    settings = build_settings(tmp_path, NAMES, api_keys=[FAKE_OPENAI_KEY], on_event=log.callback)
    swarm = AgentSwarm(settings)
    for text in (repr(settings), str(settings), repr(swarm), repr(AgentSwarmRuntime(settings, workplace_path(tmp_path), workplace_created=True))):
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


def _new_enum(field: str, value: str) -> Any:
    from vidbyte.lib.enums import AgentSwarmAgentState, AgentSwarmCompactionTrigger, AgentSwarmFolderState

    enum_type = {"compaction_trigger": AgentSwarmCompactionTrigger, "agent_state": AgentSwarmAgentState, "folder_state": AgentSwarmFolderState}[field]
    return enum_type(value)


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
    # Section 8.5, INV-21: the sixteen kinds new in v2, each with exactly its own fields.
    ("message_sent", {"peer": "builder", "message_id": 5, "text": "a note to myself"}),
    ("workplace_prepared", {"sequence": 1, "agent": "", "path": "/swarm/workplace", "folder_state": "created"}),
    ("workplace_prepared", {"sequence": 1, "agent": "", "path": "/swarm/workplace", "folder_state": "existed"}),
    ("agent_created", {"sequence": 2}),
    ("message_refused", {"peer": "nobody", "text": "nobody is not an agent in this swarm."}),
    ("message_refused", {"peer": "", "text": "The message text is blank."}),
    ("wake_refused", {"agent": "tester", "peer": "builder", "message_id": 4}),
    ("message_undelivered", {"agent": "tester", "peer": "builder", "message_id": 4}),
    ("swarm_stopping", {"agent": "", "stop_reason": "max_tokens"}),
    ("agent_released", {}),
    ("agent_cancelled", {"agent_state": "working"}),
    ("agent_cancelled", {"agent_state": "idle"}),
    ("agent_exited", {"text": "middleware_abort"}),
    ("model_called", {"input_tokens": 3, "output_tokens": 2, "cached_tokens": 1, "model_calls": 1}),
    ("model_called", {}),
    ("model_error", {"text": "ProviderRequestError: openai returned 503"}),
    ("history_trimmed", {"messages_dropped": 2}),
    ("tool_result_truncated", {"tool_name": "read_lines", "omitted_chars": 2345}),
    ("file_changed", {"path": "/swarm/workplace/notes.md", "peer": ""}),
    ("file_changed", {"path": "/swarm/workplace/notes.md", "peer": "tester"}),
    ("command_failed", {"text": "exit code 3"}),
    ("command_failed", {"text": "timeout"}),
    ("compaction", {"compaction_trigger": "tool", "text": "keep the parser decisions", "input_tokens": 72000, "messages_dropped": 4}),
    ("compaction", {"compaction_trigger": "auto", "text": "", "input_tokens": 0, "messages_dropped": 1}),
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
    # Section 8.5, INV-21, row 4: the per-kind rules of the sixteen new kinds and the ten new fields.
    pytest.param("workplace_prepared", {"path": "/w", "folder_state": "created"}, "agent", id="prepared-with-agent"),
    pytest.param("workplace_prepared", {"agent": "", "folder_state": "created"}, "path", id="prepared-without-path"),
    pytest.param("workplace_prepared", {"agent": "", "path": "/w"}, "folder_state", id="prepared-without-folder-state"),
    pytest.param("workplace_prepared", {"agent": "", "path": "/w", "folder_state": "raw:created"}, "folder_state", id="prepared-folder-state-as-text"),
    pytest.param("agent_created", {"agent": ""}, "agent", id="created-without-agent"),
    pytest.param("agent_created", {"text": "hello"}, "text", id="created-with-text"),
    pytest.param("message_refused", {"peer": "nobody", "text": ""}, "text", id="refused-without-reason"),
    pytest.param("message_refused", {"peer": "nobody", "text": "no", "message_id": 4}, "message_id", id="refused-with-message-id"),
    pytest.param("wake_refused", {"agent": "tester", "message_id": 4}, "peer", id="wake-refused-without-sender"),
    pytest.param("wake_refused", {"agent": "tester", "peer": "builder", "message_id": 5}, "message_id", id="wake-refused-id-not-earlier"),
    pytest.param("message_undelivered", {"agent": "tester", "message_id": 4}, "peer", id="undelivered-without-sender"),
    pytest.param("message_undelivered", {"agent": "tester", "peer": "builder", "message_id": 0}, "message_id", id="undelivered-id-zero"),
    pytest.param("swarm_stopping", {"stop_reason": "quiet"}, "agent", id="stopping-with-agent"),
    pytest.param("swarm_stopping", {"agent": ""}, "stop_reason", id="stopping-without-stop-reason"),
    pytest.param("agent_released", {"text": "done"}, "text", id="released-with-text"),
    pytest.param("agent_cancelled", {}, "agent_state", id="cancelled-without-state"),
    pytest.param("agent_cancelled", {"agent_state": "raw:idle"}, "agent_state", id="cancelled-state-as-text"),
    pytest.param("agent_exited", {"text": "  "}, "text", id="exited-without-reason"),
    pytest.param("model_called", {"input_tokens": -1}, "input_tokens", id="model-called-negative-input"),
    pytest.param("model_called", {"output_tokens": True}, "output_tokens", id="model-called-bool-output"),
    pytest.param("model_called", {"cached_tokens": 1.5}, "cached_tokens", id="model-called-float-cached"),
    pytest.param("model_called", {"model_calls": -1}, "model_calls", id="model-called-negative-call-count"),
    pytest.param("model_called", {"text": "reply"}, "text", id="model-called-with-text"),
    pytest.param("model_error", {"text": ""}, "text", id="model-error-without-text"),
    pytest.param("history_trimmed", {"messages_dropped": -1}, "messages_dropped", id="trimmed-negative"),
    pytest.param("history_trimmed", {"messages_dropped": 2, "input_tokens": 9}, "input_tokens", id="trimmed-with-input-tokens"),
    pytest.param("tool_result_truncated", {"omitted_chars": 5}, "tool_name", id="truncated-without-tool-name"),
    pytest.param("tool_result_truncated", {"tool_name": "bash", "omitted_chars": -5}, "omitted_chars", id="truncated-negative"),
    pytest.param("file_changed", {"peer": "tester"}, "path", id="file-changed-without-path"),
    pytest.param("file_changed", {"path": "/w/a", "text": "x"}, "text", id="file-changed-with-text"),
    pytest.param("command_failed", {"text": ""}, "text", id="command-failed-without-text"),
    pytest.param("compaction", {"text": "f", "input_tokens": 1, "messages_dropped": 1}, "compaction_trigger", id="compaction-without-trigger"),
    pytest.param("compaction", {"compaction_trigger": "raw:tool"}, "compaction_trigger", id="compaction-trigger-as-text"),
    pytest.param("compaction", {"compaction_trigger": "tool", "messages_dropped": -1}, "messages_dropped", id="compaction-negative-dropped"),
    pytest.param("tool_called", {"tool_name": "bash", "tool_status": "success", "omitted_chars": 3}, "omitted_chars", id="tool-called-with-omitted-chars"),
    pytest.param("agent_started", {"path": "/w"}, "path", id="started-with-path"),
    pytest.param("agent_idle", {"agent_state": "idle"}, "agent_state", id="idle-with-agent-state"),
    pytest.param("swarm_ended", {"agent": "", "stop_reason": "quiet", "folder_state": "created"}, "folder_state", id="ended-with-folder-state"),
    pytest.param("agent_released", {"compaction_trigger": "auto"}, "compaction_trigger", id="released-with-trigger"),
    pytest.param("message_sent", {"peer": "tester", "message_id": 5, "text": "hi", "model_calls": 1}, "model_calls", id="sent-with-model-calls"),
]


def _coerce(fields: dict[str, Any]) -> dict[str, Any]:
    # Statuses, stop reasons and the three new enum fields are written as values in the tables above; records take enum members.
    # A "raw:<value>" entry keeps the value string, which the record must refuse.
    values = dict(fields)
    if isinstance(values.get("tool_status"), str):
        values["tool_status"] = _status(values["tool_status"])
    if isinstance(values.get("stop_reason"), str):
        values["stop_reason"] = _stop(values["stop_reason"])
    for name in ("compaction_trigger", "agent_state", "folder_state"):
        if isinstance(values.get(name), str):
            raw = values[name]
            values[name] = raw.removeprefix("raw:") if raw.startswith("raw:") else _new_enum(name, raw)
    return values


@pytest.mark.parametrize(("kind", "fields", "field"), INVALID_EVENTS)
def test_event_records_enforce_the_per_kind_field_table(kind: str, fields: dict[str, Any], field: str) -> None:
    """INV-21, section 8.5: every documented event shape builds; a missing required field, a set field the kind does not list, or a bad number raises ConfigurationError naming AgentSwarmEvent.<field>."""
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


# INV-16: a quiet run now records its swarm_stopping, with the same stop reason, before swarm_ended.
QUIET_RUN = (
    ("agent_started", {}),
    ("agent_started", {"agent": "tester"}),
    ("agent_idle", {}),
    ("agent_idle", {"agent": "tester"}),
    ("swarm_stopping", {"agent": "", "stop_reason": "quiet"}),
    ("swarm_ended", {"agent": "", "stop_reason": "quiet"}),
)

INVALID_RESULTS = [
    pytest.param(lambda: {"events": ()}, ("events",), id="no-events"),
    pytest.param(lambda: {"events": tuple(_events(*QUIET_RUN)[index] for index in (0, 1, 3, 4, 5))}, ("events",), id="a-gap-in-the-sequence"),
    pytest.param(lambda: {"events": _events(*QUIET_RUN[:-1])}, ("events",), id="no-swarm-ended"),
    pytest.param(lambda: {"events": _events(QUIET_RUN[0], QUIET_RUN[4], QUIET_RUN[5], QUIET_RUN[2])}, ("events",), id="swarm-ended-not-last"),
    pytest.param(lambda: {"events": _events(QUIET_RUN[0], QUIET_RUN[4], QUIET_RUN[5], QUIET_RUN[5])}, ("events",), id="two-swarm-ended"),
    pytest.param(lambda: {"events": _events(*QUIET_RUN[:4], QUIET_RUN[5])}, ("events",), id="no-swarm-stopping"),
    pytest.param(lambda: {"events": _events(*QUIET_RUN[:5], QUIET_RUN[4], QUIET_RUN[5])}, ("events",), id="two-swarm-stopping"),
    pytest.param(lambda: {"events": _events(*QUIET_RUN[:4], ("swarm_stopping", {"agent": "", "stop_reason": "max_turns"}), QUIET_RUN[5])}, ("events",), id="swarm-stopping-with-another-reason"),
    pytest.param(lambda: {"stop_reason": _stop("max_turns")}, ("events", "stop_reason"), id="stop-reason-differs-from-swarm-ended"),
    pytest.param(lambda: {"stop_reason": "quiet"}, ("stop_reason",), id="stop-reason-as-text"),
    pytest.param(lambda: {"replies": ("builder done.",)}, ("replies",), id="a-reply-that-is-not-an-agent-message"),
    pytest.param(lambda: {"event_error_types": ("",)}, ("event_error_types",), id="blank-error-type"),
    pytest.param(lambda: {"event_error_types": ("Callback\nBoom",)}, ("event_error_types",), id="two-line-error-type"),
]


@pytest.mark.parametrize(("override", "fields"), INVALID_RESULTS)
def test_result_records_enforce_one_ordered_sequence_ending_in_swarm_ended(override: Callable[[], dict[str, Any]], fields: tuple[str, ...]) -> None:
    """INV-16: a result holds events numbered 1..N ending in its one swarm_ended, preceded by exactly one swarm_stopping, both with the result's stop reason, AgentMessage replies, and one-line error type names; anything else raises ConfigurationError naming the field."""
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmResult
    from vidbyte.lib.errors import ConfigurationError

    valid = {"stop_reason": _stop("quiet"), "events": _events(*QUIET_RUN), "replies": (_reply("builder"), _reply("tester")), "event_error_types": ("CallbackBoom",)}
    built = AgentSwarmResult(**{**valid, "events": list(valid["events"])})
    assert isinstance(built.events, tuple) and len(built.events) == 6
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
    """Section 8.4, section 12.2, INV-37: the package has its seven modules (compaction.py in, settings.py out) and no more, each budgeted module is at most 400 lines after its header, and no swarm module or swarm middleware sleeps or polls."""
    package = REPO_ROOT / "vidbyte" / "agents" / "agent_swarm"
    assert package.is_dir(), "vidbyte/agents/agent_swarm does not exist"
    assert sorted(path.name for path in package.glob("*.py")) == sorted(PACKAGE_MODULES)
    for relative in BUDGET_MODULES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is missing"
        assert _lines_after_header(path) <= 400, f"{relative} is over 400 lines after its header"
    for relative in SLEEP_FREE_MODULES:
        assert _sleep_calls(REPO_ROOT / relative) == [], f"{relative} sleeps (INV-37: no polling)"


def test_entry_points_refuse_anything_but_their_documented_types(tmp_path: Path) -> None:
    """Section 9.2: AgentSwarm takes only an AgentSwarmSettings, AgentSwarmRuntime only an AgentSwarmSettings and a Path (plus its workplace_created flag); each refusal is a ConfigurationError and touches no disk."""
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmRuntime
    from vidbyte.lib.errors import ConfigurationError

    settings = build_settings(tmp_path, NAMES)
    for bad in (object(), None, {"agents": NAMES, "workplace": str(workplace_path(tmp_path))}):
        with pytest.raises(ConfigurationError):
            AgentSwarm(bad)
    with pytest.raises(ConfigurationError):
        AgentSwarmRuntime(object(), workplace_path(tmp_path), workplace_created=True)
    with pytest.raises(ConfigurationError):
        AgentSwarmRuntime(settings, str(workplace_path(tmp_path)), workplace_created=True)
    assert snapshot(tmp_path) == {} and list(tmp_path.iterdir()) == []
