"""FILE: tests/features/codex_host/test_codex_host_thread_helpers.py

PURPOSE: Proves the thread helpers over the in-memory app-server: the recent, since and search listings (their exact thread/list params, page walk, stopping rules, argument checks and summary mapping), the lineage walk (order, stopping rules, depth bound, refused and timed-out ancestor reads), the transcript (exact thread/turns/list params, stored-turn mapping, cursors, a running turn, a notLoaded thread left unloaded), and compact and delete (their request order, the notLoaded goal check, busy and unknown threads, and the thread reservation they hold).
ROLE IN CODEBASE: Thread-helper layer of tests/features/codex_host/ (docs/spec/codex-host-thread-helpers/spec.md AC-2 to AC-23, AC-38, INV-6 to INV-19, INV-33, EC-1 to EC-23, EC-42). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake's paged_thread_list switch makes thread/list sort, filter by sourceKinds, cwd and searchTerm, honor limit and page with distinct cursors that end in null, the way codex app-server 0.162 does; thread_page_size caps a page so a walk needs several. Threads carry their own updatedAt, source, name, fork parent, parentThreadId and status, so a test seeds exactly the store a criterion names. Expected summaries are built from the seeded FakeThread by the INV-15 mapping, not from the host's answer.
COMMON MODIFICATION PATTERNS: Add a listing case by seeding threads with new_thread(updated_at=..., source=...) and asserting the exact params of every thread/list request; add a compact or delete case by seeding the thread's status and goal and asserting the request list of that thread.
KNOWN EDGE CASES: thread/read always carries includeTurns because openai-codex's thread_read sends it. The fake's legacy thread/list (paged_thread_list off) ignores every param and repeats one cursor, which is the AC-5 store. A held answer must be released after the test's assertions, so a late answer never reaches a closed host unobserved.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-thread-helpers/spec.md sections 6.1 (INV-6 to INV-19, INV-33), 6.2, 6.3 and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_thread_helpers.py
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    BUSY_TEXT,
    GOAL_UNFINISHED_MESSAGE,
    LIMIT_MESSAGE,
    QUERY_MESSAGE,
    RUNNING_THREAD_MESSAGE,
    SINCE_MESSAGE,
    WAIT_SECONDS,
    HostTestCase,
    requires_sdk,
    thread_suffix,
)
from vidbyte.lib.errors import ConfigurationError

CONNECTION_MODULE = "vidbyte.harnesses.native.codex.connection"
# Spec INV-11 and D-7: the sourceKinds every helper listing sends.
SOURCE_KINDS = ["cli", "vscode", "exec", "appServer", "unknown"]
# Spec INV-10: the four check requests no new helper sends.
PREFLIGHT_METHODS = frozenset({"account/read", "account/rateLimits/read", "windowsSandbox/readiness", "model/list"})
WORK_A = os.path.abspath(os.path.join(os.sep, "work", "a"))
WORK_B = os.path.abspath(os.path.join(os.sep, "work", "b"))
# Spec section 9.3: CODEX_HOST_THREAD_LIST_MAX_LIMIT, CODEX_HOST_THREAD_LIST_MAX_PAGES and CODEX_HOST_LINEAGE_MAX_DEPTH.
MAX_LIMIT = 1000
MAX_PAGES = 1000
LINEAGE_MAX_DEPTH = 100
# A listing that makes the walk read every one of MAX_PAGES pages needs longer than one ordinary wait.
LONG_WALK_SECONDS = 180.0
UNFINISHED_GOAL_STATUSES = ("active", "paused", "blocked", "usageLimited", "budgetLimited")
SPAWN_SUB_AGENT = {"subAgent": {"thread_spawn": {"depth": 1, "parent_thread_id": "thr-elsewhere"}}}


def _listing(limit: int, **extra: Any) -> dict[str, Any]:
    """The exact INV-11 params of one helper thread/list request."""
    return {"sortKey": "updated_at", "sortDirection": "desc", "sourceKinds": list(SOURCE_KINDS), "limit": limit, **extra}


def _summary(thread: Any) -> Any:
    """The INV-15 summary of a seeded FakeThread, built without the host."""
    from vidbyte.lib.dataclasses.codex_host import CodexThreadSummary

    return CodexThreadSummary(
        thread_id=thread.thread_id,
        title=thread.name or None,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        parent_thread_id=thread.forked_from or thread.parent_thread_id,
        model=thread.model or "",
    )


def _thread_methods(requests: list[Any], thread_id: str) -> list[str]:
    return [request.method for request in requests if request.params.get("threadId") == thread_id]


class _HelperCase(HostTestCase):
    """Opens a host and remembers where its requests begin, so a test sees only what its own calls sent."""

    async def opened(self) -> Any:
        host = await self.open_host()
        self.mark = len(self.server.requests)
        return host

    def sent(self) -> list[Any]:
        return list(self.server.requests)[self.mark :]

    def sent_methods(self) -> list[str]:
        return [request.method for request in self.sent()]

    def remark(self) -> None:
        self.mark = len(self.server.requests)

    async def call(self, awaitable: Any, seconds: float = WAIT_SECONDS) -> Any:
        return await asyncio.wait_for(awaitable, seconds)

    async def refused(self, awaitable: Any) -> ConfigurationError:
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(awaitable, WAIT_SECONDS)
        return caught.exception


@requires_sdk
class CodexThreadListingTests(_HelperCase):
    """AC-2 to AC-8, INV-10 to INV-14: the listing params, the page walk and its stopping rules."""

    async def test_recent_threads_come_newest_first_without_sub_agents_or_a_preflight(self) -> None:
        # AC-2: eight threads; the two sub-agent threads are the newest, so a missing sourceKinds filter would list them first.
        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        plain = [self.server.new_thread(created_at=base + index, updated_at=base + 10 * (index + 1), source=source, name=f"Thread {index}") for index, source in enumerate(("cli", "vscode", "exec", "appServer", "unknown", "cli"))]
        self.server.new_thread(updated_at=base + 500, source={"subAgent": "review"})
        self.server.new_thread(updated_at=base + 400, source=SPAWN_SUB_AGENT)
        host = await self.opened()
        result = await self.call(host.list_recent_codex_threads("", limit=5))
        newest = sorted(plain, key=lambda thread: thread.updated_at, reverse=True)[:5]
        self.assertEqual(result, tuple(_summary(thread) for thread in newest))
        self.assertEqual([request.params for request in self.server.matching("thread/list")], [_listing(5)])
        self.assertFalse(PREFLIGHT_METHODS & set(self.sent_methods()), self.sent_methods())
        self.assertEqual(self.sent_methods(), ["thread/list"])

    async def test_a_cwd_goes_on_every_page_and_an_empty_cwd_sends_none(self) -> None:
        # AC-3, EC-40: Codex matches cwd exactly, so only WORK_A's threads come back.
        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        self.server.thread_page_size = 2
        in_a = [self.server.new_thread(cwd=WORK_A, updated_at=base + 100 + index) for index in range(4)]
        for index in range(3):
            self.server.new_thread(cwd=WORK_B, updated_at=base + 200 + index)
        host = await self.opened()
        result = await self.call(host.list_recent_codex_threads(WORK_A, limit=5))
        self.assertEqual(result, tuple(_summary(thread) for thread in reversed(in_a)))
        self.assertEqual([request.params for request in self.sent()], [_listing(5, cwd=WORK_A), _listing(3, cwd=WORK_A, cursor="threads-after-2")])

        self.remark()
        await self.call(host.list_recent_codex_threads("", limit=5))
        self.assertTrue(self.sent())
        for request in self.sent():
            self.assertNotIn("cwd", request.params)

    async def test_the_walk_asks_for_the_remaining_count_with_each_cursor(self) -> None:
        # AC-4: ten threads, two per page; limit 5 takes pages of 2, 2 and 1.
        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        self.server.thread_page_size = 2
        threads = [self.server.new_thread(updated_at=base + index) for index in range(10)]
        host = await self.opened()
        result = await self.call(host.list_recent_codex_threads("", limit=5))
        self.assertEqual(result, tuple(_summary(thread) for thread in sorted(threads, key=lambda thread: thread.updated_at, reverse=True)[:5]))
        self.assertEqual(
            [request.params for request in self.sent()],
            [_listing(5), _listing(3, cursor="threads-after-2"), _listing(1, cursor="threads-after-4")],
        )

    async def test_a_repeated_cursor_ends_the_walk_without_duplicates(self) -> None:
        # AC-5, EC-4, EC-6, INV-13: the legacy fake answers every page with all threads and the same cursor.
        threads = [self.server.new_thread() for _ in range(3)]
        host = await self.opened()
        result = await self.call(host.list_recent_codex_threads("", limit=50))
        self.assertEqual(result, tuple(_summary(thread) for thread in threads))
        # The first cursor is new, so a second page is read; its cursor repeats, so the walk ends there.
        self.assertEqual([request.params for request in self.sent()], [_listing(50), _listing(47, cursor="cursor-after-page")])

        self.remark()
        cut = await self.call(host.list_recent_codex_threads("", limit=2))
        self.assertEqual(cut, tuple(_summary(thread) for thread in threads[:2]))
        self.assertEqual(self.sent_methods(), ["thread/list"])

    async def test_since_returns_the_inclusive_window_and_stops_at_the_first_older_thread(self) -> None:
        # AC-6, INV-14: T is kept, T-1 is not, and no page after the one holding T-1 is read.
        moment = self.fakes.BASE_TIME + 1000
        self.server.paged_thread_list = True
        self.server.thread_page_size = 2
        threads = [self.server.new_thread(updated_at=moment + offset) for offset in (100, 50, 0, -1, -2, -3)]
        host = await self.opened()
        result = await self.call(host.list_codex_threads_since("", moment, limit=10))
        self.assertEqual(result, tuple(_summary(thread) for thread in threads[:3]))
        self.assertEqual([request.params for request in self.sent()], [_listing(10), _listing(8, cursor="threads-after-2")])

    async def test_an_empty_window_is_an_empty_tuple_and_milliseconds_lie_in_the_future(self) -> None:
        # AC-7, EC-9, EC-10, D-9: no error, one page read.
        self.server.paged_thread_list = True
        for _ in range(3):
            self.server.new_thread()
        host = await self.opened()
        self.assertEqual(await self.call(host.list_codex_threads_since("", self.fakes.BASE_TIME + 86_400)), ())
        self.assertEqual(self.sent_methods(), ["thread/list"])
        self.assertEqual(await self.call(host.list_codex_threads_since("", self.fakes.BASE_TIME * 1000)), ())

    async def test_search_sends_the_search_term_and_refuses_a_blank_query(self) -> None:
        # AC-8, EC-3: Codex matches the title; a blank query is refused before any request.
        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        matching = [self.server.new_thread(name=name, updated_at=base + offset) for name, offset in (("fix the build", 30), ("prefix notes", 20))]
        self.server.new_thread(name="readme", updated_at=base + 40)
        host = await self.opened()
        result = await self.call(host.search_codex_threads("", "fix", limit=3))
        self.assertEqual(result, tuple(_summary(thread) for thread in matching))
        self.assertEqual([request.params for request in self.sent()], [_listing(3, searchTerm="fix")])

        self.remark()
        for query in ("", "   "):
            with self.subTest(query=query):
                error = await self.refused(host.search_codex_threads("", query, limit=3))
                self.assertEqual(str(error), QUERY_MESSAGE.format(operation="search_codex_threads"))
        self.assertEqual(self.sent(), [])

    async def test_bad_limits_and_timestamps_are_refused_before_any_request(self) -> None:
        # AC-9, EC-1, EC-2, INV-6: the message names the function and the field.
        self.server.paged_thread_list = True
        host = await self.opened()
        listings = {
            "list_recent_codex_threads": lambda limit: host.list_recent_codex_threads("", limit=limit),
            "list_codex_threads_since": lambda limit: host.list_codex_threads_since("", 0, limit=limit),
            "search_codex_threads": lambda limit: host.search_codex_threads("", "fix", limit=limit),
        }
        for operation, listing in listings.items():
            for limit in (0, -1, True, MAX_LIMIT + 1):
                with self.subTest(operation=operation, limit=limit):
                    error = await self.refused(listing(limit))
                    self.assertEqual(str(error), LIMIT_MESSAGE.format(operation=operation, minimum=1, maximum=MAX_LIMIT))
            for limit in (2.5, "5", None):
                with self.subTest(operation=operation, limit=limit):
                    error = await self.refused(listing(limit))
                    self.assertIn(operation, str(error))
                    self.assertIn("limit", str(error))
        for since in (-1, True, 1.5):
            with self.subTest(since=since):
                error = await self.refused(host.list_codex_threads_since("", since))
                self.assertEqual(str(error), SINCE_MESSAGE.format(operation="list_codex_threads_since"))
        for since in ("1760000000", None):
            with self.subTest(since=since):
                error = await self.refused(host.list_codex_threads_since("", since))
                self.assertIn("list_codex_threads_since", str(error))
                self.assertIn("since", str(error))
        seeded = self.server.seed_thread(completed_turns=1)
        for limit in (0, -1, True, 1.5):
            with self.subTest(turns_limit=limit):
                error = await self.refused(host.list_codex_turns(seeded.thread_id, limit=limit))
                self.assertIn("list_codex_turns", str(error))
                self.assertIn("limit", str(error))
        self.assertEqual(self.sent(), [])

        # The bounds themselves are accepted.
        await self.call(host.list_recent_codex_threads("", limit=1))
        await self.call(host.list_recent_codex_threads("", limit=MAX_LIMIT))
        await self.call(host.list_codex_threads_since("", 0, limit=1))
        await self.call(host.list_codex_turns(seeded.thread_id, limit=1))

    async def test_endless_cursors_end_after_the_page_bound(self) -> None:
        # EC-5, INV-13, D-8: every answer is an empty page with a fresh cursor, as a per-page title filter can give.
        self.server.endless_thread_list = True
        host = await self.opened()
        result = await self.call(host.search_codex_threads("", "fix", limit=5), LONG_WALK_SECONDS)
        self.assertEqual(result, ())
        self.assertEqual(self.sent_methods(), ["thread/list"] * MAX_PAGES)


@requires_sdk
class CodexThreadSummaryTests(_HelperCase):
    """AC-10, EC-8 and INV-15: the summary record each listing and lineage step builds from a Thread."""

    async def test_titles_parents_and_models_map_as_section_6_1_says(self) -> None:
        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        no_name = self.server.new_thread(name=None, explicit_name=True, forked_from="thr-fork-parent", updated_at=base + 50, created_at=base + 1)
        empty_name = self.server.new_thread(name="", explicit_name=True, updated_at=base + 40, created_at=base + 2)
        parented = self.server.new_thread(parent_thread_id="thr-spawn-parent", name="Child", updated_at=base + 30, created_at=base + 3)
        both = self.server.new_thread(forked_from="thr-fork-wins", parent_thread_id="thr-spawn-loses", updated_at=base + 20, created_at=base + 4)
        no_model = self.server.new_thread(model=None, name="No model", updated_at=base + 10, created_at=base + 5)
        host = await self.opened()

        listed = await self.call(host.list_recent_codex_threads("", limit=10))
        threads = (no_name, empty_name, parented, both, no_model)
        self.assertEqual(listed, tuple(_summary(thread) for thread in threads))
        self.assertEqual([summary.title for summary in listed], [None, None, "Child", None, "No model"])
        self.assertEqual([summary.parent_thread_id for summary in listed], ["thr-fork-parent", None, "thr-spawn-parent", "thr-fork-wins", None])
        self.assertEqual(listed[-1].model, "")
        self.assertEqual({summary.harness for summary in listed}, {"codex"})

        # The lineage builds the same record from thread/read.
        for thread in threads:
            with self.subTest(thread=thread.thread_id):
                lineage = await self.call(host.get_codex_thread_lineage(thread.thread_id))
                self.assertEqual(lineage[0], _summary(thread))


@requires_sdk
class CodexThreadLineageTests(_HelperCase):
    """AC-11 to AC-14, EC-11 to EC-14 and INV-16: the walk up the parent links and where it stops."""

    async def test_the_lineage_walks_fork_and_spawn_parents_to_the_root(self) -> None:
        # AC-11: each thread is read once, without turns, child first.
        root = self.server.new_thread(name="Root")
        middle = self.server.new_thread(forked_from=root.thread_id)
        leaf = self.server.new_thread(forked_from=middle.thread_id)
        host = await self.opened()
        lineage = await self.call(host.get_codex_thread_lineage(leaf.thread_id))
        self.assertEqual(lineage, (_summary(leaf), _summary(middle), _summary(root)))
        self.assertIsNone(lineage[-1].parent_thread_id)
        self.assertEqual([request.params for request in self.sent()], [{"threadId": thread.thread_id, "includeTurns": False} for thread in (leaf, middle, root)])

        # A spawn parent (parentThreadId) is followed the same way.
        self.remark()
        spawned = self.server.new_thread(parent_thread_id=leaf.thread_id)
        mixed = await self.call(host.get_codex_thread_lineage(spawned.thread_id))
        self.assertEqual([summary.thread_id for summary in mixed], [spawned.thread_id, leaf.thread_id, middle.thread_id, root.thread_id])
        self.assertEqual(self.sent_methods(), ["thread/read"] * 4)

    async def test_an_unknown_or_refused_ancestor_ends_the_walk_without_an_error(self) -> None:
        # AC-12, EC-11, EC-14: the last summary keeps the parent id it could not read.
        parent = self.server.new_thread(forked_from="thr-deleted")
        child = self.server.new_thread(forked_from=parent.thread_id)
        host = await self.opened()
        lineage = await self.call(host.get_codex_thread_lineage(child.thread_id))
        self.assertEqual(lineage, (_summary(child), _summary(parent)))
        self.assertEqual(lineage[-1].parent_thread_id, "thr-deleted")

        # A read Codex refuses for another reason (-32602) also ends the walk as not found.
        grandparent = self.server.new_thread()
        parent.forked_from = grandparent.thread_id
        self.server.fail("thread/read", self.fakes.FakeRpcError(-32602, "malformed thread id"), predicate=lambda params: params["threadId"] == grandparent.thread_id)
        refused = await self.call(host.get_codex_thread_lineage(child.thread_id))
        self.assertEqual([summary.thread_id for summary in refused], [child.thread_id, parent.thread_id])
        self.assertEqual(refused[-1].parent_thread_id, grandparent.thread_id)

    async def test_an_unknown_start_is_not_found_and_a_cycle_reads_each_thread_once(self) -> None:
        # AC-13, EC-12, INV-7.
        host = await self.opened()
        error = await self.assert_codex_error(host.get_codex_thread_lineage("thr-never"), "codex.session_not_found")
        self.assertEqual(error.operation, "get_codex_thread_lineage")
        self.assertIn("thr-never", error.message)
        self.assertEqual(self.sent_methods(), ["thread/read"])

        first = self.server.new_thread()
        second = self.server.new_thread(forked_from=first.thread_id)
        first.forked_from = second.thread_id
        self.remark()
        lineage = await self.call(host.get_codex_thread_lineage(first.thread_id))
        self.assertEqual([summary.thread_id for summary in lineage], [first.thread_id, second.thread_id])
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/read"])

    async def test_a_chain_deeper_than_the_bound_returns_exactly_the_bound(self) -> None:
        # AC-14, EC-13, D-20.
        chain = [self.server.new_thread()]
        for _ in range(LINEAGE_MAX_DEPTH + 1):
            chain.append(self.server.new_thread(forked_from=chain[-1].thread_id))
        host = await self.opened()
        lineage = await self.call(host.get_codex_thread_lineage(chain[-1].thread_id))
        self.assertEqual(len(lineage), LINEAGE_MAX_DEPTH)
        self.assertIsNotNone(lineage[-1].parent_thread_id)
        self.assertEqual(lineage, tuple(_summary(thread) for thread in reversed(chain[-LINEAGE_MAX_DEPTH:])))
        self.assertEqual(self.sent_methods(), ["thread/read"] * LINEAGE_MAX_DEPTH)

    async def test_an_ancestor_read_that_times_out_propagates(self) -> None:
        # EC-14, INV-16: a transport failure never cuts the walk short silently.
        parent = self.server.new_thread()
        child = self.server.new_thread(forked_from=parent.thread_id)
        host = await self.opened()
        hold = self.server.hold("thread/read", lambda params: params["threadId"] == parent.thread_id)
        with mock.patch(f"{CONNECTION_MODULE}.CODEX_HOST_REQUEST_TIMEOUT_SECONDS", 0.3):
            error = await self.assert_codex_error(host.get_codex_thread_lineage(child.thread_id), "codex.api_error")
        hold.release()
        self.assertEqual(error.operation, "get_codex_thread_lineage")


@requires_sdk
class CodexThreadTranscriptTests(_HelperCase):
    """AC-15, AC-16, EC-15, EC-16, INV-17 and INV-33: the stored turns, oldest first, with every item."""

    def _stored_thread(self) -> Any:
        skill_path = os.path.abspath(os.path.join(os.sep, "skills", "s", "SKILL.md"))
        thread = self.server.seed_thread(completed_turns=0)
        done = self.fakes.FakeTurn(turn_id=self.server.next_turn_id(), status="completed")
        done.items = [
            {"type": "userMessage", "id": "item-user-1", "content": [{"type": "text", "text": "do it"}, {"type": "skill", "name": "s", "path": skill_path}]},
            {"type": "reasoning", "id": "item-reasoning-1", "summary": ["Plan the change."], "content": ["PRIVATE-REASONING-CANARY"]},
            self.fakes.agent_message("item-final-1", "Final answer."),
        ]
        failed = self.fakes.FakeTurn(turn_id=self.server.next_turn_id(), status="failed", error={"message": "Codex failed the turn.", "codexErrorInfo": "other"})
        failed.items = [{"type": "userMessage", "id": "item-user-2", "content": [{"type": "text", "text": "try again"}]}]
        thread.turns = [done, failed]
        return thread

    async def test_turns_come_with_their_items_and_the_cursor_and_limit_pass_through(self) -> None:
        # AC-15: the host method sends no limit of its own (AC-41).
        from vidbyte.lib.enums.codex import CodexTurnStatus

        base = self.fakes.BASE_TIME
        thread = self._stored_thread()
        done, failed = thread.turns
        host = await self.opened()
        page = await self.call(host.list_codex_turns(thread.thread_id))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/turns/list"])
        self.assertEqual(self.server.matching("thread/turns/list")[0].params, {"threadId": thread.thread_id, "itemsView": "full", "sortDirection": "asc"})

        self.assertEqual(page.next_cursor, "")
        self.assertEqual([turn.turn_id for turn in page.turns], [done.turn_id, failed.turn_id])
        first, second = page.turns
        self.assertEqual(
            (first.status, first.final_response, first.error_message, first.started_at, first.completed_at),
            (CodexTurnStatus.COMPLETED, "Final answer.", "", base, base + 5),
        )
        self.assertEqual(
            (second.status, second.final_response, second.error_message, second.started_at, second.completed_at),
            (CodexTurnStatus.FAILED, "", "Codex failed the turn.", base, base + 5),
        )
        self.assertEqual([(item.id, item.type) for item in first.items], [("item-user-1", "userMessage"), ("item-reasoning-1", "reasoning"), ("item-final-1", "agentMessage")])
        user, reasoning, final = first.items
        # INV-17: reasoning content never leaves the serializer; its summary does.
        self.assertEqual(dict(reasoning.fields), {"summary": ["Plan the change."]})
        self.assertEqual([entry["type"] for entry in user.fields["content"]], ["text", "skill"])
        self.assertEqual(user.fields["content"][1]["name"], "s")
        self.assertEqual((final.fields["text"], final.fields["phase"]), ("Final answer.", "final_answer"))
        for turn in page.turns:
            for item in turn.items:
                self.assertNotIn("PRIVATE-REASONING-CANARY", repr(item.fields))

        self.server.turn_cursors["c1"] = 1
        self.remark()
        second_page = await self.call(host.list_codex_turns(thread.thread_id, cursor="c1", limit=1))
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "itemsView": "full", "sortDirection": "asc", "cursor": "c1", "limit": 1})
        self.assertEqual([turn.turn_id for turn in second_page.turns], [failed.turn_id])
        self.assertEqual(second_page.next_cursor, "")

        first_page = await self.call(host.list_codex_turns(thread.thread_id, limit=1))
        self.assertEqual([turn.turn_id for turn in first_page.turns], [done.turn_id])
        self.assertEqual(first_page.next_cursor, "turns-after-1")

    async def test_a_running_turn_is_listed_with_its_items_so_far(self) -> None:
        # EC-15.
        from vidbyte.lib.enums.codex import CodexTurnStatus

        thread = self.server.seed_thread(completed_turns=1, running_turn=True)
        running = thread.turns[-1]
        running.items.append({"type": "userMessage", "id": "item-user-run", "content": [{"type": "text", "text": "keep going"}]})
        host = await self.opened()
        page = await self.call(host.list_codex_turns(thread.thread_id))
        last = page.turns[-1]
        self.assertEqual((last.turn_id, last.status, last.completed_at, last.final_response), (running.turn_id, CodexTurnStatus.RUNNING, None, ""))
        self.assertEqual([item.type for item in last.items], ["userMessage"])

    async def test_a_not_loaded_thread_is_read_without_loading_it(self) -> None:
        # EC-16, INV-33: no resume and no turn start; Codex still reports notLoaded afterwards.
        from vidbyte.lib.enums.codex import CodexThreadStatus

        thread = self.server.seed_thread(completed_turns=2)
        thread.status = "notLoaded"
        host = await self.opened()
        page = await self.call(host.list_codex_turns(thread.thread_id))
        self.assertEqual(len(page.turns), 2)
        self.assertFalse({"thread/resume", "turn/start"} & set(self.sent_methods()), self.sent_methods())
        info = await self.call(host.read_codex_thread(thread.thread_id))
        self.assertEqual(info.status, CodexThreadStatus.NOT_LOADED)

    async def test_an_unknown_thread_is_not_found_before_any_turn_listing(self) -> None:
        # AC-16, INV-7.
        host = await self.opened()
        error = await self.assert_codex_error(host.list_codex_turns("thr-never"), "codex.session_not_found")
        self.assertEqual(error.operation, "list_codex_turns")
        self.assertIn("thr-never", error.message)
        self.assertEqual(self.sent_methods(), ["thread/read"])


@requires_sdk
class CodexThreadCompactTests(_HelperCase):
    """AC-17, AC-18, AC-38, EC-42, INV-18 and INV-33: what compact sends for each thread status."""

    async def test_an_idle_or_failed_thread_is_compacted_without_a_goal_check_or_resume(self) -> None:
        # AC-17: one thread/compact/start, no preflight and no resume.
        host = await self.opened()
        for status in (None, "systemError"):
            with self.subTest(status=status):
                thread = self.server.seed_thread(completed_turns=1)
                thread.status = status
                self.remark()
                self.assertIsNone(await self.call(host.compact_codex_thread(thread.thread_id)))
                self.assertEqual(self.sent_methods(), ["thread/read", "thread/compact/start"])
                self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id})
                self.assertFalse(PREFLIGHT_METHODS & set(self.sent_methods()))

    async def test_a_not_loaded_thread_without_a_goal_is_checked_then_resumed_as_continue_resumes(self) -> None:
        # AC-18, INV-18, INV-20, INV-33: get_codex_goal never loads; compact resumes exactly as continue does.
        thread = self.server.seed_thread(completed_turns=1)
        thread.status = "notLoaded"
        host = await self.opened()
        self.assertIsNone(await self.call(host.get_codex_goal(thread.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id})
        self.assertEqual(thread.status, "notLoaded")

        self.remark()
        self.assertIsNone(await self.call(host.compact_codex_thread(thread.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get", "thread/resume", "thread/compact/start"])
        compact_resume = dict(self.sent()[2].params)

        # The oracle: the resume continue_codex_thread sends with no overrides, on another notLoaded thread.
        other = self.server.seed_thread(completed_turns=1)
        other.status = "notLoaded"
        await self.call(host.continue_codex_thread(other.thread_id, "Carry on."))
        continue_resume = dict(self.server.matching("thread/resume", lambda params: params["threadId"] == other.thread_id)[0].params)
        self.assertEqual(compact_resume.pop("threadId"), thread.thread_id)
        self.assertEqual(continue_resume.pop("threadId"), other.thread_id)
        self.assertEqual(compact_resume, continue_resume)

    async def test_a_not_loaded_thread_with_a_complete_goal_is_loaded_and_compacted(self) -> None:
        # INV-18, D-13: complete is the one resumable goal status.
        thread = self.server.seed_thread(completed_turns=1)
        thread.status = "notLoaded"
        thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", "complete")
        host = await self.opened()
        self.assertIsNone(await self.call(host.compact_codex_thread(thread.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get", "thread/resume", "thread/compact/start"])

    async def test_a_not_loaded_thread_with_an_unfinished_goal_is_refused_before_any_resume(self) -> None:
        # AC-38, EC-42: the message names the thread and the goal's wire status.
        host = await self.opened()
        for status in UNFINISHED_GOAL_STATUSES:
            with self.subTest(status=status):
                thread = self.server.seed_thread(completed_turns=1)
                thread.status = "notLoaded"
                thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", status)
                self.remark()
                error = await self.assert_codex_error(host.compact_codex_thread(thread.thread_id), "codex.goal_unfinished")
                self.assertEqual(error.operation, "compact_codex_thread")
                self.assertEqual(error.message, GOAL_UNFINISHED_MESSAGE.format(status=status) + thread_suffix(thread.thread_id))
                self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
                self.assertEqual(thread.status, "notLoaded")
                # The reservation was released: a second compact meets the same goal check, not session_busy.
                await self.assert_codex_error(host.compact_codex_thread(thread.thread_id), "codex.goal_unfinished")


@requires_sdk
class CodexThreadBusyAndUnknownTests(_HelperCase):
    """AC-19 to AC-22, EC-17, EC-18, EC-22, EC-23, INV-7, INV-8 and INV-19."""

    async def test_this_hosts_own_running_turn_refuses_compact_and_delete_before_any_request(self) -> None:
        # AC-19, EC-17.
        host = await self.opened()
        handle = await self.spawn(host)
        self.remark()
        for name in ("compact_codex_thread", "delete_codex_thread"):
            with self.subTest(method=name):
                error = await self.assert_codex_error(getattr(host, name)(handle.thread_id), "codex.session_busy")
                self.assertEqual(error.operation, name)
                self.assertEqual(error.message, BUSY_TEXT + thread_suffix(handle.thread_id))
        self.assertEqual(self.sent(), [])

    async def test_a_thread_codex_reports_active_refuses_compact_and_delete_after_one_read(self) -> None:
        # AC-19, EC-18: another client's turn runs on the thread.
        thread = self.server.seed_thread(completed_turns=1, running_turn=True)
        host = await self.opened()
        for name in ("compact_codex_thread", "delete_codex_thread"):
            with self.subTest(method=name):
                self.remark()
                error = await self.assert_codex_error(getattr(host, name)(thread.thread_id), "codex.session_busy")
                self.assertEqual(error.operation, name)
                self.assertEqual(error.message, RUNNING_THREAD_MESSAGE + thread_suffix(thread.thread_id))
                self.assertEqual(self.sent_methods(), ["thread/read"])
        self.assertIn(thread.thread_id, self.server.threads)

    async def test_an_unknown_thread_is_not_found_and_a_second_delete_finds_nothing(self) -> None:
        # AC-20, AC-22, EC-23, INV-7.
        host = await self.opened()
        for name in ("compact_codex_thread", "delete_codex_thread", "get_codex_goal"):
            with self.subTest(method=name):
                self.remark()
                error = await self.assert_codex_error(getattr(host, name)("thr-never"), "codex.session_not_found")
                self.assertEqual(error.operation, name)
                self.assertIn("thr-never", error.message)
                self.assertEqual(self.sent_methods(), ["thread/read"])

        thread = self.server.seed_thread(completed_turns=1)
        self.remark()
        self.assertIsNone(await self.call(host.delete_codex_thread(thread.thread_id)))
        await self.assert_codex_error(host.delete_codex_thread(thread.thread_id), "codex.session_not_found")
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/delete", "thread/read"])

    async def test_delete_never_resumes_and_a_deleted_thread_is_gone_but_its_usage_stays(self) -> None:
        # AC-21, EC-22, INV-19, D-14.
        host = await self.opened()
        stored = self.server.seed_thread(completed_turns=1)
        stored.status = "notLoaded"
        self.assertIsNone(await self.call(host.delete_codex_thread(stored.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/delete"])
        self.assertEqual(self.sent()[-1].params, {"threadId": stored.thread_id})
        self.assertNotIn(stored.thread_id, self.server.threads)

        # An idle thread this host ran a turn on is deleted too; later reads find nothing, local usage remains.
        self.server.autocomplete = {"final": "Done.", "usage": self.fakes.token_usage((120, 30), (120, 30))}
        handle = await self.spawn(host)
        await self.wait_done(host, handle)
        self.remark()
        self.assertIsNone(await self.call(host.delete_codex_thread(handle.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/delete"])
        await self.assert_codex_error(host.read_codex_thread(handle.thread_id), "codex.session_not_found")
        await self.assert_codex_error(host.continue_codex_thread(handle.thread_id, "Carry on."), "codex.session_not_found")
        usage = await self.call(host.track_codex_thread_usage(handle.thread_id))
        self.assertEqual(usage.thread_id, handle.thread_id)


@requires_sdk
class CodexThreadReservationTests(_HelperCase):
    """AC-23 and INV-9: compact and delete hold the thread, and release it on every outcome."""

    async def test_a_compact_in_flight_holds_the_thread_until_it_ends(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        hold = self.server.hold("thread/compact/start")
        task = asyncio.ensure_future(host.compact_codex_thread(thread.thread_id))
        await asyncio.to_thread(hold.wait_arrived)
        self.remark()
        refused = (
            ("continue_codex_thread", lambda: host.continue_codex_thread(thread.thread_id, "x")),
            ("start_codex_review", lambda: host.start_codex_review(thread.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES))),
            ("compact_codex_thread", lambda: host.compact_codex_thread(thread.thread_id)),
            ("delete_codex_thread", lambda: host.delete_codex_thread(thread.thread_id)),
        )
        for name, start in refused:
            with self.subTest(method=name):
                error = await self.assert_codex_error(start(), "codex.session_busy")
                self.assertEqual(error.operation, name)
        self.assertEqual(self.sent(), [])
        hold.release()
        self.assertIsNone(await self.call(task))
        # Once the compact ends, the thread is free again.
        handle = await self.call(host.continue_codex_thread(thread.thread_id, "Carry on."))
        self.assertEqual(handle.thread_id, thread.thread_id)

    async def test_a_failed_or_cancelled_compact_releases_the_thread(self) -> None:
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        self.server.fail("thread/compact/start", self.fakes.FakeRpcError(-32603, "compaction failed"), times=1)
        error = await self.assert_codex_error(host.compact_codex_thread(thread.thread_id), "codex.api_error")
        self.assertEqual(error.operation, "compact_codex_thread")

        hold = self.server.hold("thread/compact/start")
        task = asyncio.ensure_future(host.compact_codex_thread(thread.thread_id))
        await asyncio.to_thread(hold.wait_arrived)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        hold.release()
        await asyncio.to_thread(hold.wait_responded)
        # Neither outcome kept the reservation: the next compact and a delete both go through.
        self.assertIsNone(await self.call(host.compact_codex_thread(thread.thread_id)))
        self.assertIsNone(await self.call(host.delete_codex_thread(thread.thread_id)))


if __name__ == "__main__":
    unittest.main()
