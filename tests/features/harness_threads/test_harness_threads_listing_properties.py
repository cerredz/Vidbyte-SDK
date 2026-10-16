"""FILE: tests/features/harness_threads/test_harness_threads_listing_properties.py

PURPOSE: Seeded, deterministic property checks of the listing and lineage contracts over generated Grok stores: for every generated store, window and limit, `list_grok_threads` equals an independent INV-7 oracle (window, newest first, ties by id descending, one entry per id keeping the newer, limit), with timestamps written in mixed offsets (EC-15); the wrappers equal the base list (INV-7 wrapper equivalence); `search_grok_threads` equals the oracle's literal case-insensitive filter (D-3); and every lineage is root first, linked, and ends at the requested thread (INV-10).
ROLE IN CODEBASE: Start here when a list or lineage is right for hand-written stores but wrong for some mix of ties, duplicates, offsets and limits.
ARCHITECTURE NOTE: Hypothesis is not installed in this repository, so each case is drawn from random.Random(seed) over a fixed seed list; a failure names its seed, and rerunning that seed rebuilds the same store. Grok listing reads files only, so many stores cost no child process. Every generated time sits a whole number of hours before the test's own clock reading, at least one hour away from any window edge, because the helper reads the clock itself.
FUNCTION INVENTORY: draw_store builds one random store and returns its oracle rows; oracle applies INV-7 to the rows; render writes a time in a random offset; the test_* functions are one property each.
COMMON MODIFICATION PATTERNS: To widen the search, add seeds; keep offsets and windows on the whole-hour grid with one-hour margins.
WHAT NOT TO DO IN THIS FILE: Do not compute the oracle with SDK code; it must stay independent.
KNOWN EDGE CASES: Duplicated ids sit in a second group folder of the same private home, as two encodings of one path would.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-7, INV-10, §6.3 EC-15 to EC-17, EC-25, D-3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_listing_properties.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

SEEDS = list(range(1, 21))
OFFSET_HOURS = (1, 2, 5, 30, 50, 100)
WINDOW_HOURS = (3, 10, 40, 75)
WORDS = ("Alpha", "beta", "Fix", "cache", "LOGIN", "flaky", "store", "Retry", "bug", "Docs")
PLUS_TWO = timezone(timedelta(hours=2))
SECOND_GROUP = "second-encoding-of-ws"


def render(rng: random.Random, value: datetime) -> str:
    choice = rng.choice(("z", "utc", "plus-two"))
    if choice == "z":
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.astimezone(timezone.utc if choice == "utc" else PLUS_TWO).isoformat()


def draw_store(rng: random.Random, stores, now: datetime) -> list[dict]:
    # 6 to 14 threads, some sharing an offset (ties), some ids repeated
    # in a second group (duplicates); the rows keep every copy and the
    # oracle keeps only the newer one.
    rows = []
    count = rng.randint(6, 14)
    for index in range(count):
        thread_id = f"t{rng.randint(0, 40):02d}-{index:02d}"
        updated = now - timedelta(hours=rng.choice(OFFSET_HOURS))
        title = " ".join(rng.sample(WORDS, 3))
        summary = " ".join(rng.sample(WORDS, 2))
        stores.grok_thread(thread_id, created=render(rng, updated - timedelta(hours=1)), updated=render(rng, updated), title=title, session_summary=summary)
        rows.append({"id": thread_id, "updated": updated, "texts": (title, summary)})
        if rng.random() < 0.2:
            other = now - timedelta(hours=rng.choice(OFFSET_HOURS))
            stores.grok_thread(thread_id, group=SECOND_GROUP, created=render(rng, other - timedelta(hours=1)), updated=render(rng, other), title=title, session_summary=summary)
            rows.append({"id": thread_id, "updated": other, "texts": (title, summary)})
    return rows


def oracle(rows: list[dict], now: datetime, *, since: timedelta | None, limit: int, query: str | None = None) -> list[str]:
    newest: dict[str, dict] = {}
    for row in rows:
        if row["id"] not in newest or row["updated"] > newest[row["id"]]["updated"]:
            newest[row["id"]] = row
    kept = [row for row in newest.values() if since is None or row["updated"] >= now - since]
    if query is not None:
        kept = [row for row in kept if any(query.lower() in text.lower() for text in row["texts"] if text)]
    kept.sort(key=lambda row: row["id"], reverse=True)
    kept.sort(key=lambda row: row["updated"], reverse=True)
    return [row["id"] for row in kept[:limit]]


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", SEEDS)
async def test_list_matches_the_inv7_oracle_for_generated_stores(sandbox, helper, stores, seed) -> None:
    # INV-7 / EC-15 / EC-16 / EC-17: window, order, tie-break,
    # uniqueness and limit, for every window and a few limits.
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = draw_store(rng, stores, now)
    ws = sandbox.workspace
    for window in (None, *WINDOW_HOURS):
        since = None if window is None else timedelta(hours=window)
        for limit in (1, rng.randint(2, 8), 200):
            listed = await helper("list_grok_threads", ws, since=since, limit=limit)
            assert [summary.thread_id for summary in listed] == oracle(rows, now, since=since, limit=limit), f"seed {seed}, since {window} h, limit {limit}"
            stamps = [summary.updated_at for summary in listed]
            assert all(stamp.utcoffset() == timedelta(0) for stamp in stamps)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", SEEDS[:8])
async def test_wrappers_equal_the_base_list_for_generated_stores(sandbox, helper, stores, seed) -> None:
    # INV-7 wrapper equivalence.
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    draw_store(rng, stores, now)
    ws = sandbox.workspace
    for limit in (1, 3, 10, 200):
        assert await helper("list_recent_grok_threads", ws, limit=limit) == await helper("list_grok_threads", ws, limit=limit)
        for window in WINDOW_HOURS:
            since = timedelta(hours=window)
            assert await helper("list_grok_threads_since", ws, since, limit=limit) == await helper("list_grok_threads", ws, since=since, limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", SEEDS[:10])
async def test_search_matches_the_literal_case_insensitive_oracle(sandbox, helper, stores, seed) -> None:
    # D-3 / INV-7: a substring of a title or summary in another letter
    # case finds exactly the threads that contain it.
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = draw_store(rng, stores, now)
    for _ in range(4):
        text = rng.choice(rng.choice(rows)["texts"])
        start = rng.randint(0, len(text) - 3)
        query = text[start : start + rng.randint(3, 6)].swapcase()
        limit = rng.choice((1, 5, 200))
        found = await helper("search_grok_threads", sandbox.workspace, query, limit=limit)
        assert [summary.thread_id for summary in found] == oracle(rows, now, since=None, limit=limit, query=query), f"seed {seed}, query {query!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", SEEDS[:10])
async def test_every_lineage_is_root_first_linked_and_ends_at_the_thread(sandbox, helper, stores, seed) -> None:
    # INV-10 / EC-25: a random forest, some parents missing from the
    # store; every chain follows the parents up to a root or a gap.
    rng = random.Random(seed)
    ids = [f"node-{index:02d}" for index in range(12)]
    parents: dict[str, str | None] = {}
    for index, thread_id in enumerate(ids):
        choice = rng.random()
        parents[thread_id] = None if index == 0 or choice < 0.25 else ("gone-" + thread_id if choice < 0.35 else rng.choice(ids[:index]))
        stores.grok_thread(thread_id, parent=parents[thread_id])
    for thread_id in rng.sample(ids, 5):
        expected = [thread_id]
        while parents.get(expected[0]) in parents:
            expected.insert(0, parents[expected[0]])
        chain = await helper("get_grok_thread_lineage", thread_id, sandbox.workspace)
        assert [summary.thread_id for summary in chain] == expected, f"seed {seed}, thread {thread_id}"
        assert chain[0].parent_thread_id == parents[expected[0]]
        assert all(chain[step + 1].parent_thread_id == chain[step].thread_id for step in range(len(chain) - 1))
