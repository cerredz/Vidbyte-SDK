"""FILE: tests/features/grok_host/test_grok_host_session_id_case.py

PURPOSE: INV-14 for Grok session ids: a UUID and its upper-cased form name the same session, so the busy check (EC-29) and the fork id checks (EC-32, EC-35, EC-36, EC-39) all compare ignoring letter case, while a genuinely different returned id is still refused (EC-39 lock).
ROLE IN CODEBASE: Proves the r8 case-insensitivity rule (review R-8 / S4-6) for vidbyte.harnesses.native.grok.GrokHost, driven through the real host over real pipes to fake_grok_peer.py. The lower-case equivalents of these cases live in test_grok_host_errors.py and test_grok_host_reads.py.
ARCHITECTURE NOTE: Every session id here is a valid UUID that require_uuid accepts in either case (pinned at test_grok_host_records.py:66). The fake's session/list carries KNOWN and OTHER in lower case, and oneshot_stdout returns the scenario's session_id verbatim, so a case-sensitive host and a case-insensitive host take different branches on the same inputs.
FUNCTION INVENTORY: the test_* functions are one INV-14 rule each; the last two are EC-39 locks (the success and the target-mismatch guard) that already hold under the current code.
COMMON MODIFICATION PATTERNS: A new case-insensitivity rule gets one test here and keeps its lower-case twin in the errors or reads module.
WHAT NOT TO DO IN THIS FILE: 1. Do not weaken the EC-39 locks; they guard the already-correct case-insensitive accept and the still-required target-mismatch refusal. 2. Do not reach the real grok; every host runs the fake through grok_command.
KNOWN EDGE CASES: A held turn on KNOWN must be released or interrupted; __aexit__ interrupts it. The EC-39 success case needs new_session_id absent from the listing, so NEW_SESSION is used, never KNOWN or OTHER.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.1 INV-14, §6.3.3 EC-32/EC-35/EC-36/EC-39
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_session_id_case.py
"""

from __future__ import annotations

import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
OTHER_SESSION = "0c9b8a7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"
NEW_SESSION = "11111111-2222-4333-8444-555555555555"
THIRD_SESSION = "22222222-3333-4444-8555-666666666666"
PROMPT = "Summarise the README."
WAIT_SECONDS = 30.0


@pytest.mark.asyncio
async def test_continue_on_the_upper_cased_id_of_a_live_session_is_busy(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # INV-14 / EC-29: the upper-cased id names the same live session, so the second continue is refused as busy.
    async with make_grok_host({"acp": {"session_prompt": {"mode": "hold"}}}) as host:
        live = await host.continue_grok_session(KNOWN_SESSION, grok_api.GrokTurnRequest(prompt=PROMPT))
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.continue_grok_session(KNOWN_SESSION.upper(), grok_api.GrokTurnRequest(prompt=PROMPT))
        check_native_error(caught.value, code="grok.session_busy", token="interrupt_grok_turn", operation="continue_grok_session")
        peers = [record for record in grok_fake.records("start") if record["role"] == "peer"]
        assert len(peers) == 1, "the upper-cased id must not open a second peer for the same session"
        grok_fake.release()
        await host.wait_grok_turn(live, timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_fork_on_the_upper_cased_source_id_is_accepted(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-35 / INV-14: the source id is matched against session/list ignoring case, so KNOWN.upper() is found and the fork runs.
    async with make_grok_host() as host:
        result = await host.fork_grok_session(KNOWN_SESSION.upper(), grok_api.GrokOneShotRequest(prompt=PROMPT))
    assert len(grok_fake.launches("oneshot")) == 1, "the source was found, so the fork CLI ran"
    assert result.session_id.lower() not in ("", KNOWN_SESSION), "a fork names a new session, not its source"


@pytest.mark.asyncio
async def test_fork_new_session_id_that_collides_case_insensitively_is_refused(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-36 / INV-14: new_session_id equals an existing id ignoring case, so it is refused before the money-spending run.
    async with make_grok_host() as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.fork_grok_session(KNOWN_SESSION, grok_api.GrokOneShotRequest(prompt=PROMPT), new_session_id=OTHER_SESSION.upper())
    check_native_error(caught.value, code="configuration.invalid_argument", token="new_session_id", operation="fork_grok_session")
    assert grok_fake.launches("oneshot") == [], "EC-36 is caught before the fork CLI runs"


@pytest.mark.asyncio
async def test_fork_accepts_a_returned_id_equal_to_the_request_ignoring_case(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-39 / INV-14 lock: the caller passes NEW.upper() and Grok echoes it in lower case; equal ignoring case is a success.
    # This holds under the current code already (the EC-39 target comparison is case-insensitive); it locks that against regression.
    async with make_grok_host({"oneshot": {"session_id": NEW_SESSION}}) as host:
        result = await host.fork_grok_session(KNOWN_SESSION, grok_api.GrokOneShotRequest(prompt=PROMPT), new_session_id=NEW_SESSION.upper())
    assert result.session_id.lower() == NEW_SESSION
    assert len(grok_fake.launches("oneshot")) == 1


@pytest.mark.asyncio
async def test_fork_refuses_a_returned_id_that_differs_from_the_request(grok_api, grok_fake, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-39 lock: a returned sessionId that differs from the requested new_session_id (even ignoring case) is a protocol mismatch.
    async with make_grok_host({"oneshot": {"session_id": THIRD_SESSION}}) as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.fork_grok_session(KNOWN_SESSION, grok_api.GrokOneShotRequest(prompt=PROMPT), new_session_id=NEW_SESSION)
    check_native_error(caught.value, code="grok.protocol_mismatch", token="check_grok_ready", operation="fork_grok_session")
