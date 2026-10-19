"""FILE: vidbyte/harnesses/native/codex/thread_helpers.py

PURPOSE: CodexThreadHelpers, the CodexHost collaborator behind the thread helpers: the recent, since and search listings over one bounded page walk, the lineage walk up a thread's parents, the full transcript page, compact, delete and the stored-goal read.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost builds it in _open() next to CodexPreflight, and each of its thread-helper methods guards, then delegates here.
ARCHITECTURE NOTE: Reaches Codex only through CodexConnection, builds params with CodexParamsTranslator and records with CodexResponseTranslator, so every call is bounded and mapped like any other host call. Imports openai-codex, the connection, the translators, the preflight and the registry only under TYPE_CHECKING, so importing CodexHost still loads no SDK module (codex-host D-21). Each public method is one narrated main function over flat leaf helpers.
COMMON MODIFICATION PATTERNS: A new thread helper is one public method here, taking its input record from vidbyte/lib/dataclasses/codex_host_inputs.py, plus one guarded host method that builds that record; a new listing filter goes through CodexParamsTranslator.thread_list and the same page walk, never a second walk. Messages live in vidbyte/lib/constants/codex_host.py.
KNOWN EDGE CASES: The walk ends on a repeated or empty cursor, at the first thread older than since, at the limit or at CODEX_HOST_THREAD_LIST_MAX_PAGES pages (INV-13). Every JSON-RPC error on thread/read maps to session_not_found, so a refused ancestor ends the lineage quietly while a timeout propagates (INV-16). Compact loads a notLoaded thread only when no unfinished goal could resume (INV-18); delete never loads one (INV-19).
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (sections 6.1 INV-6 to INV-20, 8.1 D-1, D-8, D-13 to D-15, and 9.2)
TESTS: tests/features/codex_host/test_codex_host_thread_helpers.py, tests/features/codex_host/test_codex_host_helper_lifecycle.py, tests/features/codex_host/test_codex_host_helper_surface.py
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import (
    CODEX_GOAL_GET_METHOD,
    CODEX_HOST_HELPER_SOURCE_KINDS,
    CODEX_HOST_LINEAGE_MAX_DEPTH,
    CODEX_HOST_RESUMABLE_GOAL_STATUSES,
    CODEX_HOST_THREAD_LIST_MAX_PAGES,
    CODEX_THREAD_COMPACT_METHOD,
    CODEX_THREAD_DELETE_METHOD,
    CODEX_THREAD_LIST_METHOD,
    CODEX_THREAD_RESUME_METHOD,
    CODEX_THREAD_TURNS_LIST_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_GOAL_UNFINISHED_MESSAGE,
    CODEX_HOST_RUNNING_THREAD_MESSAGE,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexSpawnRequest,
    CodexThreadGoal,
    CodexThreadSummary,
    CodexTurnPage,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexThreadListing,
    CodexThreadRef,
    CodexTurnListRequest,
)
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

if TYPE_CHECKING:
    from openai_codex.generated.v2_all import Thread, ThreadListResponse

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.preflight import CodexPreflight
    from vidbyte.harnesses.native.codex.turns import CodexTurnRegistry
    from vidbyte.harnesses.native.codex.wire import (
        CodexParamsTranslator,
        CodexResponseTranslator,
    )

class CodexThreadHelpers:
    """Lists, walks, reads, compacts and deletes stored Codex threads for one CodexHost."""

    def __init__(
        self,
        connection: CodexConnection,
        params: CodexParamsTranslator,
        responses: CodexResponseTranslator,
        preflight: CodexPreflight,
        registry: CodexTurnRegistry,
    ) -> None:
        # The host's own parts, built once the host opened.
        self._connection = connection
        self._params = params
        self._responses = responses
        self._preflight = preflight
        self._registry = registry

    async def list_threads(self, listing: CodexThreadListing) -> tuple[CodexThreadSummary, ...]:
        # @intent one-bounded-walk-serves-every-listing
        # Recent, since and search share this walk (D-8). It always
        # ends: at the limit, on an empty or repeated cursor, at the
        # first thread older than since, or after the page bound,
        # because a server may repeat or invent cursors forever. The
        # listing record already checked every argument, so a bad one
        # sent nothing.
        operation, cwd, search, since, limit = listing.operation, listing.cwd, listing.query, listing.since, listing.limit
        summaries: dict[str, CodexThreadSummary] = {}
        sent: set[str] = set()
        cursor = ""
        for _ in range(CODEX_HOST_THREAD_LIST_MAX_PAGES):
            # Ask for the summaries still wanted, newest first.
            page = await self._list_page(operation, cwd, search, cursor, limit - len(summaries))
            # Keep each thread once, and stop at the limit or at the
            # first thread older than the since window.
            if self._collect(page.data, summaries, since, limit):
                break
            # Follow the cursor only while it is new.
            cursor = page.next_cursor or ""
            if not cursor or cursor in sent:
                break
            sent.add(cursor)
        return tuple(summaries.values())

    async def lineage(self, ref: CodexThreadRef) -> tuple[CodexThreadSummary, ...]:
        # @intent the-lineage-ends-where-a-parent-cannot-be-read
        # The thread, then each parent in order, each read once without
        # turns (INV-16). An unknown start is not found; a refused
        # parent ends the walk, so the last summary keeps the parent id
        # it could not read and the chain shows itself incomplete.
        operation = ref.operation
        summary = self._responses.summary(await self._preflight.require_thread(operation, ref.thread_id))
        chain = [summary]
        visited = {summary.thread_id}
        # Walk up until a root, a cycle, a refused parent or the depth
        # bound.
        while summary.parent_thread_id is not None and summary.parent_thread_id not in visited and len(chain) < CODEX_HOST_LINEAGE_MAX_DEPTH:
            parent = await self._ancestor(operation, summary.parent_thread_id)
            if parent is None:
                break
            summary = self._responses.summary(parent)
            visited.add(summary.thread_id)
            chain.append(summary)
        return tuple(chain)

    async def turns(self, operation: CodexHostOperation, listing: CodexTurnListRequest) -> CodexTurnPage:
        # One page of the stored transcript, oldest first, every item
        # included, without loading the thread (INV-17, INV-33). The
        # thread must exist, so an unknown id is not found.
        thread_id = listing.thread_id
        await self._preflight.require_thread(operation, thread_id)
        connection = self._connection
        page_call = connection.raw(CODEX_THREAD_TURNS_LIST_METHOD, self._params.turns_page(thread_id, listing.cursor, listing.limit))
        page = await connection.call(operation, CODEX_THREAD_TURNS_LIST_METHOD, page_call, thread_id=thread_id)
        return self._responses.turn_page(page)

    async def compact(self, ref: CodexThreadRef) -> None:
        # @intent compact-loads-a-thread-only-when-no-goal-can-resume
        # Compaction runs in this host's app-server. A thread not
        # loaded here must be loaded first, and loading one with an
        # unfinished goal could let Codex continue that goal as
        # untracked paid turns, so the goal is read first (INV-18).
        # Refuse a thread this host is running or starting a turn on,
        # and hold it, so no continue, review, compact or delete on it
        # races this one (INV-8, INV-9).
        operation, thread_id = ref.operation, ref.thread_id
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # The thread must exist, with no turn Codex reports running.
            status = await self._stored_status(operation, thread_id)
            # A thread not loaded here is loaded only when it has no
            # goal, or a complete one, exactly as continue loads it.
            if status is CodexThreadStatus.NOT_LOADED:
                self._refuse_unfinished(operation, thread_id, await self._stored_goal(operation, thread_id))
                await self._resume(operation, thread_id)
            # One compaction request, never retried; Codex compacts in
            # the background once it accepts.
            connection = self._connection
            await connection.call(operation, CODEX_THREAD_COMPACT_METHOD, connection.client.thread_compact, thread_id, thread_id=thread_id)
        finally:
            self._registry.release(thread_id)

    async def delete(self, ref: CodexThreadRef) -> None:
        # @intent delete-is-irreversible-so-busy-threads-are-refused
        # Codex removes the stored thread for good, so a thread this
        # host or another client is running a turn on is refused, and
        # the thread is held while the delete runs (INV-8, INV-9).
        operation, thread_id = ref.operation, ref.thread_id
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # The thread must exist, with no turn Codex reports running;
            # it is never loaded first (INV-19).
            await self._stored_status(operation, thread_id)
            # One delete through the raw path, which keeps the SDK's
            # overload retries, since an overload is refused before any
            # work runs.
            connection = self._connection
            delete = connection.raw(CODEX_THREAD_DELETE_METHOD, self._params.thread_params(thread_id))
            await connection.call(operation, CODEX_THREAD_DELETE_METHOD, delete, thread_id=thread_id)
        finally:
            self._registry.release(thread_id)

    async def goal(self, ref: CodexThreadRef) -> CodexThreadGoal | None:
        # The thread's stored goal, or None, read without loading the
        # thread whatever its status (INV-20, INV-33).
        await self._preflight.require_thread(ref.operation, ref.thread_id)
        return await self._stored_goal(ref.operation, ref.thread_id)

    async def _list_page(self, operation: CodexHostOperation, cwd: str, search: str, cursor: str, remaining: int) -> ThreadListResponse:
        # One newest-first page of every top-level source, the SDK's
        # own appServer threads included (INV-11, D-7).
        connection = self._connection
        listing = self._params.thread_list(cwd, search, False, CODEX_HOST_HELPER_SOURCE_KINDS, CodexThreadSortKey.UPDATED_AT, CodexSortDirection.DESC, cursor, remaining)
        return await connection.call(operation, CODEX_THREAD_LIST_METHOD, connection.client.thread_list, listing)

    def _collect(self, threads: Sequence[Thread], summaries: dict[str, CodexThreadSummary], since: int | None, limit: int) -> bool:
        # Adds each new thread in Codex's order and answers whether the
        # walk is done: the limit is reached, or a thread is older than
        # since, after which every thread is older (INV-12, INV-14).
        for thread in threads:
            if since is not None and thread.updated_at < since:
                return True
            if thread.id not in summaries:
                summaries[thread.id] = self._responses.summary(thread)
            if len(summaries) >= limit:
                return True
        return False

    async def _ancestor(self, operation: CodexHostOperation, thread_id: str) -> Thread | None:
        # @intent only-an-unreadable-parent-ends-the-lineage
        # Any JSON-RPC error on thread/read means not found, so a
        # deleted, malformed or refused parent ends the walk as None;
        # a timeout or a dead process still propagates (INV-16).
        try:
            return await self._preflight.require_thread(operation, thread_id)
        except CodexAgentError as exc:
            if exc.failure_code != FailureCode.CODEX_SESSION_NOT_FOUND.value:
                raise
            return None

    async def _stored_status(self, operation: CodexHostOperation, thread_id: str) -> CodexThreadStatus:
        # The thread must exist, and a turn Codex reports running on it,
        # from any client, refuses the call (INV-7, INV-8).
        thread = await self._preflight.require_thread(operation, thread_id)
        status = self._responses.thread_info(thread).status
        if status is CodexThreadStatus.ACTIVE:
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_BUSY, CODEX_HOST_RUNNING_THREAD_MESSAGE, operation, thread_id)
        return status

    async def _stored_goal(self, operation: CodexHostOperation, thread_id: str) -> CodexThreadGoal | None:
        # One raw thread/goal/get, which answers without loading the
        # thread (INV-20).
        connection = self._connection
        read = connection.raw(CODEX_GOAL_GET_METHOD, self._params.thread_params(thread_id))
        return self._responses.goal(await connection.call(operation, CODEX_GOAL_GET_METHOD, read, thread_id=thread_id))

    @staticmethod
    def _refuse_unfinished(operation: CodexHostOperation, thread_id: str, goal: CodexThreadGoal | None) -> None:
        # Only a complete goal is trusted not to resume work once the
        # thread loads; every other status is refused (D-13).
        if goal is not None and goal.status not in CODEX_HOST_RESUMABLE_GOAL_STATUSES:
            raise CodexErrorMapper.error(FailureCode.CODEX_GOAL_UNFINISHED, CODEX_HOST_GOAL_UNFINISHED_MESSAGE.format(status=goal.status.value), operation, thread_id)

    async def _resume(self, operation: CodexHostOperation, thread_id: str) -> None:
        # Load the thread exactly as continue_codex_thread does with no
        # overrides, so compact applies no posture of its own (INV-18).
        connection = self._connection
        resume = self._params.thread_resume(thread_id, CodexSpawnRequest())
        await connection.call(operation, CODEX_THREAD_RESUME_METHOD, connection.client.thread_resume, thread_id, resume, thread_id=thread_id)


__all__ = ["CodexThreadHelpers"]
