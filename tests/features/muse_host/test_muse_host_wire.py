"""FILE: tests/features/muse_host/test_muse_host_wire.py

PURPOSE: The MSP 1.0.1 frames MuseHost sends, member by member (spec §8.5): initialize with clientInfo {MUSE_CLIENT_NAME, vidbyte.__version__} followed by the initialized notification, the params of every command and read, UUIDv7 commandIds from MuseWire.new_command_id(), the launch argv, the absence of any approve-everything value (INV-9, AC-19), and MuseWire's inbound parsers with their protocol_mismatch guard (D-13).
ROLE IN CODEBASE: Proves the wire half of FR-3 and FR-20 for vidbyte.harnesses.native.muse.wire. The fake also enforces the schema's required members and answers a violation with -32602, so a missing member fails a happy-path test as well as the exact-params assertions here.
ARCHITECTURE NOTE: Frames are read back from the fake's per-process JSONL logs. A short-lived read peer is one process, so its frames are in send order; peer_frames picks one process by pid.
FUNCTION INVENTORY: peer_frames returns one peer's frames in order; params_of returns the params of the frames with one method; the test_* functions check one call's frame each, the command id layout, INV-9, and each inbound parser.
COMMON MODIFICATION PATTERNS: When §8.5 adds a member to a call, add it to that call's expected key set here and to the fake's required table.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare two commandIds made within one millisecond; only the 48-bit prefix of ids made at least 1 ms apart is ordered (spec §13). 2. Do not sleep to space them; spin on time.monotonic_ns with a bound.
KNOWN EDGE CASES: In native mode the workspaceRoot is the workspace path as the host sees it; the test accepts the given or the resolved spelling, in native or POSIX form. clientInfo.version is read from vidbyte.__version__ when the params are built, so a patched attribute must reach the wire.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5, §9.3, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_wire.py
"""

from __future__ import annotations

import importlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
NEW_SESSION = "0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"
FORK_SESSION = "0192f0c4-aaaa-7bbb-8ccc-dddddddddddd"
TURN_ID = "turn-0001"
COMMAND_ID = "0192f0c4-1111-7222-8333-444444444444"
PROMPT = "List the top-level folders."
WAIT_SECONDS = 30.0
SPACING_NS = 1_000_000
SPIN_LIMIT_SECONDS = 1.0
CLOCK_SKEW_MS = 5_000
UUID7_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
APPROVE_EVERYTHING = ("allowAll", "--yolo", "--always-approve", "bypassPermissions", "yoloMode", "--dangerously-skip-permissions")


def peer_frames(muse_fake: Any, pid: int) -> list[dict[str, Any]]:
    return [record["frame"] for record in muse_fake.records("frame") if record["pid"] == pid]


def params_of(muse_fake: Any, method: str) -> list[dict[str, Any]]:
    return [frame.get("params") or {} for frame in muse_fake.received(method)]


def workspace_spellings(workspace: Path) -> set[str]:
    return {str(workspace), str(workspace.resolve()), workspace.as_posix(), workspace.resolve().as_posix()}


@pytest.fixture
def muse_wire() -> Any:
    return importlib.import_module("vidbyte.harnesses.native.muse.wire").MuseWire


@pytest.mark.asyncio
async def test_initialize_sends_client_info_and_then_initialized_before_any_request(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5 / review R-16: clientInfo has both required members; `initialized` precedes every other request.
    vidbyte = importlib.import_module("vidbyte")
    async with make_muse_host() as host:
        await host.list_muse_models()
    pids = muse_fake.pids("peer")
    assert len(pids) == 1
    frames = peer_frames(muse_fake, pids[0])
    assert [frame.get("method") for frame in frames[:3]] == ["initialize", "initialized", "model/list"]
    assert frames[0]["params"]["clientInfo"] == {"name": muse_api.constants.MUSE_CLIENT_NAME, "version": vidbyte.__version__}
    assert muse_api.constants.MUSE_CLIENT_NAME == "vidbyte_sdk"
    assert "id" not in frames[1], "initialized is a notification"
    assert not muse_fake.records("schema_violation")


@pytest.mark.asyncio
async def test_client_info_version_is_read_from_the_package_at_call_time(muse_api, muse_fake, make_muse_host, fast_stop, monkeypatch: pytest.MonkeyPatch) -> None:
    # §8.5: the version is vidbyte.__version__, never a literal copied at import time.
    vidbyte = importlib.import_module("vidbyte")
    monkeypatch.setattr(vidbyte, "__version__", "0.0.0+wiretest")
    async with make_muse_host() as host:
        await host.list_muse_models()
    assert params_of(muse_fake, "initialize")[0]["clientInfo"]["version"] == "0.0.0+wiretest"


@pytest.mark.asyncio
async def test_session_start_and_turn_start_carry_exactly_the_listed_members(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5: session/start {commandId, workspaceRoot, modelId when set, approvalMode denyUnmatched}; turn/start {commandId, sessionId, input, reasoningEffort when set}.
    async with make_muse_host() as host:
        request = muse_api.MuseTurnRequest(prompt=PROMPT, model="muse-fast", reasoning_effort=muse_api.MuseReasoningEffort.HIGH)
        handle = await host.spawn_muse_session(request)
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    start = params_of(muse_fake, "session/start")[0]
    assert set(start) == {"commandId", "workspaceRoot", "modelId", "approvalMode"}
    assert start["approvalMode"] == "denyUnmatched" == muse_api.constants.MUSE_APPROVAL_MODE
    assert start["modelId"] == "muse-fast"
    assert start["workspaceRoot"] in workspace_spellings(muse_fake.workspace)
    turn = params_of(muse_fake, "turn/start")[0]
    assert set(turn) == {"commandId", "sessionId", "input", "reasoningEffort"}
    assert turn["sessionId"] == NEW_SESSION
    assert turn["input"] == [{"type": "text", "text": PROMPT}]
    assert turn["reasoningEffort"] == "high"
    assert UUID7_PATTERN.match(start["commandId"]) and UUID7_PATTERN.match(turn["commandId"])
    assert start["commandId"] != turn["commandId"], "every command gets a fresh id"


@pytest.mark.asyncio
async def test_optional_members_are_left_out_when_unset(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5: modelId and reasoningEffort are sent only when set, and model/list is not needed without a model.
    async with make_muse_host() as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert "modelId" not in params_of(muse_fake, "session/start")[0]
    assert "reasoningEffort" not in params_of(muse_fake, "turn/start")[0]


@pytest.mark.asyncio
async def test_continue_resumes_with_command_and_session_only(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5: session/resume {commandId, sessionId}.
    async with make_muse_host() as host:
        handle = await host.continue_muse_session(KNOWN_SESSION, muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    resume = params_of(muse_fake, "session/resume")[0]
    assert set(resume) == {"commandId", "sessionId"}
    assert resume["sessionId"] == KNOWN_SESSION
    assert UUID7_PATTERN.match(resume["commandId"])


@pytest.mark.asyncio
async def test_fork_sends_a_cut_point_only_with_a_last_turn_id_and_never_a_top_level_one(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5 / review R-1: cutPoint {lastTurnId} only when given; lastTurnId at the top level is not a schema member.
    async with make_muse_host() as host:
        cut = await host.fork_muse_session(KNOWN_SESSION, last_turn_id=TURN_ID)
        whole = await host.fork_muse_session(KNOWN_SESSION)
    first, second = params_of(muse_fake, "session/fork")
    assert set(first) == {"commandId", "sessionId", "cutPoint"}
    assert first["cutPoint"] == {"lastTurnId": TURN_ID}
    assert set(second) == {"commandId", "sessionId"}
    assert first["sessionId"] == second["sessionId"] == KNOWN_SESSION
    assert cut.session_id == FORK_SESSION and whole.session_id == FORK_SESSION
    assert not muse_fake.records("schema_violation")


@pytest.mark.asyncio
async def test_reads_send_their_listed_members(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §8.5: session/list {workspaceRoot, cursor, limit}; session/read {sessionId, excludeItems: true}; view/page {sessionId, limit, cursor, direction}.
    async with make_muse_host({"msp": {"session/list": {"pages": [[KNOWN_SESSION], [NEW_SESSION]]}}}) as host:
        await host.list_muse_sessions(cursor="page-1", limit=7)
        await host.read_muse_session(KNOWN_SESSION)
        await host.page_muse_session(KNOWN_SESSION, limit=9, direction=muse_api.MuseViewDirection.BACKWARD)
    listed = params_of(muse_fake, "session/list")[0]
    assert listed["cursor"] == "page-1" and listed["limit"] == 7
    assert listed["workspaceRoot"] in workspace_spellings(muse_fake.workspace)
    assert params_of(muse_fake, "session/read")[0] == {"sessionId": KNOWN_SESSION, "excludeItems": True}
    page = params_of(muse_fake, "view/page")[0]
    assert page["sessionId"] == KNOWN_SESSION and page["limit"] == 9 and page["direction"] == "backward"
    assert set(page) <= {"sessionId", "limit", "cursor", "direction"}


@pytest.mark.asyncio
async def test_launch_argv_appends_only_serve_or_version(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §13 / D-19: the host appends `serve` to the muse_command prefix for peers, and `--version` for the check.
    async with make_muse_host() as host:
        await host.check_muse_ready()
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert muse_fake.launches("version") == [["--version"]]
    assert muse_fake.launches("peer") == [["serve"], ["serve"]]


@pytest.mark.asyncio
async def test_no_frame_or_argv_carries_an_approve_everything_value(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # INV-9 / AC-19: nothing the host sends or launches can approve everything, even when approvals are offered.
    scenario = {"turn": {"approvals": [{"updates": [{"source_index": 1}]}], "user_inputs": [{}]}}
    async with make_muse_host(scenario) as host:
        await host.check_muse_ready()
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    sent_text = json.dumps(muse_fake.received()) + json.dumps(muse_fake.launches())
    for value in APPROVE_EVERYTHING:
        assert value not in sent_text, f"INV-9: {value} must never be sent"
    assert {params["choiceId"] for params in params_of(muse_fake, "approval/decide")} == {"choice-deny-once"}
    assert all(params.get("approvalMode") == "denyUnmatched" for params in params_of(muse_fake, "session/start"))


def test_new_command_id_is_an_rfc_9562_uuid7_with_the_pinned_layout(muse_api, muse_wire) -> None:
    # §8.5 / §9.3: 48-bit unix_ts_ms, version 7, 12-bit rand_a, variant 0b10, 62-bit rand_b.
    constants = muse_api.constants
    assert (constants.MUSE_UUID_TIMESTAMP_SHIFT, constants.MUSE_UUID_VERSION, constants.MUSE_UUID_VERSION_SHIFT) == (80, 7, 76)
    assert (constants.MUSE_UUID_RAND_A_SHIFT, constants.MUSE_UUID_VARIANT, constants.MUSE_UUID_VARIANT_SHIFT) == (64, 0b10, 62)
    assert (constants.MUSE_UUID_RANDOM_BITS, constants.MUSE_UUID_RAND_B_BITS) == (74, 62)
    assert constants.MUSE_UUID_TIMESTAMP_MASK == (1 << 48) - 1 and constants.MUSE_UUID_RAND_B_MASK == (1 << 62) - 1
    before_ms = time.time_ns() // 1_000_000
    ids = [muse_wire.new_command_id() for _ in range(256)]
    after_ms = time.time_ns() // 1_000_000
    assert len(set(ids)) == len(ids), "ids are random beyond the timestamp"
    for value in ids:
        assert isinstance(value, str) and UUID7_PATTERN.match(value), value
        number = uuid.UUID(value).int
        assert (number >> 76) & 0xF == 7
        assert (number >> 62) & 0b11 == 0b10
        assert before_ms - CLOCK_SKEW_MS <= number >> 80 <= after_ms + CLOCK_SKEW_MS, "the prefix is time.time_ns() // 1_000_000"


def test_command_id_prefix_does_not_decrease_across_calls_a_millisecond_apart(muse_wire) -> None:
    # §13: the first 12 hex digits do not decrease across calls made at least 1 ms apart; spin, never sleep.
    previous = muse_wire.new_command_id()
    for _ in range(5):
        started = time.monotonic_ns()
        deadline = time.monotonic() + SPIN_LIMIT_SECONDS
        while time.monotonic_ns() - started < SPACING_NS and time.monotonic() < deadline:
            pass
        if time.monotonic_ns() - started < SPACING_NS:
            pytest.skip("the monotonic clock did not advance 1 ms within the spin bound")
        current = muse_wire.new_command_id()
        assert current.replace("-", "")[:12] >= previous.replace("-", "")[:12], (previous, current)
        previous = current


def test_turn_acks_parse_the_authoritative_turn_id(muse_wire) -> None:
    # §8.5 / §9.1 MuseTurnAck: turn_id comes from the result; disposition is required for turn/start and absent for turn/steer.
    started = muse_wire.parse_turn_start_result({"commandId": COMMAND_ID, "turnId": "turn-x", "status": "accepted", "disposition": "queued", "startedNewTurn": False})
    assert (started.command_id, started.turn_id, started.status, started.disposition) == (COMMAND_ID, "turn-x", "accepted", "queued")
    steered = muse_wire.parse_turn_steer_result({"commandId": COMMAND_ID, "status": "accepted", "turnId": "turn-x"})
    assert (steered.turn_id, steered.status, steered.disposition) == ("turn-x", "accepted", None)


def test_inbound_turn_frames_parse_into_their_records(muse_wire) -> None:
    # §9.1 inbound records: item/completed reads its item; turn/completed carries the error fields only when failed.
    item = muse_wire.parse_item_completed({"sessionId": NEW_SESSION, "item": {"itemId": "item-1", "kind": "agentMessage", "revision": 1, "status": "completed", "turnId": TURN_ID, "text": "alpha"}})
    assert (item.session_id, item.item_id, item.kind, item.turn_id, item.text, item.truncated) == (NEW_SESSION, "item-1", "agentMessage", TURN_ID, "alpha", False)
    failed = muse_wire.parse_turn_completed({"sessionId": NEW_SESSION, "turnId": TURN_ID, "terminal": "failed", "error": {"kind": "stepLimit", "message": "limit", "retryable": False}})
    assert (failed.terminal, failed.error_kind, failed.error_message, failed.error_retryable) == ("failed", "stepLimit", "limit", False)
    usage = {"inputTokens": 11, "outputTokens": 7, "reasoningTokens": 2, "cachedTokens": 0}
    completed = muse_wire.parse_turn_completed({"sessionId": NEW_SESSION, "turnId": TURN_ID, "terminal": "completed", "usage": usage})
    assert (completed.error_kind, completed.error_message, completed.error_retryable) == (None, None, None)
    assert (completed.usage.input_tokens, completed.usage.output_tokens, completed.usage.reasoning_tokens) == (11, 7, 2)


def test_inbound_requests_parse_into_their_records(muse_wire) -> None:
    # §9.1: the requirement comes from currentRequirementId; turn_id and tool_name are absent on approval/updated.
    choices = [{"choiceId": "choice-deny-once", "decision": "denied", "label": "Deny", "scope": "once"}]
    updated = muse_wire.parse_approval_request({
        "approvalId": "approval-0", "availableChoices": choices, "change": {"kind": "requirementAdvanced"},
        "currentRequirementId": {"approvalId": "approval-0", "sourceIndex": 2}, "sessionId": NEW_SESSION,
    })
    assert (updated.approval_id, updated.requirement_approval_id, updated.requirement_source_index) == ("approval-0", "approval-0", 2)
    assert (updated.turn_id, updated.tool_name) == (None, None)
    assert [(choice.choice_id, choice.decision, choice.scope) for choice in updated.choices] == [("choice-deny-once", "denied", "once")]
    asked = muse_wire.parse_user_input_request({"sessionId": NEW_SESSION, "turnId": TURN_ID, "userInputId": "input-0", "toolName": "ask_user", "itemId": "i", "questions": []})
    assert (asked.session_id, asked.turn_id, asked.user_input_id, asked.tool_name) == (NEW_SESSION, TURN_ID, "input-0", "ask_user")


PARSE_MISMATCHES = [
    pytest.param("parse_turn_start_result", {"commandId": COMMAND_ID, "status": "accepted", "disposition": "started"}, id="ack-without-turn-id"),
    pytest.param("parse_turn_start_result", {"commandId": COMMAND_ID, "turnId": 7, "status": "accepted", "disposition": "started"}, id="ack-turn-id-type"),
    pytest.param("parse_turn_start_result", {"commandId": COMMAND_ID, "turnId": "turn-x", "status": "accepted"}, id="start-ack-without-disposition"),
    pytest.param("parse_item_completed", {"sessionId": NEW_SESSION, "item": {"kind": "agentMessage", "turnId": TURN_ID}}, id="item-without-id"),
    pytest.param("parse_turn_completed", {"sessionId": NEW_SESSION, "turnId": TURN_ID, "terminal": "failed"}, id="failed-without-error"),
    pytest.param("parse_approval_request", {"approvalId": "a", "availableChoices": [], "currentRequirementId": {"approvalId": "a", "sourceIndex": "0"}, "sessionId": NEW_SESSION}, id="requirement-index-type"),
    pytest.param("parse_user_input_request", {"sessionId": NEW_SESSION, "turnId": TURN_ID, "toolName": "ask_user"}, id="user-input-without-id"),
]


@pytest.mark.parametrize(("parser", "payload"), PARSE_MISMATCHES)
def test_parsers_raise_protocol_mismatch_for_a_missing_or_mistyped_member(parser: str, payload: dict[str, Any], muse_api, muse_wire, check_native_error) -> None:
    # D-13 / EC-98: a missing or wrongly typed relied-on member raises muse.protocol_mismatch; parsers never fall back.
    with pytest.raises(muse_api.NativeHostError) as caught:
        getattr(muse_wire, parser)(payload)
    check_native_error(caught.value, code="muse.protocol_mismatch", token="check_muse_ready")
