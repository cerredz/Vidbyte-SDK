"""FILE: tests/features/grok_host/test_grok_host_tools.py

PURPOSE: The model-facing Grok tools and the shared tool base: GrokTools and read_only (§9.2 rows 1-10, T-5), the executor's default policy (AC-15, EC-142), argument failures (EC-138), unexpected errors (EC-140), cancellation (EC-141), output clipping (EC-143), the tool-only limits (EC-144, EC-145), and the tool parameters that must not exist (AC-19, INV-9).
ROLE IN CODEBASE: Start here when a Grok tool raises, mis-encodes a result, or offers a parameter it should not. The host error rows in tool mode live in test_grok_host_errors.py.
ARCHITECTURE NOTE: Tools wrap a real GrokHost on fake_grok_peer.py; nothing in the tool base is mocked. Direct execute() calls reach EC-138; calls through ToolExecutor show the executor's own unchanged checks.
FUNCTION INVENTORY: TOOL_TABLE is §9.2 rows 1-10; open_tools builds a host and its toolset; execute runs one tool by name; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When §9.2 changes, update TOOL_TABLE first; every other test reads it.
WHAT NOT TO DO IN THIS FILE: 1. Do not grant PermissionPolicy.allow_all() in the AC-15 test; the default policy is the point. 2. Do not compare tool output text byte for byte; decode the JSON and compare fields.
KNOWN EDGE CASES: The clipping case streams three-byte characters, so a cut that ignores UTF-8 boundaries leaves a replacement character. A direct execute() with a missing required parameter is EC-138, while the same call through ToolExecutor is the executor's validation_error.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.7, §8.5 (Tools, Toolsets), §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_tools.py
"""

from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

import pytest

PROMPT = "List the top-level folders."
KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
# §9.2 rows 1-10: tool name -> (permission, {parameter: required}).
TOOL_TABLE: dict[str, tuple[str, dict[str, bool]]] = {
    "check_grok_ready": ("read", {}),
    "list_grok_models": ("read", {}),
    "spawn_grok_session": ("write", {"prompt": True, "model": False, "reasoning_effort": False, "max_turn_seconds": False}),
    "run_grok_once": ("write", {"prompt": True, "model": False, "reasoning_effort": False, "max_turns": False, "max_turn_seconds": False}),
    "continue_grok_session": ("write", {"session_id": True, "prompt": True, "model": False, "reasoning_effort": False, "max_turn_seconds": False}),
    "fork_grok_session": ("write", {"session_id": True, "prompt": True, "new_session_id": False, "model": False, "reasoning_effort": False, "max_turns": False, "max_turn_seconds": False}),
    "list_grok_sessions": ("read", {"cursor": False}),
    "search_grok_sessions": ("read", {"query": True, "limit": False}),
    "wait_grok_turn": ("read", {"handle": True, "timeout_seconds": False}),
    "interrupt_grok_turn": ("write", {"handle": True}),
}
PARAMETER_TYPES = {
    "prompt": "string", "model": "string", "reasoning_effort": "string", "session_id": "string", "new_session_id": "string", "cursor": "string",
    "query": "string", "max_turn_seconds": "number", "timeout_seconds": "number", "max_turns": "integer", "limit": "integer", "handle": "object",
}
FORBIDDEN_PARAMETERS = {"permission_mode", "allow_rules", "deny_rules", "allowed_tool_kinds", "cwd", "workspace", "always_approve", "yolo", "grok_command"}


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


def test_grok_tools_match_the_spec_table(grok_api, grok_tools_api, make_grok_host) -> None:
    # §9.2 rows 1-10: names, permissions and parameters; building the toolset starts nothing.
    host = make_grok_host()
    tools = tools_of(grok_tools_api.GrokTools(host))
    assert set(tools) == set(TOOL_TABLE)
    for name, (permission, parameters) in TOOL_TABLE.items():
        spec = tools[name].spec()
        assert spec.name == name
        assert spec.permission is grok_tools_api.ToolPermission(permission), name
        declared = {parameter.name: parameter.required for parameter in spec.parameters}
        assert declared == parameters, name
        for parameter in spec.parameters:
            assert parameter.type == PARAMETER_TYPES[parameter.name], (name, parameter.name)


def test_no_grok_tool_offers_an_approve_everything_or_directory_parameter(grok_tools_api, make_grok_host) -> None:
    # AC-19 / INV-9 / T-2: the toolset parameters cannot carry a permission mode, rules, tool kinds or a directory.
    for tool in grok_tools_api.GrokTools(make_grok_host()).all():
        names = {parameter.name for parameter in tool.spec().parameters}
        assert not names & FORBIDDEN_PARAMETERS, (tool.name, names & FORBIDDEN_PARAMETERS)


def test_read_only_returns_exactly_the_read_tools(grok_tools_api, make_grok_host) -> None:
    # T-5: read_only(host) is what MCP exposure gets.
    host = make_grok_host()
    read_only = tools_of(grok_tools_api.GrokTools.read_only(host))
    expected = {name for name, (permission, _) in TOOL_TABLE.items() if permission == "read"}
    assert set(read_only) == expected == {"check_grok_ready", "list_grok_models", "list_grok_sessions", "search_grok_sessions", "wait_grok_turn"}
    assert all(tool.spec().permission is grok_tools_api.ToolPermission.READ for tool in read_only.values())


def test_tool_classes_are_named_after_their_functions_and_exported() -> None:
    # §8.5: one class per tool named <FunctionInPascalCase>Tool, exported from vidbyte.tools.builtins.grok.
    package = importlib.import_module("vidbyte.tools.builtins.grok")
    for name in TOOL_TABLE:
        assert hasattr(package, pascal_tool_class(name)), pascal_tool_class(name)
    assert "GrokTools" in importlib.import_module("vidbyte.tools.toolsets").__all__
    base = importlib.import_module("vidbyte.tools.builtins.native_host_tool")
    assert all(issubclass(getattr(package, pascal_tool_class(name)), base.NativeHostTool) for name in TOOL_TABLE)


@pytest.mark.asyncio
async def test_default_policy_denies_the_write_tool_and_runs_the_read_tool(grok_api, grok_tools_api, grok_fake, make_grok_host, fast_stop) -> None:
    # AC-15 / EC-142: the default PermissionPolicy allows SAFE and READ only.
    async with make_grok_host() as host:
        executor = grok_tools_api.ToolExecutor(grok_tools_api.GrokTools(host))
        denied = await executor.execute_call(grok_tools_api.ToolCall("spawn_grok_session", {"prompt": PROMPT}))
        launched_after_denial = list(grok_fake.launches())
        allowed = await executor.execute_call(grok_tools_api.ToolCall("list_grok_sessions", {}))
    assert denied.status is grok_tools_api.ToolStatus.ERROR
    assert denied.metadata["error"] == "permission_denied"
    assert launched_after_denial == [], "a denied WRITE tool never reaches the host"
    assert allowed.status is grok_tools_api.ToolStatus.SUCCESS, allowed.output
    assert [session["session_id"] for session in json.loads(allowed.output)["sessions"]][0] == KNOWN_SESSION


@pytest.mark.asyncio
async def test_spawn_then_wait_round_trips_the_handle_as_json(grok_api, grok_tools_api, make_grok_host, fast_stop) -> None:
    # §8.5 NativeResultEncoder: record -> JSON text with sorted keys; the handle travels as {harness, session_id, turn_id}.
    async with make_grok_host() as host:
        tools = grok_tools_api.GrokTools(host)
        spawned = await execute(grok_tools_api, tools, "spawn_grok_session", {"prompt": PROMPT})
        assert spawned.status is grok_tools_api.ToolStatus.SUCCESS, spawned.output
        handle = handle_object(json.loads(spawned.output))
        waited = await execute(grok_tools_api, tools, "wait_grok_turn", {"handle": handle, "timeout_seconds": 30})
    assert handle["harness"] == "grok" and len(handle["turn_id"]) == 32
    assert waited.status is grok_tools_api.ToolStatus.SUCCESS, waited.output
    payload = json.loads(waited.output)
    assert payload["status"] == "completed" and payload["text"] == "alpha-beta"
    assert list(payload) == sorted(payload), "keys are sorted"
    assert waited.metadata.get("truncated") in (None, False)


@pytest.mark.asyncio
async def test_unopened_host_through_a_tool_returns_process_exited(grok_tools_api, make_grok_host, check_tool_error) -> None:
    # EC-2 in tool mode: the tool returns the error and does not raise.
    tools = grok_tools_api.GrokTools(make_grok_host())
    result = await execute(grok_tools_api, tools, "list_grok_sessions", {})
    check_tool_error(result, code="grok.process_exited", token="async with", tool_name="list_grok_sessions")


EC138_CASES = [
    pytest.param("spawn_grok_session", {"prompt": 7}, "prompt", id="spawn-prompt-type"),
    pytest.param("spawn_grok_session", {}, "prompt", id="spawn-prompt-missing-direct"),
    pytest.param("spawn_grok_session", {"prompt": PROMPT, "max_turn_seconds": "fast"}, "max_turn_seconds", id="spawn-seconds-type"),
    pytest.param("spawn_grok_session", {"prompt": PROMPT, "model": "--yolo"}, "model", id="spawn-model-record-check"),
    pytest.param("run_grok_once", {"prompt": PROMPT, "max_turns": "3"}, "max_turns", id="once-max-turns-type"),
    pytest.param("run_grok_once", {"prompt": PROMPT, "max_turns": 0}, "max_turns", id="once-max-turns-range"),
    pytest.param("continue_grok_session", {"session_id": 12, "prompt": PROMPT}, "session_id", id="continue-session-type"),
    pytest.param("fork_grok_session", {"session_id": KNOWN_SESSION, "prompt": PROMPT, "new_session_id": "nope"}, "new_session_id", id="fork-new-id"),
    pytest.param("list_grok_sessions", {"cursor": 5}, "cursor", id="list-cursor-type"),
    pytest.param("search_grok_sessions", {"query": "parser", "limit": "ten"}, "limit", id="search-limit-type"),
    pytest.param("search_grok_sessions", {"query": "parser", "limit": 1.5}, "limit", id="search-limit-float"),
    pytest.param("wait_grok_turn", {"handle": {"harness": "grok", "session_id": KNOWN_SESSION, "turn_id": "0" * 32}, "timeout_seconds": "soon"}, "timeout_seconds", id="wait-timeout-type"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "arguments", "token"), EC138_CASES)
async def test_bad_arguments_return_invalid_argument_naming_the_parameter(tool_name: str, arguments: dict[str, Any], token: str, grok_tools_api, grok_fake, make_grok_host, fast_stop, check_tool_error) -> None:
    # EC-138: argument parsing or record construction fails inside execute; nothing starts.
    async with make_grok_host() as host:
        result = await execute(grok_tools_api, grok_tools_api.GrokTools(host), tool_name, arguments)
    check_tool_error(result, code="configuration.invalid_argument", token=token, tool_name=tool_name)
    assert grok_fake.launches() == []


@pytest.mark.asyncio
async def test_missing_required_parameter_under_the_executor_is_its_validation_error(grok_tools_api, make_grok_host, fast_stop) -> None:
    # EC-138 scope note: ToolExecutor's validate_call reports a missing parameter before execute; unchanged behaviour.
    async with make_grok_host() as host:
        executor = grok_tools_api.ToolExecutor(grok_tools_api.GrokTools(host), permission_policy=grok_tools_api.PermissionPolicy.allow_all())
        result = await executor.execute_call(grok_tools_api.ToolCall("search_grok_sessions", {}))
    assert result.metadata["error"] == "validation_error"


EC144_CASES = [
    pytest.param("wait_grok_turn", {"handle": {"harness": "grok", "session_id": KNOWN_SESSION, "turn_id": "0" * 32}, "timeout_seconds": 240.5}, "timeout_seconds", id="wait"),
    pytest.param("run_grok_once", {"prompt": PROMPT, "max_turn_seconds": 241}, "max_turn_seconds", id="once"),
    pytest.param("fork_grok_session", {"session_id": KNOWN_SESSION, "prompt": PROMPT, "max_turn_seconds": 241}, "max_turn_seconds", id="fork"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "arguments", "token"), EC144_CASES)
async def test_tool_waits_above_the_tool_cap_are_refused(tool_name: str, arguments: dict[str, Any], token: str, grok_tools_api, grok_fake, make_grok_host, fast_stop, check_tool_error) -> None:
    # EC-144: NATIVE_TOOL_WAIT_MAX_SECONDS (240) keeps a tool call under Codex's 300 s cutoff.
    async with make_grok_host() as host:
        result = await execute(grok_tools_api, grok_tools_api.GrokTools(host), tool_name, arguments)
    check_tool_error(result, code="configuration.invalid_argument", token=token, tool_name=tool_name)
    assert grok_fake.launches("oneshot") == [] and grok_fake.launches("peer") == []


@pytest.mark.asyncio
async def test_tool_wait_at_exactly_the_cap_is_accepted(grok_tools_api, make_grok_host, fast_stop) -> None:
    async with make_grok_host() as host:
        tools = grok_tools_api.GrokTools(host)
        spawned = await execute(grok_tools_api, tools, "spawn_grok_session", {"prompt": PROMPT})
        waited = await execute(grok_tools_api, tools, "wait_grok_turn", {"handle": handle_object(json.loads(spawned.output)), "timeout_seconds": 240})
    assert waited.status is grok_tools_api.ToolStatus.SUCCESS, waited.output


EC145_CASES = [
    pytest.param("wait_grok_turn", "not-a-handle", id="wait-string"),
    pytest.param("wait_grok_turn", {"harness": "grok", "session_id": 5, "turn_id": "0" * 32}, id="wait-number-field"),
    pytest.param("wait_grok_turn", ["grok", KNOWN_SESSION, "0" * 32], id="wait-list"),
    pytest.param("interrupt_grok_turn", {"harness": "grok", "session_id": KNOWN_SESSION}, id="interrupt-missing-turn"),
    pytest.param("interrupt_grok_turn", {"harness": None, "session_id": KNOWN_SESSION, "turn_id": "0" * 32}, id="interrupt-null-harness"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "handle"), EC145_CASES)
async def test_malformed_handle_argument_returns_invalid_argument(tool_name: str, handle: Any, grok_tools_api, make_grok_host, fast_stop, check_tool_error) -> None:
    # EC-145: handle must be an object with string harness, session_id and turn_id.
    async with make_grok_host() as host:
        result = await execute(grok_tools_api, grok_tools_api.GrokTools(host), tool_name, {"handle": handle})
    check_tool_error(result, code="configuration.invalid_argument", token="handle", tool_name=tool_name)


@pytest.mark.asyncio
async def test_unexpected_tool_exception_becomes_runtime_error_naming_only_the_class(grok_tools_api) -> None:
    # EC-140: a non-host exception becomes runtime.error; the text is never built from str(exc) (S017).
    tool_class = importlib.import_module("vidbyte.tools.builtins.grok").SpawnGrokSessionTool
    tool = tool_class(object())
    result = await tool.execute(grok_tools_api.ToolCall("spawn_grok_session", {"prompt": PROMPT}))
    assert result.status is grok_tools_api.ToolStatus.ERROR
    assert result.metadata["error"] == "runtime.error"
    assert "error_type" in result.metadata["next_step"]
    assert "AttributeError" in result.output
    assert "has no attribute" not in result.output, "the exception text must not leak"
    assert result.metadata["hint"] == result.metadata["next_step"]
    assert result.metadata["operation"] == "spawn_grok_session" and result.metadata["harness"] == "grok"


@pytest.mark.asyncio
async def test_cancelling_a_tool_call_propagates_and_leaves_the_turn_running(grok_api, grok_tools_api, grok_fake, make_grok_host, fast_stop, wait_until) -> None:
    # EC-141 / INV-12: CancelledError is the only exception a tool lets through; the waited turn keeps running.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        tools = grok_tools_api.GrokTools(host)
        spawned = await execute(grok_tools_api, tools, "spawn_grok_session", {"prompt": PROMPT})
        handle = handle_object(json.loads(spawned.output))
        task = asyncio.create_task(execute(grok_tools_api, tools, "wait_grok_turn", {"handle": handle, "timeout_seconds": 200}))
        assert await wait_until(lambda: bool(grok_fake.received("session/prompt")), 20.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert grok_fake.received("session/cancel") == []
        grok_fake.release()
        finished = await execute(grok_tools_api, tools, "wait_grok_turn", {"handle": handle, "timeout_seconds": 30})
    assert json.loads(finished.output)["status"] == "completed"


@pytest.mark.asyncio
async def test_large_output_is_clipped_at_a_utf8_boundary(grok_api, grok_tools_api, make_grok_host, fast_stop) -> None:
    # EC-143: output above NATIVE_TOOL_OUTPUT_MAX_BYTES is cut at a UTF-8 boundary with metadata["truncated"] = True.
    cap = grok_api.constants.NATIVE_TOOL_OUTPUT_MAX_BYTES
    chunks = ["語" * 10000, "語" * 10000, "語" * 10000]
    async with make_grok_host({"acp": {"session_prompt": {"chunks": chunks}}}) as host:
        tools = grok_tools_api.GrokTools(host)
        spawned = await execute(grok_tools_api, tools, "spawn_grok_session", {"prompt": PROMPT})
        waited = await execute(grok_tools_api, tools, "wait_grok_turn", {"handle": handle_object(json.loads(spawned.output)), "timeout_seconds": 30})
    assert waited.status is grok_tools_api.ToolStatus.SUCCESS
    encoded = waited.output.encode("utf-8")
    assert cap // 2 < len(encoded) <= cap == 64000, "clipped to the cap, keeping most of the text"
    assert "�" not in waited.output
    assert waited.metadata["truncated"] is True
