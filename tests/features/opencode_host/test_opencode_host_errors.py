"""FILE: tests/features/opencode_host/test_opencode_host_errors.py

PURPOSE: The OpencodeHost error contract as one table: each case is a (function, code) row of spec §6.3.2 and §6.3.4 reproduced through FakeOpencodeServer, asserting the exact FailureCode member, a non-empty next_step that holds the row's required token, and the matching tool's error result (AC-2).
ROLE IN CODEBASE: Proves FR-6, FR-7, FR-21 and INV-1/INV-5/INV-8 for vidbyte.harnesses.native.opencode.OpencodeHost and the vidbyte.tools.builtins.opencode tools. It also covers the shared rows EC-1 (argument checks), EC-2 (host not open) and EC-3 (host reused), and the __aenter__ rows of the host-wide table.
ARCHITECTURE NOTE: ROWS is data; CALLS maps a row to the call that reproduces it. A row's failure is armed on the fake only after __aenter__ and the call's own setup, through RowContext.invoke, so the injected failure hits the function under test and nothing before it. One row runs twice: "host" asserts the raised NativeHostError, "tool" asserts the ToolResult.error built from it (INV-7).
FUNCTION INVENTORY: Row describes one case; RowContext arms the failure and runs a call as host or tool; call_* reproduce the triggers; test_opencode_error_row runs the table; test_aenter_error_row covers the host-wide rows at __aenter__; test_unopened_or_closed_host_raises_process_exited covers EC-2; test_reentering_a_host_raises_invalid_argument covers EC-3; test_invalid_primitive_arguments_make_no_request covers EC-1, EC-64, EC-71, EC-74 and EC-77.
COMMON MODIFICATION PATTERNS: A new §6.3.4 row is one Row entry; add a call_* function only when no existing one reproduces its trigger. Keep one case per (function, code) and list any pruned duplicate in the test plan.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert on message wording beyond names the spec fixes; assert codes, tokens and context keys. 2. Do not arm a failure before __aenter__ in a row; the health check would fail first and the row would prove the wrong function.
KNOWN EDGE CASES: Turn-failure rows (wait_opencode_turn) do not assert operation, because the spec does not say which operation a recorded turn failure names. EC-57's next step is row-specific (token server_password), unlike EC-63 and EC-82, which use the code's default (token opencode auth login).
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1, §6.3.2, §6.3.4, §6.3.7
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_errors.py
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

KNOWN_SESSION = "ses_known0001"
OTHER_SESSION = "ses_other0002"
MISSING_SESSION = "ses_missing0003"
KNOWN_USER_MESSAGE = "msg_00000001"
KNOWN_REPLY_MESSAGE = "msg_00000002"
MISSING_MESSAGE = "msg_99999999"
KNOWN_PART = "prt_00000001"
PROMPT = "List the top-level folders."
UNKNOWN_MODEL = "acme/coder-ultra"
UNISSUED_TURN_ID = "a" * 32
SHORT_WAIT_SECONDS = 0.3
TURN_WAIT_SECONDS = 30.0


@dataclass(frozen=True)
class Row:
    """One (function, code) row of the §6.3 error tables."""

    ec: str
    operation: str
    code: str
    token: str
    call: str = ""
    variant: str = ""
    fail: tuple[str, str] | None = None
    prepare: str = ""
    plan: Mapping[str, Any] = field(default_factory=dict)
    max_live_turns: int = 4
    request_timeout: float = 10.0
    context: Mapping[str, str] = field(default_factory=dict)
    context_keys: tuple[str, ...] = ()
    never_sent: tuple[str, ...] = ()
    check_operation: bool = True
    tool: bool = True


@dataclass
class RowContext:
    """Arms the row's failure after setup, then runs the final call against the host or the tool."""

    host: Any
    api: SimpleNamespace
    fake: Any
    row: Row
    tools: Any = None
    tools_api: SimpleNamespace | None = None
    armed_at: int = 0

    async def invoke(self, tool_name: str, tool_args: Mapping[str, Any], direct: Callable[[], Awaitable[Any]]) -> Any:
        self.arm()
        if self.tools is None:
            return await direct()
        tool = {tool.name: tool for tool in self.tools.all()}[tool_name]
        return await tool.execute(self.tools_api.ToolCall(tool_name, dict(tool_args)))

    def arm(self) -> None:
        self.armed_at = len(self.fake.requests)
        if self.row.fail is not None:
            self.fake.fail(*self.row.fail)
        PREPARES[self.row.prepare](self.fake)


def handle_args(handle: Any) -> dict[str, str]:
    return {"harness": handle.harness.value, "session_id": handle.session_id, "turn_id": handle.turn_id}


def prompt_request(api: SimpleNamespace, **fields: Any) -> Any:
    return api.OpencodePromptRequest(prompt=PROMPT, **fields)


def spawn_request(api: SimpleNamespace, **fields: Any) -> Any:
    return api.OpencodeSpawnRequest(turn=prompt_request(api, **fields))


def foreign_handle(api: SimpleNamespace) -> Any:
    return api.NativeTurnHandle(harness=api.NativeHarness.GROK, session_id="6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b", turn_id=UNISSUED_TURN_ID)


def unissued_handle(api: SimpleNamespace) -> Any:
    return api.NativeTurnHandle(harness=api.NativeHarness.OPENCODE, session_id=KNOWN_SESSION, turn_id=UNISSUED_TURN_ID)


async def call_check(ctx: RowContext) -> Any:
    return await ctx.invoke("check_opencode_ready", {}, lambda: ctx.host.check_opencode_ready())


async def call_list_models(ctx: RowContext) -> Any:
    return await ctx.invoke("list_opencode_models", {}, lambda: ctx.host.list_opencode_models())


async def call_list_models_unknown_provider(ctx: RowContext) -> Any:
    return await ctx.invoke("list_opencode_models", {"provider_id": "ghost-ai"}, lambda: ctx.host.list_opencode_models("ghost-ai"))


async def call_list_providers(ctx: RowContext) -> Any:
    return await ctx.invoke("list_opencode_providers", {}, lambda: ctx.host.list_opencode_providers())


async def call_provider_auth(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_provider_auth", {}, lambda: ctx.host.get_opencode_provider_auth())


async def call_spawn(ctx: RowContext) -> Any:
    return await ctx.invoke("spawn_opencode_session", {"prompt": PROMPT}, lambda: ctx.host.spawn_opencode_session(spawn_request(ctx.api)))


async def call_spawn_unknown_model(ctx: RowContext) -> Any:
    args = {"prompt": PROMPT, "model": UNKNOWN_MODEL}
    return await ctx.invoke("spawn_opencode_session", args, lambda: ctx.host.spawn_opencode_session(spawn_request(ctx.api, model=UNKNOWN_MODEL)))


async def call_spawn_at_cap(ctx: RowContext) -> Any:
    # max_live_turns=1: the first, held turn fills the host (EC-67).
    ctx.fake.plan("hold")
    await ctx.host.spawn_opencode_session(spawn_request(ctx.api))
    return await call_spawn(ctx)


async def call_continue(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT}
    return await ctx.invoke("continue_opencode_session", args, lambda: ctx.host.continue_opencode_session(KNOWN_SESSION, prompt_request(ctx.api)))


async def call_continue_unknown_model(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "prompt": PROMPT, "model": UNKNOWN_MODEL}
    return await ctx.invoke("continue_opencode_session", args, lambda: ctx.host.continue_opencode_session(KNOWN_SESSION, prompt_request(ctx.api, model=UNKNOWN_MODEL)))


async def call_continue_missing(ctx: RowContext) -> Any:
    args = {"session_id": MISSING_SESSION, "prompt": PROMPT}
    return await ctx.invoke("continue_opencode_session", args, lambda: ctx.host.continue_opencode_session(MISSING_SESSION, prompt_request(ctx.api)))


async def call_continue_with_live_turn(ctx: RowContext) -> Any:
    # This host already runs a turn on the session (EC-73, INV-14).
    ctx.fake.plan("hold")
    await ctx.host.continue_opencode_session(KNOWN_SESSION, prompt_request(ctx.api))
    return await call_continue(ctx)


async def call_fork(ctx: RowContext) -> Any:
    return await ctx.invoke("fork_opencode_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.fork_opencode_session(KNOWN_SESSION))


async def call_fork_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("fork_opencode_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.fork_opencode_session(MISSING_SESSION))


async def call_fork_missing_message(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": MISSING_MESSAGE}
    return await ctx.invoke("fork_opencode_session", args, lambda: ctx.host.fork_opencode_session(KNOWN_SESSION, MISSING_MESSAGE))


async def call_revert(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": KNOWN_REPLY_MESSAGE}
    return await ctx.invoke("revert_opencode_session", args, lambda: ctx.host.revert_opencode_session(KNOWN_SESSION, KNOWN_REPLY_MESSAGE))


async def call_revert_missing(ctx: RowContext) -> Any:
    args = {"session_id": MISSING_SESSION, "message_id": KNOWN_REPLY_MESSAGE}
    return await ctx.invoke("revert_opencode_session", args, lambda: ctx.host.revert_opencode_session(MISSING_SESSION, KNOWN_REPLY_MESSAGE))


async def call_revert_missing_message(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": MISSING_MESSAGE}
    return await ctx.invoke("revert_opencode_session", args, lambda: ctx.host.revert_opencode_session(KNOWN_SESSION, MISSING_MESSAGE))


async def call_unrevert(ctx: RowContext) -> Any:
    return await ctx.invoke("unrevert_opencode_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.unrevert_opencode_session(KNOWN_SESSION))


async def call_unrevert_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("unrevert_opencode_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.unrevert_opencode_session(MISSING_SESSION))


async def call_list_sessions(ctx: RowContext) -> Any:
    return await ctx.invoke("list_opencode_sessions", {}, lambda: ctx.host.list_opencode_sessions())


async def call_get_session(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session", {"session_id": KNOWN_SESSION}, lambda: ctx.host.get_opencode_session(KNOWN_SESSION))


async def call_get_session_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session", {"session_id": MISSING_SESSION}, lambda: ctx.host.get_opencode_session(MISSING_SESSION))


async def call_get_messages(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session_messages", {"session_id": KNOWN_SESSION}, lambda: ctx.host.get_opencode_session_messages(KNOWN_SESSION))


async def call_get_messages_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session_messages", {"session_id": MISSING_SESSION}, lambda: ctx.host.get_opencode_session_messages(MISSING_SESSION))


async def call_get_message(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": KNOWN_REPLY_MESSAGE}
    return await ctx.invoke("get_opencode_message", args, lambda: ctx.host.get_opencode_message(KNOWN_SESSION, KNOWN_REPLY_MESSAGE))


async def call_get_message_missing_session(ctx: RowContext) -> Any:
    args = {"session_id": MISSING_SESSION, "message_id": KNOWN_REPLY_MESSAGE}
    return await ctx.invoke("get_opencode_message", args, lambda: ctx.host.get_opencode_message(MISSING_SESSION, KNOWN_REPLY_MESSAGE))


async def call_get_message_missing(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": MISSING_MESSAGE}
    return await ctx.invoke("get_opencode_message", args, lambda: ctx.host.get_opencode_message(KNOWN_SESSION, MISSING_MESSAGE))


async def call_get_diff(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session_diff", {"session_id": KNOWN_SESSION}, lambda: ctx.host.get_opencode_session_diff(KNOWN_SESSION))


async def call_get_diff_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("get_opencode_session_diff", {"session_id": MISSING_SESSION}, lambda: ctx.host.get_opencode_session_diff(MISSING_SESSION))


async def call_get_diff_missing_message(ctx: RowContext) -> Any:
    args = {"session_id": KNOWN_SESSION, "message_id": MISSING_MESSAGE}
    return await ctx.invoke("get_opencode_session_diff", args, lambda: ctx.host.get_opencode_session_diff(KNOWN_SESSION, MISSING_MESSAGE))


async def call_wait_after_spawn(ctx: RowContext) -> Any:
    # The row's plan scripts the turn; the failure is recorded by the watcher and raised by wait.
    ctx.fake.plan(ctx.row.plan["mode"], **{key: value for key, value in ctx.row.plan.items() if key != "mode"})
    handle = await ctx.host.spawn_opencode_session(spawn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": TURN_WAIT_SECONDS}
    return await ctx.invoke("wait_opencode_turn", args, lambda: ctx.host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS))


async def call_wait_too_short(ctx: RowContext) -> Any:
    ctx.fake.plan("hold")
    handle = await ctx.host.spawn_opencode_session(spawn_request(ctx.api))
    args = {"handle": handle_args(handle), "timeout_seconds": SHORT_WAIT_SECONDS}
    return await ctx.invoke("wait_opencode_turn", args, lambda: ctx.host.wait_opencode_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS))


async def call_wait_foreign_handle(ctx: RowContext) -> Any:
    handle = foreign_handle(ctx.api)
    return await ctx.invoke("wait_opencode_turn", {"handle": handle_args(handle)}, lambda: ctx.host.wait_opencode_turn(handle))


async def call_wait_unissued_handle(ctx: RowContext) -> Any:
    handle = unissued_handle(ctx.api)
    return await ctx.invoke("wait_opencode_turn", {"handle": handle_args(handle)}, lambda: ctx.host.wait_opencode_turn(handle))


async def call_interrupt_running(ctx: RowContext) -> Any:
    ctx.fake.plan("hold")
    handle = await ctx.host.spawn_opencode_session(spawn_request(ctx.api))
    return await ctx.invoke("interrupt_opencode_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_opencode_turn(handle))


async def call_interrupt_deleted_session(ctx: RowContext) -> Any:
    # EC-90: abort answers `200 true` for a missing session, so the host must check first.
    ctx.fake.plan("hold")
    handle = await ctx.host.spawn_opencode_session(spawn_request(ctx.api))
    ctx.fake.delete_session(handle.session_id)
    return await ctx.invoke("interrupt_opencode_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_opencode_turn(handle))


async def call_interrupt_foreign_handle(ctx: RowContext) -> Any:
    handle = foreign_handle(ctx.api)
    return await ctx.invoke("interrupt_opencode_turn", {"handle": handle_args(handle)}, lambda: ctx.host.interrupt_opencode_turn(handle))


async def call_track_usage(ctx: RowContext) -> Any:
    return await ctx.invoke("track_opencode_session_usage", {"session_id": KNOWN_SESSION}, lambda: ctx.host.track_opencode_session_usage(KNOWN_SESSION))


async def call_track_usage_missing(ctx: RowContext) -> Any:
    return await ctx.invoke("track_opencode_session_usage", {"session_id": MISSING_SESSION}, lambda: ctx.host.track_opencode_session_usage(MISSING_SESSION))


async def call_add_mcp(ctx: RowContext) -> Any:
    config = ctx.api.OpencodeMcpServerConfig(name="files", kind=ctx.api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"))
    return await ctx.invoke("add_opencode_mcp_server", {"name": "files"}, lambda: ctx.host.add_opencode_mcp_server(config))


CALLS: dict[str, Callable[[RowContext], Awaitable[Any]]] = {
    "check_opencode_ready": call_check,
    "list_opencode_models": call_list_models,
    "list_models_unknown_provider": call_list_models_unknown_provider,
    "list_opencode_providers": call_list_providers,
    "get_opencode_provider_auth": call_provider_auth,
    "spawn_opencode_session": call_spawn,
    "spawn_unknown_model": call_spawn_unknown_model,
    "spawn_at_cap": call_spawn_at_cap,
    "continue_opencode_session": call_continue,
    "continue_unknown_model": call_continue_unknown_model,
    "continue_missing": call_continue_missing,
    "continue_with_live_turn": call_continue_with_live_turn,
    "fork_opencode_session": call_fork,
    "fork_missing": call_fork_missing,
    "fork_missing_message": call_fork_missing_message,
    "revert_opencode_session": call_revert,
    "revert_missing": call_revert_missing,
    "revert_missing_message": call_revert_missing_message,
    "unrevert_opencode_session": call_unrevert,
    "unrevert_missing": call_unrevert_missing,
    "list_opencode_sessions": call_list_sessions,
    "get_opencode_session": call_get_session,
    "get_session_missing": call_get_session_missing,
    "get_opencode_session_messages": call_get_messages,
    "get_messages_missing": call_get_messages_missing,
    "get_opencode_message": call_get_message,
    "get_message_missing_session": call_get_message_missing_session,
    "get_message_missing": call_get_message_missing,
    "get_opencode_session_diff": call_get_diff,
    "get_diff_missing": call_get_diff_missing,
    "get_diff_missing_message": call_get_diff_missing_message,
    "wait_after_spawn": call_wait_after_spawn,
    "wait_too_short": call_wait_too_short,
    "wait_foreign_handle": call_wait_foreign_handle,
    "wait_unissued_handle": call_wait_unissued_handle,
    "interrupt_opencode_turn": call_interrupt_running,
    "interrupt_deleted_session": call_interrupt_deleted_session,
    "interrupt_foreign_handle": call_interrupt_foreign_handle,
    "track_opencode_session_usage": call_track_usage,
    "track_usage_missing": call_track_usage_missing,
    "add_opencode_mcp_server": call_add_mcp,
}


def nothing(fake: Any) -> None:
    del fake


def status_busy(fake: Any) -> None:
    fake.status[KNOWN_SESSION] = {"type": "busy"}


def status_retry(fake: Any) -> None:
    fake.status[KNOWN_SESSION] = {"type": "retry", "attempt": 1, "message": "provider overloaded", "next": 0}


def health_old(fake: Any) -> None:
    fake.health = {"healthy": True, "version": "1.18.30"}


def health_unhealthy(fake: Any) -> None:
    fake.health = {"healthy": False, "version": "1.18.31"}


def health_without_version(fake: Any) -> None:
    fake.override("health", 200, {"healthy": True})


def nothing_connected(fake: Any) -> None:
    fake.connected = []


def provider_without_all(fake: Any) -> None:
    fake.override("provider", 200, {"default": {}, "connected": ["acme"]})


def config_without_providers(fake: Any) -> None:
    fake.override("config_providers", 200, {"default": {}})


def session_list_entry_without_id(fake: Any) -> None:
    fake.override("session_list", 200, [{"title": "no id here", "time": {"created": 1, "updated": 1}}])


def mcp_failed(fake: Any) -> None:
    fake.mcp_answer = {"files": {"status": "failed", "error": "spawn node ENOENT"}}


def mcp_needs_auth(fake: Any) -> None:
    fake.mcp_answer = {"files": {"status": "needs_auth"}}


def mcp_without_name(fake: Any) -> None:
    fake.mcp_answer = {"other-server": {"status": "connected"}}


def prompt_fails_after_create(fake: Any) -> None:
    fake.fail("prompt_async", "400")


def prompt_finds_no_session(fake: Any) -> None:
    fake.fail("prompt_async", "404")


def malformed_status(fake: Any) -> None:
    fake.override("session_status", 200, ["not", "a", "map"])


PREPARES: dict[str, Callable[[Any], None]] = {
    "": nothing,
    "status_busy": status_busy,
    "status_retry": status_retry,
    "health_old": health_old,
    "health_unhealthy": health_unhealthy,
    "health_without_version": health_without_version,
    "nothing_connected": nothing_connected,
    "provider_without_all": provider_without_all,
    "config_without_providers": config_without_providers,
    "session_list_entry_without_id": session_list_entry_without_id,
    "mcp_failed": mcp_failed,
    "mcp_needs_auth": mcp_needs_auth,
    "mcp_without_name": mcp_without_name,
    "prompt_fails_after_create": prompt_fails_after_create,
    "prompt_finds_no_session": prompt_finds_no_session,
    "malformed_status": malformed_status,
}

NO_TURN = ("session_create", "prompt_async")
NO_PROMPT = ("prompt_async",)
PRIMARY_ROUTES: dict[str, str] = {
    "check_opencode_ready": "provider",
    "list_opencode_models": "config_providers",
    "list_opencode_providers": "provider",
    "get_opencode_provider_auth": "provider_auth",
    "spawn_opencode_session": "session_create",
    "continue_opencode_session": "session_get",
    "fork_opencode_session": "fork",
    "revert_opencode_session": "revert",
    "unrevert_opencode_session": "unrevert",
    "list_opencode_sessions": "session_list",
    "get_opencode_session": "session_get",
    "get_opencode_session_messages": "messages",
    "get_opencode_message": "message_get",
    "get_opencode_session_diff": "diff",
    "track_opencode_session_usage": "session_get",
    "add_opencode_mcp_server": "mcp_add",
}


def host_wide_rows() -> list[Row]:
    # EC-55, EC-57, EC-58 and EC-59 for every function, on the route that function itself calls.
    rows: list[Row] = []
    for operation, route in PRIMARY_ROUTES.items():
        rows.append(Row("EC-55", operation, "opencode.server_unreachable", "request_timeout_seconds", fail=(route, "connect"), variant="connect"))
        rows.append(Row("EC-57", operation, "opencode.not_signed_in", "server_password", fail=(route, "401"), variant="401"))
        rows.append(Row("EC-58", operation, "opencode.protocol_mismatch", "check_opencode_ready", fail=(route, "not_json"), variant="not-json"))
        if operation != "spawn_opencode_session":
            rows.append(Row("EC-59", operation, "opencode.api_error", "vendor_error", fail=(route, "500"), variant="500", context={"status_code": "500"}, context_keys=("vendor_error",)))
    for kind, code, token, ec in (("connect", "opencode.server_unreachable", "request_timeout_seconds", "EC-55"), ("401", "opencode.not_signed_in", "server_password", "EC-57"), ("500", "opencode.api_error", "vendor_error", "EC-59")):
        rows.append(Row(ec, "interrupt_opencode_turn", code, token, fail=("abort", kind), variant=kind))
    return rows


SPECIFIC_ROWS: tuple[Row, ...] = (
    # check_opencode_ready
    Row("EC-55", "check_opencode_ready", "opencode.server_unreachable", "request_timeout_seconds", prepare="health_unhealthy", variant="healthy-false"),
    Row("EC-58", "check_opencode_ready", "opencode.protocol_mismatch", "check_opencode_ready", prepare="health_without_version", variant="no-version"),
    Row("EC-60", "check_opencode_ready", "opencode.version_unsupported", "opencode upgrade", prepare="health_old"),
    Row("EC-63", "check_opencode_ready", "opencode.not_signed_in", "opencode auth login", prepare="nothing_connected"),
    # list_opencode_models / list_opencode_providers
    Row("EC-65", "list_opencode_models", "opencode.model_unknown", "list_opencode_providers", call="list_models_unknown_provider", context_keys=("available_providers",)),
    Row("EC-58", "list_opencode_models", "opencode.protocol_mismatch", "check_opencode_ready", prepare="config_without_providers", variant="no-providers"),
    Row("EC-55", "list_opencode_providers", "opencode.server_unreachable", "request_timeout_seconds", fail=("provider", "503"), variant="503"),
    Row("EC-58", "list_opencode_providers", "opencode.protocol_mismatch", "check_opencode_ready", prepare="provider_without_all", variant="no-all"),
    # spawn_opencode_session
    Row("EC-67", "spawn_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", call="spawn_at_cap", max_live_turns=1, context={"live_turns": "1"}),
    Row("EC-68", "spawn_opencode_session", "opencode.model_unknown", "list_opencode_models", call="spawn_unknown_model", context_keys=("available_models",), never_sent=NO_TURN),
    Row("EC-69", "spawn_opencode_session", "opencode.api_error", "vendor_error", fail=("session_create", "400"), never_sent=NO_PROMPT, context={"status_code": "400"}),
    Row("EC-70", "spawn_opencode_session", "opencode.api_error", "vendor_error", prepare="prompt_fails_after_create", variant="prompt-async", context_keys=("session_id",)),
    # continue_opencode_session
    Row("EC-72", "continue_opencode_session", "opencode.session_not_found", "list_opencode_sessions", call="continue_missing", never_sent=NO_PROMPT),
    Row("EC-72", "continue_opencode_session", "opencode.session_not_found", "list_opencode_sessions", prepare="prompt_finds_no_session", variant="prompt-async-404"),
    Row("EC-73", "continue_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", prepare="status_busy", never_sent=NO_PROMPT),
    Row("EC-73", "continue_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", prepare="status_retry", variant="retry", never_sent=NO_PROMPT),
    Row("EC-73", "continue_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", call="continue_with_live_turn", variant="local-turn"),
    Row("EC-68", "continue_opencode_session", "opencode.model_unknown", "list_opencode_models", call="continue_unknown_model", context_keys=("available_models",), never_sent=NO_PROMPT),
    Row("EC-70", "continue_opencode_session", "opencode.api_error", "vendor_error", prepare="prompt_fails_after_create", variant="prompt-async", context={"session_id": KNOWN_SESSION}),
    # fork / revert / unrevert
    Row("EC-72", "fork_opencode_session", "opencode.session_not_found", "list_opencode_sessions", call="fork_missing", never_sent=("fork",)),
    Row("EC-76", "fork_opencode_session", "opencode.session_not_found", "list_opencode_sessions", fail=("fork", "404"), variant="fork-404"),
    Row("EC-73", "fork_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", prepare="status_busy", never_sent=("fork",)),
    Row("EC-75", "fork_opencode_session", "opencode.message_not_found", "get_opencode_session_messages", call="fork_missing_message", never_sent=("fork",)),
    Row("EC-72", "revert_opencode_session", "opencode.session_not_found", "list_opencode_sessions", call="revert_missing", never_sent=("revert",)),
    Row("EC-75", "revert_opencode_session", "opencode.message_not_found", "get_opencode_session_messages", call="revert_missing_message", never_sent=("revert",)),
    Row("EC-78", "revert_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", fail=("revert", "409"), variant="409"),
    Row("EC-78", "revert_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", prepare="status_busy", variant="status", never_sent=("revert",)),
    Row("EC-72", "unrevert_opencode_session", "opencode.session_not_found", "list_opencode_sessions", call="unrevert_missing", never_sent=("unrevert",)),
    Row("EC-78", "unrevert_opencode_session", "opencode.session_busy", "interrupt_opencode_turn", fail=("unrevert", "409"), variant="409"),
    # reads
    Row("EC-58", "list_opencode_sessions", "opencode.protocol_mismatch", "check_opencode_ready", fail=("session_list", "404"), variant="404-without-meaning"),
    Row("EC-58", "list_opencode_sessions", "opencode.protocol_mismatch", "check_opencode_ready", fail=("session_list", "oversize"), variant="oversize"),
    Row("EC-58", "list_opencode_sessions", "opencode.protocol_mismatch", "check_opencode_ready", prepare="session_list_entry_without_id", variant="entry-without-id"),
    Row("EC-72", "get_opencode_session", "opencode.session_not_found", "list_opencode_sessions", call="get_session_missing"),
    Row("EC-72", "get_opencode_session_messages", "opencode.session_not_found", "list_opencode_sessions", call="get_messages_missing"),
    Row("EC-72", "get_opencode_message", "opencode.session_not_found", "list_opencode_sessions", call="get_message_missing_session", never_sent=("message_get",)),
    Row("EC-75", "get_opencode_message", "opencode.message_not_found", "get_opencode_session_messages", call="get_message_missing"),
    Row("EC-72", "get_opencode_session_diff", "opencode.session_not_found", "list_opencode_sessions", call="get_diff_missing", never_sent=("diff",)),
    Row("EC-75", "get_opencode_session_diff", "opencode.message_not_found", "get_opencode_session_messages", call="get_diff_missing_message", never_sent=("diff",)),
    Row("EC-72", "track_opencode_session_usage", "opencode.session_not_found", "list_opencode_sessions", call="track_usage_missing"),
    # wait_opencode_turn (recorded by the watcher, raised by wait)
    Row("EC-80", "wait_opencode_turn", "opencode.turn_not_found", "spawn_opencode_session", call="wait_foreign_handle", variant="foreign"),
    Row("EC-80", "wait_opencode_turn", "opencode.turn_not_found", "spawn_opencode_session", call="wait_unissued_handle", variant="unissued"),
    Row("EC-81", "wait_opencode_turn", "opencode.turn_timed_out", "wait_opencode_turn", call="wait_too_short"),
    Row("EC-82", "wait_opencode_turn", "opencode.not_signed_in", "opencode auth login", call="wait_after_spawn", variant="provider-auth", check_operation=False,
        plan={"mode": "complete", "replies": [{"text": "", "finish": None, "error": {"name": "ProviderAuthError", "data": {"providerID": "acme", "message": "invalid key"}}}]}),
    Row("EC-82", "wait_opencode_turn", "opencode.not_signed_in", "opencode auth login", call="wait_after_spawn", variant="api-403", check_operation=False,
        plan={"mode": "complete", "replies": [{"text": "", "finish": None, "error": {"name": "APIError", "data": {"message": "forbidden", "statusCode": 403, "isRetryable": False}}}]}),
    Row("EC-83", "wait_opencode_turn", "opencode.usage_limited", "reset", call="wait_after_spawn", check_operation=False, context={"retryable": "true"},
        plan={"mode": "complete", "replies": [{"text": "", "finish": None, "error": {"name": "APIError", "data": {"message": "rate limited", "statusCode": 429, "isRetryable": True}}}]}),
    Row("EC-84", "wait_opencode_turn", "opencode.billing_error", "billing", call="wait_after_spawn", check_operation=False,
        plan={"mode": "complete", "replies": [{"text": "", "finish": None, "error": {"name": "APIError", "data": {"message": "payment required", "statusCode": 402, "isRetryable": False}}}]}),
    Row("EC-85", "wait_opencode_turn", "opencode.api_error", "vendor_error", call="wait_after_spawn", variant="unknown-error", check_operation=False, context_keys=("vendor_error",),
        plan={"mode": "complete", "replies": [{"text": "", "finish": None, "error": {"name": "UnknownError", "data": {"message": "model crashed"}}}]}),
    Row("EC-85", "wait_opencode_turn", "opencode.api_error", "vendor_error", call="wait_after_spawn", variant="no-reply", check_operation=False, context={"reason": "no_reply"}, plan={"mode": "no_reply"}),
    Row("EC-85", "wait_opencode_turn", "opencode.api_error", "vendor_error", call="wait_after_spawn", variant="prompt-not-seen", check_operation=False, context={"reason": "prompt_not_seen"},
        request_timeout=0.5, plan={"mode": "prompt_not_seen"}),
    Row("EC-155", "wait_opencode_turn", "opencode.usage_limited", "reset", call="wait_after_spawn", variant="retry-rate-limit", check_operation=False, context={"retry_attempt": "5", "reason": "rate_limit"},
        plan={"mode": "retry", "retry": {"attempt": 5, "message": "Too Many Requests from provider", "reason": "rate_limit"}}),
    Row("EC-155", "wait_opencode_turn", "opencode.api_error", "vendor_error", call="wait_after_spawn", variant="retry-other", check_operation=False, context={"retry_attempt": "6"},
        plan={"mode": "retry", "retry": {"attempt": 6, "message": "upstream connection reset"}}),
    Row("EC-87", "wait_opencode_turn", "opencode.server_unreachable", "request_timeout_seconds", call="wait_after_spawn", fail=("session_status", "connect"), check_operation=False, plan={"mode": "hold"}),
    Row("EC-58", "wait_opencode_turn", "opencode.protocol_mismatch", "check_opencode_ready", call="wait_after_spawn", prepare="malformed_status", check_operation=False, plan={"mode": "hold"}),
    # interrupt_opencode_turn
    Row("EC-80", "interrupt_opencode_turn", "opencode.turn_not_found", "spawn_opencode_session", call="interrupt_foreign_handle", variant="foreign"),
    Row("EC-90", "interrupt_opencode_turn", "opencode.session_not_found", "list_opencode_sessions", call="interrupt_deleted_session", never_sent=("abort",)),
    # add_opencode_mcp_server
    Row("EC-92", "add_opencode_mcp_server", "opencode.mcp_server_failed", "OAuth", prepare="mcp_failed", context={"status": "failed"}),
    Row("EC-92", "add_opencode_mcp_server", "opencode.mcp_server_failed", "OAuth", prepare="mcp_needs_auth", variant="needs-auth", context={"status": "needs_auth"}),
    Row("EC-92", "add_opencode_mcp_server", "opencode.mcp_server_failed", "OAuth", prepare="mcp_without_name", variant="name-missing"),
    Row("EC-93", "add_opencode_mcp_server", "opencode.api_error", "vendor_error", fail=("mcp_add", "400"), context={"status_code": "400"}),
)

ROWS: tuple[Row, ...] = (*host_wide_rows(), *SPECIFIC_ROWS)


def row_id(row: Row) -> str:
    suffix = f"-{row.variant}" if row.variant else ""
    return f"{row.operation}-{row.ec}-{row.code}{suffix}"


CASES = [pytest.param(row, "host", id=f"{row_id(row)}-host") for row in ROWS] + [
    pytest.param(row, "tool", id=f"{row_id(row)}-tool") for row in ROWS if row.tool
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "mode"), CASES)
async def test_opencode_error_row(row: Row, mode: str, request: pytest.FixtureRequest, opencode_api, fake_opencode, make_opencode_host, check_native_error, attached_secret) -> None:
    host = make_opencode_host(max_live_turns=row.max_live_turns, request_timeout_seconds=row.request_timeout)
    call = CALLS[row.call or row.operation]
    async with host:
        if mode == "host":
            with pytest.raises(opencode_api.NativeHostError) as caught:
                await call(RowContext(host, opencode_api, fake_opencode, row))
            error = caught.value
        else:
            tools_api = request.getfixturevalue("opencode_tools_api")
            context = RowContext(host, opencode_api, fake_opencode, row, tools_api.OpencodeTools(host), tools_api)
            result = await call(context)
    if mode == "host":
        check_native_error(error, code=row.code, token=row.token, operation=row.operation if row.check_operation else None)
        for key, value in row.context.items():
            assert error.context.get(key) == value, f"context[{key!r}] should be {value!r}: {dict(error.context)}"
        for key in row.context_keys:
            assert error.context.get(key), f"context should carry {key!r}: {dict(error.context)}"
        # AC-2: the message and context never carry the server password the host injected.
        assert attached_secret not in str(error) and attached_secret not in repr(dict(error.context))
    else:
        request.getfixturevalue("check_tool_error")(result, code=row.code, token=row.token, tool_name=row.operation)
        assert attached_secret not in result.output and attached_secret not in repr(dict(result.metadata))
    routes = fake_opencode.routes()
    for route in row.never_sent:
        assert route not in routes, f"{route} must not be called for {row.ec}; the fake saw {routes}"
    assert "unknown" not in routes, "spec §8.5: the host calls only the listed routes"


@pytest.mark.asyncio
async def test_api_error_context_names_the_vendor_error_and_status(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-59: `vendor_error` is the response name plus the scrubbed data.message; `status_code` is the status.
    async with make_opencode_host() as host:
        fake_opencode.fail("session_list", "500")
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_sessions()
    assert caught.value.context["status_code"] == "500"
    assert "UnknownError" in caught.value.context["vendor_error"]
    assert "backend exploded" in caught.value.context["vendor_error"]


@pytest.mark.asyncio
async def test_model_unknown_context_lists_at_most_twenty_ids(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-68: the context lists the available ids, at most NATIVE_CONTEXT_LIST_MAX_ITEMS of them.
    fake_opencode.providers[0]["models"].update({f"bulk-{index:02d}": fake_opencode.providers[0]["models"]["coder-1"] for index in range(30)})
    async with make_opencode_host() as host:
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.spawn_opencode_session(spawn_request(opencode_api, model=UNKNOWN_MODEL))
    listed = caught.value.context["available_models"]
    offered = ["coder-1", "coder-mini", *(f"bulk-{index:02d}" for index in range(30))]
    assert "coder-ultra" not in listed
    assert 1 <= sum(1 for model_id in offered if model_id in listed) <= 20


AENTER_ROWS = (
    pytest.param("EC-55", ("health", "connect"), "", "opencode.server_unreachable", "request_timeout_seconds", id="EC-55-connect"),
    pytest.param("EC-55", ("health", "503"), "", "opencode.server_unreachable", "request_timeout_seconds", id="EC-55-503"),
    pytest.param("EC-57", ("health", "401"), "", "opencode.not_signed_in", "server_password", id="EC-57-401"),
    pytest.param("EC-58", ("health", "not_json"), "", "opencode.protocol_mismatch", "check_opencode_ready", id="EC-58-not-json"),
    pytest.param("EC-59", ("health", "500"), "", "opencode.api_error", "vendor_error", id="EC-59-500"),
    pytest.param("EC-60", None, "health_old", "opencode.version_unsupported", "opencode upgrade", id="EC-60-old-version"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("ec", "fail", "prepare", "code", "token"), AENTER_ROWS)
async def test_aenter_error_row(ec: str, fail: tuple[str, str] | None, prepare: str, code: str, token: str, opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # Host-wide rows at __aenter__ against an attached server: the version check runs on entry (EC-60).
    if fail is not None:
        fake_opencode.fail(*fail)
    PREPARES[prepare](fake_opencode)
    host = make_opencode_host()
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with host:
            pass
    check_native_error(caught.value, code=code, token=token)
    with pytest.raises(opencode_api.NativeHostError) as later:
        await host.list_opencode_sessions()
    check_native_error(later.value, code="opencode.process_exited", token="async with", operation="list_opencode_sessions")


EC2_CALLS: dict[str, Callable[[Any, SimpleNamespace], Awaitable[Any]]] = {
    "check_opencode_ready": lambda host, api: host.check_opencode_ready(),
    "list_opencode_models": lambda host, api: host.list_opencode_models(),
    "list_opencode_providers": lambda host, api: host.list_opencode_providers(),
    "get_opencode_provider_auth": lambda host, api: host.get_opencode_provider_auth(),
    "spawn_opencode_session": lambda host, api: host.spawn_opencode_session(spawn_request(api)),
    "continue_opencode_session": lambda host, api: host.continue_opencode_session(KNOWN_SESSION, prompt_request(api)),
    "fork_opencode_session": lambda host, api: host.fork_opencode_session(KNOWN_SESSION),
    "revert_opencode_session": lambda host, api: host.revert_opencode_session(KNOWN_SESSION, KNOWN_REPLY_MESSAGE),
    "unrevert_opencode_session": lambda host, api: host.unrevert_opencode_session(KNOWN_SESSION),
    "list_opencode_sessions": lambda host, api: host.list_opencode_sessions(),
    "get_opencode_session": lambda host, api: host.get_opencode_session(KNOWN_SESSION),
    "get_opencode_session_messages": lambda host, api: host.get_opencode_session_messages(KNOWN_SESSION),
    "get_opencode_message": lambda host, api: host.get_opencode_message(KNOWN_SESSION, KNOWN_REPLY_MESSAGE),
    "get_opencode_session_diff": lambda host, api: host.get_opencode_session_diff(KNOWN_SESSION),
    "wait_opencode_turn": lambda host, api: host.wait_opencode_turn(unissued_handle(api)),
    "interrupt_opencode_turn": lambda host, api: host.interrupt_opencode_turn(unissued_handle(api)),
    "track_opencode_session_usage": lambda host, api: host.track_opencode_session_usage(KNOWN_SESSION),
    "add_opencode_mcp_server": lambda host, api: host.add_opencode_mcp_server(api.OpencodeMcpServerConfig(name="files", kind=api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"))),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(EC2_CALLS))
async def test_unopened_or_closed_host_raises_process_exited(operation: str, opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # EC-2: never entered, then entered and exited; both raise before any request.
    assert len(EC2_CALLS) == 18, "FR-2: OpencodeHost has 18 functions"
    host = make_opencode_host()
    with pytest.raises(opencode_api.NativeHostError) as before:
        await EC2_CALLS[operation](host, opencode_api)
    check_native_error(before.value, code="opencode.process_exited", token="async with", operation=operation)
    assert fake_opencode.requests == [], "EC-2 sends nothing"
    async with host:
        pass
    sent = len(fake_opencode.requests)
    with pytest.raises(opencode_api.NativeHostError) as after:
        await EC2_CALLS[operation](host, opencode_api)
    check_native_error(after.value, code="opencode.process_exited", token="async with", operation=operation)
    assert len(fake_opencode.requests) == sent, "EC-2 sends nothing after exit"


@pytest.mark.asyncio
async def test_reentering_a_host_raises_invalid_argument(opencode_api, make_opencode_host, check_native_error) -> None:
    # EC-3: a host is used once, whether it is open or already closed.
    host = make_opencode_host()
    async with host:
        with pytest.raises(opencode_api.NativeHostError) as while_open:
            await host.__aenter__()
    check_native_error(while_open.value, code="configuration.invalid_argument", token="new host")
    with pytest.raises(opencode_api.NativeHostError) as after_close:
        async with host:
            pass
    check_native_error(after_close.value, code="configuration.invalid_argument", token="new host")


BAD_SESSION_IDS = ("ses", "msg_00000001", "", "ses bad", "ses/../etc", "--always-approve", 42, None)
SESSION_ID_OPERATIONS = (
    "continue_opencode_session", "fork_opencode_session", "revert_opencode_session", "unrevert_opencode_session", "get_opencode_session",
    "get_opencode_session_messages", "get_opencode_message", "get_opencode_session_diff", "track_opencode_session_usage",
)
BAD_TIMEOUTS = (("bool", True), ("nan", math.nan), ("inf", math.inf), ("minus-inf", -math.inf), ("zero", 0), ("negative", -1), ("over-cap", 3600.5), ("str", "10"))

EC1_CASES: list[Any] = [
    *[pytest.param(operation, {"session_id": value}, "session_id", id=f"{operation}-session_id-{index}") for operation in SESSION_ID_OPERATIONS for index, value in enumerate(BAD_SESSION_IDS)],
    *[pytest.param(operation, {"message_id": value}, "message_id", id=f"{operation}-message_id-{index}")
      for operation in ("fork_opencode_session", "revert_opencode_session", "get_opencode_message", "get_opencode_session_diff") for index, value in enumerate(("msg", "ses_known0001", "msg bad", 7))],
    *[pytest.param("revert_opencode_session", {"part_id": value}, "part_id", id=f"revert-part_id-{index}") for index, value in enumerate(("prt", "msg_00000001", "prt bad", 7))],
    *[pytest.param("get_opencode_session_messages", {"before": value}, "before", id=f"messages-before-{index}") for index, value in enumerate(("x", "", "msg bad", 7))],
    *[pytest.param("get_opencode_session_messages", {"limit": value}, "limit", id=f"messages-limit-{index}") for index, value in enumerate((0, 201, True, "5", -1))],
    *[pytest.param("list_opencode_sessions", {"limit": value}, "limit", id=f"list-limit-{index}") for index, value in enumerate((0, 201, True, "5", 2.5))],
    *[pytest.param("list_opencode_models", {"provider_id": value}, "provider_id", id=f"models-provider_id-{index}") for index, value in enumerate(("", "a" * 65, "acme/coder", "   ", 9))],
    pytest.param("spawn_opencode_session", {"request": "List the folders."}, "request", id="spawn-request-type"),
    pytest.param("spawn_opencode_session", {"request": "prompt-request"}, "request", id="spawn-request-is-prompt-request"),
    pytest.param("continue_opencode_session", {"request": "List the folders."}, "request", id="continue-request-type"),
    pytest.param("add_opencode_mcp_server", {"config": "files"}, "config", id="mcp-config-type"),
    pytest.param("wait_opencode_turn", {"handle": "not-a-handle"}, "handle", id="wait-handle-str"),
    pytest.param("wait_opencode_turn", {"handle": None}, "handle", id="wait-handle-none"),
    pytest.param("wait_opencode_turn", {"handle": {"harness": "opencode"}}, "handle", id="wait-handle-mapping"),
    *[pytest.param("wait_opencode_turn", {"timeout_seconds": value}, "timeout_seconds", id=f"wait-timeout-{label}") for label, value in BAD_TIMEOUTS],
    pytest.param("interrupt_opencode_turn", {"handle": "not-a-handle"}, "handle", id="interrupt-handle-str"),
    pytest.param("interrupt_opencode_turn", {"handle": {"harness": "opencode"}}, "handle", id="interrupt-handle-mapping"),
]


async def call_with(host: Any, api: SimpleNamespace, operation: str, overrides: Mapping[str, Any]) -> Any:
    # Builds a call whose only bad value is the overridden argument (EC-1).
    session_id = overrides.get("session_id", KNOWN_SESSION)
    message_id = overrides.get("message_id", KNOWN_REPLY_MESSAGE)
    if operation == "spawn_opencode_session":
        request = prompt_request(api) if overrides["request"] == "prompt-request" else overrides["request"]
        return await host.spawn_opencode_session(request)
    if operation == "continue_opencode_session":
        return await host.continue_opencode_session(session_id, overrides.get("request", prompt_request(api)))
    if operation == "fork_opencode_session":
        return await host.fork_opencode_session(session_id, overrides.get("message_id"))
    if operation == "revert_opencode_session":
        return await host.revert_opencode_session(session_id, message_id, overrides.get("part_id"))
    if operation == "unrevert_opencode_session":
        return await host.unrevert_opencode_session(session_id)
    if operation == "get_opencode_session":
        return await host.get_opencode_session(session_id)
    if operation == "get_opencode_session_messages":
        return await host.get_opencode_session_messages(session_id, limit=overrides.get("limit", 50), before=overrides.get("before"))
    if operation == "get_opencode_message":
        return await host.get_opencode_message(session_id, message_id)
    if operation == "get_opencode_session_diff":
        return await host.get_opencode_session_diff(session_id, overrides.get("message_id"))
    if operation == "track_opencode_session_usage":
        return await host.track_opencode_session_usage(session_id)
    if operation == "list_opencode_sessions":
        return await host.list_opencode_sessions(limit=overrides["limit"])
    if operation == "list_opencode_models":
        return await host.list_opencode_models(overrides["provider_id"])
    if operation == "add_opencode_mcp_server":
        return await host.add_opencode_mcp_server(overrides["config"])
    handle = overrides.get("handle", unissued_handle(api))
    if operation == "wait_opencode_turn":
        return await host.wait_opencode_turn(handle, timeout_seconds=overrides.get("timeout_seconds", 1.0))
    return await host.interrupt_opencode_turn(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "overrides", "argument"), EC1_CASES)
async def test_invalid_primitive_arguments_make_no_request(operation: str, overrides: Mapping[str, Any], argument: str, opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # EC-1, EC-64, EC-71, EC-74, EC-77: checked before any I/O; opencode answers 500 for malformed ids, so they must never be sent.
    async with make_opencode_host() as host:
        sent = len(fake_opencode.requests)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await call_with(host, opencode_api, operation, overrides)
        after = len(fake_opencode.requests)
    check_native_error(caught.value, code="configuration.invalid_argument", token=argument, operation=operation)
    assert argument in str(caught.value), "EC-1: the message names the argument"
    assert after == sent, f"EC-1 fails before any request; the fake saw {fake_opencode.routes()[sent:]}"
