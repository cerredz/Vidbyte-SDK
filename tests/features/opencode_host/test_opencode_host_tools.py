"""FILE: tests/features/opencode_host/test_opencode_host_tools.py

PURPOSE: The 18 model-facing opencode tools: OpencodeTools and read_only (§9.2 rows 11-28, T-5), the executor's default policy (AC-15, EC-142), the success encoding (§9.2 Success), argument failures (EC-138), the tool-only rows (EC-144, EC-145, EC-146) and the tool parameters that must not exist (AC-19, INV-9, T-2).
ROLE IN CODEBASE: Start here when an opencode tool offers the wrong parameter, mis-encodes a result, or reaches the server when it should not. The host error rows in tool mode live in test_opencode_host_errors.py; the shared tool base (EC-140, EC-141, EC-143) is covered once in tests/features/grok_host.
ARCHITECTURE NOTE: Tools wrap a real OpencodeHost on FakeOpencodeServer; nothing in the tool base is mocked. A refused call is proved by comparing the recorded routes before and after it, so a tool that reached the server fails even when it returned the right error.
FUNCTION INVENTORY: TOOL_TABLE is §9.2 rows 11-28; tools_of maps names to tools; execute runs one tool by name; handle_object reads the handle from a spawn result; sorted_everywhere checks JSON key order; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When §9.2 changes, update TOOL_TABLE first; every other test reads it.
WHAT NOT TO DO IN THIS FILE: 1. Do not grant PermissionPolicy.allow_all() in the AC-15 test; the default policy is the point. 2. Do not compare tool output text byte for byte; decode the JSON and compare fields.
KNOWN EDGE CASES: A direct execute() with a missing required parameter is EC-138, while the same call through ToolExecutor is the executor's unchanged validation_error. The add tool takes only a registered name (EC-146), so the body it sends must be the registered config.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.7, §8.5 (Tools, Toolsets), §9.2, §10 T-2 and T-5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_tools.py
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

PROMPT = "List the top-level folders."
KNOWN_SESSION = "ses_known0001"
KNOWN_MESSAGE = "msg_00000002"
UNISSUED_HANDLE = {"harness": "opencode", "session_id": KNOWN_SESSION, "turn_id": "0" * 32}
EC146_NEXT_STEP = "Register the MCP server in OpencodeHostSettings.mcp_servers; the tool only adds registered servers."
# §9.2 rows 11-28: tool name -> (permission, {parameter: required}).
TOOL_TABLE: dict[str, tuple[str, dict[str, bool]]] = {
    "check_opencode_ready": ("read", {}),
    "list_opencode_models": ("read", {"provider_id": False}),
    "list_opencode_providers": ("read", {}),
    "get_opencode_provider_auth": ("read", {}),
    "spawn_opencode_session": ("write", {"prompt": True, "model": False, "agent": False, "title": False, "max_turn_seconds": False}),
    "continue_opencode_session": ("write", {"session_id": True, "prompt": True, "model": False, "agent": False, "max_turn_seconds": False}),
    "fork_opencode_session": ("write", {"session_id": True, "message_id": False}),
    "revert_opencode_session": ("write", {"session_id": True, "message_id": True, "part_id": False}),
    "unrevert_opencode_session": ("write", {"session_id": True}),
    "list_opencode_sessions": ("read", {"limit": False}),
    "get_opencode_session": ("read", {"session_id": True}),
    "get_opencode_session_messages": ("read", {"session_id": True, "limit": False, "before": False}),
    "get_opencode_message": ("read", {"session_id": True, "message_id": True}),
    "get_opencode_session_diff": ("read", {"session_id": True, "message_id": False}),
    "wait_opencode_turn": ("read", {"handle": True, "timeout_seconds": False}),
    "interrupt_opencode_turn": ("write", {"handle": True}),
    "track_opencode_session_usage": ("read", {"session_id": True}),
    "add_opencode_mcp_server": ("write", {"name": True}),
}
PARAMETER_TYPES = {
    "prompt": "string", "model": "string", "agent": "string", "title": "string", "session_id": "string", "message_id": "string", "part_id": "string",
    "before": "string", "provider_id": "string", "name": "string", "max_turn_seconds": "number", "timeout_seconds": "number", "limit": "integer", "handle": "object",
}
FORBIDDEN_PARAMETERS = {
    "permission_rules", "permission", "rules", "action", "cwd", "directory", "workspace", "command", "url", "environment", "headers",
    "server_url", "server_password", "opencode_command", "always_approve", "yolo",
}


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


def sorted_everywhere(value: Any) -> bool:
    # json.loads keeps the text's key order, so sorted keys at every level show the encoder sorted them.
    if isinstance(value, dict):
        return list(value) == sorted(value) and all(sorted_everywhere(item) for item in value.values())
    if isinstance(value, list):
        return all(sorted_everywhere(item) for item in value)
    return True


def test_opencode_tools_match_the_spec_table(opencode_tools_api, make_opencode_host, fake_opencode) -> None:
    # §9.2 rows 11-28: names, permissions and parameters; building the toolset sends nothing.
    tools = tools_of(opencode_tools_api.OpencodeTools(make_opencode_host()))
    assert set(tools) == set(TOOL_TABLE)
    for name, (permission, parameters) in TOOL_TABLE.items():
        spec = tools[name].spec()
        assert spec.name == name
        assert spec.permission is opencode_tools_api.ToolPermission(permission), name
        declared = {parameter.name: parameter.required for parameter in spec.parameters}
        assert declared == parameters, name
        for parameter in spec.parameters:
            assert parameter.type == PARAMETER_TYPES[parameter.name], (name, parameter.name)
    assert fake_opencode.requests == []


def test_no_opencode_tool_offers_a_permission_directory_or_mcp_shape_parameter(opencode_tools_api, make_opencode_host) -> None:
    # AC-19 / INV-9 / T-2 / D-11: no tool can pass rules, a directory, or an MCP command, URL, env value or header.
    for tool in opencode_tools_api.OpencodeTools(make_opencode_host()).all():
        names = {parameter.name for parameter in tool.spec().parameters}
        assert not names & FORBIDDEN_PARAMETERS, (tool.name, names & FORBIDDEN_PARAMETERS)


def test_read_only_returns_exactly_the_read_tools(opencode_tools_api, make_opencode_host) -> None:
    # T-5: read_only(host) is what MCP exposure gets; rows 11-14, 20-25 and 27.
    read_only = tools_of(opencode_tools_api.OpencodeTools.read_only(make_opencode_host()))
    expected = {name for name, (permission, _) in TOOL_TABLE.items() if permission == "read"}
    assert len(expected) == 11
    assert set(read_only) == expected
    assert all(tool.spec().permission is opencode_tools_api.ToolPermission.READ for tool in read_only.values())


def test_tool_classes_are_named_after_their_functions_and_exported() -> None:
    # §8.5: one class per tool named <FunctionInPascalCase>Tool, exported from vidbyte.tools.builtins.opencode.
    package = importlib.import_module("vidbyte.tools.builtins.opencode")
    base = importlib.import_module("vidbyte.tools.builtins.native_host_tool")
    missing = [pascal_tool_class(name) for name in TOOL_TABLE if not hasattr(package, pascal_tool_class(name))]
    assert missing == []
    assert all(issubclass(getattr(package, pascal_tool_class(name)), base.NativeHostTool) for name in TOOL_TABLE)
    assert "OpencodeTools" in importlib.import_module("vidbyte.tools.toolsets").__all__


@pytest.mark.asyncio
async def test_default_policy_denies_the_write_tool_and_runs_the_read_tool(opencode_tools_api, fake_opencode, make_opencode_host) -> None:
    # AC-15 / EC-142: the default PermissionPolicy allows SAFE and READ only.
    async with make_opencode_host() as host:
        executor = opencode_tools_api.ToolExecutor(opencode_tools_api.OpencodeTools(host))
        denied = await executor.execute_call(opencode_tools_api.ToolCall("spawn_opencode_session", {"prompt": PROMPT}))
        sent_after_denial = fake_opencode.routes()
        allowed = await executor.execute_call(opencode_tools_api.ToolCall("list_opencode_sessions", {}))
    assert denied.status is opencode_tools_api.ToolStatus.ERROR
    assert denied.metadata["error"] == "permission_denied"
    assert "session_create" not in sent_after_denial and "prompt_async" not in sent_after_denial, "a denied WRITE tool never reaches the server"
    assert allowed.status is opencode_tools_api.ToolStatus.SUCCESS, allowed.output
    assert KNOWN_SESSION in {session["session_id"] for session in json.loads(allowed.output)["sessions"]}


@pytest.mark.asyncio
async def test_spawn_then_wait_round_trips_the_handle_as_json(opencode_tools_api, fake_opencode, make_opencode_host) -> None:
    # §9.2 Success: record -> JSON with sorted keys and metadata {harness, operation, truncated}; the handle travels as an object.
    async with make_opencode_host() as host:
        tools = opencode_tools_api.OpencodeTools(host)
        spawned = await execute(opencode_tools_api, tools, "spawn_opencode_session", {"prompt": PROMPT, "title": "Tool spawn"})
        assert spawned.status is opencode_tools_api.ToolStatus.SUCCESS, spawned.output
        handle = handle_object(json.loads(spawned.output))
        waited = await execute(opencode_tools_api, tools, "wait_opencode_turn", {"handle": handle, "timeout_seconds": 30})
    assert handle["harness"] == "opencode" and handle["session_id"].startswith("ses") and len(handle["turn_id"]) == 32
    assert dict(spawned.metadata) == {"harness": "opencode", "operation": "spawn_opencode_session", "truncated": False}
    assert waited.status is opencode_tools_api.ToolStatus.SUCCESS, waited.output
    payload = json.loads(waited.output)
    assert payload["status"] == "completed" and payload["text"] == "alpha-beta"
    assert sorted_everywhere(payload)
    assert dict(waited.metadata) == {"harness": "opencode", "operation": "wait_opencode_turn", "truncated": False}


@pytest.mark.asyncio
async def test_spawn_tool_sends_no_permission_rules(opencode_tools_api, fake_opencode, make_opencode_host) -> None:
    # D-11 / INV-9: the tool has no rule parameter, so the session it creates carries no rules at all.
    async with make_opencode_host() as host:
        spawned = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), "spawn_opencode_session", {"prompt": PROMPT, "title": "Tool spawn"})
    assert spawned.status is opencode_tools_api.ToolStatus.SUCCESS, spawned.output
    body = fake_opencode.seen("session_create")[0].body or {}
    assert body.get("title") == "Tool spawn"
    assert body.get("permission", []) == []
    assert fake_opencode.seen("prompt_async")[0].body["parts"] == [{"type": "text", "text": PROMPT}]


@pytest.mark.asyncio
async def test_usage_tool_encodes_decimal_cost_as_a_string(opencode_tools_api, make_opencode_host) -> None:
    # §9.2 Success: Decimal values are JSON strings, enums are their values.
    async with make_opencode_host() as host:
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), "track_opencode_session_usage", {"session_id": KNOWN_SESSION})
    assert result.status is opencode_tools_api.ToolStatus.SUCCESS, result.output
    payload = json.loads(result.output)
    assert payload["harness"] == "opencode" and payload["session_id"] == KNOWN_SESSION
    assert payload["totals"]["cost_usd"] == "0.5"
    assert sorted_everywhere(payload)


@pytest.mark.asyncio
async def test_add_tool_with_an_unregistered_name_is_refused(opencode_tools_api, fake_opencode, make_opencode_host, check_tool_error) -> None:
    # EC-146 / T-2: only a key of OpencodeHostSettings.mcp_servers is accepted; nothing is posted.
    async with make_opencode_host() as host:
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), "add_opencode_mcp_server", {"name": "ghost"})
    check_tool_error(result, code="configuration.invalid_argument", token="mcp_servers", tool_name="add_opencode_mcp_server")
    assert result.metadata["next_step"] == EC146_NEXT_STEP
    assert fake_opencode.seen("mcp_add") == []


@pytest.mark.asyncio
async def test_add_tool_posts_the_registered_config(opencode_api, opencode_tools_api, fake_opencode, make_opencode_host) -> None:
    # T-2: the tool takes a name only, so the command the server receives is the one the developer registered.
    config = opencode_api.OpencodeMcpServerConfig(name="files", kind=opencode_api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"), timeout_ms=5000)
    async with make_opencode_host(mcp_servers={"files": config}) as host:
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), "add_opencode_mcp_server", {"name": "files"})
    assert result.status is opencode_tools_api.ToolStatus.SUCCESS, result.output
    assert json.loads(result.output)["status"] == "connected"
    body = fake_opencode.seen("mcp_add")[0].body
    assert body["name"] == "files" and body["config"]["command"] == ["node", "files-server.js"] and body["config"]["type"] == "local"


@pytest.mark.asyncio
async def test_unopened_host_through_a_tool_returns_process_exited(opencode_tools_api, fake_opencode, make_opencode_host, check_tool_error) -> None:
    # EC-2 in tool mode: the tool returns the error and does not raise; nothing is sent.
    result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(make_opencode_host()), "list_opencode_sessions", {})
    check_tool_error(result, code="opencode.process_exited", token="async with", tool_name="list_opencode_sessions")
    assert fake_opencode.requests == []


EC138_CASES = [
    pytest.param("spawn_opencode_session", {"prompt": 7}, "prompt", id="spawn-prompt-type"),
    pytest.param("spawn_opencode_session", {}, "prompt", id="spawn-prompt-missing-direct"),
    pytest.param("spawn_opencode_session", {"prompt": PROMPT, "model": "coder-1"}, "model", id="spawn-model-record-check"),
    pytest.param("spawn_opencode_session", {"prompt": PROMPT, "agent": "-plan"}, "agent", id="spawn-agent-record-check"),
    pytest.param("spawn_opencode_session", {"prompt": PROMPT, "title": ""}, "title", id="spawn-title-record-check"),
    pytest.param("spawn_opencode_session", {"prompt": PROMPT, "max_turn_seconds": "fast"}, "max_turn_seconds", id="spawn-seconds-type"),
    pytest.param("continue_opencode_session", {"session_id": 12, "prompt": PROMPT}, "session_id", id="continue-session-type"),
    pytest.param("continue_opencode_session", {"session_id": "not-a-session", "prompt": PROMPT}, "session_id", id="continue-session-pattern"),
    pytest.param("fork_opencode_session", {"session_id": KNOWN_SESSION, "message_id": 5}, "message_id", id="fork-message-type"),
    pytest.param("revert_opencode_session", {"session_id": KNOWN_SESSION, "message_id": KNOWN_MESSAGE, "part_id": 9}, "part_id", id="revert-part-type"),
    pytest.param("list_opencode_models", {"provider_id": 3}, "provider_id", id="models-provider-type"),
    pytest.param("list_opencode_sessions", {"limit": "ten"}, "limit", id="list-limit-type"),
    pytest.param("list_opencode_sessions", {"limit": 1.5}, "limit", id="list-limit-float"),
    pytest.param("list_opencode_sessions", {"limit": 201}, "limit", id="list-limit-range"),
    pytest.param("get_opencode_session_messages", {"session_id": KNOWN_SESSION, "before": 5}, "before", id="messages-before-type"),
    pytest.param("get_opencode_message", {"session_id": KNOWN_SESSION, "message_id": "m1"}, "message_id", id="message-id-pattern"),
    pytest.param("add_opencode_mcp_server", {"name": 5}, "name", id="add-name-type"),
    pytest.param("wait_opencode_turn", {"handle": UNISSUED_HANDLE, "timeout_seconds": "soon"}, "timeout_seconds", id="wait-timeout-type"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "arguments", "token"), EC138_CASES)
async def test_bad_arguments_return_invalid_argument_naming_the_parameter(tool_name: str, arguments: dict[str, Any], token: str, opencode_tools_api, fake_opencode, make_opencode_host, check_tool_error) -> None:
    # EC-138: argument parsing or record construction fails inside execute; nothing reaches the server.
    async with make_opencode_host() as host:
        sent_before = fake_opencode.routes()
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), tool_name, arguments)
        sent_after = fake_opencode.routes()
    check_tool_error(result, code="configuration.invalid_argument", token=token, tool_name=tool_name)
    assert sent_after == sent_before


@pytest.mark.asyncio
async def test_missing_required_parameter_under_the_executor_is_its_validation_error(opencode_tools_api, make_opencode_host) -> None:
    # EC-138 scope note: ToolExecutor's validate_call reports a missing parameter before execute; unchanged behaviour.
    async with make_opencode_host() as host:
        executor = opencode_tools_api.ToolExecutor(opencode_tools_api.OpencodeTools(host), permission_policy=opencode_tools_api.PermissionPolicy.allow_all())
        result = await executor.execute_call(opencode_tools_api.ToolCall("get_opencode_session", {}))
    assert result.metadata["error"] == "validation_error"


@pytest.mark.asyncio
async def test_tool_wait_above_the_tool_cap_is_refused(opencode_tools_api, fake_opencode, make_opencode_host, check_tool_error) -> None:
    # EC-144: NATIVE_TOOL_WAIT_MAX_SECONDS (240) keeps a tool call under Codex's 300 s cutoff.
    async with make_opencode_host() as host:
        sent_before = fake_opencode.routes()
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), "wait_opencode_turn", {"handle": UNISSUED_HANDLE, "timeout_seconds": 240.5})
        sent_after = fake_opencode.routes()
    check_tool_error(result, code="configuration.invalid_argument", token="timeout_seconds", tool_name="wait_opencode_turn")
    assert sent_after == sent_before


@pytest.mark.asyncio
async def test_tool_wait_at_exactly_the_cap_is_accepted(opencode_tools_api, make_opencode_host) -> None:
    async with make_opencode_host() as host:
        tools = opencode_tools_api.OpencodeTools(host)
        spawned = await execute(opencode_tools_api, tools, "spawn_opencode_session", {"prompt": PROMPT})
        waited = await execute(opencode_tools_api, tools, "wait_opencode_turn", {"handle": handle_object(json.loads(spawned.output)), "timeout_seconds": 240})
    assert waited.status is opencode_tools_api.ToolStatus.SUCCESS, waited.output


EC145_CASES = [
    pytest.param("wait_opencode_turn", "not-a-handle", id="wait-string"),
    pytest.param("wait_opencode_turn", {"harness": "opencode", "session_id": 5, "turn_id": "0" * 32}, id="wait-number-field"),
    pytest.param("wait_opencode_turn", ["opencode", KNOWN_SESSION, "0" * 32], id="wait-list"),
    pytest.param("interrupt_opencode_turn", {"harness": "opencode", "session_id": KNOWN_SESSION}, id="interrupt-missing-turn"),
    pytest.param("interrupt_opencode_turn", {"harness": None, "session_id": KNOWN_SESSION, "turn_id": "0" * 32}, id="interrupt-null-harness"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "handle"), EC145_CASES)
async def test_malformed_handle_argument_returns_invalid_argument(tool_name: str, handle: Any, opencode_tools_api, fake_opencode, make_opencode_host, check_tool_error) -> None:
    # EC-145: handle must be an object with string harness, session_id and turn_id; no abort is sent.
    async with make_opencode_host() as host:
        result = await execute(opencode_tools_api, opencode_tools_api.OpencodeTools(host), tool_name, {"handle": handle})
    check_tool_error(result, code="configuration.invalid_argument", token="handle", tool_name=tool_name)
    assert fake_opencode.seen("abort") == []
