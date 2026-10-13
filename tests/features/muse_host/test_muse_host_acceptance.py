"""FILE: tests/features/muse_host/test_muse_host_acceptance.py

PURPOSE: Caller-visible acceptance for MuseHost: a spawn that returns while the turn runs (AC-6), a wait that times out and then succeeds (AC-11), a double interrupt of a finished turn (AC-12), and the plain spawn and continue paths that give the reply text from agentMessage items.
ROLE IN CODEBASE: Start here for a caller-visible regression in vidbyte.harnesses.native.muse. Every test drives the real host over real pipes to fake_muse_peer.py through MuseHostSettings.muse_command, the spec §13 seam.
ARCHITECTURE NOTE: A held turn sends its agentMessage items, then waits for the release file before turn/completed, so a test can prove the handle came back while the turn was RUNNING. What the fake sent and received comes from its JSONL logs.
FUNCTION INVENTORY: sent_methods lists what the fake wrote; the test_* functions are one acceptance criterion or one happy path each.
COMMON MODIFICATION PATTERNS: A new caller-visible guarantee for Muse gets its own test here; error rows go in test_muse_host_errors.py instead.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace the held-turn proof with a timing guess; AC-6 is proven by the fake not having sent turn/completed. 2. Do not reach the real muse; every host here uses the fake.
KNOWN EDGE CASES: The reply text joins agentMessage items with a blank line (spec §8.5), so the two default items "alpha" and "beta" read "alpha\n\nbeta". A finished turn's peer is already closed, so interrupting it must send nothing.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.2, §8.5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_acceptance.py
"""

from __future__ import annotations

import re
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
NEW_SESSION = "0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"
PROMPT = "List the top-level folders."
REPLY_TEXT = "alpha\n\nbeta"
HELD_TURN = {"turn": {"mode": "hold"}}
SHORT_WAIT_SECONDS = 0.3
WAIT_SECONDS = 30.0
TURN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def sent_methods(muse_fake: Any) -> list[str]:
    return [record["frame"].get("method") for record in muse_fake.records("sent")]


@pytest.mark.asyncio
async def test_spawn_returns_a_handle_while_the_turn_is_still_running(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # AC-6 / INV-11: the handle comes back once turn/start is accepted; wait returns once the peer finishes.
    async with make_muse_host(HELD_TURN) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        assert handle.harness is muse_api.NativeHarness.MUSE
        assert handle.session_id == NEW_SESSION, "the session id comes from the session/start result"
        assert TURN_ID_PATTERN.match(handle.turn_id), "the handle's turn id is the host's own uuid4().hex"
        assert muse_fake.received("turn/start"), "the prompt reached the fake"
        assert "turn/completed" not in sent_methods(muse_fake), "the turn must still be running when spawn returns"
        muse_fake.release()
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.handle == handle
    assert result.text == REPLY_TEXT
    assert result.interrupt_source is None


@pytest.mark.asyncio
async def test_wait_times_out_without_touching_the_turn_and_a_later_wait_returns(muse_api, muse_fake, make_muse_host, fast_stop, check_native_error) -> None:
    # AC-11 / INV-12 / EC-116: the first wait raises at its deadline, sends nothing, and the second returns the result.
    async with make_muse_host(HELD_TURN) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        with pytest.raises(muse_api.NativeHostError) as first:
            await host.wait_muse_turn(handle, timeout_seconds=SHORT_WAIT_SECONDS)
        check_native_error(first.value, code="muse.turn_timed_out", token="wait_muse_turn", operation="wait_muse_turn")
        assert muse_fake.received("turn/interrupt") == [], "a timed-out wait never interrupts the turn"
        muse_fake.release()
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.text == REPLY_TEXT


@pytest.mark.asyncio
async def test_interrupting_a_finished_turn_twice_reports_not_running(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # AC-12 / INV-13: both calls return was_running=False, raise nothing and send nothing.
    async with make_muse_host() as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
        first = await host.interrupt_muse_turn(handle)
        second = await host.interrupt_muse_turn(handle)
    assert first.was_running is False and second.was_running is False
    assert first.handle == handle and second.handle == handle
    assert muse_fake.received("turn/interrupt") == []


@pytest.mark.asyncio
async def test_spawn_starts_a_session_and_returns_the_agent_message_text(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # FR-3: session/start then turn/start; the reply is the turn's agentMessage items joined by a blank line.
    async with make_muse_host() as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.text == REPLY_TEXT
    assert result.text_truncated is False
    assert result.decisions == ()
    methods = muse_fake.received_methods()
    assert methods.index("session/start") < methods.index("turn/start")
    assert "session/resume" not in methods


@pytest.mark.asyncio
async def test_continue_resumes_the_named_session_and_runs_a_turn_on_it(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # FR-3: continue resumes the session first, then starts the turn on that session id.
    async with make_muse_host() as host:
        handle = await host.continue_muse_session(KNOWN_SESSION, muse_api.MuseTurnRequest(prompt=PROMPT))
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert handle.session_id == KNOWN_SESSION
    assert result.status is muse_api.NativeTurnStatus.COMPLETED
    assert result.text == REPLY_TEXT
    resumes = muse_fake.received("session/resume")
    starts = muse_fake.received("turn/start")
    assert [frame["params"]["sessionId"] for frame in resumes] == [KNOWN_SESSION]
    assert [frame["params"]["sessionId"] for frame in starts] == [KNOWN_SESSION]
    assert muse_fake.received("session/start") == []


@pytest.mark.asyncio
async def test_interrupting_a_running_turn_ends_it_interrupted_by_the_caller(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # INV-13: was_running=True for a live turn, and the result records the caller as the source.
    async with make_muse_host(HELD_TURN) as host:
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT))
        interrupted = await host.interrupt_muse_turn(handle)
        result = await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
        again = await host.interrupt_muse_turn(handle)
    assert interrupted.was_running is True
    assert result.status is muse_api.NativeTurnStatus.INTERRUPTED
    assert result.interrupt_source is muse_api.InterruptSource.CALLER
    assert again.was_running is False
    assert len(muse_fake.received("turn/interrupt")) == 1
