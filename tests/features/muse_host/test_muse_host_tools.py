"""FILE: tests/features/muse_host/test_muse_host_tools.py

PURPOSE: The twelve Muse tools of spec §9.2 rows 29-40 and MuseTools: names, permissions, parameters and JSON types, read_only (T-5), the default-policy split (AC-15), success results and their metadata, the Muse-specific argument parsing (enum values, the handle object), and the tool-only rows EC-144 and EC-145.
ROLE IN CODEBASE: Proves FR-5 and INV-7 for vidbyte.tools.builtins.muse and vidbyte.tools.toolsets.muse. The shared tool rows EC-138 to EC-143 are proven once in the grok_host pack; this file adds only what differs for Muse.
ARCHITECTURE NOTE: Tools run against a real MuseHost on the fake muse, either directly through Tool.execute or through ToolExecutor with the default PermissionPolicy. Handles travel between tools as JSON objects {harness, session_id, turn_id}.
FUNCTION INVENTORY: pascal_tool_class gives the §8.5 class name; tools_of indexes a toolset by name; execute runs one tool; handle_object reads the handle from a spawn result; the test_* functions check one rule each.
COMMON MODIFICATION PATTERNS: When §9.2 changes a Muse row, change TOOL_TABLE and PARAMETER_TYPES together.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a permission, approval or directory parameter to TOOL_TABLE; tools never pass permission fields (D-11, T-2). 2. Do not re-prove EC-138 to EC-143 for every tool; the grok_host pack owns the shared rows.
KNOWN EDGE CASES: wait_muse_turn defaults timeout_seconds to 60 and refuses more than NATIVE_TOOL_WAIT_MAX_SECONDS (240) even though the host method accepts up to 3600. A WRITE tool denied by the executor never reaches the host, so nothing is launched.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.7, §8.5 Tools, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_tools.py
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

PROMPT = "List the top-level folders."
KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
UNISSUED_TURN_ID = "b" * 32
WAIT_SECONDS = 30
# §9.2 rows 29-40: tool name -> (permission, {parameter: required}).
TOOL_TABLE: dict[str, tuple[str, dict[str, bool]]] = {
    "check_muse_ready": ("read", {}),
    "list_muse_models": ("read", {}),
    "spawn_muse_session": ("write", {"prompt": True, "model": False, "reasoning_effort": False, "max_turn_seconds": False}),
    "continue_muse_session": ("write", {"session_id": True, "prompt": True, "model": False, "reasoning_effort": False, "max_turn_seconds": False}),
    "fork_muse_session": ("write", {"session_id": True, "last_turn_id": False}),
    "list_muse_sessions": ("read", {"cursor": False, "limit": False}),
    "read_muse_session": ("read", {"session_id": True}),
    "page_muse_session": ("read", {"session_id": True, "cursor": False, "limit": False, "direction": False}),
    "steer_muse_turn": ("write", {"handle": True, "text": True}),
    "interrupt_muse_turn": ("write", {"handle": True}),
    "wait_muse_turn": ("read", {"handle": True, "timeout_seconds": False}),
    "track_muse_session_usage": ("read", {"session_id": True}),
}
PARAMETER_TYPES = {
    "prompt": "string", "model": "string", "reasoning_effort": "string", "max_turn_seconds": "number", "session_id": "string", "last_turn_id": "string",
    "cursor": "string", "limit": "integer", "direction": "string", "handle": "object", "text": "string", "timeout_seconds": "number",
}
FORBIDDEN_PARAMETERS = {"approval_mode", "approvalMode", "permission", "permissions", "allow_all", "yolo", "cwd", "workspace", "workspace_root", "muse_command", "muse_path", "wsl_distro"}


def pascal_tool_class(tool_name: str) -> str:
    return "".join(part.capitalize() for part in tool_name.split("_")) + "Tool"


def tools_of(toolset: Any) -> dict[str, Any]:
    return {tool.name: tool for tool in toolset.all()}


async def execute(tools_api: Any, toolset: Any, name: str, arguments: dict[str, Any]) -> Any:
    return await tools_of(toolset)[name].execute(tools_api.ToolCall(name, arguments))


def handle_object(payload: dict[str, Any]) -> dict[str, Any]:
    # The spawn tool's JSON output carries the handle as {harness, session_id, turn_id}.
    handle = payload.get("handle", payload)
    return {key: handle[key] for key in ("harness", "session_id", "turn_id")}


def test_muse_tools_match_the_spec_table(muse_tools_api, muse_fake, make_muse_host) -> None:
    # §9.2 rows 29-40: names, permissions, parameters and JSON types; building the toolset starts nothing.
    tools = tools_of(muse_tools_api.MuseTools(make_muse_host()))
    assert set(tools) == set(TOOL_TABLE)
    for name, (permission, parameters) in TOOL_TABLE.items():
        spec = tools[name].spec()
        assert spec.name == name
        assert spec.permission is muse_tools_api.ToolPermission(permission), name
        assert {parameter.name: parameter.required for parameter in spec.parameters} == parameters, name
        for parameter in spec.parameters:
            assert parameter.type == PARAMETER_TYPES[parameter.name], (name, parameter.name)
    assert muse_fake.starts() == []


def test_wait_tool_defaults_its_timeout_to_sixty_seconds(muse_tools_api, make_muse_host) -> None:
    # §9.2 row 39: timeout_seconds (default 60).
    spec = tools_of(muse_tools_api.MuseTools(make_muse_host()))["wait_muse_turn"].spec()
    timeout = next(parameter for parameter in spec.parameters if parameter.name == "timeout_seconds")
    assert timeout.default == 60


def test_no_muse_tool_offers_an_approval_launcher_or_directory_parameter(muse_tools_api, make_muse_host) -> None:
    # AC-19 / INV-9 / T-2: tool parameters cannot carry an approval mode, a launcher or a directory.
    for tool in muse_tools_api.MuseTools(make_muse_host()).all():
        names = {parameter.name for parameter in tool.spec().parameters}
        assert not names & FORBIDDEN_PARAMETERS, (tool.name, names & FORBIDDEN_PARAMETERS)


def test_read_only_returns_exactly_the_read_tools(muse_tools_api, make_muse_host) -> None:
    # T-5: read_only(host) is what MCP exposure gets.
    read_only = tools_of(muse_tools_api.MuseTools.read_only(make_muse_host()))
    expected = {name for name, (permission, _) in TOOL_TABLE.items() if permission == "read"}
    assert set(read_only) == expected == {
        "check_muse_ready", "list_muse_models", "list_muse_sessions", "read_muse_session", "page_muse_session", "wait_muse_turn", "track_muse_session_usage",
    }
    assert all(tool.spec().permission is muse_tools_api.ToolPermission.READ for tool in read_only.values())


def test_tool_classes_are_named_after_their_functions_and_exported(muse_tools_api) -> None:
    # §8.5: one class per tool named <FunctionInPascalCase>Tool, exported from vidbyte.tools.builtins.muse.
    package = muse_tools_api.muse_tools_module
    base = importlib.import_module("vidbyte.tools.builtins.native_host_tool")
    for name in TOOL_TABLE:
        assert hasattr(package, pascal_tool_class(name)), pascal_tool_class(name)
        assert issubclass(getattr(package, pascal_tool_class(name)), base.NativeHostTool)
    assert "MuseTools" in importlib.import_module("vidbyte.tools.toolsets").__all__


@pytest.mark.asyncio
async def test_default_policy_denies_the_write_tool_and_runs_the_read_tool(muse_tools_api, muse_fake, make_muse_host, fast_stop) -> None:
    # AC-15 / EC-142 for Muse: the default PermissionPolicy allows SAFE and READ only.
    async with make_muse_host() as host:
        executor = muse_tools_api.ToolExecutor(muse_tools_api.MuseTools(host))
        denied = await executor.execute_call(muse_tools_api.ToolCall("spawn_muse_session", {"prompt": PROMPT}))
        launched_after_denial = list(muse_fake.launches())
        allowed = await executor.execute_call(muse_tools_api.ToolCall("list_muse_sessions", {}))
    assert denied.status is muse_tools_api.ToolStatus.ERROR
    assert denied.metadata["error"] == "permission_denied"
    assert launched_after_denial == [], "a denied WRITE tool never reaches the host"
    assert allowed.status is muse_tools_api.ToolStatus.SUCCESS, allowed.output
    assert json.loads(allowed.output)["sessions"][0]["session_id"] == KNOWN_SESSION


@pytest.mark.asyncio
async def test_spawn_then_wait_round_trips_the_handle_and_reports_success_metadata(muse_tools_api, make_muse_host, fast_stop) -> None:
    # §9.2 Tool results: sorted-key JSON output and metadata {harness, operation, truncated}.
    async with make_muse_host() as host:
        tools = muse_tools_api.MuseTools(host)
        spawned = await execute(muse_tools_api, tools, "spawn_muse_session", {"prompt": PROMPT, "reasoning_effort": "low"})
        assert spawned.status is muse_tools_api.ToolStatus.SUCCESS, spawned.output
        handle = handle_object(json.loads(spawned.output))
        waited = await execute(muse_tools_api, tools, "wait_muse_turn", {"handle": handle, "timeout_seconds": WAIT_SECONDS})
    assert handle["harness"] == "muse" and len(handle["turn_id"]) == 32
    assert waited.status is muse_tools_api.ToolStatus.SUCCESS, waited.output
    payload = json.loads(waited.output)
    assert payload["status"] == "completed" and payload["text"] == "alpha\n\nbeta"
    assert list(payload) == sorted(payload), "keys are sorted"
    assert waited.metadata == {"harness": "muse", "operation": "wait_muse_turn", "truncated": False}
    assert spawned.metadata["operation"] == "spawn_muse_session" and spawned.metadata["harness"] == "muse"


@pytest.mark.asyncio
async def test_page_tool_parses_the_direction_value(muse_tools_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §9.2 row 36: direction is the MuseViewDirection value string and reaches the wire unchanged.
    async with make_muse_host() as host:
        result = await execute(muse_tools_api, muse_tools_api.MuseTools(host), "page_muse_session", {"session_id": KNOWN_SESSION, "direction": "backward", "limit": 3})
    assert result.status is muse_tools_api.ToolStatus.SUCCESS, result.output
    params = muse_fake.received("view/page")[0]["params"]
    assert params["direction"] == "backward" and params["limit"] == 3


MUSE_ARGUMENT_CASES = [
    pytest.param("spawn_muse_session", {"prompt": PROMPT, "reasoning_effort": "maximum"}, "reasoning_effort", id="spawn-effort-unknown"),
    pytest.param("continue_muse_session", {"session_id": "not-a-uuid", "prompt": PROMPT}, "session_id", id="continue-session-format"),
    pytest.param("fork_muse_session", {"session_id": KNOWN_SESSION, "last_turn_id": ""}, "last_turn_id", id="fork-last-turn-empty"),
    pytest.param("page_muse_session", {"session_id": KNOWN_SESSION, "direction": "sideways"}, "direction", id="page-direction-unknown"),
    pytest.param("page_muse_session", {"session_id": KNOWN_SESSION, "limit": 201}, "limit", id="page-limit-over"),
    pytest.param("list_muse_sessions", {"limit": "ten"}, "limit", id="list-limit-type"),
    pytest.param("steer_muse_turn", {"handle": {"harness": "muse", "session_id": KNOWN_SESSION, "turn_id": UNISSUED_TURN_ID}, "text": ""}, "text", id="steer-text-empty"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "arguments", "token"), MUSE_ARGUMENT_CASES)
async def test_bad_muse_arguments_return_invalid_argument_naming_the_parameter(tool_name: str, arguments: dict[str, Any], token: str, muse_tools_api, muse_fake, make_muse_host, fast_stop, check_tool_error) -> None:
    # EC-138 for the Muse-only parameters (enum values, session id format, limits); nothing starts.
    async with make_muse_host() as host:
        result = await execute(muse_tools_api, muse_tools_api.MuseTools(host), tool_name, arguments)
    check_tool_error(result, code="configuration.invalid_argument", token=token, tool_name=tool_name)
    assert muse_fake.launches() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [240.5, 241, 3600], ids=["just-over", "integer-over", "host-cap"])
async def test_wait_tool_refuses_a_timeout_above_the_tool_cap(timeout_seconds: float, muse_api, muse_tools_api, make_muse_host, fast_stop, check_tool_error) -> None:
    # EC-144: NATIVE_TOOL_WAIT_MAX_SECONDS (240) keeps a tool call under Codex's 300 s cutoff.
    assert muse_api.constants.NATIVE_TOOL_WAIT_MAX_SECONDS == 240.0
    handle = {"harness": "muse", "session_id": KNOWN_SESSION, "turn_id": UNISSUED_TURN_ID}
    async with make_muse_host() as host:
        result = await execute(muse_tools_api, muse_tools_api.MuseTools(host), "wait_muse_turn", {"handle": handle, "timeout_seconds": timeout_seconds})
    check_tool_error(result, code="configuration.invalid_argument", token="timeout_seconds", tool_name="wait_muse_turn")


@pytest.mark.asyncio
async def test_wait_tool_accepts_exactly_the_cap(muse_tools_api, make_muse_host, fast_stop) -> None:
    async with make_muse_host() as host:
        tools = muse_tools_api.MuseTools(host)
        spawned = await execute(muse_tools_api, tools, "spawn_muse_session", {"prompt": PROMPT})
        waited = await execute(muse_tools_api, tools, "wait_muse_turn", {"handle": handle_object(json.loads(spawned.output)), "timeout_seconds": 240})
    assert waited.status is muse_tools_api.ToolStatus.SUCCESS, waited.output


EC145_CASES = [
    pytest.param("steer_muse_turn", "not-a-handle", id="steer-string"),
    pytest.param("steer_muse_turn", {"harness": "muse", "session_id": KNOWN_SESSION}, id="steer-missing-turn"),
    pytest.param("interrupt_muse_turn", {"harness": "muse", "session_id": 5, "turn_id": UNISSUED_TURN_ID}, id="interrupt-number-field"),
    pytest.param("interrupt_muse_turn", ["muse", KNOWN_SESSION, UNISSUED_TURN_ID], id="interrupt-list"),
    pytest.param("wait_muse_turn", {"harness": None, "session_id": KNOWN_SESSION, "turn_id": UNISSUED_TURN_ID}, id="wait-null-harness"),
    pytest.param("wait_muse_turn", 42, id="wait-number"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "handle"), EC145_CASES)
async def test_malformed_handle_argument_returns_invalid_argument(tool_name: str, handle: Any, muse_tools_api, make_muse_host, fast_stop, check_tool_error) -> None:
    # EC-145: handle must be an object with string harness, session_id and turn_id.
    arguments: dict[str, Any] = {"handle": handle}
    if tool_name == "steer_muse_turn":
        arguments["text"] = "Also list hidden folders."
    async with make_muse_host() as host:
        result = await execute(muse_tools_api, muse_tools_api.MuseTools(host), tool_name, arguments)
    check_tool_error(result, code="configuration.invalid_argument", token="handle", tool_name=tool_name)


@pytest.mark.asyncio
async def test_unopened_host_through_a_tool_returns_process_exited(muse_tools_api, make_muse_host, check_tool_error) -> None:
    # EC-2 in tool mode: the tool returns the error and does not raise.
    result = await execute(muse_tools_api, muse_tools_api.MuseTools(make_muse_host()), "list_muse_sessions", {})
    check_tool_error(result, code="muse.process_exited", token="async with", tool_name="list_muse_sessions")
