"""FILE: tests/features/opencode_host/test_opencode_host_acceptance.py

PURPOSE: End-to-end acceptance for OpencodeHost against an attached server: spawn returns while the turn runs (AC-6), the model is checked before anything is spent (AC-7), a timed-out wait leaves the turn running (AC-11), a double interrupt of a finished turn (AC-12), an unresponsive server (AC-3), cancellation (AC-4), concurrent callers (EC-9), and the success shape of every read function.
ROLE IN CODEBASE: Start here for a caller-visible regression in vidbyte.harnesses.native.opencode. Every test drives the real host, OpencodeClient and HttpTransport against FakeOpencodeServer, except AC-3, which uses a real loopback socket that never answers.
ARCHITECTURE NOTE: An attached host (`server_url` plus credentials) starts no process, so these tests isolate HTTP behaviour; the owned `opencode serve` lifecycle is in test_opencode_host_owned_server.py. Held routes (FakeOpencodeServer.hold) give cancellation a deterministic point to land on.
FUNCTION INVENTORY: the test_* functions are one acceptance criterion or one read function each; spawn_request and prompt_request build the request records.
COMMON MODIFICATION PATTERNS: When a §6.2 criterion changes, change its test here and the spec's §6.2 Proof column together.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace the held-route gates with sleeps. 2. Do not loosen the request-order checks in AC-7; they are the guarantee that nothing is spent on a bad model.
KNOWN EDGE CASES: The AC-3 test uses a real socket, so it does not install the MockTransport patch; its bound allows SLACK_SECONDS on top of request_timeout_seconds because an attached host starts no process. Session listings come back from the fake oldest first on purpose, so the host's own sort is what the test sees.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.2, §6.3.4, §8.5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_acceptance.py
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

KNOWN_SESSION = "ses_known0001"
OTHER_SESSION = "ses_other0002"
KNOWN_USER_MESSAGE = "msg_00000001"
KNOWN_REPLY_MESSAGE = "msg_00000002"
PROMPT = "List the top-level folders."
MODEL = "acme/coder-1"
SHORT_WAIT_SECONDS = 0.3
TURN_WAIT_SECONDS = 30.0
GATE_SECONDS = 10.0
SLACK_SECONDS = 2.0


def prompt_request(api: Any, **fields: Any) -> Any:
    return api.OpencodePromptRequest(prompt=PROMPT, **fields)


def spawn_request(api: Any, **fields: Any) -> Any:
    return api.OpencodeSpawnRequest(turn=prompt_request(api, **fields))


@pytest.mark.asyncio
async def test_spawn_returns_a_handle_while_the_turn_is_still_running(opencode_api, fake_opencode, make_opencode_host) -> None:
    # AC-6 / INV-11: the handle comes back once prompt_async answered 204; wait returns once the turn finishes.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await asyncio.wait_for(host.spawn_opencode_session(spawn_request(opencode_api, model=MODEL)), timeout=GATE_SECONDS)
        assert handle.harness is opencode_api.NativeHarness.OPENCODE
        assert handle.session_id in fake_opencode.sessions and handle.session_id not in (KNOWN_SESSION, OTHER_SESSION)
        assert len(handle.turn_id) == 32 and handle.turn_id == handle.turn_id.lower()
        assert [item.params["sid"] for item in fake_opencode.seen("prompt_async")] == [handle.session_id]
        assert fake_opencode.turns[handle.session_id].done is False, "the turn must still be running when spawn returns"
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.text == "alpha-beta"
    assert result.stop_reason == "stop"
    assert result.handle == handle
    assert result.interrupt_source is None


@pytest.mark.asyncio
async def test_spawn_sends_the_title_rules_and_prompt_in_the_vendor_shape(opencode_api, fake_opencode, make_opencode_host) -> None:
    # D-11 / §8.5: the session is created with the request's rules; prompt_async carries one text part.
    rule = opencode_api.OpencodePermissionRule(permission="bash", pattern="*", action=opencode_api.OpencodePermissionAction.ASK)
    request = opencode_api.OpencodeSpawnRequest(turn=prompt_request(opencode_api, model=MODEL), title="Folder survey", permission_rules=(rule,))
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(request)
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    created = fake_opencode.seen("session_create")[0].body
    assert created["title"] == "Folder survey"
    assert created["permission"] == [{"permission": "bash", "pattern": "*", "action": "ask"}]
    assert fake_opencode.seen("prompt_async")[0].body["parts"] == [{"type": "text", "text": PROMPT}]
    routes = fake_opencode.routes()
    assert routes.index("config_providers") < routes.index("session_create") < routes.index("prompt_async"), "INV-5: the model is checked before anything is created"


@pytest.mark.asyncio
async def test_continue_sends_the_model_agent_and_system_with_the_prompt(opencode_api, fake_opencode, make_opencode_host) -> None:
    # continue_opencode_session: prompt_async is the only request that can carry the turn's model, agent and system text.
    request = prompt_request(opencode_api, model=MODEL, agent="build", system="Answer briefly.")
    async with make_opencode_host() as host:
        handle = await host.continue_opencode_session(KNOWN_SESSION, request)
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    sent = fake_opencode.seen("prompt_async")[0].body
    assert sent["parts"] == [{"type": "text", "text": PROMPT}]
    assert sent["model"] == {"providerID": "acme", "modelID": "coder-1"}
    assert sent["agent"] == "build"
    assert sent["system"] == "Answer briefly."
    routes = fake_opencode.routes()
    assert routes.index("session_get") < routes.index("prompt_async") and routes.index("config_providers") < routes.index("prompt_async")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["spawn_opencode_session", "continue_opencode_session"])
async def test_unknown_model_is_refused_before_any_turn_starts(operation: str, opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # AC-7: model_unknown with the available ids; no POST /session and no prompt_async.
    async with make_opencode_host() as host:
        with pytest.raises(opencode_api.NativeHostError) as caught:
            if operation == "spawn_opencode_session":
                await host.spawn_opencode_session(spawn_request(opencode_api, model="acme/coder-ultra"))
            else:
                await host.continue_opencode_session(KNOWN_SESSION, prompt_request(opencode_api, model="ghost-ai/model-x"))
    check_native_error(caught.value, code="opencode.model_unknown", token="list_opencode_models", operation=operation)
    assert "coder-1" in caught.value.context["available_models"]
    assert fake_opencode.seen("session_create") == [] and fake_opencode.seen("prompt_async") == []


@pytest.mark.asyncio
async def test_wait_times_out_then_returns_the_result(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # AC-11 / INV-12: a timed-out wait does not touch the turn, and a later wait gets the outcome.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(spawn_request(opencode_api))
        with pytest.raises(opencode_api.NativeHostError) as first:
            await host.wait_opencode_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(first.value, code="opencode.turn_timed_out", token="wait_opencode_turn", operation="wait_opencode_turn")
        assert fake_opencode.seen("abort") == [], "a timed-out wait never aborts the turn"
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED
    assert result.text == "alpha-beta"


@pytest.mark.asyncio
async def test_interrupting_a_finished_turn_twice_reports_not_running(opencode_api, fake_opencode, make_opencode_host) -> None:
    # AC-12 / INV-13: both calls return was_running=False, raise nothing and send no abort.
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(spawn_request(opencode_api))
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
        first = await host.interrupt_opencode_turn(handle)
        second = await host.interrupt_opencode_turn(handle)
    assert first.was_running is False and second.was_running is False
    assert first.handle == handle and second.handle == handle
    assert fake_opencode.seen("abort") == []


@pytest.mark.asyncio
async def test_interrupting_a_running_turn_aborts_it(opencode_api, fake_opencode, make_opencode_host) -> None:
    # interrupt_opencode_turn: GET /session/{id} first (EC-90), then POST …/abort; the turn ends INTERRUPTED by the caller.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(spawn_request(opencode_api))
        interrupted = await host.interrupt_opencode_turn(handle)
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert interrupted.was_running is True
    assert [item.params["sid"] for item in fake_opencode.seen("abort")] == [handle.session_id]
    assert result.status is opencode_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is opencode_api.InterruptSource.CALLER


@pytest.mark.asyncio
async def test_unresponsive_server_raises_server_unreachable_within_the_timeout(opencode_api, fast_timings, attached_secret, silent_loopback, tmp_path: Path, check_native_error) -> None:
    # AC-3: a server that accepts the connection and never answers; an attached host starts no process.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = silent_loopback(answer_health=True)
    settings = opencode_api.OpencodeHostSettings(workspace=workspace, server_url=server.url, server_username="opencode", server_password=attached_secret, request_timeout_seconds=0.5)
    async with opencode_api.OpencodeHost(settings) as host:
        started = time.monotonic()
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_sessions()
        elapsed = time.monotonic() - started
    check_native_error(caught.value, code="opencode.server_unreachable", token="request_timeout_seconds", operation="list_opencode_sessions")
    assert elapsed < 0.5 + SLACK_SECONDS


@pytest.mark.asyncio
async def test_unresponsive_server_fails_aenter_within_the_timeout(opencode_api, fast_timings, attached_secret, silent_loopback, tmp_path: Path, check_native_error) -> None:
    # AC-3 at __aenter__: the health check itself never gets an answer.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = silent_loopback(answer_health=False)
    settings = opencode_api.OpencodeHostSettings(workspace=workspace, server_url=server.url, server_username="opencode", server_password=attached_secret, request_timeout_seconds=0.5)
    started = time.monotonic()
    with pytest.raises(opencode_api.NativeHostError) as caught:
        async with opencode_api.OpencodeHost(settings):
            pass
    elapsed = time.monotonic() - started
    check_native_error(caught.value, code="opencode.server_unreachable", token="request_timeout_seconds")
    assert elapsed < 0.5 + SLACK_SECONDS


CANCEL_POINTS = {
    "spawn_opencode_session": "session_create",
    "continue_opencode_session": "session_get",
    "check_opencode_ready": "provider",
    "list_opencode_sessions": "session_list",
    "get_opencode_session_messages": "messages",
}


def start_call(host: Any, api: Any, operation: str) -> asyncio.Task[Any]:
    calls = {
        "spawn_opencode_session": lambda: host.spawn_opencode_session(spawn_request(api)),
        "continue_opencode_session": lambda: host.continue_opencode_session(KNOWN_SESSION, prompt_request(api)),
        "check_opencode_ready": lambda: host.check_opencode_ready(),
        "list_opencode_sessions": lambda: host.list_opencode_sessions(),
        "get_opencode_session_messages": lambda: host.get_opencode_session_messages(KNOWN_SESSION),
    }
    return asyncio.create_task(calls[operation]())


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(CANCEL_POINTS))
async def test_cancelling_a_call_propagates_and_releases_its_reservation(operation: str, opencode_api, fake_opencode, make_opencode_host) -> None:
    # AC-4 / EC-4 / INV-2: CancelledError propagates; a cancelled spawn or continue leaves no live-turn slot or session reserved.
    async with make_opencode_host(max_live_turns=1) as host:
        entered, release = fake_opencode.hold(CANCEL_POINTS[operation])
        task = start_call(host, opencode_api, operation)
        await asyncio.wait_for(entered.wait(), timeout=GATE_SECONDS)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        del fake_opencode.holds[CANCEL_POINTS[operation]]
        assert fake_opencode.seen("prompt_async") == [], "a cancelled call never reaches prompt_async"
        handle = await host.continue_opencode_session(KNOWN_SESSION, prompt_request(opencode_api))
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancelling_a_wait_leaves_the_turn_running(opencode_api, fake_opencode, make_opencode_host, wait_until) -> None:
    # AC-4 for wait_* / INV-12: the turn keeps running and a later wait returns its result.
    fake_opencode.plan("hold")
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(spawn_request(opencode_api))
        waiter = asyncio.create_task(host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS))
        assert await wait_until(lambda: len(fake_opencode.seen("session_status")) >= 2, GATE_SECONDS)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert fake_opencode.seen("abort") == []
        fake_opencode.release_turn()
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_two_concurrent_continues_on_one_session_cannot_both_pass(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # EC-9 / INV-14: the session is reserved before the first await, so the second caller gets session_busy.
    async with make_opencode_host() as host:
        entered, release = fake_opencode.hold("session_get")
        first = asyncio.create_task(host.continue_opencode_session(KNOWN_SESSION, prompt_request(opencode_api)))
        await asyncio.wait_for(entered.wait(), timeout=GATE_SECONDS)
        with pytest.raises(opencode_api.NativeHostError) as second:
            await asyncio.wait_for(host.continue_opencode_session(KNOWN_SESSION, prompt_request(opencode_api)), timeout=GATE_SECONDS)
        release.set()
        handle = await first
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    check_native_error(second.value, code="opencode.session_busy", token="interrupt_opencode_turn", operation="continue_opencode_session")
    assert len(fake_opencode.seen("prompt_async")) == 1


@pytest.mark.asyncio
async def test_two_concurrent_spawns_at_the_cap_cannot_both_pass(opencode_api, fake_opencode, make_opencode_host, check_native_error) -> None:
    # EC-9 / EC-67: the live-turn slot is reserved synchronously.
    async with make_opencode_host(max_live_turns=1) as host:
        entered, release = fake_opencode.hold("session_create")
        first = asyncio.create_task(host.spawn_opencode_session(spawn_request(opencode_api)))
        await asyncio.wait_for(entered.wait(), timeout=GATE_SECONDS)
        with pytest.raises(opencode_api.NativeHostError) as second:
            await asyncio.wait_for(host.spawn_opencode_session(spawn_request(opencode_api)), timeout=GATE_SECONDS)
        release.set()
        handle = await first
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    check_native_error(second.value, code="opencode.session_busy", token="interrupt_opencode_turn", operation="spawn_opencode_session")
    assert second.value.context.get("live_turns") == "1"


@pytest.mark.asyncio
async def test_a_failed_spawn_releases_its_live_turn_slot(opencode_api, fake_opencode, make_opencode_host) -> None:
    # EC-9: a reservation is released when the call fails.
    async with make_opencode_host(max_live_turns=1) as host:
        fake_opencode.fail("session_create", "500", times=1)
        with pytest.raises(opencode_api.NativeHostError):
            await host.spawn_opencode_session(spawn_request(opencode_api))
        handle = await host.spawn_opencode_session(spawn_request(opencode_api))
        result = await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert result.status is opencode_api.NativeTurnStatus.COMPLETED


@pytest.mark.asyncio
async def test_check_ready_reports_version_url_and_providers(opencode_api, fake_opencode, make_opencode_host, attached_secret) -> None:
    # check_opencode_ready → OpencodeReadiness; server_url never carries credentials.
    async with make_opencode_host() as host:
        readiness = await host.check_opencode_ready()
    assert readiness.version == "1.18.31"
    assert readiness.server_url.rstrip("/") == "http://127.0.0.1:4096"
    assert attached_secret not in readiness.server_url and "@" not in readiness.server_url
    assert readiness.connected_providers == ("acme",)
    assert dict(readiness.default_models) == {"acme": "coder-1"}


@pytest.mark.asyncio
async def test_models_providers_and_auth_methods_are_mapped(opencode_api, fake_opencode, make_opencode_host) -> None:
    # list_opencode_models (GET /config/providers), list_opencode_providers (GET /provider), get_opencode_provider_auth (GET /provider/auth).
    async with make_opencode_host() as host:
        models = await host.list_opencode_models()
        acme_models = await host.list_opencode_models("acme")
        providers = await host.list_opencode_providers()
        auth = await host.get_opencode_provider_auth()
    assert {(model.provider_id, model.model_id) for model in models} == {("acme", "coder-1"), ("acme", "coder-mini")}
    assert {model.model_id for model in acme_models} == {"coder-1", "coder-mini"}
    coder = next(model for model in models if model.model_id == "coder-1")
    assert (coder.name, coder.status, coder.context_limit, coder.output_limit) == ("Coder One", "active", 200000, 32000)
    by_id = {provider.provider_id: provider for provider in providers}
    assert set(by_id) == {"acme", "zai-coding-plan"}
    assert by_id["acme"].connected is True and by_id["zai-coding-plan"].connected is False
    assert by_id["acme"].env_vars == ("ACME_API_KEY",) and by_id["acme"].source == "env"
    assert set(by_id["acme"].model_ids) == {"coder-1", "coder-mini"} and by_id["acme"].default_model_id == "coder-1"
    methods = {entry.provider_id: [(method.method_type, method.label) for method in entry.methods] for entry in auth}
    assert methods == {"acme": [("api", "API key")], "zai-coding-plan": [("oauth", "Z.AI login"), ("api", "Manual key")]}


@pytest.mark.asyncio
async def test_list_sessions_sends_the_limit_and_sorts_newest_first(opencode_api, fake_opencode, make_opencode_host) -> None:
    # list_opencode_sessions: `limit` goes in the query; the host sorts by time.updated, newest first.
    fake_opencode.sessions[KNOWN_SESSION]["time"]["updated"] = 1
    async with make_opencode_host() as host:
        sessions = await host.list_opencode_sessions(limit=5)
    assert fake_opencode.seen("session_list")[-1].query["limit"] == "5"
    assert [session.session_id for session in sessions] == [OTHER_SESSION, KNOWN_SESSION]
    assert [session.updated_ms for session in sessions] == sorted((session.updated_ms for session in sessions), reverse=True)


@pytest.mark.asyncio
async def test_get_session_and_its_usage_totals(opencode_api, fake_opencode, make_opencode_host) -> None:
    # get_opencode_session → OpencodeSession; track_opencode_session_usage totals come from the Session object (D-14).
    async with make_opencode_host() as host:
        session = await host.get_opencode_session(KNOWN_SESSION)
        usage = await host.track_opencode_session_usage(KNOWN_SESSION)
    assert (session.session_id, session.title, session.parent_id) == (KNOWN_SESSION, "Refactor the parser", None)
    assert Path(session.directory) == fake_opencode.workspace
    assert usage.harness is opencode_api.NativeHarness.OPENCODE and usage.session_id == KNOWN_SESSION
    assert usage.totals.input_tokens == 900 and usage.totals.output_tokens == 300
    assert usage.totals.reasoning_tokens == 40 and usage.totals.cache_read_tokens == 70 and usage.totals.cache_write_tokens == 8
    assert usage.totals.cost_usd == Decimal("0.5")
    assert [entry.message_id for entry in usage.per_message] == [KNOWN_REPLY_MESSAGE]
    assert usage.truncated is False


@pytest.mark.asyncio
async def test_usage_tracking_cuts_the_message_list_past_the_limit(opencode_api, fake_opencode, make_opencode_host) -> None:
    # track_opencode_session_usage: more than OPENCODE_TURN_MESSAGE_LIMIT messages sets truncated=True; totals still come from the session.
    for _ in range(1001):
        fake_opencode.add_reply(OTHER_SESSION, None, {"text": "step"})
    fake_opencode.sessions[OTHER_SESSION].update({"cost": 2.25, "tokens": {"input": 5, "output": 6, "reasoning": 0, "cache": {"read": 0, "write": 0}}})
    async with make_opencode_host() as host:
        usage = await host.track_opencode_session_usage(OTHER_SESSION)
    assert usage.truncated is True
    assert len(usage.per_message) <= 1000
    assert usage.totals.cost_usd == Decimal("2.25")


@pytest.mark.asyncio
async def test_message_page_and_single_message(opencode_api, fake_opencode, make_opencode_host) -> None:
    # get_opencode_session_messages pages backwards with `before`; next_before is the oldest id when the page is full.
    async with make_opencode_host() as host:
        full = await host.get_opencode_session_messages(KNOWN_SESSION, limit=1)
        older = await host.get_opencode_session_messages(KNOWN_SESSION, limit=1, before=KNOWN_REPLY_MESSAGE)
        everything = await host.get_opencode_session_messages(KNOWN_SESSION)
        reply = await host.get_opencode_message(KNOWN_SESSION, KNOWN_REPLY_MESSAGE)
    assert [message.message_id for message in full.messages] == [KNOWN_REPLY_MESSAGE] and full.next_before == KNOWN_REPLY_MESSAGE
    assert fake_opencode.seen("messages")[1].query["before"] == KNOWN_REPLY_MESSAGE
    assert [message.message_id for message in older.messages] == [KNOWN_USER_MESSAGE]
    assert [message.role for message in everything.messages] == ["user", "assistant"] and everything.next_before is None
    assert (reply.role, reply.text, reply.parent_id, reply.provider_id, reply.model_id, reply.finish) == ("assistant", "old answer", KNOWN_USER_MESSAGE, "acme", "coder-1", "stop")
    assert reply.completed_ms is not None and reply.error is None and reply.text_truncated is False


@pytest.mark.asyncio
async def test_diff_maps_fields_and_cuts_long_patches(opencode_api, fake_opencode, make_opencode_host) -> None:
    # get_opencode_session_diff: vendor FileDiff → OpencodeFileDiff; a patch over OPENCODE_PATCH_MAX_CHARS is cut.
    fake_opencode.diffs[KNOWN_SESSION] = [
        {"file": "README.md", "patch": "@@ -1 +1 @@\n-a\n+b\n", "additions": 1, "deletions": 1, "status": "modified"},
        {"file": "big.txt", "patch": "+" + "x" * 30000, "additions": 1, "deletions": 0, "status": "added"},
    ]
    async with make_opencode_host() as host:
        diffs = await host.get_opencode_session_diff(KNOWN_SESSION, KNOWN_REPLY_MESSAGE)
    assert fake_opencode.seen("diff")[0].query["messageID"] == KNOWN_REPLY_MESSAGE
    small, big = diffs
    assert (small.path, small.status, small.additions, small.deletions, small.patch_truncated) == ("README.md", "modified", 1, 1, False)
    assert big.patch_truncated is True and len(big.patch) <= 20000 and big.patch.startswith("+xxx")


@pytest.mark.asyncio
async def test_fork_revert_and_unrevert(opencode_api, fake_opencode, make_opencode_host) -> None:
    # fork_opencode_session, revert_opencode_session (EC-79: the vendor's revert block) and unrevert_opencode_session.
    async with make_opencode_host() as host:
        forked = await host.fork_opencode_session(KNOWN_SESSION, KNOWN_REPLY_MESSAGE)
        reverted = await host.revert_opencode_session(KNOWN_SESSION, KNOWN_REPLY_MESSAGE, "prt_00000004")
        restored = await host.unrevert_opencode_session(KNOWN_SESSION)
    assert forked.session_id in fake_opencode.sessions and forked.session_id != KNOWN_SESSION
    assert fake_opencode.seen("fork")[0].body == {"messageID": KNOWN_REPLY_MESSAGE}
    assert fake_opencode.seen("revert")[0].body == {"messageID": KNOWN_REPLY_MESSAGE, "partID": "prt_00000004"}
    assert (reverted.revert_message_id, reverted.revert_part_id) == (KNOWN_REPLY_MESSAGE, "prt_00000004")
    assert (restored.revert_message_id, restored.revert_part_id) == (None, None)


@pytest.mark.asyncio
async def test_add_mcp_server_returns_the_connected_status(opencode_api, fake_opencode, make_opencode_host) -> None:
    # add_opencode_mcp_server: POST /mcp with the config in the vendor shape.
    config = opencode_api.OpencodeMcpServerConfig(name="files", kind=opencode_api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"), timeout_ms=5000)
    async with make_opencode_host() as host:
        status = await host.add_opencode_mcp_server(config)
    assert (status.name, status.status) == ("files", "connected")
    body = fake_opencode.seen("mcp_add")[0].body
    assert body["name"] == "files"
    assert body["config"]["type"] == "local" and body["config"]["command"] == ["node", "files-server.js"] and body["config"]["timeout"] == 5000


@pytest.mark.asyncio
async def test_every_request_names_the_workspace_and_carries_basic_auth(opencode_api, fake_opencode, make_opencode_host, attached_secret) -> None:
    # §8.5 / §10: every call carries directory=<workspace>; basic auth goes in a header with the attached credentials.
    async with make_opencode_host() as host:
        await host.check_opencode_ready()
        await host.list_opencode_sessions()
        handle = await host.continue_opencode_session(KNOWN_SESSION, prompt_request(opencode_api))
        await host.wait_opencode_turn(handle, timeout_seconds=TURN_WAIT_SECONDS)
    assert fake_opencode.requests, "the host made requests"
    for item in fake_opencode.requests:
        assert Path(item.query["directory"]) == fake_opencode.workspace, f"{item.route} lacks directory"
        assert item.auth == ("opencode", attached_secret), f"{item.route} lacks basic auth"
        assert attached_secret not in item.path and attached_secret not in str(item.query)
    assert "unknown" not in fake_opencode.routes()
