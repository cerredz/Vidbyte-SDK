"""FILE: tests/features/opencode_host/test_opencode_host_watcher.py

PURPOSE: The OpencodeTurnWatcher contract seen through wait_opencode_turn: which reply is the turn's (the snapshot and the parentID reply set), when a turn is complete (idle confirmations and time.completed), how text, stop_reason and usage are built (D-14), how vendor errors become outcomes (EC-82 to EC-89, EC-155), and how pending permissions and questions in the turn's session tree are rejected and recorded (EC-154, INV-10).
ROLE IN CODEBASE: Start here when a turn returns the wrong text, finishes too early, hangs on an approval, or reports the wrong code. Covers vidbyte.harnesses.native.opencode.turn and wire through OpencodeHost.
ARCHITECTURE NOTE: FakeOpencodeServer advances a turn by one step per `GET /session/status` poll and OPENCODE_POLL_INTERVAL_SECONDS is shrunk by fast_timings, so every outcome here depends on poll counts, not wall-clock time. Each failing outcome's code and token are asserted in test_opencode_host_errors.py; this file asserts the behaviour around them.
FUNCTION INVENTORY: run_turn spawns or continues one turn under a plan and waits for it; reply builds a scripted assistant step; the test_* functions are one watcher rule each.
COMMON MODIFICATION PATTERNS: A new watcher rule is a new plan mode in conftest.FakeOpencodeServer.advance plus one test here.
WHAT NOT TO DO IN THIS FILE: 1. Do not use costs that binary floats cannot hold exactly; the sums are compared as Decimal. 2. Do not wait on fixed sleeps; use wait_until on what the fake has seen.
KNOWN EDGE CASES: A reply that exists without time.completed while the session reads idle must not complete the turn (§8.5 step 5). A permission from a session outside the turn's tree is left pending, because on an attached server it may belong to the user.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.4 (wait_opencode_turn), §8.5 OpencodeTurnWatcher, D-9, D-11, D-14
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_watcher.py
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any

import pytest

KNOWN_SESSION = "ses_known0001"
OTHER_SESSION = "ses_other0002"
PROMPT = "List the top-level folders."
SHORT_WAIT_SECONDS = 0.5
TURN_WAIT_SECONDS = 30.0
GATE_SECONDS = 10.0
SLACK_SECONDS = 2.0


def reply(text: str, *, finish: str | None = "stop", error: dict[str, Any] | None = None, tokens: dict[str, Any] | None = None, cost: float = 0.25) -> dict[str, Any]:
    spec: dict[str, Any] = {"text": text, "finish": finish, "cost": cost, "tokens": tokens or {"input": 10, "output": 20, "reasoning": 3, "cache": {"read": 4, "write": 1}}}
    if error is not None:
        spec["error"] = error
    return spec


def permission(request_id: str, session_id: str, name: str = "edit") -> dict[str, Any]:
    return {"id": request_id, "sessionID": session_id, "permission": name, "patterns": ["README.md"], "metadata": {}, "always": []}


async def run_turn(host: Any, api: Any, *, continue_session: str | None = None, timeout_seconds: float = TURN_WAIT_SECONDS) -> Any:
    if continue_session is None:
        handle = await host.spawn_opencode_session(api.OpencodeSpawnRequest(turn=api.OpencodePromptRequest(prompt=PROMPT)))
    else:
        handle = await host.continue_opencode_session(continue_session, api.OpencodePromptRequest(prompt=PROMPT))
    return await host.wait_opencode_turn(handle, timeout_seconds=timeout_seconds)


@pytest.mark.asyncio
async def test_text_comes_from_the_newest_reply_and_usage_is_summed_over_every_step(opencode_api, fake_opencode, make_opencode_host) -> None:
    # §8.5 steps 3-4 / D-14: one assistant message per model step; text and finish from the newest, usage summed field by field.
    first = reply("calling a tool", finish="tool-calls", cost=0.25, tokens={"input": 100, "output": 7, "reasoning": 2, "cache": {"read": 30, "write": 5}})
    second = reply("final answer", finish="stop", cost=0.5, tokens={"input": 140, "output": 9, "reasoning": 0, "cache": {"read": 60, "write": 0}})
    fake_opencode.plan("steps", steps=[first, second], per_poll=1)
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.text == "final answer"
    assert result.stop_reason == "stop"
    usage = result.usage
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (240, 16, 2)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (90, 5)
    assert usage.cost_usd == Decimal("0.75")
    assert usage.total_tokens is None, "INV-15: the vendor reported no total, so it stays None"


@pytest.mark.asyncio
async def test_reported_total_tokens_are_kept(opencode_api, fake_opencode, make_opencode_host) -> None:
    # INV-15: a field is set when the vendor reported it.
    fake_opencode.plan("complete", replies=[reply("done", tokens={"total": 170, "input": 100, "output": 70, "reasoning": 0, "cache": {"read": 0, "write": 0}})])
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.usage.total_tokens == 170


@pytest.mark.asyncio
async def test_replies_that_left_the_message_window_still_count(opencode_api, fake_opencode, make_opencode_host) -> None:
    # §8.5 step 3: replies are accumulated by message id across polls, beyond the newest OPENCODE_WATCH_MESSAGE_LIMIT (50).
    steps = [reply(f"step {index}", finish="tool-calls" if index < 59 else "stop", tokens={"input": 1, "output": 2, "reasoning": 0, "cache": {"read": 0, "write": 0}}) for index in range(60)]
    fake_opencode.plan("steps", steps=steps, per_poll=10)
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.text == "step 59"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (60, 120)
    assert result.usage.cost_usd == Decimal("15")
    assert all(int(item.query.get("limit", "0")) <= 50 for item in fake_opencode.seen("messages")), "the watcher reads at most OPENCODE_WATCH_MESSAGE_LIMIT messages per poll"


@pytest.mark.asyncio
async def test_a_reply_to_an_earlier_turn_is_never_taken_for_this_turn(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # §8.5 step 1 / EC-85: the snapshot taken before prompt_async keeps the session's earlier "old answer" out of this turn.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.continue_opencode_session(KNOWN_SESSION, opencode_api.OpencodePromptRequest(prompt=PROMPT))
        with pytest.raises(opencode_api.NativeHostError) as still_running:
            await host.wait_opencode_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(still_running.value, code="opencode.turn_timed_out", token="wait_opencode_turn")
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.text == "alpha-beta"
    routes = fake_opencode.routes()
    snapshot = [index for index, item in enumerate(fake_opencode.requests) if item.route == "messages" and item.query.get("limit") == "1"]
    assert snapshot and snapshot[0] < routes.index("prompt_async"), "the snapshot is taken before prompt_async"


@pytest.mark.asyncio
async def test_a_reply_still_being_written_never_completes_the_turn(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # §8.5 step 5: idle polls count only once the newest reply has time.completed.
    fake_opencode.plan("writing")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        with pytest.raises(opencode_api.NativeHostError) as still_running:
            await host.wait_opencode_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(still_running.value, code="opencode.turn_timed_out", token="wait_opencode_turn")
        assert len(fake_opencode.seen("session_status")) > 3, "more than OPENCODE_IDLE_CONFIRMATIONS idle polls passed"
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.text == "fully written"


@pytest.mark.asyncio
async def test_an_earlier_steps_error_does_not_decide_the_turn(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-85: only the newest reply's error decides the outcome.
    failed_step = reply("", finish=None, error={"name": "APIError", "data": {"message": "rate limited", "statusCode": 429, "isRetryable": True}})
    fake_opencode.plan("steps", steps=[failed_step, reply("recovered")], per_poll=1)
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.text == "recovered"


@pytest.mark.asyncio
async def test_output_length_error_completes_with_its_stop_reason(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-89: MessageOutputLengthError is not an error; the turn is COMPLETED with stop_reason "output_length".
    fake_opencode.plan("complete", replies=[reply("partial text", finish="length", error={"name": "MessageOutputLengthError", "data": {}})])
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.stop_reason == "output_length"
    assert result.text == "partial text"


@pytest.mark.asyncio
async def test_an_abort_from_elsewhere_ends_the_turn_interrupted(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-88: MessageAbortedError is an interruption, not a failure.
    fake_opencode.plan("complete", replies=[reply("", finish=None, error={"name": "MessageAbortedError", "data": {"message": "The operation was aborted."}})])
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.status is opencode_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is not None


@pytest.mark.asyncio
async def test_turn_ceiling_aborts_and_ends_interrupted_by_deadline(opencode_api, fake_opencode, make_opencode_host, fast_timings) -> None:
    # D-10 / EC-88: at max_turn_seconds the watcher sends POST …/abort and the turn ends INTERRUPTED/DEADLINE.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        started = time.monotonic()
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT, max_turn_seconds=1.0)))
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
        elapsed = time.monotonic() - started
    assert result.status is opencode_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is opencode_api.InterruptSource.DEADLINE
    assert [item.params["sid"] for item in fake_opencode.seen("abort")] == [handle.session_id]
    assert elapsed < 1.0 + fast_timings.grace + SLACK_SECONDS


@pytest.mark.asyncio
async def test_host_exit_aborts_live_turns_as_host_closed(opencode_api, fake_opencode, make_opencode_host, fast_timings) -> None:
    # EC-8: __aexit__ interrupts every live turn; each ends INTERRUPTED/HOST_CLOSED.
    fake_opencode.plan("hold")
    host = make_opencode_host()
    async with host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        waiter = asyncio.create_task(host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS))
        await asyncio.sleep(0)
        started = time.monotonic()
    elapsed = time.monotonic() - started
    result = await waiter
    assert result.status is opencode_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is opencode_api.InterruptSource.HOST_CLOSED
    assert [item.params["sid"] for item in fake_opencode.seen("abort")] == [handle.session_id]
    assert elapsed < fast_timings.grace + SLACK_SECONDS


@pytest.mark.asyncio
async def test_aexit_never_suppresses_the_body_exception(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-8: __aexit__ raises nothing of its own and never swallows the exception it was given.
    fake_opencode.plan("hold")
    with pytest.raises(LookupError, match="body failure"):
        async with make_opencode_host() as host:
            await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
            raise LookupError("body failure")
    assert fake_opencode.seen("abort"), "the live turn was aborted on the error path too"


@pytest.mark.asyncio
async def test_intermittent_poll_failures_below_the_limit_do_not_fail_the_turn(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-87: only OPENCODE_POLL_FAILURE_LIMIT (5) failed polls in a row end the turn.
    fake_opencode.plan("complete", finish_after=1)
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        fake_opencode.fail("session_status", "connect", times=4)
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_session_deleted_mid_turn_fails_with_session_not_found(opencode_api, fake_opencode, make_opencode_host, wait_until, check_native_error) -> None:
    # EC-86: a watcher poll gets 404 for the session.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        assert await wait_until(lambda: len(fake_opencode.seen("session_status")) >= 1, GATE_SECONDS)
        fake_opencode.delete_session(handle.session_id)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    check_native_error(caught.value, code="opencode.session_not_found", token="list_opencode_sessions")


@pytest.mark.asyncio
async def test_retry_below_the_attempt_limit_keeps_the_turn_running(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # EC-155: attempts below OPENCODE_RETRY_ATTEMPT_LIMIT (5) do not end the turn and send no abort.
    fake_opencode.plan("retry", retry={"attempt": 4, "message": "Too Many Requests from provider", "reason": "rate_limit"})
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        with pytest.raises(opencode_api.NativeHostError) as still_running:
            await host.wait_opencode_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(still_running.value, code="opencode.turn_timed_out", token="wait_opencode_turn")
        assert fake_opencode.seen("abort") == []
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_retry_at_the_limit_aborts_the_turn(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-155: the watcher sends POST …/abort and records FAILED with the scrubbed retry message as vendor_error.
    fake_opencode.plan("retry", retry={"attempt": 5, "message": "Too Many Requests from provider", "reason": "rate_limit"})
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert [item.params["sid"] for item in fake_opencode.seen("abort")] == [handle.session_id]
    assert "Too Many Requests" in caught.value.context["vendor_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["session_status", "permission_list"])
async def test_a_single_non_counted_poll_failure_aborts_before_failing_the_turn(route: str, opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # R-6 / INV-10 / INV-13: one 500 (EC-59) is not counted by EC-87, so the turn fails; one best-effort abort must be sent first.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        fake_opencode.fail(route, "500", times=1)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
        aborts = [item.params["sid"] for item in fake_opencode.seen("abort")]
        assert aborts == [handle.session_id], "R-6: one best-effort abort for this session before the turn reports failure"
    check_native_error(caught.value, code="opencode.api_error", token="vendor_error")


@pytest.mark.asyncio
async def test_failed_turn_raises_the_same_code_on_every_wait(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-148 / INV-13: the failure is recorded once and raised by every later wait.
    fake_opencode.plan("complete", replies=[reply("", finish=None, error={"name": "APIError", "data": {"message": "payment required", "statusCode": 402, "isRetryable": False}})])
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        codes = []
        for _ in range(2):
            with pytest.raises(opencode_api.NativeHostError) as caught:
                await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
            codes.append(caught.value.failure_code)
    assert codes == [opencode_api.FailureCode.OPENCODE_BILLING_ERROR] * 2


@pytest.mark.asyncio
async def test_retryable_vendor_flag_reaches_the_tool_metadata_as_a_bool(opencode_api, opencode_tools_api, fake_opencode, make_opencode_host, tool_by_name) -> None:
    # INV-7: metadata carries `retryable` (a bool) when the vendor reported one.
    fake_opencode.plan("complete", replies=[reply("", finish=None, error={"name": "APIError", "data": {"message": "rate limited", "statusCode": 429, "isRetryable": True}})])
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        tool = tool_by_name(opencode_tools_api.OpencodeTools(host), "wait_opencode_turn")
        args = {"handle": {"harness": "opencode", "session_id": handle.session_id, "turn_id": handle.turn_id}, "timeout_seconds": TURN_WAIT_SECONDS}
        result = await tool.execute(opencode_tools_api.ToolCall("wait_opencode_turn", args))
    assert result.metadata["error"] == "opencode.usage_limited"
    assert result.metadata["retryable"] is True


@pytest.mark.asyncio
async def test_long_reply_text_is_capped(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-150 / INV-16: the first NATIVE_RESULT_TEXT_MAX_CHARS characters are kept and text_truncated is set.
    fake_opencode.plan("complete", replies=[reply("é" * 100_001)])
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api)
    assert result.text_truncated is True
    assert result.text == "é" * 100_000


@pytest.mark.asyncio
async def test_permissions_and_questions_in_the_turn_tree_are_rejected_and_recorded(opencode_api, fake_opencode, make_opencode_host, wait_until) -> None:
    # EC-154 / INV-10 / D-11: the turn's session, a child and a grandchild are rejected; an outside session is left alone.
    fake_opencode.add_session("ses_child01", "subagent", parent_id=KNOWN_SESSION)
    fake_opencode.add_session("ses_grand01", "sub-subagent", parent_id="ses_child01")
    fake_opencode.plan(
        "hold",
        permissions=[permission("per_own", "$session", "bash"), permission("per_child", "ses_child01"), permission("per_grand", "ses_grand01"), permission("per_outside", OTHER_SESSION)],
        questions=[{"id": "que_own", "sessionID": "$session", "questions": [{"question": "Proceed?", "header": "Confirm", "options": []}]}],
    )
    async with make_opencode_host() as host:
        handle = await host.continue_opencode_session(KNOWN_SESSION, opencode_api.OpencodePromptRequest(prompt=PROMPT))
        replied = await wait_until(lambda: {item.params["rid"] for item in fake_opencode.seen("permission_reply")} >= {"per_own", "per_child", "per_grand"} and fake_opencode.seen("question_reject"), GATE_SECONDS)
        assert replied, f"the turn's requests were not all answered: {fake_opencode.routes()}"
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert {item.params["rid"] for item in fake_opencode.seen("permission_reply")} == {"per_own", "per_child", "per_grand"}
    assert all(item.body == {"reply": "reject"} for item in fake_opencode.seen("permission_reply")), "D-11: always reject, never once or always"
    assert [item.params["rid"] for item in fake_opencode.seen("question_reject")] == ["que_own"]
    assert [entry["id"] for entry in fake_opencode.permissions] == ["per_outside"], "a request outside every live turn's tree is left alone"
    decisions = sorted((decision.request_kind, decision.outcome) for decision in result.decisions)
    rejected = opencode_api.ApprovalOutcome.REJECTED
    assert decisions == sorted([("opencode.permission:bash", rejected), ("opencode.permission:edit", rejected), ("opencode.permission:edit", rejected), ("opencode.question", rejected)])


@pytest.mark.asyncio
async def test_an_outside_session_id_causes_one_tree_walk_only(opencode_api, fake_opencode, make_opencode_host, wait_until) -> None:
    # EC-154: an id found outside the tree is remembered for the turn and never causes another children walk.
    fake_opencode.plan("hold", permissions=[permission("per_outside", OTHER_SESSION)])
    async with make_opencode_host() as host:
        handle = await host.continue_opencode_session(KNOWN_SESSION, opencode_api.OpencodePromptRequest(prompt=PROMPT))
        assert await wait_until(lambda: len(fake_opencode.seen("session_status")) >= 10, GATE_SECONDS)
        walks = len(fake_opencode.seen("session_children"))
        assert await wait_until(lambda: len(fake_opencode.seen("session_status")) >= 20, GATE_SECONDS)
        assert len(fake_opencode.seen("session_children")) == walks
        fake_opencode.release_turn()
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert walks >= 1, "the unknown id triggered one refresh of the tree"
    assert fake_opencode.seen("permission_reply") == []


@pytest.mark.asyncio
async def test_a_tree_past_the_limit_aborts_the_turn_by_policy(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-154: more than OPENCODE_MAX_SESSION_TREE (64) sessions → POST …/abort, INTERRUPTED with source POLICY.
    for index in range(65):
        fake_opencode.add_session(f"ses_child{index:03d}", "subagent", parent_id=KNOWN_SESSION)
    fake_opencode.plan("hold", permissions=[permission("per_stranger", "ses_stranger")])
    async with make_opencode_host() as host:
        result = await run_turn(host, opencode_api, continue_session=KNOWN_SESSION)
    assert result.status is opencode_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is opencode_api.InterruptSource.POLICY
    assert [item.params["sid"] for item in fake_opencode.seen("abort")] == [KNOWN_SESSION]


@pytest.mark.asyncio
async def test_a_malformed_pending_permission_is_a_protocol_mismatch(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # D-13: OpencodeWire.parse_permission_requests raises protocol_mismatch for a missing relied-on member.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        fake_opencode.override("permission_list", 200, [{"id": "per_broken", "permission": "edit"}])
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    check_native_error(caught.value, code="opencode.protocol_mismatch", token="check_opencode_ready")
