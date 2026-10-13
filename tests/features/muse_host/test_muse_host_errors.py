"""FILE: tests/features/muse_host/test_muse_host_errors.py

PURPOSE: The MuseHost error contract as one table: each case is a (function, code) row of spec §6.3.2 and §6.3.5 reproduced through the fake muse, asserting the exact FailureCode member, a non-empty next_step that holds the row's required token, and the matching tool's error result (AC-2).
ROLE IN CODEBASE: Proves FR-3, FR-6, FR-7, FR-21 and INV-1/INV-8 for vidbyte.harnesses.native.muse.MuseHost and the vidbyte.tools.builtins.muse tools. The table also covers the shared rows EC-1 (argument checks), EC-2 (host not open) and EC-3 (host reused), and the native EC-95 `which` check at __aenter__.
ARCHITECTURE NOTE: ROWS is data; CALLS maps a row to the call that reproduces it. A call drives either the host method or the matching tool through RowContext.invoke, so one row runs twice: "host" asserts the raised NativeHostError, "tool" asserts the ToolResult.error built from it (INV-7). Setup steps inside a call (a held turn before a busy check) always use the host directly. The WSL-only rows (EC-94 and the WSL forms of EC-95) live in test_muse_host_wsl.py.
FUNCTION INVENTORY: Row describes one case; RowContext runs a call as host or tool; call_* reproduce the triggers; test_muse_error_row runs the table; test_unopened_or_closed_host_raises_process_exited covers EC-2; test_reentering_a_host_raises_invalid_argument covers EC-3; test_invalid_primitive_arguments_fail_before_any_process covers EC-1 and EC-110; test_aenter_without_muse_on_path_raises_not_installed covers EC-95 at __aenter__.
COMMON MODIFICATION PATTERNS: A new §6.3 row is one Row entry; add a call_* function only when no existing one reproduces its trigger. Keep one case per (function, code) plus named variants for distinct guards, and list any pruned duplicate in the test plan.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert on message wording beyond names the spec fixes; assert codes, tokens and context keys. 2. Do not reach the real muse: every host here runs the fake or a path that does not exist.
KNOWN EDGE CASES: Rows whose trigger is a silent fake shrink control_timeout_seconds to 0.5 and depend on fast_stop for a quick close. Turn-failure rows (EC-98 on turn/completed, EC-117 to EC-120) do not assert operation, because the spec does not say which operation a recorded turn failure names. EC-115's own next step (token continue_muse_session) replaces the turn_not_found default for steer, interrupt and wait alike, as the row says.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1, §6.3.2, §6.3.5, §6.3.7
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_errors.py
"""

from __future__ import annotations

import math
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
MISSING_SESSION = "99999999-8888-4777-a666-555555555555"
PROMPT = "List the top-level folders."
STEER_TEXT = "Also list hidden folders."
UNKNOWN_MODEL = "muse-unknown"
UNKNOWN_TURN = "turn-9999"
SHORT_CONTROL_SECONDS = 0.5
SHORT_WAIT_SECONDS = 0.3
WAIT_SECONDS = 30.0
UNISSUED_TURN_ID = "b" * 32

INIT_EXIT = {"msp": {"initialize": {"mode": "exit"}}}
INIT_SILENT = {"msp": {"initialize": {"mode": "silent"}}}
OLD_SERVER = {"msp": {"initialize": {"server_version": "1.0.0"}}}
HELD_TURN = {"turn": {"mode": "hold"}}
OVERLOADED = {"code": -32001, "message": "server overloaded"}
BACKPRESSURED = {"code": -32031, "message": "too many commands in flight"}
NOT_FOUND_METHOD = {"code": -32601, "message": "Method not found"}
CAPABILITY_REQUIRED = {"code": -32010, "message": "capability required"}
NOT_LOADED = {"code": -32024, "message": "session not loaded"}
AE_CONTEXT = {"vendor_code": "-32001", "vendor_kind": "overloaded"}
AE_KEYS = ("retryable", "vendor_error")


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
    return api.MuseTurnRequest(prompt=PROMPT, **fields)


async def call_check(ctx: RowContext) -> Any:
    return await ctx.invoke("check_muse_ready", {}, lambda: ctx.host.check_muse_ready())


async def call_list_models(ctx: RowContext) -> Any:
    return await ctx.invoke("list_muse_models", {}, lambda: ctx.host.list_muse_models())


async def call_spawn(ctx: RowContext) -> Any:
    return await ctx.invoke("spawn_muse_session", {"prompt": PROMPT}, lambda: ctx.host.spawn_muse_session(turn_request(ctx.api)))


async def call_spawn_unknown_model(ctx: RowContext) -> Any:
    args = {"prompt": PROMPT, "model": UNKNOWN_MODEL}
    return await ctx.invoke("spawn_muse_session", args, lambda: ctx.host.spawn_muse_session(turn_request(ctx.api, model=UNKNOWN_MODEL)))


async def call_spawn_at_cap(ctx: RowContext) -> Any:
    await ctx.host.spawn_muse_session(turn_request(ctx.api))
    return await call_spawn(ctx)


async def call_continue(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT}
    return await ctx.invoke("continue_muse_session", args, lambda: ctx.host.continue_muse_session(KNOWN_SESSION, turn_request(ctx.api)))


async def call_continue_missing(ctx: RowContext) -> Any:
    args = {"session_id": MISSING_SESSION, "prompt": PROMPT}
    return await ctx.invoke("continue_muse_session", args, lambda: ctx.host.continue_muse_session(MISSING_SESSION, turn_request(ctx.api)))


async def call_continue_unknown_model(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "model": UNKNOWN_MODEL}
    request = turn_request(ctx.api, model=UNKNOWN_MODEL)
    return await ctx.invoke("continue_muse_session", args, lambda: ctx.host.continue_muse_session(KNOWN_SESSION, request))


async def call_continue_busy(ctx: RowContext) -> Any:
    await ctx.host.continue_muse_session(KNOWN_SESSION, turn_request(ctx.api))
    return await call_continue(ctx)


async def call_fork(ctx: RowContext) -> Any:
    return await ctx.invoke("fork_muse_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.fork_muse_session(KNOWN_SESSION))


async def call_fork_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("fork_muse_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.fork_muse_session(MISSING_SESSION))


async def call_fork_bad_boundary(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "last_turn_id": UNKNOWN_TURN}
    return await ctx.invoke("fork_muse_session", args, lambda: ctx.host.fork_muse_session(KNOWN_SESSION, last_turn_id=UNKNOWN_TURN))


async def call_fork_busy(ctx: RowContext) -> Any:
    await ctx.host.continue_muse_session(KNOWN_SESSION, turn_request(ctx.api))
    return await call_fork(ctx)


async def call_list(ctx: RowContext) -> Any:
    return await ctx.invoke("list_muse_sessions", {}, lambda: ctx.host.list_muse_sessions())


async def call_list_stale_cursor(ctx: RowContext) -> Any:
    return await ctx.invoke("list_muse_sessions", {"cursor": "stale-cursor"}, lambda: ctx.host.list_muse_sessions(cursor="stale-cursor"))


async def call_read(ctx: RowContext) -> Any:
    return await ctx.invoke("read_muse_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.read_muse_session(KNOWN_SESSION))


async def call_read_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("read_muse_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.read_muse_session(MISSING_SESSION))


async def call_page(ctx: RowContext) -> Any:
    return await ctx.invoke("page_muse_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.page_muse_session(KNOWN_SESSION))


async def call_page_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("page_muse_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.page_muse_session(MISSING_SESSION))


async def call_track(ctx: RowContext) -> Any:
    return await ctx.invoke("track_muse_session_usage", {"session_id": KNOWN_SESSION}, lambda: ctx.host.track_muse_session_usage(KNOWN_SESSION))


async def call_track_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("track_muse_session_usage", {"session_id": MISSING_SESSION}, lambda: ctx.host.track_muse_session_usage(MISSING_SESSION))


async def steer(ctx: RowContext, handle: Any) -> Any:
    args = {"handle": handle_args(handle), "text": STEER_TEXT}
    return await ctx.invoke("steer_muse_turn", args, lambda: ctx.host.steer_muse_turn(handle, STEER_TEXT))


async def call_steer(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_muse_session(turn_request(ctx.api))
    return await steer(ctx, handle)


async def call_steer_finished(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_muse_session(turn_request(ctx.api))
    await ctx.host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    return await steer(ctx, handle)


async def call_steer_foreign(ctx: RowContext) -> Any:
    return await steer(ctx, foreign_handle(ctx.api))


async def call_interrupt(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_muse_session(turn_request(ctx.api))
    return await ctx.invoke("interrupt_muse_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_muse_turn(handle))


async def call_interrupt_unissued(ctx: RowContext) -> Any:
    handle = unissued_handle(ctx.api)
    return await ctx.invoke("interrupt_muse_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_muse_turn(handle))


async def call_wait_after_spawn(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_muse_session(turn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": WAIT_SECONDS}
    return await ctx.invoke("wait_muse_turn", args, lambda: ctx.host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS))


async def call_wait_too_short(ctx: RowContext) -> Any:
    handle = await ctx.host.spawn_muse_session(turn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": SHORT_WAIT_SECONDS}
    return await ctx.invoke("wait_muse_turn", args, lambda: ctx.host.wait_muse_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS))


async def call_wait_foreign(ctx: RowContext) -> Any:
    handle = foreign_handle(ctx.api)
    return await ctx.invoke("wait_muse_turn", {"handle": handle_args(handle)}, lambda: ctx.host.wait_muse_turn(handle))


def foreign_handle(api: SimpleNamespace) -> Any:
    return api.NativeTurnHandle(harness=api.NativeHarness.GROK, session_id=KNOWN_SESSION, turn_id=UNISSUED_TURN_ID)


def unissued_handle(api: SimpleNamespace) -> Any:
    return api.NativeTurnHandle(harness=api.NativeHarness.MUSE, session_id=KNOWN_SESSION, turn_id=UNISSUED_TURN_ID)


CALLS: dict[str, Callable[[RowContext], Awaitable[Any]]] = {
    "check_muse_ready": call_check,
    "list_muse_models": call_list_models,
    "spawn_muse_session": call_spawn,
    "spawn_unknown_model": call_spawn_unknown_model,
    "spawn_at_cap": call_spawn_at_cap,
    "continue_muse_session": call_continue,
    "continue_missing": call_continue_missing,
    "continue_unknown_model": call_continue_unknown_model,
    "continue_busy": call_continue_busy,
    "fork_muse_session": call_fork,
    "fork_missing": call_fork_missing,
    "fork_bad_boundary": call_fork_bad_boundary,
    "fork_busy": call_fork_busy,
    "list_muse_sessions": call_list,
    "list_stale_cursor": call_list_stale_cursor,
    "read_muse_session": call_read,
    "read_missing": call_read_missing,
    "page_muse_session": call_page,
    "page_missing": call_page_missing,
    "track_muse_session_usage": call_track,
    "track_missing": call_track_missing,
    "steer_muse_turn": call_steer,
    "steer_finished": call_steer_finished,
    "steer_foreign": call_steer_foreign,
    "interrupt_muse_turn": call_interrupt,
    "interrupt_unissued": call_interrupt_unissued,
    "wait_after_spawn": call_wait_after_spawn,
    "wait_too_short": call_wait_too_short,
    "wait_foreign": call_wait_foreign,
}

NI = "muse.not_installed"
PE = "muse.process_exited"
SU = "muse.server_unreachable"
PM = "muse.protocol_mismatch"
VU = "muse.version_unsupported"
CM = "muse.capability_missing"
AE = "muse.api_error"
MU = "muse.model_unknown"
SN = "muse.session_not_found"
SB = "muse.session_busy"
BE = "muse.budget_exhausted"
SR = "muse.sandbox_not_ready"
TT = "muse.turn_timed_out"
TN = "muse.turn_not_found"
IA = "configuration.invalid_argument"


def host_wide(operation: str, main_method: str, *, protocol_result: Mapping[str, Any], ok_keys: tuple[str, ...] = ()) -> tuple[Row, ...]:
    # EC-95 to EC-100 and EC-102 for one function whose short-lived or turn peer calls main_method after initialize.
    after_init = ("session/start", "session/resume", "turn/start") if operation in ("spawn_muse_session", "continue_muse_session") else ()
    return (
        Row("EC-95", operation, NI, "muse_path", command="missing"),
        Row("EC-96", operation, PE, "check_muse_ready", INIT_EXIT, never_sent=after_init),
        Row("EC-97", operation, SU, "control_timeout_seconds", {"msp": {main_method: {"mode": "silent"}}}, control_timeout=SHORT_CONTROL_SECONDS, never_sent=("turn/start",)),
        Row("EC-98", operation, PM, "check_muse_ready", {"msp": {main_method: {"result": dict(protocol_result)}}}, never_sent=("turn/start",)),
        Row("EC-99", operation, VU, "1.0.1", OLD_SERVER, context_keys=ok_keys, never_sent=(main_method, "turn/start")),
        Row("EC-100", operation, CM, "upgrade", {"msp": {main_method: {"error": CAPABILITY_REQUIRED if operation == "spawn_muse_session" else NOT_FOUND_METHOD}}}, never_sent=("turn/start",)),
        Row("EC-102", operation, AE, "vendor_error", {"msp": {main_method: {"error": OVERLOADED}}}, context=AE_CONTEXT, context_keys=AE_KEYS, never_sent=("turn/start",)),
    )


ROWS: tuple[Row, ...] = (
    # check_muse_ready: `<launcher> --version` through CliRunner, then a short-lived initialize and `initialized`.
    Row("EC-95", "check_muse_ready", NI, "muse_path", command="missing"),
    Row("EC-96", "check_muse_ready", PE, "check_muse_ready", INIT_EXIT, variant="peer-exit"),
    Row("EC-96", "check_muse_ready", PE, "check_muse_ready", command="not_executable", variant="launch-oserror"),
    Row("EC-97", "check_muse_ready", SU, "control_timeout_seconds", INIT_SILENT, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-98", "check_muse_ready", PM, "check_muse_ready", {"msp": {"initialize": {"schema_version": 2}}}),
    Row("EC-104", "check_muse_ready", PM, "check_muse_ready", {"version": {"stdout": "muse build unknown\n"}}, never_launched=("peer",)),
    Row("EC-99", "check_muse_ready", VU, "1.0.1", OLD_SERVER),
    Row("EC-103", "check_muse_ready", VU, "1.0.1", {"version": {"stdout": "Muse Code 1.0.0 (1.0.0-R1999.1)\n"}}, never_launched=("peer",)),
    Row("EC-100", "check_muse_ready", CM, "upgrade", {"msp": {"initialize": {"error": NOT_FOUND_METHOD}}}),
    Row("EC-102", "check_muse_ready", AE, "vendor_error", {"msp": {"initialize": {"error": OVERLOADED}}}, context=AE_CONTEXT, context_keys=AE_KEYS),
    # list_muse_models: initialize, initialized, model/list (EC-98 when models is not a list).
    *host_wide("list_muse_models", "model/list", protocol_result={"models": "not-a-list", "profileId": None, "providerId": "meta", "source": "providerCatalog"}),
    # spawn_muse_session: initialize, initialized, [model/list], session/start, turn/start.
    *host_wide("spawn_muse_session", "session/start", protocol_result={"viewCursor": "v-1"}),
    Row("EC-101", "spawn_muse_session", IA, "prompt", {"msp": {"turn/start": {"error": {"code": -32002, "message": "input too large"}}}}),
    Row("EC-108", "spawn_muse_session", MU, "list_muse_models", call="spawn_unknown_model", context_keys=("available_models",), never_sent=("session/start", "turn/start")),
    Row("EC-107", "spawn_muse_session", SB, "interrupt_muse_turn", HELD_TURN, call="spawn_at_cap", max_live_turns=1, peer_launches=1),
    # continue_muse_session: initialize, initialized, [model/list], session/resume, turn/start.
    *host_wide("continue_muse_session", "session/resume", protocol_result={"viewCursor": "v-1"}),
    Row("EC-111", "continue_muse_session", SN, "list_muse_sessions", call="continue_missing", never_sent=("turn/start",)),
    Row("EC-112", "continue_muse_session", SB, "interrupt_muse_turn", HELD_TURN, call="continue_busy", variant="local-live-turn", peer_launches=1),
    Row("EC-112", "continue_muse_session", SB, "interrupt_muse_turn", {"session_overrides": {KNOWN_SESSION: {"status": "running"}}}, variant="status-running", never_sent=("turn/start",)),
    Row("EC-112", "continue_muse_session", SB, "interrupt_muse_turn", {"session_overrides": {KNOWN_SESSION: {"activeTurnId": "turn-elsewhere"}}}, variant="active-turn-id", never_sent=("turn/start",)),
    Row("EC-112", "continue_muse_session", SB, "interrupt_muse_turn", {"msp": {"session/resume": {"error": {"code": -32021, "message": "session in use"}}}}, variant="minus-32021", never_sent=("turn/start",)),
    Row("EC-108", "continue_muse_session", MU, "list_muse_models", call="continue_unknown_model", context_keys=("available_models",), never_sent=("session/resume", "turn/start")),
    # fork_muse_session: initialize, initialized, session/fork (one session/resume and retry on -32024).
    *host_wide("fork_muse_session", "session/fork", protocol_result={"viewCursor": "v-1"}),
    Row("EC-111", "fork_muse_session", SN, "list_muse_sessions", call="fork_missing"),
    Row("EC-112", "fork_muse_session", SB, "interrupt_muse_turn", HELD_TURN, call="fork_busy", peer_launches=1, never_sent=("session/fork",)),
    Row("EC-113", "fork_muse_session", IA, "last_turn_id", call="fork_bad_boundary"),
    Row("EC-114", "fork_muse_session", AE, "vendor_error", {"msp": {"session/fork": {"errors_first": [NOT_LOADED, NOT_LOADED]}}}, variant="second-not-loaded", context={"vendor_code": "-32024"}),
    # list_muse_sessions: initialize, initialized, session/list.
    *host_wide("list_muse_sessions", "session/list", protocol_result={"sessions": "not-a-list", "nextCursor": None}),
    Row("EC-1", "list_muse_sessions", IA, "without a cursor", {"msp": {"session/list": {"cursor_error": {"code": -32602, "message": "Invalid params"}}}}, call="list_stale_cursor", variant="stale-cursor"),
    # read_muse_session: initialize, initialized, session/read with excludeItems.
    *host_wide("read_muse_session", "session/read", protocol_result={"viewCursor": "v-1"}),
    Row("EC-111", "read_muse_session", SN, "list_muse_sessions", call="read_missing"),
    Row("EC-114", "read_muse_session", AE, "vendor_error", {"msp": {"session/read": {"errors_first": [NOT_LOADED, NOT_LOADED]}}}, variant="second-not-loaded", context={"vendor_code": "-32024"}),
    # page_muse_session: initialize, initialized, view/page.
    *host_wide("page_muse_session", "view/page", protocol_result={"events": "not-a-list", "nextCursor": None}),
    Row("EC-111", "page_muse_session", SN, "list_muse_sessions", call="page_missing"),
    # track_muse_session_usage: initialize, initialized, backward view/page reads.
    *host_wide("track_muse_session_usage", "view/page", protocol_result={"events": "not-a-list", "nextCursor": None}),
    Row("EC-111", "track_muse_session_usage", SN, "list_muse_sessions", call="track_missing"),
    # steer_muse_turn: turn/steer on the turn's own peer (EC-96, EC-97, EC-101, EC-102, EC-115).
    Row("EC-96", "steer_muse_turn", PE, "check_muse_ready", {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"mode": "exit"}}}),
    Row("EC-97", "steer_muse_turn", SU, "control_timeout_seconds", {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"mode": "silent"}}}, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-98", "steer_muse_turn", PM, "check_muse_ready", {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"result": {"commandId": "not-an-ack"}}}}),
    Row("EC-101", "steer_muse_turn", IA, "prompt", {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"error": {"code": -32002, "message": "input too large"}}}}),
    Row("EC-102", "steer_muse_turn", AE, "vendor_error", {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"error": BACKPRESSURED}}}, context={"vendor_code": "-32031", "vendor_kind": "backpressured"}, context_keys=AE_KEYS),
    Row("EC-115", "steer_muse_turn", TN, "continue_muse_session", call="steer_finished", variant="finished-turn", never_sent=("turn/steer",)),
    Row("EC-115", "steer_muse_turn", TN, "continue_muse_session", call="steer_foreign", variant="foreign-handle"),
    # interrupt_muse_turn: turn/interrupt on the turn's own peer (EC-96, EC-97, EC-115 for a foreign or unknown handle).
    Row("EC-96", "interrupt_muse_turn", PE, "check_muse_ready", {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"mode": "exit"}}}),
    Row("EC-97", "interrupt_muse_turn", SU, "control_timeout_seconds", {"turn": {"mode": "hold", "on_interrupt": "ignore"}, "msp": {"turn/interrupt": {"mode": "silent"}}}, control_timeout=SHORT_CONTROL_SECONDS),
    Row("EC-115", "interrupt_muse_turn", TN, "continue_muse_session", call="interrupt_unissued"),
    # wait_muse_turn: outcomes recorded by the driver and raised by wait (D-9).
    Row("EC-115", "wait_muse_turn", TN, "continue_muse_session", call="wait_foreign"),
    Row("EC-116", "wait_muse_turn", TT, "wait_muse_turn", HELD_TURN, call="wait_too_short"),
    Row("EC-117", "wait_muse_turn", BE, "continue_muse_session", {"turn": {"terminal": "failed", "error": {"kind": "stepLimit", "message": "step limit reached", "retryable": False}}}, call="wait_after_spawn", check_operation=False),
    Row("EC-118", "wait_muse_turn", SR, "muse sandbox", {"turn": {"terminal": "failed", "error": {"kind": "environmentError", "message": "sandbox failed", "retryable": False}}}, call="wait_after_spawn", check_operation=False),
    Row("EC-119", "wait_muse_turn", AE, "vendor_error", {"turn": {"terminal": "failed", "error": {"kind": "modelError", "message": "model refused", "retryable": True}}}, call="wait_after_spawn", context={"vendor_kind": "modelError"}, context_keys=AE_KEYS, check_operation=False),
    Row("EC-120", "wait_muse_turn", PE, "check_muse_ready", {"turn": {"mode": "exit_before_complete"}}, call="wait_after_spawn", check_operation=False),
    Row("EC-98", "wait_muse_turn", PM, "check_muse_ready", {"turn": {"terminal": "failed", "drop_error": True}}, call="wait_after_spawn", check_operation=False),
)


def row_id(row: Row) -> str:
    suffix = f"-{row.variant}" if row.variant else ""
    return f"{row.ec}-{row.operation}-{row.code}{suffix}"


CASES = [pytest.param(row, "host", id=f"{row_id(row)}-host") for row in ROWS] + [
    pytest.param(row, "tool", id=f"{row_id(row)}-tool") for row in ROWS if row.tool
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "mode"), CASES)
async def test_muse_error_row(row: Row, mode: str, request: pytest.FixtureRequest, muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    command = {"fake": None, "missing": muse_fake.missing_command, "not_executable": muse_fake.not_executable_command}[row.command]
    host = make_muse_host(row.scenario, command=command() if command else None, control_timeout_seconds=row.control_timeout, max_live_turns=row.max_live_turns)
    call = CALLS[row.call or row.operation]
    async with host:
        if mode == "host":
            with pytest.raises(muse_api.NativeHostError) as caught:
                await call(RowContext(host, muse_api))
            error = caught.value
        else:
            tools_api = request.getfixturevalue("muse_tools_api")
            result = await call(RowContext(host, muse_api, tools_api.MuseTools(host), tools_api))
    if mode == "host":
        check_native_error(error, code=row.code, token=row.token, operation=row.operation if row.check_operation else None)
        for key, value in row.context.items():
            assert error.context.get(key) == value, f"context[{key!r}] should be {value!r}: {dict(error.context)}"
        for key in row.context_keys:
            assert error.context.get(key), f"context should carry {key!r}: {dict(error.context)}"
    else:
        request.getfixturevalue("check_tool_error")(result, code=row.code, token=row.token, tool_name=row.operation)
        if "retryable" in row.context_keys:
            assert isinstance(result.metadata.get("retryable"), bool), f"INV-7: metadata carries retryable as a bool: {dict(result.metadata)}"
    assert_fake_saw(row, muse_fake)


def assert_fake_saw(row: Row, muse_fake: Any) -> None:
    # INV-5: a failed check makes zero vendor calls that can start a turn.
    received = muse_fake.received_methods()
    for method in row.never_sent:
        assert method not in received, f"{method} must not be sent for {row.ec}; the fake received {received}"
    roles = [record["role"] for record in muse_fake.starts()]
    for role in row.never_launched:
        assert role not in roles, f"no {role} process may start for {row.ec}; started {roles}"
    if row.peer_launches is not None:
        assert roles.count("peer") == row.peer_launches, f"{row.ec} must not start another peer; started {roles}"


@pytest.mark.asyncio
async def test_model_unknown_context_names_the_models_muse_offers(muse_api, make_muse_host, fast_stop) -> None:
    # AC-7: the context lists the available ids, and the unknown id is not among them.
    async with make_muse_host() as host:
        with pytest.raises(muse_api.NativeHostError) as caught:
            await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT, model=UNKNOWN_MODEL))
    listed = caught.value.context["available_models"]
    assert "muse-large" in listed and "muse-fast" in listed
    assert UNKNOWN_MODEL not in listed


def muse_handle(api: SimpleNamespace) -> Any:
    return unissued_handle(api)


EC2_CALLS: dict[str, Callable[[Any, SimpleNamespace], Awaitable[Any]]] = {
    "check_muse_ready": lambda host, api: host.check_muse_ready(),
    "list_muse_models": lambda host, api: host.list_muse_models(),
    "spawn_muse_session": lambda host, api: host.spawn_muse_session(turn_request(api)),
    "continue_muse_session": lambda host, api: host.continue_muse_session(KNOWN_SESSION, turn_request(api)),
    "fork_muse_session": lambda host, api: host.fork_muse_session(KNOWN_SESSION),
    "list_muse_sessions": lambda host, api: host.list_muse_sessions(),
    "read_muse_session": lambda host, api: host.read_muse_session(KNOWN_SESSION),
    "page_muse_session": lambda host, api: host.page_muse_session(KNOWN_SESSION),
    "steer_muse_turn": lambda host, api: host.steer_muse_turn(muse_handle(api), STEER_TEXT),
    "interrupt_muse_turn": lambda host, api: host.interrupt_muse_turn(muse_handle(api)),
    "wait_muse_turn": lambda host, api: host.wait_muse_turn(muse_handle(api)),
    "track_muse_session_usage": lambda host, api: host.track_muse_session_usage(KNOWN_SESSION),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(EC2_CALLS))
async def test_unopened_or_closed_host_raises_process_exited(operation: str, muse_api, muse_fake, make_muse_host, check_native_error) -> None:
    # EC-2: never entered, then entered and exited; both raise before anything starts.
    host = make_muse_host()
    with pytest.raises(muse_api.NativeHostError) as before:
        await EC2_CALLS[operation](host, muse_api)
    check_native_error(before.value, code="muse.process_exited", token="async with", operation=operation)
    async with host:
        pass
    with pytest.raises(muse_api.NativeHostError) as after:
        await EC2_CALLS[operation](host, muse_api)
    check_native_error(after.value, code="muse.process_exited", token="async with", operation=operation)
    assert muse_fake.starts() == [], "EC-2 starts nothing"


@pytest.mark.asyncio
async def test_reentering_a_host_raises_invalid_argument(muse_api, muse_fake, make_muse_host, check_native_error) -> None:
    # EC-3: a host is used once, whether it is open or already closed; __aenter__ starts no muse process.
    host = make_muse_host()
    async with host:
        with pytest.raises(muse_api.NativeHostError) as while_open:
            await host.__aenter__()
    check_native_error(while_open.value, code="configuration.invalid_argument", token="new host")
    with pytest.raises(muse_api.NativeHostError) as after_close:
        async with host:
            pass
    check_native_error(after_close.value, code="configuration.invalid_argument", token="new host")
    assert muse_fake.starts() == [], "__aenter__ starts no muse process (§6.3.5)"


def _bad_session_ids() -> list[Any]:
    return ["not-a-uuid", "", "--yolo", "2d4c6e8f1a3b4c5d8e7f9a0b1c2d3e4f", 42]


EC1_CASES: list[Any] = [
    pytest.param("spawn_muse_session", {"request": "List the folders."}, "request", id="spawn-request-str"),
    *[pytest.param("continue_muse_session", {"session_id": value}, "session_id", id=f"continue-session_id-{index}") for index, value in enumerate(_bad_session_ids())],
    pytest.param("continue_muse_session", {"request": {"prompt": PROMPT}}, "request", id="continue-request-mapping"),
    *[pytest.param("fork_muse_session", {"session_id": value}, "session_id", id=f"fork-session_id-{index}") for index, value in enumerate(_bad_session_ids())],
    pytest.param("fork_muse_session", {"last_turn_id": ""}, "last_turn_id", id="fork-last_turn_id-empty"),
    pytest.param("fork_muse_session", {"last_turn_id": "t" * 129}, "last_turn_id", id="fork-last_turn_id-too-long"),
    pytest.param("list_muse_sessions", {"cursor": ""}, "cursor", id="list-cursor-empty"),
    pytest.param("list_muse_sessions", {"cursor": "c" * 513}, "cursor", id="list-cursor-too-long"),
    pytest.param("list_muse_sessions", {"cursor": 7}, "cursor", id="list-cursor-type"),
    pytest.param("list_muse_sessions", {"limit": 0}, "limit", id="list-limit-zero"),
    pytest.param("list_muse_sessions", {"limit": 201}, "limit", id="list-limit-over"),
    pytest.param("list_muse_sessions", {"limit": True}, "limit", id="list-limit-bool"),
    pytest.param("read_muse_session", {"session_id": "not-a-uuid"}, "session_id", id="read-session_id"),
    pytest.param("page_muse_session", {"session_id": "not-a-uuid"}, "session_id", id="page-session_id"),
    pytest.param("page_muse_session", {"limit": 0}, "limit", id="page-limit-zero"),
    pytest.param("page_muse_session", {"limit": 201}, "limit", id="page-limit-over"),
    pytest.param("page_muse_session", {"limit": 2.5}, "limit", id="page-limit-float"),
    pytest.param("page_muse_session", {"direction": "forward"}, "direction", id="page-direction-str"),
    pytest.param("page_muse_session", {"cursor": ""}, "cursor", id="page-cursor-empty"),
    pytest.param("steer_muse_turn", {"handle": "not-a-handle"}, "handle", id="steer-handle-str"),
    pytest.param("steer_muse_turn", {"text": ""}, "text", id="steer-text-empty"),
    pytest.param("steer_muse_turn", {"text": "   "}, "text", id="steer-text-blank"),
    pytest.param("steer_muse_turn", {"text": "s" * 200001}, "text", id="steer-text-too-long"),
    pytest.param("steer_muse_turn", {"text": 5}, "text", id="steer-text-type"),
    pytest.param("interrupt_muse_turn", {"handle": "not-a-handle"}, "handle", id="interrupt-handle-str"),
    pytest.param("interrupt_muse_turn", {"handle": {"harness": "muse"}}, "handle", id="interrupt-handle-mapping"),
    pytest.param("wait_muse_turn", {"handle": None}, "handle", id="wait-handle-none"),
    *[
        pytest.param("wait_muse_turn", {"timeout_seconds": value}, "timeout_seconds", id=f"wait-timeout-{label}")
        for label, value in (("bool", True), ("nan", math.nan), ("inf", math.inf), ("minus-inf", -math.inf), ("zero", 0), ("negative", -1), ("over-cap", 3600.5), ("str", "10"))
    ],
    pytest.param("track_muse_session_usage", {"session_id": "not-a-uuid"}, "session_id", id="track-session_id"),
]


async def call_with(host: Any, api: SimpleNamespace, operation: str, overrides: Mapping[str, Any]) -> Any:
    # Builds a call whose only bad value is the overridden argument (EC-1, EC-110).
    session_id = overrides.get("session_id", KNOWN_SESSION)
    request = overrides.get("request", turn_request(api))
    handle = overrides.get("handle", muse_handle(api))
    calls: dict[str, Callable[[], Awaitable[Any]]] = {
        "spawn_muse_session": lambda: host.spawn_muse_session(request),
        "continue_muse_session": lambda: host.continue_muse_session(session_id, request),
        "fork_muse_session": lambda: host.fork_muse_session(session_id, last_turn_id=overrides.get("last_turn_id")),
        "list_muse_sessions": lambda: host.list_muse_sessions(cursor=overrides.get("cursor"), limit=overrides.get("limit", 50)),
        "read_muse_session": lambda: host.read_muse_session(session_id),
        "page_muse_session": lambda: host.page_muse_session(session_id, cursor=overrides.get("cursor"), limit=overrides.get("limit", 50), direction=overrides.get("direction", api.MuseViewDirection.FORWARD)),
        "steer_muse_turn": lambda: host.steer_muse_turn(handle, overrides.get("text", STEER_TEXT)),
        "interrupt_muse_turn": lambda: host.interrupt_muse_turn(handle),
        "wait_muse_turn": lambda: host.wait_muse_turn(handle, timeout_seconds=overrides.get("timeout_seconds", 1.0)),
        "track_muse_session_usage": lambda: host.track_muse_session_usage(session_id),
    }
    return await calls[operation]()


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "overrides", "argument"), EC1_CASES)
async def test_invalid_primitive_arguments_fail_before_any_process(operation: str, overrides: Mapping[str, Any], argument: str, muse_api, muse_fake, make_muse_host, check_native_error) -> None:
    # EC-1 / EC-110: checked before any I/O, so the bad value wins even over an unissued handle.
    async with make_muse_host() as host:
        with pytest.raises(muse_api.NativeHostError) as caught:
            await call_with(host, muse_api, operation, overrides)
    check_native_error(caught.value, code="configuration.invalid_argument", token=argument, operation=operation)
    assert argument in str(caught.value), "EC-1: the message names the argument"
    assert muse_fake.starts() == [], "EC-1 fails before any process starts"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="on win32 a host without muse_command or wsl_distro raises muse.wsl_unavailable instead (EC-94); see test_muse_host_wsl.py")
async def test_aenter_without_muse_on_path_raises_not_installed(muse_api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # EC-95 at __aenter__: native mode, no muse_command, and shutil.which("muse") finds nothing.
    empty = tmp_path / "empty-path"
    empty.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    host = muse_api.MuseHost(muse_api.MuseHostSettings(workspace=workspace))
    with pytest.raises(muse_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code="muse.not_installed", token="muse_path")
    assert caught.value.next_step == "Install Muse Code 1.0.1 or newer in the distro, or set MuseHostSettings.muse_path."
