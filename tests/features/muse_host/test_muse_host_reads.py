"""FILE: tests/features/muse_host/test_muse_host_reads.py

PURPOSE: What MuseHost's read functions return on the happy path and on their non-error rows: check_muse_ready (EC-105), list_muse_models (an empty catalog, EC-108 pass-through), list_muse_sessions paging, read_muse_session, fork_muse_session, page_muse_session (compact sorted event JSON, the NATIVE_EVENT_MAX_CHARS cut), track_muse_session_usage (D-14, the MUSE_USAGE_MAX_PAGES limit) and the one-resume retry on -32024 (EC-114).
ROLE IN CODEBASE: Proves the output records of spec §9.1 (`vidbyte.lib.dataclasses.muse`) as MuseHost builds them from the fake's MSP results.
ARCHITECTURE NOTE: The fake builds full MSP 1.0.1 result shapes (Session, ModelListResult, ViewPageResult) from small scenario keys, so each test sets only the part it checks.
FUNCTION INVENTORY: usage_event builds one session/tokenUsage view event; the test_* functions check one read each.
COMMON MODIFICATION PATTERNS: A new output field gets an assertion in the test of the read that returns it; keep vendor strings verbatim (D-13).
WHAT NOT TO DO IN THIS FILE: 1. Do not assert a mapping the spec leaves open (forked_from from a ForkProvenance object, MuseModel.display_name, MuseViewEvent.kind); the FEATURE.md lists them. 2. Do not treat an empty model list or a missing usage event as an error; the spec says neither is one.
KNOWN EDGE CASES: The usage search pages backward and stops at the first page with a session/tokenUsage event; with none it reads exactly MUSE_USAGE_MAX_PAGES pages. readiness.version is "1.0.1" from both the --version line and serverInfo, so the test does not depend on which source the host reads.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_reads.py
"""

from __future__ import annotations

import json
from typing import Any

import pytest

KNOWN_SESSION = "2d4c6e8f-1a3b-4c5d-8e7f-9a0b1c2d3e4f"
OTHER_SESSION = "7e6d5c4b-3a29-4817-b6a5-948372615040"
NEW_SESSION = "0192f0c4-5b6a-7c8d-9e0f-1a2b3c4d5e6f"
FORK_SESSION = "0192f0c4-aaaa-7bbb-8ccc-dddddddddddd"
TURN_ID = "turn-0001"
PROMPT = "List the top-level folders."
WAIT_SECONDS = 30.0
NOT_LOADED = {"code": -32024, "message": "session not loaded"}
SMALL_EVENT = {"method": "item/completed", "params": {"item": {"itemId": "item-1", "kind": "agentMessage", "revision": 1, "status": "completed", "turnId": TURN_ID, "text": "alpha"}}}


def usage_event(output_tokens: int, prompt_tokens: int) -> dict[str, Any]:
    cumulative = {"outputTokens": output_tokens, "promptTokens": prompt_tokens, "totalTokens": output_tokens + prompt_tokens}
    return {"method": "session/tokenUsage", "params": {"cumulative": cumulative}}


@pytest.mark.asyncio
async def test_check_muse_ready_reports_the_version_schema_and_launcher(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §6.3.5 check_muse_ready / EC-105: signed_in is None on MSP 1.0.1; the launcher is the resolved argv prefix.
    command = muse_fake.command()
    async with make_muse_host(command=command) as host:
        readiness = await host.check_muse_ready()
    assert readiness.version == "1.0.1"
    assert readiness.schema_version == 1
    assert readiness.signed_in is None
    assert tuple(readiness.launcher) == command
    assert readiness.wsl_distro is None
    methods = muse_fake.received_methods()
    assert methods[:1] == ["initialize"] and "initialized" in methods
    assert [record["role"] for record in muse_fake.starts()].count("version") == 1


@pytest.mark.asyncio
async def test_list_muse_models_returns_the_catalog(muse_api, make_muse_host, fast_stop) -> None:
    # §9.1 MuseModelCatalog: provider, profile, source verbatim and the model ids in order.
    async with make_muse_host() as host:
        catalog = await host.list_muse_models()
    assert catalog.provider_id == "meta"
    assert catalog.profile_id is None
    assert catalog.source == "providerCatalog"
    assert [model.model_id for model in catalog.models] == ["muse-large", "muse-fast"]
    assert isinstance(catalog.models, tuple)


@pytest.mark.asyncio
async def test_empty_model_list_is_not_an_error_and_a_model_passes_through(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §6.3.5 list_muse_models and EC-108 / A-12: an empty bundledCatalog list is returned, and spawn passes the id through.
    async with make_muse_host({"msp": {"model/list": {"models": [], "source": "bundledCatalog"}}}) as host:
        catalog = await host.list_muse_models()
        handle = await host.spawn_muse_session(muse_api.MuseTurnRequest(prompt=PROMPT, model="muse-anything"))
        await host.wait_muse_turn(handle, timeout_seconds=WAIT_SECONDS)
    assert catalog.models == ()
    assert catalog.source == "bundledCatalog"
    assert [frame["params"]["modelId"] for frame in muse_fake.received("session/start")] == ["muse-anything"]


@pytest.mark.asyncio
async def test_list_muse_sessions_pages_with_the_vendor_cursor(muse_api, make_muse_host, fast_stop) -> None:
    # §9.1 MuseSessionPage: sessions in order and next_cursor verbatim; the last page has no cursor.
    async with make_muse_host({"msp": {"session/list": {"pages": [[KNOWN_SESSION, OTHER_SESSION], [NEW_SESSION]]}}}) as host:
        first = await host.list_muse_sessions(limit=2)
        second = await host.list_muse_sessions(cursor=first.next_cursor, limit=2)
    assert [session.session_id for session in first.sessions] == [KNOWN_SESSION, OTHER_SESSION]
    assert first.next_cursor == "page-1"
    assert [session.session_id for session in second.sessions] == [NEW_SESSION]
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_read_muse_session_maps_the_session_fields(muse_api, make_muse_host, fast_stop) -> None:
    # §9.1 MuseSession: status verbatim (an open set), optional fields None when Muse sends null.
    overrides = {"session_overrides": {KNOWN_SESSION: {"status": "notLoaded", "turnCount": 5}}}
    async with make_muse_host(overrides) as host:
        session = await host.read_muse_session(KNOWN_SESSION)
    assert session.session_id == KNOWN_SESSION
    assert session.status == "notLoaded"
    assert session.active_turn_id is None
    assert session.model_id == "muse-large" and session.provider_id == "meta"
    assert session.turn_count == 5
    assert session.created_at == "2026-10-01T09:00:00Z" and session.updated_at == "2026-10-02T09:30:00Z"


@pytest.mark.asyncio
async def test_fork_returns_the_new_session(muse_api, make_muse_host, fast_stop) -> None:
    # §6.3.5 fork_muse_session: the result is the forked session, not the source.
    async with make_muse_host() as host:
        forked = await host.fork_muse_session(KNOWN_SESSION, last_turn_id=TURN_ID)
    assert forked.session_id == FORK_SESSION
    assert forked.status == "idle"


@pytest.mark.asyncio
async def test_page_muse_session_returns_events_as_compact_sorted_json(muse_api, make_muse_host, fast_stop) -> None:
    # §9.1 MuseViewEvent: event_json is the event object as compact sorted JSON; next_cursor is verbatim.
    async with make_muse_host({"msp": {"view/page": {"pages": [[SMALL_EVENT], [SMALL_EVENT]]}}}) as host:
        page = await host.page_muse_session(KNOWN_SESSION, limit=5)
    assert page.session_id == KNOWN_SESSION
    assert page.next_cursor == "page-1"
    assert len(page.events) == 1
    event = page.events[0]
    decoded = json.loads(event.event_json)
    assert decoded["method"] == "item/completed"
    assert decoded["params"]["item"]["text"] == "alpha"
    assert event.event_json == json.dumps(decoded, sort_keys=True, separators=(",", ":"))
    assert event.truncated is False


@pytest.mark.asyncio
async def test_oversized_event_is_cut_and_marked_truncated(muse_api, make_muse_host, fast_stop) -> None:
    # §6.3.5 page_muse_session: params over NATIVE_EVENT_MAX_CHARS are cut and marked; this is not an error.
    limit = muse_api.constants.NATIVE_EVENT_MAX_CHARS
    big = {"method": "item/completed", "params": {"item": {"itemId": "item-big", "kind": "agentMessage", "revision": 1, "status": "completed", "text": "x" * (limit + 500)}}}
    async with make_muse_host({"msp": {"view/page": {"pages": [[big]]}}}) as host:
        page = await host.page_muse_session(KNOWN_SESSION)
    event = page.events[0]
    assert event.truncated is True
    assert len(event.event_json) <= limit


@pytest.mark.asyncio
async def test_track_usage_reads_the_latest_cumulative_by_paging_backward(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # D-14: totals come from the first session/tokenUsage found paging backward; cost is always None (NG-14).
    pages = [[SMALL_EVENT], [usage_event(40, 100)], [usage_event(1, 1)]]
    async with make_muse_host({"msp": {"view/page": {"pages": pages}}}) as host:
        usage = await host.track_muse_session_usage(KNOWN_SESSION)
    assert usage.harness is muse_api.NativeHarness.MUSE
    assert usage.session_id == KNOWN_SESSION
    assert usage.totals is not None
    assert usage.totals.output_tokens == 40
    assert usage.totals.total_tokens == 140
    assert usage.totals.cost_usd is None
    assert usage.truncated is False
    directions = [frame["params"].get("direction") for frame in muse_fake.received("view/page")]
    assert directions == ["backward", "backward"], "the search stops at the first page with a usage event"


@pytest.mark.asyncio
async def test_track_usage_without_an_event_is_truncated_after_the_page_limit(muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # §6.3.5 track_muse_session_usage: no event within MUSE_USAGE_MAX_PAGES pages gives None totals and truncated=True.
    async with make_muse_host({"msp": {"view/page": {"endless": True}}}) as host:
        usage = await host.track_muse_session_usage(KNOWN_SESSION)
    assert usage.totals is None
    assert usage.truncated is True
    assert len(muse_fake.received("view/page")) == muse_api.constants.MUSE_USAGE_MAX_PAGES == 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "operation"),
    [("session/read", "read_muse_session"), ("view/page", "page_muse_session"), ("session/fork", "fork_muse_session")],
)
async def test_session_not_loaded_is_fixed_by_one_resume_and_one_retry(method: str, operation: str, muse_api, muse_fake, make_muse_host, fast_stop) -> None:
    # EC-114 / A-8: one -32024 makes the host call session/resume once, then retry once and succeed.
    async with make_muse_host({"msp": {method: {"errors_first": [NOT_LOADED]}}}) as host:
        await getattr(host, operation)(KNOWN_SESSION)
    methods = [name for name in muse_fake.received_methods() if name in (method, "session/resume")]
    assert methods == [method, "session/resume", method]
    assert [frame["params"]["sessionId"] for frame in muse_fake.received("session/resume")] == [KNOWN_SESSION]
