"""FILE: tests/features/grok_host/test_grok_host_turns.py

PURPOSE: The live-turn behaviour of GrokHost: approvals answered by policy and recorded (AC-8, D-11, INV-10), terminal states and interrupt sources (EC-50, EC-53, D-10, INV-13), the wire shapes the host sends (§8.5 ACP calls, INV-9), bounded text and decisions (EC-150, INV-16), unknown usage (INV-15), host-scoped handles (INV-17) and the session and live-turn reservations under concurrency (EC-9, INV-14).
ROLE IN CODEBASE: Covers vidbyte.harnesses.native.grok.turn (GrokTurnDriver) and the turn parts of grok.host through the public methods only.
ARCHITECTURE NOTE: The fake plays each turn from its scenario: permission requests, extra server requests, notifications, chunks, then an answer or a hold that the test ends with the release file or that the host ends with session/cancel. Assertions read the fake's JSONL log and the NativeTurnResult.
FUNCTION INVENTORY: spawn_and_wait runs one turn to its result; permission_answers reads the answers the fake logged; the test_* functions each pin one rule.
COMMON MODIFICATION PATTERNS: A new turn rule gets a scenario key in fake_grok_peer.py and one test here.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert interleavings the spec leaves open, such as which of two concurrent calls wins. 2. Do not sleep to wait for a turn; wait_grok_turn or the release file drives every turn.
KNOWN EDGE CASES: The POSIX-only tests (EC-27, EC-51) close the fake's stdin so the host's next write fails at once; Windows reports a write to a closed pipe asynchronously, so there the failure can surface later as EC-48.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.1, §6.3.3, §8.5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_turns.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
PROMPT = "List the top-level folders."
WAIT_SECONDS = 30.0
ALWAYS_OPTIONS = ("opt-allow-always", "opt-reject-always")
FORBIDDEN_ARGS = ("--always-approve", "--dangerously-skip-permissions", "--yolo", "bypassPermissions", "auto", "allowAll")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows reports a write to a closed pipe asynchronously, so the failure can surface at wait (EC-48) instead")


async def spawn_and_wait(host: Any, api: Any, **request_fields: Any) -> Any:
    handle = await host.spawn_grok_session(api.GrokTurnRequest(prompt=PROMPT, **request_fields))
    return await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)


def permission_answers(grok_fake: Any) -> list[Any]:
    return [record["answer"] for record in grok_fake.records("permission_answer")]


def assert_no_approve_everything(grok_fake: Any) -> None:
    # INV-9: no approve-everything flag in any argv, and session/new never carries _meta.
    for argv in grok_fake.launches():
        for arg in argv:
            assert not any(arg == flag or arg.endswith("=" + flag) for flag in FORBIDDEN_ARGS), argv
    for frame in grok_fake.received("session/new"):
        assert "_meta" not in frame.get("params", {}), frame


@pytest.mark.asyncio
async def test_edit_permission_is_rejected_then_allowed_by_policy(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # AC-8: allowed_tool_kinds empty selects reject_once; {EDIT} selects allow_once; never an *_always option.
    async with make_grok_host({"acp": {"session_prompt": {"permissions": [{"kind": "edit"}]}}}) as host:
        rejected = await spawn_and_wait(host, grok_api)
        allowed = await spawn_and_wait(host, grok_api, allowed_tool_kinds=frozenset({grok_api.AcpToolKind.EDIT}))
    answers = permission_answers(grok_fake)
    assert [answer["result"]["outcome"] for answer in answers] == [
        {"outcome": "selected", "optionId": "opt-reject-once"},
        {"outcome": "selected", "optionId": "opt-allow-once"},
    ]
    assert not any(answer["result"]["outcome"].get("optionId") in ALWAYS_OPTIONS for answer in answers)
    assert [(decision.request_kind, decision.outcome) for decision in rejected.decisions] == [("acp.permission:edit", grok_api.ApprovalOutcome.REJECTED)]
    assert [(decision.request_kind, decision.outcome) for decision in allowed.decisions] == [("acp.permission:edit", grok_api.ApprovalOutcome.ALLOWED)]
    assert rejected.decisions[0].title == "Edit README.md"
    assert rejected.status is grok_api.NativeTurnStatus.COMPLETED and allowed.status is grok_api.NativeTurnStatus.COMPLETED
    assert_no_approve_everything(grok_fake)


@pytest.mark.asyncio
async def test_permission_without_a_reject_option_is_answered_cancelled(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # D-11: with no reject option the host answers the "cancelled" outcome, never an allow it was not given.
    options = [{"optionId": "opt-allow-once", "name": "Allow once", "kind": "allow_once"}, {"optionId": "opt-allow-always", "name": "Always", "kind": "allow_always"}]
    async with make_grok_host({"acp": {"session_prompt": {"permissions": [{"kind": "execute", "options": options}]}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    assert permission_answers(grok_fake)[0]["result"]["outcome"] == {"outcome": "cancelled"}
    assert [(decision.request_kind, decision.outcome) for decision in result.decisions] == [("acp.permission:execute", grok_api.ApprovalOutcome.CANCELLED)]


@pytest.mark.asyncio
async def test_missing_or_unknown_tool_kind_counts_as_other(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # §9.1 AcpToolKind: a missing or unknown kind is treated as OTHER, so allowing OTHER allows it.
    permissions = [{"kind": "teleport"}, {"kind": None}]
    async with make_grok_host({"acp": {"session_prompt": {"permissions": permissions}}}) as host:
        result = await spawn_and_wait(host, grok_api, allowed_tool_kinds=frozenset({grok_api.AcpToolKind.OTHER}))
    assert [answer["result"]["outcome"]["optionId"] for answer in permission_answers(grok_fake)] == ["opt-allow-once", "opt-allow-once"]
    assert [decision.request_kind for decision in result.decisions] == ["acp.permission:other", "acp.permission:other"]


@pytest.mark.asyncio
async def test_unknown_server_request_gets_method_not_found_and_is_recorded(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # INV-10: any other server request gets JSON-RPC -32601, and every answer is recorded.
    async with make_grok_host({"acp": {"session_prompt": {"server_requests": [{"method": "fs/read_text_file", "params": {"path": "README.md"}}]}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    answer = grok_fake.records("server_request_answer")[0]["answer"]
    assert answer is not None, "INV-10: the host answered inside the turn"
    assert answer["error"]["code"] == -32601
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert [(decision.request_kind, decision.outcome) for decision in result.decisions] == [("fs/read_text_file", grok_api.ApprovalOutcome.NOT_SUPPORTED)]


@pytest.mark.asyncio
async def test_recorded_decisions_are_capped_and_the_overflow_counted(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # INV-16: at most NATIVE_MAX_RECORDED_DECISIONS decisions, with the rest counted in decisions_dropped.
    cap = grok_api.constants.NATIVE_MAX_RECORDED_DECISIONS
    permissions = [{"kind": "edit"}] * (cap + 5)
    async with make_grok_host({"acp": {"session_prompt": {"permissions": permissions}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    assert len(permission_answers(grok_fake)) == cap + 5, "every request is still answered"
    assert len(result.decisions) == cap
    assert result.decisions_dropped == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["end_turn", "max_tokens", "max_turn_requests", "refusal"])
async def test_completed_stop_reasons_are_kept_verbatim(stop_reason: str, grok_api, make_grok_host, fast_stop) -> None:
    # EC-50, first group: COMPLETED with the vendor stop_reason.
    async with make_grok_host({"acp": {"session_prompt": {"stop_reason": stop_reason}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert result.stop_reason == stop_reason
    assert result.interrupt_source is None


@pytest.mark.asyncio
@pytest.mark.parametrize("on_cancel", ["cancelled", "error_32800"])
async def test_interrupt_sends_cancel_and_the_turn_ends_interrupted_by_the_caller(on_cancel: str, grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-53 and EC-50, second group: stopReason "cancelled" or a -32800 answer both end INTERRUPTED with source CALLER.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold", "on_cancel": on_cancel}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        interrupted = await host.interrupt_grok_turn(handle)
        result = await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert interrupted.was_running is True
    cancels = grok_fake.received("session/cancel")
    assert len(cancels) == 1 and "id" not in cancels[0], "session/cancel is a notification"
    assert cancels[0]["params"]["sessionId"] == handle.session_id
    assert result.status is grok_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is grok_api.InterruptSource.CALLER


@pytest.mark.asyncio
async def test_interrupt_returns_at_once_and_closes_a_peer_that_ignores_cancel(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-53: was_running=True at once; NATIVE_STOP_GRACE_SECONDS later the driver closes the peer and the turn ends INTERRUPTED.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold", "on_cancel": "ignore"}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        started = time.monotonic()
        interrupted = await host.interrupt_grok_turn(handle)
        assert time.monotonic() - started < fast_stop.grace, "interrupt does not wait for the turn to end"
        result = await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
        elapsed = time.monotonic() - started
    assert interrupted.was_running is True
    assert result.status is grok_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is grok_api.InterruptSource.CALLER
    assert elapsed < fast_stop.grace * 2 + fast_stop.kill_wait * 2 + fast_stop.slack


@pytest.mark.asyncio
@pytest.mark.parametrize("on_cancel", ["cancelled", "ignore"])
async def test_turn_ceiling_interrupts_with_deadline_source(on_cancel: str, grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # D-10: at max_turn_seconds the host interrupts, waits out the grace and closes the peer; source DEADLINE.
    ceiling = 1.0
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold", "on_cancel": on_cancel}}}) as host:
        started = time.monotonic()
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT, max_turn_seconds=ceiling))
        result = await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
        elapsed = time.monotonic() - started
    assert result.status is grok_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is grok_api.InterruptSource.DEADLINE
    assert grok_fake.received("session/cancel"), "the ceiling sends the protocol interrupt first (D-23)"
    assert ceiling <= elapsed < ceiling + fast_stop.grace + fast_stop.kill_wait * 2 + fast_stop.slack


@pytest.mark.asyncio
async def test_unknown_notifications_and_update_kinds_are_ignored(grok_api, make_grok_host, fast_stop) -> None:
    # EC-7: vendor vocabularies are open; unknown notifications and session/update variants change nothing.
    notifications = [
        {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "$session", "update": {"sessionUpdate": "plan", "entries": []}}},
        {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "$session", "update": {"sessionUpdate": "brand_new_kind", "payload": 1}}},
        {"jsonrpc": "2.0", "method": "x/vendor_event", "params": {"anything": True}},
    ]
    async with make_grok_host({"acp": {"session_prompt": {"notifications": notifications}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert result.text == "alpha-beta"


@pytest.mark.asyncio
async def test_text_over_the_cap_is_cut_and_flagged(grok_api, make_grok_host, fast_stop) -> None:
    # EC-150 / INV-16: the first NATIVE_RESULT_TEXT_MAX_CHARS characters are kept and text_truncated is set.
    cap = grok_api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    chunk = "y" * (cap // 2 + 1)
    async with make_grok_host({"acp": {"session_prompt": {"chunks": [chunk, chunk, "tail"]}}}) as host:
        result = await spawn_and_wait(host, grok_api)
    assert result.status is grok_api.NativeTurnStatus.COMPLETED
    assert len(result.text) == cap
    assert result.text_truncated is True


@pytest.mark.asyncio
async def test_usage_is_none_when_grok_reports_none(grok_api, make_grok_host, fast_stop) -> None:
    # INV-15: unknown usage is None, never zero.
    async with make_grok_host() as host:
        result = await spawn_and_wait(host, grok_api)
    assert result.usage is None
    assert result.text_truncated is False
    assert result.decisions == () and result.decisions_dropped == 0


@pytest.mark.asyncio
async def test_a_failed_turn_raises_the_same_code_on_every_wait(grok_api, make_grok_host, fast_stop) -> None:
    # EC-148 and the note under EC-50: a FAILED turn raises the same error on every wait.
    async with make_grok_host({"acp": {"session_prompt": {"error": {"code": -32000, "message": "Authentication required"}}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        codes = []
        for _ in range(2):
            with pytest.raises(grok_api.NativeHostError) as caught:
                await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
            codes.append(caught.value.failure_code)
    assert codes == [grok_api.FailureCode.GROK_NOT_SIGNED_IN, grok_api.FailureCode.GROK_NOT_SIGNED_IN]


@pytest.mark.asyncio
async def test_a_handle_is_scoped_to_the_host_that_issued_it(grok_api, make_grok_host, fast_stop, check_native_error) -> None:
    # INV-17: a handle this host never issued raises turn_not_found, even when another host issued it.
    async with make_grok_host() as first, make_grok_host() as second:
        handle = await first.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        with pytest.raises(grok_api.NativeHostError) as caught:
            await second.wait_grok_turn(handle, timeout_seconds=1.0)
        await first.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
    check_native_error(caught.value, code="grok.turn_not_found", token="spawn_grok_session", operation="wait_grok_turn")


@pytest.mark.asyncio
async def test_concurrent_continues_on_one_session_let_only_one_through(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-9 / INV-14: the session is reserved before the first await, so two continues cannot both pass.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        outcomes = await asyncio.gather(
            host.continue_grok_session(KNOWN_SESSION, grok_api.GrokTurnRequest(prompt=PROMPT)),
            host.continue_grok_session(KNOWN_SESSION, grok_api.GrokTurnRequest(prompt=PROMPT)),
            return_exceptions=True,
        )
    handles = [outcome for outcome in outcomes if isinstance(outcome, grok_api.NativeTurnHandle)]
    errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(handles) == 1 and len(errors) == 1, outcomes
    check_native_error(errors[0], code="grok.session_busy", token="interrupt_grok_turn", operation="continue_grok_session")
    assert len(grok_fake.launches("peer")) == 1, "the losing call starts no process"


@pytest.mark.asyncio
async def test_concurrent_spawns_respect_the_live_turn_cap(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-9 with EC-24: the live-turn slot is reserved synchronously, so a cap of one admits one spawn.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}, max_live_turns=1) as host:
        outcomes = await asyncio.gather(
            host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT)),
            host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT)),
            return_exceptions=True,
        )
    errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(errors) == 1, outcomes
    check_native_error(errors[0], code="grok.session_busy", token="interrupt_grok_turn", operation="spawn_grok_session")
    assert errors[0].context["live_turns"] == "1"
    assert len(grok_fake.launches("peer")) == 1


@pytest.mark.asyncio
async def test_a_failed_spawn_releases_its_reservation(grok_api, make_grok_host, fast_stop) -> None:
    # EC-9: reservations are released when the call fails, so the slot is free for the next spawn.
    async with make_grok_host({"acp": {"session_new": {"error": {"code": -32099, "message": "backend exploded"}}}}, max_live_turns=1) as host:
        for _ in range(2):
            with pytest.raises(grok_api.NativeHostError) as caught:
                await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
            assert caught.value.failure_code is grok_api.FailureCode.GROK_API_ERROR, "the second spawn is not refused as busy"


@pytest.mark.asyncio
async def test_turn_peer_wire_shapes(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # §8.5 ACP calls: initialize, a _meta-free session/new with the workspace and no MCP servers, one text block.
    async with make_grok_host() as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
    workspaces = {str(grok_fake.workspace), str(grok_fake.workspace.resolve())}
    assert grok_fake.launches("peer") == [["agent", "--no-leader", "stdio"]]
    initialize = grok_fake.received("initialize")[0]["params"]
    assert initialize["protocolVersion"] == 1
    assert initialize["clientCapabilities"] == {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}
    assert initialize["clientInfo"]
    session_new = grok_fake.received("session/new")[0]["params"]
    assert set(session_new) == {"cwd", "mcpServers"} and session_new["mcpServers"] == []
    assert session_new["cwd"] in workspaces
    prompt = grok_fake.received("session/prompt")[0]["params"]
    assert prompt["sessionId"] == handle.session_id
    assert prompt["prompt"] == [{"type": "text", "text": PROMPT}]
    assert_no_approve_everything(grok_fake)


@pytest.mark.asyncio
async def test_peer_argv_carries_model_and_effort_in_name_value_form(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # D-2, D-12, T-2: every peer argv is agent --no-leader [--model=<id>] [--reasoning-effort=<effort>] stdio.
    async with make_grok_host() as host:
        await spawn_and_wait(host, grok_api, model="grok-4-heavy", reasoning_effort="high")
    assert grok_fake.launches("peer") == [["agent", "--no-leader", "--model=grok-4-heavy", "--reasoning-effort=high", "stdio"]]


@pytest.mark.asyncio
async def test_continue_resumes_the_session_in_the_workspace(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # §8.5: session/resume carries sessionId, cwd and no MCP servers; the prompt targets the resumed session.
    async with make_grok_host() as host:
        handle = await host.continue_grok_session(KNOWN_SESSION, grok_api.GrokTurnRequest(prompt=PROMPT))
        result = await host.wait_grok_turn(handle, timeout_seconds=WAIT_SECONDS)
    resume = grok_fake.received("session/resume")[0]["params"]
    assert resume["sessionId"] == KNOWN_SESSION and resume["mcpServers"] == []
    assert resume["cwd"] in {str(grok_fake.workspace), str(grok_fake.workspace.resolve())}
    assert grok_fake.received("session/new") == []
    assert grok_fake.received("session/prompt")[0]["params"]["sessionId"] == KNOWN_SESSION
    assert handle.session_id == KNOWN_SESSION
    assert result.status is grok_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
@posix_only
async def test_spawn_raises_process_exited_when_the_prompt_write_fails(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-27: session/new succeeds, then the peer stops reading, so writing session/prompt fails.
    async with make_grok_host({"acp": {"session_new": {"mode": "close_stdin_then_answer"}}}) as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
    check_native_error(caught.value, code="grok.process_exited", token="check_grok_ready", operation="spawn_grok_session")


@pytest.mark.asyncio
@posix_only
async def test_interrupt_raises_process_exited_when_the_cancel_write_fails(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-51: the turn is RUNNING but the peer no longer reads stdin, so session/cancel cannot be written.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "close_stdin_hold"}}}) as host:
        handle = await host.spawn_grok_session(grok_api.GrokTurnRequest(prompt=PROMPT))
        assert await _stdin_closed(grok_fake), "the fake closed its stdin"
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.interrupt_grok_turn(handle)
    check_native_error(caught.value, code="grok.process_exited", token="check_grok_ready", operation="interrupt_grok_turn")


async def _stdin_closed(grok_fake: Any) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    while loop.time() < deadline:
        if grok_fake.records("stdin_closed"):
            return True
        await asyncio.sleep(0.05)
    return False
