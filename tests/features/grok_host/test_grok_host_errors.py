"""FILE: tests/features/grok_host/test_grok_host_errors.py

PURPOSE: The GrokHost error contract as one table: each case is a (function, code) row of spec §6.3.2-§6.3.3 reproduced through the fake grok, asserting the exact FailureCode member, a non-empty next_step that holds the row's required token, and the matching tool's error result (AC-2).
ROLE IN CODEBASE: Proves FR-6, FR-7, FR-21 and INV-1/INV-8 for vidbyte.harnesses.native.grok.GrokHost and the vidbyte.tools.builtins.grok tools. The table also covers the shared rows EC-1 (argument checks), EC-2 (host not open) and EC-3 (host reused).
ARCHITECTURE NOTE: ROWS is data; CALLS maps a row to the call that reproduces it. A RowCall drives either the host method or the matching tool through RowContext.invoke, so one row runs twice: "host" asserts the raised NativeHostError, "tool" asserts the ToolResult.error built from it (INV-7). Setup steps inside a call (a held turn before a busy check) always use the host directly.
FUNCTION INVENTORY: Row describes one case; RowContext runs a call as host or tool; call_* reproduce the triggers; test_grok_error_row runs the table; test_unopened_or_closed_host_raises_process_exited covers EC-2; test_reentering_a_host_raises_invalid_argument covers EC-3; test_invalid_primitive_arguments_fail_before_any_process covers EC-1; test_aenter_without_any_grok_raises_not_installed covers EC-11 at __aenter__.
COMMON MODIFICATION PATTERNS: A new §6.3 row is one Row entry; add a call_* function only when no existing one reproduces its trigger. Keep one case per (function, code) and list any pruned duplicate in the test plan.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert on message wording beyond names the spec fixes; assert codes, tokens and context keys. 2. Do not reach the real grok: every host here runs the fake or a path that does not exist.
KNOWN EDGE CASES: Rows whose trigger is a silent fake shrink control_timeout_seconds to 0.5 and depend on fast_stop for a quick close. Turn-failure rows (EC-45 to EC-49) do not assert operation, because the spec does not say which operation a recorded turn failure names.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1-§6.3.3, §6.3.7
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_errors.py
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
OTHER_SESSION = "0c9b8a7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"
MISSING_SESSION = "99999999-8888-4777-a666-555555555555"
PROMPT = "List the top-level folders."
UNKNOWN_MODEL = "grok-unknown-9"
SHORT_CONTROL_SECONDS = 0.5
SHORT_RUN_SECONDS = 1.0
SHORT_WAIT_SECONDS = 0.3
UNISSUED_TURN_ID = "a" * 32

INIT_EXIT = {"acp": {"initialize": {"mode": "exit"}}}
INIT_SILENT = {"acp": {"initialize": {"mode": "silent"}}}
OLD_AGENT = {"acp": {"initialize": {"agent_version": "1.0.12"}}}
NO_LIST_CAPABILITY = {"acp": {"initialize": {"session_capabilities": {"resume": {}}}}}
NO_RESUME_CAPABILITY = {"acp": {"initialize": {"session_capabilities": {"list": {}}}}}
HELD_TURN = {"acp": {"session_prompt": {"mode": "hold"}}}
SIGNED_OUT = {"code": -32000, "message": "Authentication required"}
VENDOR_FAILURE = {"code": -32099, "message": "backend exploded"}
FS_NOT_FOUND = {"code": -32603, "message": "Internal error", "data": {"code": "FS_NOT_FOUND"}}
LIST_SILENT = {"acp": {"session_list": {"mode": "silent"}}}
LIST_WITHOUT_CWD = {"acp": {"session_list": {"pages": [[{"sessionId": KNOWN_SESSION, "cwd": "$drop"}]]}}}


@dataclass(frozen=True)
class Row:
    """One (function, code) row of the §6.3 error tables."""

    ec: str
    operation: str
    code: str
    token: str
    scenario: Mapping[str, Any] = field(default_factory=dict)
    call: str = ""
    variant: str = ""
    command: str = "fake"
    control_timeout: float = 10.0
    max_live_turns: int = 4
    context: Mapping[str, str] = field(default_factory=dict)
    context_keys: tuple[str, ...] = ()
    never_sent: tuple[str, ...] = ()
    never_launched: tuple[str, ...] = ()
    peer_launches: int | None = None
    check_operation: bool = True
    tool: bool = True


@dataclass
class RowContext:
    """Runs a row's final call against the host, or against the matching tool."""

    host: Any
    api: SimpleNamespace
    tools: Any = None
    tools_api: SimpleNamespace | None = None

    async def invoke(self, tool_name: str, tool_args: Mapping[str, Any], direct: Callable[[], Awaitable[Any]]) -> Any:
        if self.tools is None:
            return await direct()
        tool = {tool.name: tool for tool in self.tools.all()}[tool_name]
        return await tool.execute(self.tools_api.ToolCall(tool_name, dict(tool_args)))


def handle_args(handle: Any) -> dict[str, str]:
    return {"harness": handle.harness.value, "session_id": handle.session_id, "turn_id": handle.turn_id}


def turn_request(api: SimpleNamespace, **fields: Any) -> Any:
    return api.GrokTurnRequest(prompt=PROMPT, **fields)


def oneshot_request(api: SimpleNamespace, **fields: Any) -> Any:
    return api.GrokOneShotRequest(prompt=PROMPT, **fields)


async def call_check(ctx: RowContext) -> Any:
    return await ctx.invoke("check_grok_ready", {}, lambda: ctx.host.check_grok_ready())


async def call_list_models(ctx: RowContext) -> Any:
    return await ctx.invoke("list_grok_models", {}, lambda: ctx.host.list_grok_models())


async def call_spawn(ctx: RowContext) -> Any:
    return await ctx.invoke("spawn_grok_session", {"prompt": PROMPT}, lambda: ctx.host.spawn_grok_session(turn_request(ctx.api)))


async def call_spawn_unknown_model(ctx: RowContext) -> Any:
    args = {"prompt": PROMPT, "model": UNKNOWN_MODEL}
    return await ctx.invoke("spawn_grok_session", args, lambda: ctx.host.spawn_grok_session(turn_request(ctx.api, model=UNKNOWN_MODEL)))


async def call_spawn_unoffered_effort(ctx: RowContext) -> Any:
    # grok-4-heavy offers only "high" in the fake's _meta.reasoningEfforts (EC-26).
    args = {"prompt": PROMPT, "model": "grok-4-heavy", "reasoning_effort": "low"}
    request = turn_request(ctx.api, model="grok-4-heavy", reasoning_effort="low")
    return await ctx.invoke("spawn_grok_session", args, lambda: ctx.host.spawn_grok_session(request))


async def call_spawn_at_cap(ctx: RowContext) -> Any:
    await ctx.host.spawn_grok_session(turn_request(ctx.api))
    return await call_spawn(ctx)


async def call_run_once(ctx: RowContext) -> Any:
    return await ctx.invoke("run_grok_once", {"prompt": PROMPT}, lambda: ctx.host.run_grok_once(oneshot_request(ctx.api)))


async def call_run_once_unknown_model(ctx: RowContext) -> Any:
    args = {"prompt": PROMPT, "model": UNKNOWN_MODEL}
    return await ctx.invoke("run_grok_once", args, lambda: ctx.host.run_grok_once(oneshot_request(ctx.api, model=UNKNOWN_MODEL)))


async def call_run_once_short(ctx: RowContext) -> Any:
    args = {"prompt": PROMPT, "max_turn_seconds": SHORT_RUN_SECONDS}
    request = oneshot_request(ctx.api, max_turn_seconds=SHORT_RUN_SECONDS)
    return await ctx.invoke("run_grok_once", args, lambda: ctx.host.run_grok_once(request))


async def call_continue(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT}
    return await ctx.invoke("continue_grok_session", args, lambda: ctx.host.continue_grok_session(KNOWN_SESSION, turn_request(ctx.api)))


async def call_continue_unknown_model(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "model": UNKNOWN_MODEL}
    request = turn_request(ctx.api, model=UNKNOWN_MODEL)
    return await ctx.invoke("continue_grok_session", args, lambda: ctx.host.continue_grok_session(KNOWN_SESSION, request))


async def call_continue_busy(ctx: RowContext) -> Any:
    await ctx.host.continue_grok_session(KNOWN_SESSION, turn_request(ctx.api))
    return await call_continue(ctx)


async def call_fork(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT}
    return await ctx.invoke("fork_grok_session", args, lambda: ctx.host.fork_grok_session(KNOWN_SESSION, oneshot_request(ctx.api)))


async def call_fork_missing_session(ctx: RowContext) -> Any:
    args = {"session_id": MISSING_SESSION, "prompt": PROMPT}
    return await ctx.invoke("fork_grok_session", args, lambda: ctx.host.fork_grok_session(MISSING_SESSION, oneshot_request(ctx.api)))


async def call_fork_taken_new_id(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "new_session_id": OTHER_SESSION}
    request = oneshot_request(ctx.api)
    return await ctx.invoke("fork_grok_session", args, lambda: ctx.host.fork_grok_session(KNOWN_SESSION, request, new_session_id=OTHER_SESSION))


async def call_fork_busy(ctx: RowContext) -> Any:
    await ctx.host.continue_grok_session(KNOWN_SESSION, turn_request(ctx.api))
    return await call_fork(ctx)


async def call_fork_unknown_model(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "model": UNKNOWN_MODEL}
    request = oneshot_request(ctx.api, model=UNKNOWN_MODEL)
    return await ctx.invoke("fork_grok_session", args, lambda: ctx.host.fork_grok_session(KNOWN_SESSION, request))


async def call_fork_short(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "max_turn_seconds": SHORT_RUN_SECONDS}
    request = oneshot_request(ctx.api, max_turn_seconds=SHORT_RUN_SECONDS)
    return await ctx.invoke("fork_grok_session", args, lambda: ctx.host.fork_grok_session(KNOWN_SESSION, request))


async def call_list_sessions(ctx: RowContext) -> Any:
    return await ctx.invoke("list_grok_sessions", {}, lambda: ctx.host.list_grok_sessions())


async def call_list_sessions_stale_cursor(ctx: RowContext) -> Any:
    return await ctx.invoke("list_grok_sessions", {"cursor": "stale-cursor"}, lambda: ctx.host.list_grok_sessions(cursor="stale-cursor"))


async def call_search(ctx: RowContext) -> Any:
    return await ctx.invoke("search_grok_sessions", {"query": "parser"}, lambda: ctx.host.search_grok_sessions("parser"))


async def call_wait_after_spawn(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_grok_session(turn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": 10}
    return await ctx.invoke("wait_grok_turn", args, lambda: ctx.host.wait_grok_turn(handle, timeout_seconds=10))


async def call_wait_too_short(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_grok_session(turn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": SHORT_WAIT_SECONDS}
    return await ctx.invoke("wait_grok_turn", args, lambda: ctx.host.wait_grok_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS))


async def call_wait_foreign_handle(ctx: RowContext) -> Any:
    handle = ctx.api.NativeTurnHandle(harness=ctx.api.NativeHarness.OPENCODE, session_id="ses_foreign1", turn_id=UNISSUED_TURN_ID)
    return await ctx.invoke("wait_grok_turn", {"handle": handle_args(handle)}, lambda: ctx.host.wait_grok_turn(handle))


async def call_interrupt_unissued_handle(ctx: RowContext) -> Any:
    handle = ctx.api.NativeTurnHandle(harness=ctx.api.NativeHarness.GROK, session_id=KNOWN_SESSION, turn_id=UNISSUED_TURN_ID)
    return await ctx.invoke("interrupt_grok_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_grok_turn(handle))


CALLS: dict[str, Callable[[RowContext], Awaitable[Any]]] = {
    "check_grok_ready": call_check,
    "list_grok_models": call_list_models,
    "spawn_grok_session": call_spawn,
    "spawn_unknown_model": call_spawn_unknown_model,
    "spawn_unoffered_effort": call_spawn_unoffered_effort,
    "spawn_at_cap": call_spawn_at_cap,
    "run_grok_once": call_run_once,
    "run_once_unknown_model": call_run_once_unknown_model,
    "run_once_short": call_run_once_short,
    "continue_grok_session": call_continue,
    "continue_unknown_model": call_continue_unknown_model,
    "continue_busy": call_continue_busy,
    "fork_grok_session": call_fork,
    "fork_missing_session": call_fork_missing_session,
    "fork_taken_new_id": call_fork_taken_new_id,
    "fork_busy": call_fork_busy,
    "fork_unknown_model": call_fork_unknown_model,
    "fork_short": call_fork_short,
    "list_grok_sessions": call_list_sessions,
    "list_stale_cursor": call_list_sessions_stale_cursor,
    "search_grok_sessions": call_search,
    "wait_after_spawn": call_wait_after_spawn,
    "wait_too_short": call_wait_too_short,
    "wait_foreign_handle": call_wait_foreign_handle,
    "interrupt_unissued_handle": call_interrupt_unissued_handle,
}

NI = "grok.not_installed"
PE = "grok.process_exited"
SU = "grok.server_unreachable"
PM = "grok.protocol_mismatch"
NS = "grok.not_signed_in"
AE = "grok.api_error"
CM = "grok.capability_missing"
VU = "grok.version_unsupported"
MU = "grok.model_unknown"
SB = "grok.session_busy"
SN = "grok.session_not_found"
TT = "grok.turn_timed_out"
TN = "grok.turn_not_found"
IA = "configuration.invalid_argument"

ROWS: tuple[Row, ...] = (
    # check_grok_ready: --version, then a short-lived initialize, then `grok models` (§6.3.3).
    Row("EC-11", "check_grok_ready", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "check_grok_ready", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",)),
    Row("EC-13", "check_grok_ready", SU, "control_timeout_seconds", INIT_SILENT, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-19", "check_grok_ready", PM, "check_grok_ready", {"version": {"stdout": "grok build unknown\n"}}, never_launched=("peer",)),
    Row("EC-21", "check_grok_ready", NS, "grok login", {"models_cli": {"stdout": "You are not authenticated.\n", "exit": 0}}),
    Row("EC-16", "check_grok_ready", AE, "vendor_code", {"models_cli": {"stdout": "", "stderr": "unexpected failure\n", "exit": 2}}, context={"vendor_code": "2"}),
    Row("EC-20", "check_grok_ready", CM, "grok update", NO_LIST_CAPABILITY),
    Row("EC-18", "check_grok_ready", VU, "grok update", {"version": {"stdout": "grok 1.0.12 (0920c8169e27) [stable]\n"}}, context_keys=("version",), never_launched=("peer",)),
    # list_grok_models: one short-lived initialize (§6.3.3, EC-22).
    Row("EC-11", "list_grok_models", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "list_grok_models", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",)),
    Row("EC-13", "list_grok_models", SU, "control_timeout_seconds", INIT_SILENT, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-22", "list_grok_models", PM, "check_grok_ready", {"acp": {"initialize": {"drop_model_state": True}}}),
    Row("EC-15", "list_grok_models", NS, "grok login", {"acp": {"initialize": {"error": SIGNED_OUT}}}),
    Row("EC-16", "list_grok_models", AE, "vendor_code", {"acp": {"initialize": {"error": VENDOR_FAILURE}}}, context={"vendor_code": "-32099"}),
    Row("EC-17", "list_grok_models", VU, "grok update", OLD_AGENT, context_keys=("version",)),
    # spawn_grok_session.
    Row("EC-11", "spawn_grok_session", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "spawn_grok_session", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",), never_sent=("session/new",)),
    Row("EC-13", "spawn_grok_session", SU, "control_timeout_seconds", {"acp": {"session_new": {"mode": "silent"}}}, control_timeout=SHORT_CONTROL_SECONDS, never_sent=("session/prompt",)),
    Row("EC-14", "spawn_grok_session", PM, "check_grok_ready", {"acp": {"session_new": {"result": {"unexpected": True}}}}, never_sent=("session/prompt",)),
    Row("EC-15", "spawn_grok_session", NS, "grok login", {"acp": {"session_new": {"error": SIGNED_OUT}}}, never_sent=("session/prompt",)),
    Row("EC-16", "spawn_grok_session", AE, "vendor_code", {"acp": {"session_new": {"error": VENDOR_FAILURE}}}, context={"vendor_code": "-32099"}, never_sent=("session/prompt",)),
    Row("EC-17", "spawn_grok_session", VU, "grok update", OLD_AGENT, never_sent=("session/new", "session/prompt")),
    Row("EC-25", "spawn_grok_session", MU, "list_grok_models", call="spawn_unknown_model", context_keys=("available_models",), never_sent=("session/new", "session/prompt")),
    Row("EC-26", "spawn_grok_session", CM, "list_grok_models", call="spawn_unoffered_effort", never_sent=("session/new", "session/prompt")),
    Row("EC-24", "spawn_grok_session", SB, "interrupt_grok_turn", HELD_TURN, call="spawn_at_cap", max_live_turns=1, context_keys=("live_turns",), peer_launches=1),
    # run_grok_once: one CLI run (§6.3.3, EC-33, EC-37, EC-38).
    Row("EC-11", "run_grok_once", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "run_grok_once", PE, "check_grok_ready", command="not_executable"),
    Row("EC-14", "run_grok_once", PM, "check_grok_ready", {"oneshot": {"stdout": "not json at all\n"}}),
    Row("EC-15", "run_grok_once", NS, "grok login", {"oneshot": {"stdout": "", "stderr": "Error: auth token is invalid or expired\n", "exit": 1}}),
    Row("EC-16", "run_grok_once", AE, "vendor_code", {"oneshot": {"stdout": "", "stderr": "upstream overloaded\n", "exit": 3}}, context={"vendor_code": "3"}),
    Row("EC-38", "run_grok_once", TT, "max_turn_seconds", {"oneshot": {"hold": True}}, call="run_once_short"),
    Row("EC-37", "run_grok_once", MU, "list_grok_models", call="run_once_unknown_model", never_launched=("oneshot",)),
    # continue_grok_session.
    Row("EC-11", "continue_grok_session", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "continue_grok_session", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",)),
    Row("EC-13", "continue_grok_session", SU, "control_timeout_seconds", {"acp": {"session_resume": {"mode": "silent"}}}, control_timeout=SHORT_CONTROL_SECONDS, never_sent=("session/prompt",)),
    Row("EC-14", "continue_grok_session", PM, "check_grok_ready", {"acp": {"session_resume": {"error": {"code": -32700, "message": "Parse error"}}}}, never_sent=("session/prompt",)),
    Row("EC-15", "continue_grok_session", NS, "grok login", {"acp": {"session_resume": {"error": SIGNED_OUT}}}, never_sent=("session/prompt",)),
    Row("EC-16", "continue_grok_session", AE, "vendor_code", {"acp": {"session_resume": {"error": VENDOR_FAILURE}}}, context={"vendor_code": "-32099"}, never_sent=("session/prompt",)),
    Row("EC-30", "continue_grok_session", CM, "grok update", NO_RESUME_CAPABILITY, never_sent=("session/resume", "session/prompt")),
    Row("EC-31", "continue_grok_session", SN, "list_grok_sessions", {"acp": {"session_resume": {"error": FS_NOT_FOUND}}}, variant="fs-not-found", never_sent=("session/prompt",)),
    Row("EC-31", "continue_grok_session", SN, "list_grok_sessions", {"acp": {"session_resume": {"error": {"code": -32002, "message": "Resource not found"}}}}, variant="minus-32002", never_sent=("session/prompt",)),
    Row("EC-29", "continue_grok_session", SB, "interrupt_grok_turn", HELD_TURN, call="continue_busy", peer_launches=1),
    Row("EC-25", "continue_grok_session", MU, "list_grok_models", call="continue_unknown_model", context_keys=("available_models",), never_sent=("session/prompt",)),
    Row("EC-17", "continue_grok_session", VU, "grok update", OLD_AGENT, never_sent=("session/prompt",)),
    # fork_grok_session: a short-lived session/list peer, then the money-spending CLI run.
    Row("EC-11", "fork_grok_session", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "fork_grok_session", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",), never_launched=("oneshot",)),
    Row("EC-13", "fork_grok_session", SU, "control_timeout_seconds", LIST_SILENT, control_timeout=SHORT_CONTROL_SECONDS, never_launched=("oneshot",)),
    Row("EC-39", "fork_grok_session", PM, "check_grok_ready", {"oneshot": {"session_id": "$resume"}}),
    Row("EC-15", "fork_grok_session", NS, "grok login", {"oneshot": {"stdout": "", "stderr": "You are not authenticated. Run grok login.\n", "exit": 1}}),
    Row("EC-16", "fork_grok_session", AE, "vendor_code", {"oneshot": {"stdout": "", "stderr": "upstream overloaded\n", "exit": 3}}, context={"vendor_code": "3"}),
    Row("EC-35", "fork_grok_session", SN, "list_grok_sessions", call="fork_missing_session", context_keys=("truncated",), never_launched=("oneshot",)),
    Row("EC-36", "fork_grok_session", IA, "new_session_id", call="fork_taken_new_id", never_launched=("oneshot",)),
    Row("EC-34", "fork_grok_session", SB, "interrupt_grok_turn", HELD_TURN, call="fork_busy", peer_launches=1, never_launched=("oneshot",)),
    Row("EC-37", "fork_grok_session", MU, "list_grok_models", call="fork_unknown_model", never_launched=("oneshot",)),
    Row("EC-38", "fork_grok_session", TT, "max_turn_seconds", {"oneshot": {"hold": True}}, call="fork_short"),
    Row("EC-40", "fork_grok_session", CM, "grok update", NO_LIST_CAPABILITY, never_launched=("oneshot",)),
    # list_grok_sessions.
    Row("EC-11", "list_grok_sessions", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "list_grok_sessions", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",)),
    Row("EC-13", "list_grok_sessions", SU, "control_timeout_seconds", LIST_SILENT, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-42", "list_grok_sessions", PM, "check_grok_ready", LIST_WITHOUT_CWD),
    Row("EC-40", "list_grok_sessions", CM, "grok update", NO_LIST_CAPABILITY, never_sent=("session/list",)),
    Row("EC-16", "list_grok_sessions", CM, "list_grok_models", {"acp": {"session_list": {"error": {"code": -32601, "message": "Method not found"}}}}, variant="minus-32601", context_keys=("method",)),
    Row("EC-41", "list_grok_sessions", IA, "without a cursor", {"acp": {"session_list": {"cursor_error": {"code": -32602, "message": "Invalid params"}}}}, call="list_stale_cursor"),
    Row("EC-15", "list_grok_sessions", NS, "grok login", {"acp": {"session_list": {"error": SIGNED_OUT}}}),
    Row("EC-16", "list_grok_sessions", AE, "vendor_code", {"acp": {"session_list": {"error": VENDOR_FAILURE}}}, context={"vendor_code": "-32099"}),
    # search_grok_sessions pages session/list.
    Row("EC-11", "search_grok_sessions", NI, "GrokHostSettings.grok_command", command="missing"),
    Row("EC-12", "search_grok_sessions", PE, "check_grok_ready", INIT_EXIT, context_keys=("reason",)),
    Row("EC-13", "search_grok_sessions", SU, "control_timeout_seconds", LIST_SILENT, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-40", "search_grok_sessions", CM, "grok update", NO_LIST_CAPABILITY, never_sent=("session/list",)),
    Row("EC-42", "search_grok_sessions", PM, "check_grok_ready", LIST_WITHOUT_CWD),
    Row("EC-16", "search_grok_sessions", AE, "vendor_code", {"acp": {"session_list": {"error": VENDOR_FAILURE}}}, context={"vendor_code": "-32099"}),
    # wait_grok_turn: turn failures recorded by the driver and raised by wait (D-9).
    Row("EC-43", "wait_grok_turn", TN, "spawn_grok_session", call="wait_foreign_handle"),
    Row("EC-44", "wait_grok_turn", TT, "wait_grok_turn", HELD_TURN, call="wait_too_short"),
    Row("EC-45", "wait_grok_turn", NS, "grok login", {"acp": {"session_prompt": {"error": SIGNED_OUT}}}, call="wait_after_spawn", context_keys=("session_id",), check_operation=False),
    Row("EC-46", "wait_grok_turn", SN, "list_grok_sessions", {"acp": {"session_prompt": {"error": FS_NOT_FOUND}}}, call="wait_after_spawn", check_operation=False),
    Row("EC-47", "wait_grok_turn", AE, "vendor_code", {"acp": {"session_prompt": {"error": VENDOR_FAILURE}}}, call="wait_after_spawn", context={"vendor_code": "-32099"}, check_operation=False),
    Row("EC-48", "wait_grok_turn", PE, "check_grok_ready", {"acp": {"session_prompt": {"mode": "exit_after_chunks"}}}, call="wait_after_spawn", check_operation=False),
    Row("EC-49", "wait_grok_turn", PM, "check_grok_ready", {"acp": {"session_prompt": {"result": {"noStopReason": True}}}}, call="wait_after_spawn", check_operation=False),
    # interrupt_grok_turn.
    Row("EC-43", "interrupt_grok_turn", TN, "spawn_grok_session", call="interrupt_unissued_handle"),
)


def row_id(row: Row) -> str:
    suffix = f"-{row.variant}" if row.variant else ""
    return f"{row.ec}-{row.operation}-{row.code}{suffix}"


CASES = [pytest.param(row, "host", id=f"{row_id(row)}-host") for row in ROWS] + [
    pytest.param(row, "tool", id=f"{row_id(row)}-tool") for row in ROWS if row.tool
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "mode"), CASES)
async def test_grok_error_row(row: Row, mode: str, request: pytest.FixtureRequest, grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    command = {"fake": None, "missing": grok_fake.missing_command, "not_executable": grok_fake.not_executable_command}[row.command]
    host = make_grok_host(row.scenario, command=command() if command else None, control_timeout_seconds=row.control_timeout, max_live_turns=row.max_live_turns)
    call = CALLS[row.call or row.operation]
    async with host:
        if mode == "host":
            with pytest.raises(grok_api.NativeHostError) as caught:
                await call(RowContext(host, grok_api))
            error = caught.value
        else:
            tools_api = request.getfixturevalue("grok_tools_api")
            result = await call(RowContext(host, grok_api, tools_api.GrokTools(host), tools_api))
    if mode == "host":
        check_native_error(error, code=row.code, token=row.token, operation=row.operation if row.check_operation else None)
        for key, value in row.context.items():
            assert error.context.get(key) == value, f"context[{key!r}] should be {value!r}: {dict(error.context)}"
        for key in row.context_keys:
            assert error.context.get(key), f"context should carry {key!r}: {dict(error.context)}"
    else:
        request.getfixturevalue("check_tool_error")(result, code=row.code, token=row.token, tool_name=row.operation)
    assert_fake_saw(row, grok_fake)


def assert_fake_saw(row: Row, grok_fake: Any) -> None:
    # INV-5: a failed check makes zero vendor calls that can start a turn.
    received = grok_fake.received_methods()
    for method in row.never_sent:
        assert method not in received, f"{method} must not be sent for {row.ec}; the fake received {received}"
    roles = [record["role"] for record in grok_fake.records("start")]
    for role in row.never_launched:
        assert role not in roles, f"no {role} process may start for {row.ec}; started {roles}"
    if row.peer_launches is not None:
        assert roles.count("peer") == row.peer_launches, f"{row.ec} must not start another peer; started {roles}"


@pytest.mark.asyncio
async def test_model_unknown_context_names_the_models_grok_offers(grok_api, make_grok_host, fast_stop) -> None:
    async with make_grok_host() as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT, model=UNKNOWN_MODEL))
    listed = caught.value.context["available_models"]
    assert "grok-code-fast-1" in listed and "grok-4-heavy" in listed
    assert UNKNOWN_MODEL not in listed


EC2_CALLS: dict[str, Callable[[Any, SimpleNamespace], Awaitable[Any]]] = {
    "check_grok_ready": lambda host, api: host.check_grok_ready(),
    "list_grok_models": lambda host, api: host.list_grok_models(),
    "spawn_grok_session": lambda host, api: host.spawn_grok_session(turn_request(api)),
    "run_grok_once": lambda host, api: host.run_grok_once(oneshot_request(api)),
    "continue_grok_session": lambda host, api: host.continue_grok_session(KNOWN_SESSION, turn_request(api)),
    "fork_grok_session": lambda host, api: host.fork_grok_session(KNOWN_SESSION, oneshot_request(api)),
    "list_grok_sessions": lambda host, api: host.list_grok_sessions(),
    "search_grok_sessions": lambda host, api: host.search_grok_sessions("parser"),
    "wait_grok_turn": lambda host, api: host.wait_grok_turn(grok_handle(api)),
    "interrupt_grok_turn": lambda host, api: host.interrupt_grok_turn(grok_handle(api)),
}


def grok_handle(api: SimpleNamespace) -> Any:
    return api.NativeTurnHandle(harness=api.NativeHarness.GROK, session_id=KNOWN_SESSION, turn_id=UNISSUED_TURN_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(EC2_CALLS))
async def test_unopened_or_closed_host_raises_process_exited(operation: str, grok_api, grok_fake, make_grok_host, check_native_error) -> None:
    # EC-2: never entered, then entered and exited; both raise before anything starts.
    host = make_grok_host()
    with pytest.raises(grok_api.NativeHostError) as before:
        await EC2_CALLS[operation](host, grok_api)
    check_native_error(before.value, code="grok.process_exited", token="async with", operation=operation)
    async with host:
        pass
    with pytest.raises(grok_api.NativeHostError) as after:
        await EC2_CALLS[operation](host, grok_api)
    check_native_error(after.value, code="grok.process_exited", token="async with", operation=operation)
    assert grok_fake.records("start") == [], "EC-2 starts nothing"


@pytest.mark.asyncio
async def test_reentering_a_host_raises_invalid_argument(grok_api, make_grok_host, check_native_error) -> None:
    # EC-3: a host is used once, whether it is open or already closed.
    host = make_grok_host()
    async with host:
        with pytest.raises(grok_api.NativeHostError) as while_open:
            await host.__aenter__()
    check_native_error(while_open.value, code="configuration.invalid_argument", token="new host")
    with pytest.raises(grok_api.NativeHostError) as after_close:
        async with host:
            pass
    check_native_error(after_close.value, code="configuration.invalid_argument", token="new host")


def _bad_session_ids() -> list[Any]:
    return ["not-a-uuid", "", "--always-approve", "6f1d2c3b4a5e4f608a7b9c0d1e2f3a4b", 42]


EC1_CASES: list[Any] = [
    *[pytest.param("continue_grok_session", {"session_id": value}, "session_id", id=f"continue-session_id-{index}") for index, value in enumerate(_bad_session_ids())],
    *[pytest.param("fork_grok_session", {"session_id": value}, "session_id", id=f"fork-session_id-{index}") for index, value in enumerate(_bad_session_ids())],
    pytest.param("fork_grok_session", {"new_session_id": "not-a-uuid"}, "new_session_id", id="fork-new_session_id-shape"),
    pytest.param("fork_grok_session", {"new_session_id": KNOWN_SESSION}, "new_session_id", id="fork-new_session_id-equals-source"),
    pytest.param("list_grok_sessions", {"cursor": ""}, "cursor", id="list-cursor-empty"),
    pytest.param("list_grok_sessions", {"cursor": "c" * 513}, "cursor", id="list-cursor-too-long"),
    pytest.param("list_grok_sessions", {"cursor": 7}, "cursor", id="list-cursor-type"),
    pytest.param("search_grok_sessions", {"query": ""}, "query", id="search-query-empty"),
    pytest.param("search_grok_sessions", {"query": "   "}, "query", id="search-query-blank"),
    pytest.param("search_grok_sessions", {"query": "q" * 201}, "query", id="search-query-too-long"),
    pytest.param("search_grok_sessions", {"limit": 0}, "limit", id="search-limit-zero"),
    pytest.param("search_grok_sessions", {"limit": 101}, "limit", id="search-limit-over"),
    pytest.param("search_grok_sessions", {"limit": True}, "limit", id="search-limit-bool"),
    pytest.param("wait_grok_turn", {"handle": "not-a-handle"}, "handle", id="wait-handle-str"),
    pytest.param("wait_grok_turn", {"handle": None}, "handle", id="wait-handle-none"),
    *[
        pytest.param("wait_grok_turn", {"timeout_seconds": value}, "timeout_seconds", id=f"wait-timeout-{label}")
        for label, value in (("bool", True), ("nan", math.nan), ("inf", math.inf), ("minus-inf", -math.inf), ("zero", 0), ("negative", -1), ("over-cap", 3600.5), ("str", "10"))
    ],
    pytest.param("interrupt_grok_turn", {"handle": "not-a-handle"}, "handle", id="interrupt-handle-str"),
    pytest.param("interrupt_grok_turn", {"handle": {"harness": "grok"}}, "handle", id="interrupt-handle-mapping"),
]


async def call_with(host: Any, api: SimpleNamespace, operation: str, overrides: Mapping[str, Any]) -> Any:
    # Builds a call whose only bad value is the overridden argument (EC-1).
    if operation == "continue_grok_session":
        return await host.continue_grok_session(overrides.get("session_id", KNOWN_SESSION), turn_request(api))
    if operation == "fork_grok_session":
        return await host.fork_grok_session(overrides.get("session_id", KNOWN_SESSION), oneshot_request(api), new_session_id=overrides.get("new_session_id"))
    if operation == "list_grok_sessions":
        return await host.list_grok_sessions(cursor=overrides["cursor"])
    if operation == "search_grok_sessions":
        return await host.search_grok_sessions(overrides.get("query", "parser"), limit=overrides.get("limit", 20))
    handle = overrides.get("handle", grok_handle(api))
    if operation == "wait_grok_turn":
        return await host.wait_grok_turn(handle, timeout_seconds=overrides.get("timeout_seconds", 1.0))
    return await host.interrupt_grok_turn(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "overrides", "argument"), EC1_CASES)
async def test_invalid_primitive_arguments_fail_before_any_process(operation: str, overrides: Mapping[str, Any], argument: str, grok_api, grok_fake, make_grok_host, check_native_error) -> None:
    # EC-1: checked before any I/O, so the bad timeout wins even over an unissued handle.
    async with make_grok_host() as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await call_with(host, grok_api, operation, overrides)
    check_native_error(caught.value, code="configuration.invalid_argument", token=argument, operation=operation)
    assert argument in str(caught.value), "EC-1: the message names the argument"
    assert grok_fake.records("start") == [], "EC-1 fails before any process starts"


@pytest.mark.asyncio
async def test_aenter_without_any_grok_raises_not_installed(grok_api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # EC-11 at __aenter__: no grok_command, nothing on PATH, no ~/.grok/bin/grok.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    host = grok_api.GrokHost(grok_api.GrokHostSettings(workspace=workspace))
    with pytest.raises(grok_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code="grok.not_installed", token="GrokHostSettings.grok_command")
    assert caught.value.next_step == "Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command."
