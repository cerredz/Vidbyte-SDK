"""FILE: vidbyte/harnesses/native/hostkit/listing.py

PURPOSE: Defines NativeThreadListing, the one place the list, search and lineage helpers of every harness apply the listing rules: the since window, the newest-first order with its tie-break, uniqueness, the limit, the literal case-insensitive search match and the lineage step check.
ROLE IN CODEBASE: Called by GrokHelperRun (grok/helpers.py), OpencodeHelperRun (opencode/helpers.py) and MuseHelperRun (muse/helpers.py) after their wire readers have turned vendor data into NativeThreadSummary records, so the three harnesses list, search and walk lineage identically (spec INV-7, INV-10).
ARCHITECTURE NOTE: Pure functions over validated records; nothing here reads a file or starts a process. The order key is (updated_at, thread_id), compared on UTC-aware datetimes, so offsets never misorder threads (spec EC-15). The module holds no literals of its own (spec INV-15): the depth cap and the detail texts come from vidbyte/lib/constants/native_threads.py, read at call time.
FUNCTION INVENTORY: NativeThreadListing.cutoff turns since into the oldest updated_at a listing keeps; newest keeps one entry per thread id, applies the window, orders newest first with ties by thread id descending and cuts at the limit; matches says whether a query occurs literally, ignoring case, in any of a thread's texts; check_step refuses a lineage step that repeats an id or passes the depth cap.
COMMON MODIFICATION PATTERNS: A listing rule that every harness must share goes here as one more static method, called from each helper flow.
WHAT NOT TO DO IN THIS FILE: 1. Do not treat the query as a pattern; it is matched as literal text (spec D-3). 2. Do not take the current time here; the caller takes it once per call and passes it in (spec INV-7). 3. Do not import a harness subpackage; harness subpackages import hostkit, never the reverse (spec INV-20).
KNOWN EDGE CASES: A duplicated thread id keeps the entry with the newer updated_at (spec EC-17). Two threads with equal updated_at are ordered by thread id, descending (spec EC-16). A chain of exactly NATIVE_LINEAGE_MAX_DEPTH threads passes; one more parent fails (spec EC-27).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_listing_properties.py, tests/features/harness_threads/test_harness_threads_grok_helpers.py, tests/features/harness_threads/test_harness_threads_opencode_helpers.py, tests/features/harness_threads/test_harness_threads_muse_helpers.py
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadSummary,
)
from vidbyte.lib.enums.native_threads import NativeThreadProblem


class NativeThreadListing:
    """The since window, order, uniqueness, limit, search match and lineage step check every harness shares."""

    @staticmethod
    def cutoff(since: timedelta | None, now: datetime) -> datetime | None:
        # The oldest updated_at a listing keeps, from the one now the
        # call took; no since means no window.
        return None if since is None else now - since

    @staticmethod
    def newest(summaries: Iterable[NativeThreadSummary], *, cutoff: datetime | None, limit: int) -> tuple[NativeThreadSummary, ...]:
        # @intent native-listing-is-newest-first-unique-and-limited
        # One entry per thread id, the newer one when a store lists an
        # id twice; then only the threads inside the window, newest
        # first with ties by thread id descending, at most limit.
        kept: dict[str, NativeThreadSummary] = {}
        for summary in summaries:
            seen = kept.get(summary.thread_id)
            if seen is None or summary.updated_at > seen.updated_at:
                kept[summary.thread_id] = summary
        inside = [summary for summary in kept.values() if cutoff is None or summary.updated_at >= cutoff]
        inside.sort(key=lambda summary: (summary.updated_at, summary.thread_id), reverse=True)
        return tuple(inside[:limit])

    @staticmethod
    def matches(texts: Sequence[str | None], query: str) -> bool:
        # A literal, case-insensitive substring match over the texts a
        # thread has; regex characters in the query mean themselves.
        wanted = query.casefold()
        return any(wanted in text.casefold() for text in texts if text is not None)

    @staticmethod
    def check_step(chain: tuple[NativeThreadSummary, ...], parent_id: str, errors: NativeErrorFactory, request: NativeHelperRequest) -> None:
        # @intent native-lineage-walk-is-bounded
        # A parent already in the chain means corrupt data whose links
        # form a cycle, and a chain already at the depth cap cannot take
        # one more; both are protocol_mismatch, so the walk always ends.
        if any(summary.thread_id == parent_id for summary in chain):
            detail = native_threads.NATIVE_LINEAGE_CYCLE_DETAIL.format(thread_id=parent_id)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=detail)
        if len(chain) >= native_threads.NATIVE_LINEAGE_MAX_DEPTH:
            detail = native_threads.NATIVE_LINEAGE_DEPTH_DETAIL.format(depth=native_threads.NATIVE_LINEAGE_MAX_DEPTH)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=detail)


__all__ = ["NativeThreadListing"]
