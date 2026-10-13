"""FILE: tests/features/muse_host/test_muse_host_turns.py

PURPOSE: How MuseTurnDriver runs one turn: approvals decided once per requirement with a denied choice scoped once (D-11, INV-10, EC-121, EC-156), user input cancelled, approval and user-input titles recorded scrubbed (§9.1, INV-6), the turn id taken from the turn/start ack (EC-109), reply text taken only from the turn's agentMessage items (EC-150, view/gap), steer and interrupt on the wire, an interrupt or steer that loses the race to the turn's own turn/completed (RACE-1: INV-13, EC-52, EC-102, EC-115), the turn ceiling (D-10), usage (D-14, INV-15), and the turn table rules (EC-9, EC-112, EC-148, INV-14, INV-17), including a session id that Muse's own session/start returned in upper case.
ROLE IN CODEBASE: Proves the Muse half of FR-12 and the turn rules of §6.3.5 for vidbyte.harnesses.native.muse.turn, driven through MuseHost and the fake muse.
ARCHITECTURE NOTE: The fake plays a turn in a worker thread after the ack: approvals, user input, notifications, foreign-turn events, items, an optional view/gap, then turn/completed, or a hold until the release file or turn/interrupt. Where the fake waits for an answer (approval/decide, userInput/cancel) it logs request_seen or request_missing, so a missing answer shows in the logs as well as in the result.
FUNCTION INVENTORY: decides lists the approval/decide params the fake received; answer_to finds the host's response to a server request; spawn_and_wait runs one turn to its result; poll_until polls a condition every 10 ms with a 5 s limit; interrupt_expecting_no_error turns a raised interrupt into an INV-13 failure; assert_the_interrupted_turn_stands checks was_running and the recorded INTERRUPTED/CALLER result; the test_* functions are one rule each.
COMMON MODIFICATION PATTERNS: A new turn rule gets a scenario key in fake_muse_peer.py's TurnWorker and one test here.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept an approved choice or a session or persistent scope as a passing answer; INV-9 and D-11 forbid both. 2. Do not compare commandIds by order; only their shape is stable (spec §13). 3. Do not commit a key-shaped literal or print a secret in an assertion message; the title-scrub test builds its value from uuid4 and names only the surface that leaked. 4. Do not assert the spelling of handle.session_id in the vendor-id busy tests; INV-14 fixes only that both spellings name one session.
KNOWN EDGE CASES: The RACE-1 tests force the frame order with the fake's turn/interrupt "order" knob, or with a silent answer that the turn's own end overtakes; the two guards (a -32030 for a turn still running, and an interrupt while the driver is closing a completed turn) pass before and after the fix. The outcome recorded for a plain denied decide is not fixed by the spec, so those tests assert only that it is not ALLOWED; EC-156 fixes CANCELLED for a failed or benign-race decide and those tests bind it. The fake's foreign-turn events carry turn id "turn-foreign" and must change nothing. VENDOR_UPPER_SCENARIO lists the vendor id in both spellings, as a Muse that matches ids ignoring case would, so a host that misses the busy check really starts a second turn or fork instead of failing as session_not_found.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5, §8.1 D-9 to D-14, §8.5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_turns.py
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
NEW_SESSION = "0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"
VENDOR_UPPER_SESSION = "0192F0C4-ABCD-7EF0-8123-456789ABCDEF"
VENDOR_UPPER_SCENARIO = {"new_session_id": VENDOR_UPPER_SESSION, "sessions": [VENDOR_UPPER_SESSION, VENDOR_UPPER_SESSION.lower()], "turn": {"mode": "hold"}}
HANDLE_ID_SPELLINGS = [pytest.param(str, id="handle-id"), pytest.param(str.lower, id="lower-cased-handle-id")]
PROMPT = "List the top-level folders."
STEER_TEXT = "Also list hidden folders."
REPLY_TEXT = "alpha\n\nbeta"
ACK_TURN_ID = "turn-from-ack-7"
WAIT_SECONDS = 30.0
SHORT_CONTROL_SECONDS = 0.5
CEILING_SECONDS = 0.5
UUID7_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
NO_DENY_ONCE = [
    {"choiceId": "choice-approve-once", "decision": "approved", "label": "Approve once", "scope": "once"},
    {"choiceId": "choice-approve-session", "decision": "approvedForSession", "label": "Approve for session", "scope": "session"},
    {"choiceId": "choice-deny-persistent", "decision": "denied", "label": "Always deny", "scope": "localPersistent"},
]
RACE_POLL_SECONDS = 0.01
RACE_POLL_LIMIT_SECONDS = 5.0
ANSWERS_AFTER_TURN_COMPLETED = [
    pytest.param({"error": {"code": -32013, "message": "interrupted"}}, id="minus-32013"),
    pytest.param({"error": {"code": -32014, "message": "cancelled"}}, id="minus-32014"),
    pytest.param({"error": {"code": -32030, "message": "the turn is no longer running"}}, id="minus-32030"),
    pytest.param({}, id="accepted"),
]


def decides(muse_fake: Any) -> list[dict[str, Any]]:
    return [frame["params"] for frame in muse_fake.received("approval/decide")]


def answer_to(muse_fake: Any, request_id: str) -> dict[str, Any] | None:
    # The host's response to a server request is a frame with that id and no method.
    for record in muse_fake.records("frame"):
        if record["frame"].get("id") == request_id and "method" not in record["frame"]:
            return record["frame"]
    return None


async def spawn_and_wait(host: Any, api: Any, **fields: Any) -> Any:
    handle = await host.spawn_muse_session(api.MuseTurnRequest(prompt=PROMPT, **fields))
    return await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)


async def poll_until(predicate: Callable[[], bool]) -> bool:
    # Bounded polling at 10 ms, fine enough to land inside the driver's close; never a fixed sleep.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RACE_POLL_LIMIT_SECONDS
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(RACE_POLL_SECONDS)
    return predicate()


async def interrupt_expecting_no_error(host: Any, api: Any, handle: Any) -> Any:
    # INV-13 (RACE-1): an interrupt the host sent to a turn it found running raises nothing, even when the turn's own end wins the race.
    try:
        return await host.interrupt_muse_turn(handle)
    except api.NativeHostError as error:
        pytest.fail(f"INV-13: interrupt_muse_turn raised {error.failure_code.value} (reason {error.context.get('reason')!r}) for an interrupt it sent to a running turn whose own end won the race")


def assert_the_interrupted_turn_stands(interrupted: Any, result: Any, api: Any, muse_fake: Any) -> None:
    # The fake ends the turn cancelled because of the interrupt, so the recorded INTERRUPTED/CALLER state stands and was_running reports the pre-send check.
    assert interrupted.was_running is True, "INV-13 / EC-52: the host found the turn running and sent turn/interrupt"
    assert result.status is api.NativeTurnStatus.INTERRUPTED
    assert result.stop_reason == "cancelled"
    assert result.interrupt_source is api.InterruptSource.CALLER
    assert len(muse_fake.received("turn/interrupt")) == 1


@pytest.mark.asyncio
async def test_approval_is_answered_with_the_denied_once_choice_and_its_requirement(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # D-11 / INV-10: approval/decide carries every schema member, the denied+once choice and the current requirement.
    async with make_muse_host({"turn": {"approvals": [{}]}}) as host:
        result = await spawn_and_wait(host, muse_api)
    sent = decides(muse_fake)
    assert len(sent) == 1
    params = sent[0]
    assert params["choiceId"] == "choice-deny-once"
    assert params["approvalId"] == "approval-0"
    assert params["requirementId"] == {"approvalId": "approval-0", "sourceIndex": 0}
    assert params["sessionId"] == NEW_SESSION
    assert UUID7_PATTERN.match(params["commandId"])
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert [decision.request_kind for decision in result.decisions] == ["muse.approval"]
    assert result.decisions[0].outcome is not muse_api.ApprovalOutcome.ALLOWED
    assert not muse_fake.records("request_missing"), "the fake waited for a decide that never came"


@pytest.mark.asyncio
async def test_each_requirement_is_decided_once_and_a_repeated_update_is_ignored(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # D-11: an update naming a decided requirement gets no second decide; one naming a new requirement gets one.
    approval = {"updates": [{"source_index": 0, "change_kind": "subjectChanged", "expect_decide": False}, {"source_index": 1}]}
    async with make_muse_host({"turn": {"approvals": [approval]}}) as host:
        result = await spawn_and_wait(host, muse_api)
    assert [params["requirementId"]["sourceIndex"] for params in decides(muse_fake)] == [0, 1]
    assert all(params["choiceId"] == "choice-deny-once" for params in decides(muse_fake))
    assert result.status is muse_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_decide_with_terminal_false_answers_the_following_update(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-156 (not the row): terminal false leaves the approval pending; the next requirement is decided as usual.
    scenario = {"msp": {"approval/decide": {"terminal": False}}, "turn": {"approvals": [{"updates": [{"source_index": 1}]}]}}
    async with make_muse_host(scenario) as host:
        result = await spawn_and_wait(host, muse_api)
    assert [params["requirementId"] for params in decides(muse_fake)] == [{"approvalId": "approval-0", "sourceIndex": 0}, {"approvalId": "approval-0", "sourceIndex": 1}]
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert muse_fake.received("turn/interrupt") == []


@pytest.mark.asyncio
async def test_approval_without_a_denied_once_choice_interrupts_the_turn_by_policy(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-121 / INV-9: no approving or wider-scoped choice is ever picked; the turn is interrupted instead.
    scenario = {"turn": {"mode": "hold", "approvals": [{"choices": NO_DENY_ONCE, "expect_decide": False}]}}
    async with make_muse_host(scenario) as host:
        result = await spawn_and_wait(host, muse_api)
    assert decides(muse_fake) == [], "no offered choice may be sent"
    assert result.status is muse_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is muse_api.InterruptSource.POLICY
    assert [frame["params"]["turnId"] for frame in muse_fake.received("turn/interrupt")] == ["turn-0001"]
    assert all(decision.outcome is not muse_api.ApprovalOutcome.ALLOWED for decision in result.decisions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decide_config", "control_timeout"),
    [
        pytest.param({"error": {"code": -32052, "message": "choice no longer offered"}}, 10.0, id="minus-32052"),
        pytest.param({"error": {"code": -32603, "message": "internal"}}, 10.0, id="minus-32603"),
        pytest.param({"mode": "silent"}, SHORT_CONTROL_SECONDS, id="no-answer"),
    ],
)
async def test_failed_decide_records_cancelled_and_interrupts_the_turn(decide_config: dict[str, Any], control_timeout: float, muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-156: the decision is CANCELLED, turn/interrupt is sent, and the turn ends INTERRUPTED by policy.
    scenario = {"msp": {"approval/decide": decide_config}, "turn": {"mode": "hold", "approvals": [{}]}}
    async with make_muse_host(scenario, control_timeout_seconds=control_timeout) as host:
        result = await spawn_and_wait(host, muse_api)
    assert result.status is muse_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is muse_api.InterruptSource.POLICY
    assert [decision.outcome for decision in result.decisions] == [muse_api.ApprovalOutcome.CANCELLED]
    assert len(muse_fake.received("turn/interrupt")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [-32051, -32053], ids=["already-resolved", "requirement-stale"])
async def test_benign_decide_race_records_cancelled_and_the_turn_goes_on(code: int, muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-156 (benign race, D-11): CANCELLED is recorded, no interrupt is sent, and the turn completes.
    scenario = {"msp": {"approval/decide": {"error": {"code": code, "message": "lost the race"}}}, "turn": {"approvals": [{}]}}
    async with make_muse_host(scenario) as host:
        result = await spawn_and_wait(host, muse_api)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.text == REPLY_TEXT
    assert [decision.outcome for decision in result.decisions] == [muse_api.ApprovalOutcome.CANCELLED]
    assert muse_fake.received("turn/interrupt") == []


@pytest.mark.asyncio
async def test_user_input_request_is_cancelled_and_recorded(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # D-11 / INV-10: userInput/requested is answered with userInput/cancel carrying every schema member.
    async with make_muse_host({"turn": {"user_inputs": [{}]}}) as host:
        result = await spawn_and_wait(host, muse_api)
    cancels = [frame["params"] for frame in muse_fake.received("userInput/cancel")]
    assert len(cancels) == 1
    assert cancels[0]["userInputId"] == "input-0"
    assert cancels[0]["sessionId"] == NEW_SESSION
    assert UUID7_PATTERN.match(cancels[0]["commandId"])
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert [decision.request_kind for decision in result.decisions] == ["muse.user_input"]
    assert result.decisions[0].outcome is not muse_api.ApprovalOutcome.ALLOWED


@pytest.mark.asyncio
@pytest.mark.parametrize(("scenario_key", "request_kind"), [pytest.param("approvals", "muse.approval", id="approval-requested"), pytest.param("user_inputs", "muse.user_input", id="user-input-requested")])
async def test_a_credential_in_a_request_title_is_scrubbed_from_the_result_and_the_wait_tool(scenario_key: str, request_kind: str, muse_api, muse_tools_api, muse_fake, make_muse_host, fast_stop, tool_by_name) -> None:
    # §9.1 / INV-6 (re-review R-17): the title recorded for approval/requested and userInput/requested is scrubbed, so a credential in the tool name reaches neither the result nor wait_muse_turn's output.
    secret = f"sk-proj-FAKE{uuid.uuid4().hex}"
    named = f"shell OPENAI_API_KEY={secret}"
    async with make_muse_host({"turn": {scenario_key: [{"tool_name": named}]}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        arguments = {"handle": {"harness": handle.harness.value, "session_id": handle.session_id, "turn_id": handle.turn_id}, "timeout_seconds": WAIT_SECONDS}
        waited = await tool_by_name(muse_tools_api.MuseTools(host), "wait_muse_turn").execute(muse_tools_api.ToolCall("wait_muse_turn", arguments))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert [decision.request_kind for decision in result.decisions] == [request_kind], "the request was answered and recorded"
    assert waited.status is muse_tools_api.ToolStatus.SUCCESS, "the wait tool returned the turn result"
    recorded = result.decisions[0].title
    surfaces = {"decision title": recorded, "tool output": waited.output, "tool metadata": json.dumps(dict(waited.metadata), default=str)}
    leaked = [name for name, text in surfaces.items() if secret in text]
    assert not leaked, f"INV-6: the credential leaked into {leaked}"
    assert "<redacted>" in recorded, "§9.1: the title is scrubbed, not dropped"


@pytest.mark.asyncio
async def test_unknown_server_request_gets_method_not_found(muse_api, muse_fake, make_muse_host, fast_stop, wait_until) -> None:
    # D-11 / INV-10: any other server request inside the turn is answered with JSON-RPC error -32601.
    request = {"jsonrpc": "2.0", "id": "server-req-1", "method": "fs/readTextFile", "params": {"sessionId": "$session", "path": "notes.txt"}}
    async with make_muse_host({"turn": {"notifications": [request]}}) as host:
        result = await spawn_and_wait(host, muse_api)
        assert await wait_until(lambda: answer_to(muse_fake, "server-req-1") is not None, 10.0), "the host never answered the server request"
    answer = answer_to(muse_fake, "server-req-1")
    assert answer["error"]["code"] == -32601
    assert result.status is muse_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["started", "queued", "steered", "futureDisposition"])
async def test_turn_id_comes_from_the_ack_and_foreign_turn_events_are_ignored(disposition: str, muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-109: items and turn/completed match ack.turn_id, never the commandId; events for another turn change nothing.
    scenario = {"turn": {"turn_id": ACK_TURN_ID, "disposition": disposition, "foreign_events": True}}
    async with make_muse_host(scenario) as host:
        result = await spawn_and_wait(host, muse_api)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED, "the foreign turn's failed completion must not end this turn"
    assert result.text == REPLY_TEXT
    assert "IGNORED FOREIGN TEXT" not in result.text


@pytest.mark.asyncio
async def test_steer_names_the_ack_turn_and_returns_the_vendor_status(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5 turn/steer: expectedTurnId is ack.turn_id; NativeSteerResult.status is the result's status verbatim.
    async with make_muse_host({"turn": {"turn_id": ACK_TURN_ID, "mode": "hold"}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        steered = await host.steer_muse_turn(handle, STEER_TEXT)
        muse_fake.release()
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    params = muse_fake.received("turn/steer")[0]["params"]
    assert params["expectedTurnId"] == ACK_TURN_ID
    assert params["sessionId"] == NEW_SESSION
    assert params["input"] == [{"type": "text", "text": STEER_TEXT}]
    assert UUID7_PATTERN.match(params["commandId"])
    assert steered.status == "accepted"
    assert steered.handle == handle


@pytest.mark.asyncio
async def test_interrupt_names_the_ack_turn(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5 turn/interrupt: commandId, sessionId and turnId (ack.turn_id).
    async with make_muse_host({"turn": {"turn_id": ACK_TURN_ID, "mode": "hold"}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.interrupt_muse_turn(handle)
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    params = muse_fake.received("turn/interrupt")[0]["params"]
    assert params["turnId"] == ACK_TURN_ID
    assert params["sessionId"] == NEW_SESSION
    assert UUID7_PATTERN.match(params["commandId"])


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [-32013, -32014], ids=["interrupted", "cancelled"])
async def test_interrupt_answered_interrupted_or_cancelled_counts_as_success(code: int, muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §6.3.5 interrupt_muse_turn: -32013 and -32014 mean the turn is already stopping.
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"order": "answer_first", "error": {"code": code, "message": "already stopping"}}}}
    async with make_muse_host(scenario) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        interrupted = await host.interrupt_muse_turn(handle)
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert interrupted.was_running is True
    assert result.status is muse_api.NativeTurnStatus.INTERRUPTED


@pytest.mark.asyncio
async def test_interrupt_that_loses_to_turn_completed_succeeds(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # INV-13 (RACE-1 R-18): Muse never answers turn/interrupt but ends the turn cancelled, so the driver closes the peer while the call is pending; that close is the host's own, not a peer exit (EC-96).
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"mode": "silent"}}}
    async with make_muse_host(scenario) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        interrupted = await interrupt_expecting_no_error(host, muse_api, handle)
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert_the_interrupted_turn_stands(interrupted, result, muse_api, muse_fake)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ANSWERS_AFTER_TURN_COMPLETED)
async def test_interrupt_answered_after_turn_completed_succeeds(answer: dict[str, Any], muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # INV-13 (RACE-1 R-18, the CI frame order): turn/completed is written before the interrupt's answer, whatever that answer is; the interrupt still succeeds.
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"order": "completed_first", **answer}}}
    async with make_muse_host(scenario) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        interrupted = await interrupt_expecting_no_error(host, muse_api, handle)
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert [record["completed_sent"] for record in muse_fake.records("interrupt_order")] == [True], "the fake wrote turn/completed before the interrupt's answer"
    assert_the_interrupted_turn_stands(interrupted, result, muse_api, muse_fake)


@pytest.mark.asyncio
async def test_interrupt_rejected_with_32030_while_the_turn_still_runs_raises_api_error(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # Guard (EC-102) for the RACE-1 fix: Muse has not ended the turn, so a -32030 answer is a real rejection; a fix keyed on the answer code instead of the turn's own end breaks this.
    scenario = {"turn": {"mode": "hold", "on_interrupt": "ignore"}, "msp": {"turn/interrupt": {"error": {"code": -32030, "message": "command rejected"}}}}
    async with make_muse_host(scenario) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        with pytest.raises(muse_api.NativeHostError) as caught:
            await host.interrupt_muse_turn(handle)
    check_native_error(caught.value, code="muse.api_error", token="vendor_error", operation="interrupt_muse_turn")
    assert caught.value.context.get("vendor_code") == "-32030"
    completions = [record for record in muse_fake.records("sent") if record["frame"].get("method") == "turn/completed"]
    assert completions == [], "the turn was still running when the -32030 answer arrived"


@pytest.mark.asyncio
async def test_interrupt_after_turn_completed_while_the_driver_is_still_closing_sends_nothing(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # Guard (EC-52 parity with Grok's RACE-1 R-20): the turn completed and the driver is inside its close, because the fake ignores stdin EOF; the interrupt finds the turn finished.
    async with make_muse_host({"ignore_eof": True}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        assert await poll_until(lambda: bool(muse_fake.records("eof"))), "the driver never closed the peer's stdin after turn/completed"
        interrupted = await host.interrupt_muse_turn(handle)
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert interrupted.was_running is False, "EC-52: the turn had completed, so nothing is sent"
    assert muse_fake.received("turn/interrupt") == []
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.interrupt_source is None


@pytest.mark.asyncio
async def test_steer_that_loses_to_turn_completed_raises_turn_not_found(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # EC-115 (RACE-1 R-21): the turn completes while turn/steer waits for its answer, and the driver closes the peer; the turn is no longer running, so this is turn_not_found, not process_exited.
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/steer": {"mode": "silent"}}}
    async with make_muse_host(scenario) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        steer = asyncio.create_task(host.steer_muse_turn(handle, STEER_TEXT))
        assert await poll_until(lambda: bool(muse_fake.received("turn/steer"))), "turn/steer never reached the fake"
        muse_fake.release()
        with pytest.raises(muse_api.NativeHostError) as caught:
            await steer
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    check_native_error(caught.value, code="muse.turn_not_found", token="continue_muse_session", operation="steer_muse_turn")
    assert result.status is muse_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "turn",
    [
        pytest.param({"items": [{"text": "alpha", "truncated": True}]}, id="item-truncated"),
        pytest.param({"view_gap": True}, id="view-gap"),
    ],
)
async def test_server_side_truncation_marks_the_text_truncated(turn: dict[str, Any], muse_api, make_muse_host, fast_stop) -> None:
    # §8.5: an item's own truncated flag, or a view/gap that may have dropped a reply item, sets text_truncated.
    async with make_muse_host({"turn": turn}) as host:
        result = await spawn_and_wait(host, muse_api)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.text_truncated is True


@pytest.mark.asyncio
async def test_result_text_is_capped_and_only_agent_messages_count(muse_api, make_muse_host, fast_stop) -> None:
    # EC-150 / INV-16: the first NATIVE_RESULT_TEXT_MAX_CHARS characters are kept; other item kinds add nothing.
    cap = muse_api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    items = [{"kind": "toolCall", "text": "TOOL OUTPUT"}, {"text": "a" * (cap // 2 + 10)}, {"text": "b" * (cap // 2 + 10)}]
    async with make_muse_host({"turn": {"items": items}}) as host:
        result = await spawn_and_wait(host, muse_api)
    assert len(result.text) == cap
    assert result.text_truncated is True
    assert result.text.startswith("a" * (cap // 2 + 10) + "\n\nb")
    assert "TOOL OUTPUT" not in result.text


@pytest.mark.asyncio
async def test_turn_usage_sets_only_the_fields_muse_reported(muse_api, make_muse_host, fast_stop) -> None:
    # D-14 / INV-15: turn/completed.usage fills the token counts; cost and unreported fields stay None.
    usage = {"inputTokens": 120, "outputTokens": 30, "reasoningTokens": 5, "cachedTokens": 0}
    async with make_muse_host({"turn": {"usage": usage}}) as host:
        result = await spawn_and_wait(host, muse_api)
    assert result.usage is not None
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.reasoning_tokens) == (120, 30, 5)
    assert result.usage.cost_usd is None, "NG-14: Muse reports no cost"
    assert result.usage.cache_write_tokens is None
    assert result.usage.total_tokens is None


@pytest.mark.asyncio
async def test_turn_without_usage_reports_none_never_zero(muse_api, make_muse_host, fast_stop) -> None:
    # INV-15: unknown usage is None, never 0.
    async with make_muse_host() as host:
        result = await spawn_and_wait(host, muse_api)
    usage = result.usage
    fields = ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens", "total_tokens", "cost_usd")
    assert usage is None or all(getattr(usage, name) is None for name in fields)


@pytest.mark.asyncio
async def test_turn_ceiling_interrupts_the_turn_with_deadline_source(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # D-10: at max_turn_seconds the host interrupts the turn; the result is INTERRUPTED with source DEADLINE.
    async with make_muse_host({"turn": {"mode": "hold"}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT, max_turn_seconds=CEILING_SECONDS))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is muse_api.InterruptSource.DEADLINE
    assert len(muse_fake.received("turn/interrupt")) == 1


@pytest.mark.asyncio
async def test_waiting_twice_on_a_failed_turn_raises_the_same_code(muse_api, make_muse_host, fast_stop, check_native_error) -> None:
    # EC-148 / INV-13: the FAILED state is recorded once and raised on every wait.
    error = {"kind": "stepLimit", "message": "step limit reached", "retryable": False}
    async with make_muse_host({"turn": {"terminal": "failed", "error": error}}) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        raised = []
        for _ in range(2):
            with pytest.raises(muse_api.NativeHostError) as caught:
                await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
            raised.append(caught.value)
    for value in raised:
        check_native_error(value, code="muse.budget_exhausted", token="continue_muse_session")


@pytest.mark.asyncio
async def test_handle_from_another_host_is_not_found(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # INV-17: handles are host-scoped; another MuseHost never issued this turn id.
    async with make_muse_host() as first, make_muse_host() as second:
        handle = await first.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        with pytest.raises(muse_api.NativeHostError) as caught:
            await second.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
        await first.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    check_native_error(caught.value, code="muse.turn_not_found", token="continue_muse_session", operation="wait_muse_turn")


@pytest.mark.asyncio
async def test_two_concurrent_continues_on_one_session_start_one_turn(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # EC-9 / INV-14: the session is reserved before the first await, so exactly one call passes the busy check.
    async with make_muse_host({"turn": {"mode": "hold"}}) as host:
        request = muse_api.MuseTurnRequest(prompt=PROMPT)
        outcomes = await asyncio.gather(host.continue_muse_session(KNOWN_SESSION, request), host.continue_muse_session(KNOWN_SESSION, request), return_exceptions=True)
        handles = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(handles) == 1 and len(errors) == 1, outcomes
        check_native_error(errors[0], code="muse.session_busy", token="interrupt_muse_turn", operation="continue_muse_session")
        assert len(muse_fake.received("turn/start")) == 1
        muse_fake.release()
        await host.wait_muse_turn(handles[0], timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_continue_on_the_upper_cased_id_of_a_live_session_is_busy(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # EC-112 / INV-14: Muse session ids compare ignoring case, so a continue on the upper-cased id hits the live turn.
    async with make_muse_host({"turn": {"mode": "hold"}}) as host:
        live = await host.continue_muse_session(KNOWN_SESSION, muse_api.MuseTurnRequest(prompt=PROMPT))
        with pytest.raises(muse_api.NativeHostError) as caught:
            await host.continue_muse_session(KNOWN_SESSION.upper(), muse_api.MuseTurnRequest(prompt=PROMPT))
        check_native_error(caught.value, code="muse.session_busy", token="interrupt_muse_turn", operation="continue_muse_session")
        assert len(muse_fake.received("turn/start")) == 1, "the upper-cased id names the same live session, so no second turn starts"
        muse_fake.release()
        await host.wait_muse_turn(live, timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("spell", HANDLE_ID_SPELLINGS)
async def test_continue_on_a_live_session_whose_vendor_id_is_upper_case_is_busy(spell: Callable[[str], str], muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # INV-14 / EC-112 (re-review R-16): Muse chose an upper-case id at session/start, so continuing by the handle's own id or its lower-cased form must hit the live turn.
    async with make_muse_host(VENDOR_UPPER_SCENARIO) as host:
        live = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        assert live.session_id.lower() == VENDOR_UPPER_SESSION.lower(), "the spawn bound the id the fake's session/start returned"
        with pytest.raises(muse_api.NativeHostError) as caught:
            await host.continue_muse_session(spell(live.session_id), muse_api.MuseTurnRequest(prompt=PROMPT))
        check_native_error(caught.value, code="muse.session_busy", token="interrupt_muse_turn", operation="continue_muse_session")
        assert len(muse_fake.starts("peer")) == 1, "a busy session must not open a second peer"
        assert len(muse_fake.received("turn/start")) == 1, "only the live turn started"
        muse_fake.release()
        await host.wait_muse_turn(live, timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("spell", HANDLE_ID_SPELLINGS)
async def test_fork_of_a_live_session_whose_vendor_id_is_upper_case_is_busy(spell: Callable[[str], str], muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # INV-14 / EC-112 for fork (re-review R-16): the local live-turn check ignores case, so it refuses before any peer starts or session/fork is sent.
    async with make_muse_host(VENDOR_UPPER_SCENARIO) as host:
        live = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        assert live.session_id.lower() == VENDOR_UPPER_SESSION.lower(), "the spawn bound the id the fake's session/start returned"
        with pytest.raises(muse_api.NativeHostError) as caught:
            await host.fork_muse_session(spell(live.session_id))
        check_native_error(caught.value, code="muse.session_busy", token="interrupt_muse_turn", operation="fork_muse_session")
        assert muse_fake.received("session/fork") == [], "INV-14: busy is found before anything is sent"
        assert len(muse_fake.starts("peer")) == 1, "a busy session must not open a fork peer"
        muse_fake.release()
        await host.wait_muse_turn(live, timeout_seconds=WAIT_SECONDS)
