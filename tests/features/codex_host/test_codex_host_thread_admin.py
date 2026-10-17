"""FILE: tests/features/codex_host/test_codex_host_thread_admin.py

PURPOSE: Proves the slice-2 thread functions over the in-memory app-server: archive, unarchive and rename with their typed calls and retry rules; revert changing Codex's history only; inject sending the items exactly as given; the history-changing calls refusing a busy or running thread before they send; the background-terminal listing and clean without loading a thread; the account-wide content search over every top-level source; the child listing over every source kind; and the load guard that lets a not-loaded thread with a paused, blocked, usage-limited, budget-limited or complete goal (or none) load, and refuses an active one.
ROLE IN CODEBASE: Thread-administration layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-30 to AC-33, INV-7, INV-12, INV-34 to INV-40, EC-42 to EC-51, EC-56, EC-57). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: A real CodexHost talks to FakeAppServer through FeatureHostCase. The fake's thread/search and child thread/list apply Codex's default interactive-only source filter when sourceKinds is absent, so a host that drops the key finds nothing. Concurrency on one thread is proved with a held thread/read: the second call must be refused while the first one waits.
COMMON MODIFICATION PATTERNS: Add a function to LOAD_GUARDED when another call gains the INV-12 load, and a goal status to the EC-57 table when CODEX_HOST_LOAD_SAFE_GOAL_STATUSES gains one.
KNOWN EDGE CASES: The fake's thread/revert, thread/inject_items, thread/settings/update and thread/memoryMode/set refuse a notLoaded thread with -32600 (spec A-4), so a host that skips the load fails the EC-57 table. A thread seeded with a running turn reports active, the way another client's running turn shows.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3 and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_thread_admin.py
"""

from __future__ import annotations

import asyncio
import copy
import unittest
from typing import Any

from tests.features.codex_host.codex_host_feature_fakes import background_terminal
from tests.features.codex_host.codex_host_feature_support import (
    EVERY_SOURCE_KIND,
    FEATURE_NUMBERS,
    HELPER_SOURCE_KINDS,
    ITEM_CANARY,
    LOAD_GOAL_UNFINISHED_CAUSE,
    LOAD_GOAL_UNFINISHED_MESSAGE,
    LOAD_GOAL_UNFINISHED_NEXT_STEP,
    LOAD_SAFE_GOAL_STATUSES,
    THREAD_RUNNING_MESSAGE,
    assert_packet,
)
from tests.features.codex_host.codex_host_support import BUSY_TEXT, WAIT_SECONDS, FeatureHostCase, assert_no_canary, mapped_summary, requires_sdk, thread_suffix

RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
# EC-57: the four functions that load a not-loaded thread through the INV-12 guard.
LOAD_GUARDED = ("update_codex_thread_settings", "set_codex_thread_memory_mode", "revert_codex_thread", "inject_codex_items")
ITEMS = [
    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": ITEM_CANARY}]},
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Noted."}]},
]


def _spawned_by(parent: str, depth: int = 1) -> dict[str, Any]:
    return {"subAgent": {"thread_spawn": {"depth": depth, "parent_thread_id": parent}}}


class _AdminCase(FeatureHostCase):
    """Shared steps: the sent (method, params) pairs and a thread Codex reports as not loaded with a goal."""

    def sent_pairs(self) -> list[tuple[str, dict[str, Any]]]:
        return [(request.method, request.params) for request in self.sent()]

    def stored_not_loaded(self, goal_status: str | None, completed_turns: int = 2) -> Any:
        thread = self.server.seed_thread(completed_turns=completed_turns)
        thread.status = "notLoaded"
        if goal_status is not None:
            thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", goal_status)
        return thread


@requires_sdk
class CodexArchiveRenameHostTests(_AdminCase):
    """AC-30, INV-7, INV-34, INV-35, EC-42 and EC-43."""

    async def test_archive_unarchive_and_rename_send_their_one_call_each(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadInfo

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        self.assertIsNone(await self.call(host.archive_codex_thread(thread.thread_id)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/archive"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id})
        self.assertIn(thread.thread_id, self.server.archived)
        # INV-35: unarchive reads nothing first and returns the thread's CodexThreadInfo.
        self.remark()
        info = await self.call(host.unarchive_codex_thread(thread.thread_id))
        self.assertEqual(self.sent_pairs(), [("thread/unarchive", {"threadId": thread.thread_id})])
        self.assertIsInstance(info, CodexThreadInfo)
        self.assertEqual(info, await self.call(host.read_codex_thread(thread.thread_id)))
        self.remark()
        self.assertIsNone(await self.call(host.rename_codex_thread(thread.thread_id, "New name")))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/name/set"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "name": "New name"})
        self.assertEqual(self.server.threads[thread.thread_id].name, "New name")

    async def test_an_overloaded_rename_is_retried_and_an_overloaded_archive_is_not(self) -> None:
        # INV-7: thread/name/set is in CODEX_HOST_RETRIED_METHODS; thread/archive is not.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        self.server.fail("thread/name/set", self.fakes.overloaded_error(), times=1)
        await self.call(host.rename_codex_thread(thread.thread_id, "New name"))
        self.assertEqual(self.count("thread/name/set"), 2)
        self.server.fail("thread/archive", self.fakes.overloaded_error(), times=1)
        error = await self.codex_error(host.archive_codex_thread(thread.thread_id), "codex.api_error")
        self.assertEqual(error.operation, "archive_codex_thread")
        self.assertEqual(self.count("thread/archive"), 1)

    async def test_unarchiving_a_thread_that_is_not_archived_is_codexs_refusal(self) -> None:
        # EC-43, A-8: the two causes cannot be told apart, so Codex's own message is shown.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        error = await self.codex_error(host.unarchive_codex_thread(thread.thread_id), "codex.api_error")
        self.assertEqual(error.operation, "unarchive_codex_thread")
        self.assertIn(RPC_ERROR_TEXT.format(method="thread/unarchive", code=-32600, message=f"thread is not archived: {thread.thread_id}"), error.message)
        self.assertEqual(self.sent_methods(), ["thread/unarchive"])

    async def test_an_unknown_thread_stops_rename_and_archive_at_their_read(self) -> None:
        # Section 9.2 "not found": the exists check refuses before the call.
        host = await self.opened()
        for name, call in (("archive_codex_thread", lambda: host.archive_codex_thread("thr-never")), ("rename_codex_thread", lambda: host.rename_codex_thread("thr-never", "New name"))):
            with self.subTest(function=name):
                self.remark()
                error = await self.codex_error(call(), "codex.session_not_found")
                self.assertEqual(error.operation, name)
                self.assertEqual(self.sent_methods(), ["thread/read"])


@requires_sdk
class CodexHistoryChangeHostTests(_AdminCase):
    """AC-31, AC-32, INV-34, INV-36, INV-37, EC-42, EC-44 to EC-46."""

    async def test_revert_sends_one_call_after_the_read_and_returns_codexs_thread(self) -> None:
        # AC-31, INV-36: history only; Codex keeps the turns before beforeTurnId.
        from vidbyte.lib.dataclasses.codex_host import CodexThreadInfo

        thread = self.server.seed_thread(completed_turns=3)
        second = thread.turns[1].turn_id
        host = await self.opened()
        info = await self.call(host.revert_codex_thread(thread.thread_id, before_turn_id=second))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/revert"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "beforeTurnId": second})
        self.assertIsInstance(info, CodexThreadInfo)
        self.assertEqual(info.thread_id, thread.thread_id)
        self.assertEqual(len(self.server.threads[thread.thread_id].turns), 1)

    async def test_revert_leaves_the_snapshots_this_host_tracked_and_codex_lists_the_new_history(self) -> None:
        # EC-44: the registry's ended snapshots are not rewritten.
        host = await self.opened()
        handle = await self.spawn(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        snapshot = await self.wait_done(host, handle)
        await self.call(host.revert_codex_thread(handle.thread_id, before_turn_id=handle.turn_id))
        self.assertEqual(await self.call(host.wait_codex_turn(handle)), snapshot)
        page = await self.call(host.list_codex_turns(handle.thread_id))
        self.assertNotIn(handle.turn_id, [turn.turn_id for turn in page.turns])

    async def test_revert_with_an_unknown_turn_is_codexs_refusal(self) -> None:
        # EC-45: Codex refuses the unknown beforeTurnId, and its message is shown.
        thread = self.server.seed_thread(completed_turns=2)
        host = await self.opened()
        error = await self.codex_error(host.revert_codex_thread(thread.thread_id, before_turn_id="turn-never"), "codex.api_error")
        self.assertEqual(error.operation, "revert_codex_thread")
        expected = RPC_ERROR_TEXT.format(method="thread/revert", code=-32600, message="unknown beforeTurnId: turn-never")
        self.assertEqual(mapped_summary(self, error), expected + thread_suffix(thread.thread_id))

    async def test_inject_sends_the_items_exactly_as_given_and_logs_none_of_them(self) -> None:
        # AC-32, INV-37, NFR-7: one thread/inject_items with the items in order; the item canary reaches no log.
        records = self.capture_logs()
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        self.assertIsNone(await self.call(host.inject_codex_items(thread.thread_id, ITEMS)))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/inject_items"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "items": ITEMS})
        self.assertEqual(self.server.injected[thread.thread_id], ITEMS)
        assert_no_canary(self, [record.getMessage() for record in records], (ITEM_CANARY,))

    async def test_inject_sends_a_copy_so_a_later_change_by_the_caller_changes_nothing(self) -> None:
        # INV-37, section 9.1 record 14: the record stores JSON round-trip copies when it is built.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        items = copy.deepcopy(ITEMS)
        hold = self.server.hold("thread/read", lambda params: params.get("threadId") == thread.thread_id)
        injecting = asyncio.ensure_future(host.inject_codex_items(thread.thread_id, items))
        await asyncio.to_thread(hold.wait_arrived)
        items[0]["role"] = "assistant"
        items.append({"type": "message", "role": "user", "content": []})
        hold.release()
        await self.call(injecting)
        self.assertEqual(self.server.matching("thread/inject_items")[-1].params["items"], ITEMS)

    async def test_inject_refuses_bad_item_lists_before_any_request(self) -> None:
        # AC-32, EC-46: empty, a missing type, non-JSON values and too many items are refused when the record is built.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        maximum = FEATURE_NUMBERS["CODEX_HOST_INJECT_MAX_ITEMS"]
        rows = (
            ("empty", []),
            ("no type", [{"role": "user"}]),
            ("not a number JSON allows", [{"type": "message", "weight": float("nan")}]),
            ("not JSON", [{"type": "message", "value": object()}]),
            ("too many", [{"type": "message"}] * (maximum + 1)),
        )
        for label, items in rows:
            with self.subTest(items=label):
                await self.refused_locally(host.inject_codex_items(thread.thread_id, items), "items")

    async def test_history_changing_calls_refuse_a_thread_this_host_is_running_before_any_request(self) -> None:
        # INV-34 step 1: require_idle runs before the first await, so nothing is sent.
        from vidbyte.lib.errors import CodexAgentError

        host = await self.opened()
        handle = await self.spawn(host)
        calls = (
            ("archive_codex_thread", lambda: host.archive_codex_thread(handle.thread_id)),
            ("revert_codex_thread", lambda: host.revert_codex_thread(handle.thread_id, before_turn_id=handle.turn_id)),
            ("inject_codex_items", lambda: host.inject_codex_items(handle.thread_id, ITEMS)),
        )
        for name, call in calls:
            with self.subTest(function=name):
                self.remark()
                with self.assertRaises(CodexAgentError) as caught:
                    await asyncio.wait_for(call(), WAIT_SECONDS)
                self.assertEqual((caught.exception.failure_code, caught.exception.operation), ("codex.session_busy", name))
                self.assertEqual(mapped_summary(self, caught.exception), BUSY_TEXT + thread_suffix(handle.thread_id))
                self.assertEqual(self.sent_methods(), [])

    async def test_history_changing_calls_refuse_a_thread_codex_reports_running(self) -> None:
        # EC-42, INV-34 step 2: idle_status reads active, from any client, and refuses with the running message.
        thread = self.server.seed_thread(completed_turns=1, running_turn=True)
        host = await self.opened()
        calls = (
            ("archive_codex_thread", lambda: host.archive_codex_thread(thread.thread_id)),
            ("revert_codex_thread", lambda: host.revert_codex_thread(thread.thread_id, before_turn_id=thread.turns[0].turn_id)),
            ("inject_codex_items", lambda: host.inject_codex_items(thread.thread_id, ITEMS)),
        )
        for name, call in calls:
            with self.subTest(function=name):
                self.remark()
                error = await self.codex_error(call(), "codex.session_busy")
                self.assertEqual(error.operation, name)
                self.assertTrue(mapped_summary(self, error).startswith(THREAD_RUNNING_MESSAGE.format(operation=name)), error.message)
                self.assertEqual(self.sent_methods(), ["thread/read"])

    async def test_a_second_history_change_on_the_same_thread_is_refused_while_the_first_waits(self) -> None:
        # INV-34 steps 1 and 5: the reservation is taken before the first await and released in finally.
        from vidbyte.lib.errors import CodexAgentError

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        hold = self.server.hold("thread/read", lambda params: params.get("threadId") == thread.thread_id)
        archiving = asyncio.ensure_future(host.archive_codex_thread(thread.thread_id))
        await asyncio.to_thread(hold.wait_arrived)
        sent = len(self.server.requests)
        with self.assertRaises(CodexAgentError) as caught:
            await asyncio.wait_for(host.inject_codex_items(thread.thread_id, ITEMS), WAIT_SECONDS)
        self.assertEqual(caught.exception.failure_code, "codex.session_busy")
        self.assertEqual(len(self.server.requests), sent)
        hold.release()
        await self.call(archiving)
        await self.call(host.inject_codex_items(thread.thread_id, ITEMS))
        self.assertEqual(self.count("thread/inject_items"), 1)


@requires_sdk
class CodexLoadGuardHostTests(_AdminCase):
    """EC-57, INV-12, D-14, A-13: the load guard of the four functions that load a not-loaded thread."""

    def guarded_calls(self, host: Any, thread: Any) -> dict[str, tuple[str, Any]]:
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.enums.codex import CodexMemoryMode, CodexReasoningEffort

        return {
            "update_codex_thread_settings": ("thread/settings/update", lambda: host.update_codex_thread_settings(thread.thread_id, CodexThreadSettingsUpdate(effort=CodexReasoningEffort.HIGH))),
            "set_codex_thread_memory_mode": ("thread/memoryMode/set", lambda: host.set_codex_thread_memory_mode(thread.thread_id, CodexMemoryMode.DISABLED)),
            "revert_codex_thread": ("thread/revert", lambda: host.revert_codex_thread(thread.thread_id, before_turn_id=thread.turns[1].turn_id)),
            "inject_codex_items": ("thread/inject_items", lambda: host.inject_codex_items(thread.thread_id, ITEMS)),
        }

    async def test_a_safe_goal_or_no_goal_loads_the_thread_and_keeps_its_status(self) -> None:
        host = await self.opened()
        for status in (*sorted(LOAD_SAFE_GOAL_STATUSES), None):
            for name in LOAD_GUARDED:
                with self.subTest(goal=status, function=name):
                    thread = self.stored_not_loaded(status)
                    method, call = self.guarded_calls(host, thread)[name]
                    self.remark()
                    await self.call(call())
                    self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get", "thread/resume", method])
                    self.assertEqual(thread.goal["status"] if thread.goal else None, status)

    async def test_an_active_goal_is_refused_before_the_thread_is_loaded(self) -> None:
        host = await self.opened()
        for name in LOAD_GUARDED:
            with self.subTest(function=name):
                thread = self.stored_not_loaded("active")
                _, call = self.guarded_calls(host, thread)[name]
                self.remark()
                error = await self.codex_error(call(), "codex.goal_unfinished")
                assert_packet(
                    self,
                    error,
                    operation=name,
                    code="codex.goal_unfinished",
                    message=LOAD_GOAL_UNFINISHED_MESSAGE.format(status="active", operation=name),
                    cause=LOAD_GOAL_UNFINISHED_CAUSE.format(operation=name),
                    next_step=LOAD_GOAL_UNFINISHED_NEXT_STEP,
                    thread_id=thread.thread_id,
                )
                self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
                self.assertEqual(thread.status, "notLoaded")


@requires_sdk
class CodexTerminalSearchChildHostTests(_AdminCase):
    """AC-33, INV-38 to INV-40, EC-47 to EC-51 and EC-56."""

    async def test_background_terminals_are_listed_and_cleaned_after_one_exists_check(self) -> None:
        # AC-33, INV-38: the listing maps each terminal; the clean returns None and Codex forgets them.
        from vidbyte.lib.dataclasses.codex_host_features import CodexBackgroundTerminal, CodexBackgroundTerminalPage

        thread = self.server.seed_thread(completed_turns=1)
        self.server.background_terminals[thread.thread_id] = [background_terminal("proc-1", "item-1", osPid=4242, cpuPercent=1.5, rssKb=2048), background_terminal("proc-2", "item-2", command="pytest -x")]
        host = await self.opened()
        page = await self.call(host.list_codex_background_terminals(thread.thread_id))
        self.assertEqual(self.sent_pairs()[-1], ("thread/backgroundTerminals/list", {"threadId": thread.thread_id}))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/backgroundTerminals/list"])
        cwd = self.fakes.DEFAULT_CWD
        expected = (
            CodexBackgroundTerminal(process_id="proc-1", item_id="item-1", command="npm run dev", cwd=cwd, os_pid=4242, cpu_percent=1.5, rss_kb=2048),
            CodexBackgroundTerminal(process_id="proc-2", item_id="item-2", command="pytest -x", cwd=cwd),
        )
        self.assertEqual(page, CodexBackgroundTerminalPage(terminals=expected, next_cursor=""))
        self.remark()
        await self.call(host.list_codex_background_terminals(thread.thread_id, cursor="cursor-2", limit=10))
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "cursor": "cursor-2", "limit": 10})
        self.remark()
        self.assertIsNone(await self.call(host.clean_codex_background_terminals(thread.thread_id)))
        self.assertEqual(self.sent_pairs(), [("thread/read", self.sent()[0].params), ("thread/backgroundTerminals/clean", {"threadId": thread.thread_id})])
        self.assertNotIn(thread.thread_id, self.server.background_terminals)

    async def test_terminals_of_a_not_loaded_thread_are_listed_without_loading_it(self) -> None:
        # EC-47: loading could resume work, so there is no load.
        thread = self.stored_not_loaded("active")
        host = await self.opened()
        page = await self.call(host.list_codex_background_terminals(thread.thread_id))
        self.assertEqual(page.terminals, ())
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/backgroundTerminals/list"])
        self.assertEqual(thread.status, "notLoaded")

    async def test_search_names_every_top_level_source_and_finds_this_hosts_threads(self) -> None:
        # AC-33, INV-39, EC-56, D-35: sourceKinds is always the helper source kinds, so appServer and exec threads are hits; sub-agents are not.
        made_here = self.server.seed_thread(completed_turns=1)
        made_here.name = "Fix the login flow"
        by_exec = self.server.new_thread(source="exec", name="login retries")
        self.server.new_thread(source=_spawned_by(made_here.thread_id), parent_thread_id=made_here.thread_id, name="login helper")
        self.server.new_thread(source="cli", name="unrelated")
        host = await self.opened()
        page = await self.call(host.search_codex_thread_content("login"))
        self.assertEqual(self.sent_methods(), ["thread/search"])
        params = self.sent()[0].params
        self.assertEqual(params["searchTerm"], "login")
        self.assertEqual(sorted(params["sourceKinds"]), sorted(HELPER_SOURCE_KINDS))
        self.assertIn(params.get("archived"), (None, False))
        self.assertEqual(sorted(hit.thread.thread_id for hit in page.hits), sorted((made_here.thread_id, by_exec.thread_id)))
        for hit in page.hits:
            self.assertEqual(hit.snippet, self.server.search_snippet)
            self.assertEqual(hit.thread, await self.call(host.read_codex_thread(hit.thread.thread_id)))
        self.assertEqual((page.next_cursor, page.backwards_cursor), ("", ""))

    async def test_an_archived_search_sends_its_flag_and_page_fields(self) -> None:
        # INV-39: {searchTerm, sourceKinds, archived?, cursor?, limit?}.
        archived = self.server.new_thread(source="cli", name="old login work")
        self.server.archived.add(archived.thread_id)
        host = await self.opened()
        page = await self.call(host.search_codex_thread_content("login", archived=True, cursor="cursor-2", limit=5))
        params = self.sent()[0].params
        self.assertEqual({key: params.get(key) for key in ("searchTerm", "archived", "cursor", "limit")}, {"searchTerm": "login", "archived": True, "cursor": "cursor-2", "limit": 5})
        self.assertEqual([hit.thread.thread_id for hit in page.hits], [archived.thread_id])

    async def test_child_listing_names_the_parent_or_ancestor_and_every_source_kind(self) -> None:
        # AC-33, INV-40, EC-49: direct children by parentThreadId, every depth by ancestorThreadId; an unknown kind is not listed.
        parent = self.server.seed_thread(completed_turns=1)
        child = self.server.new_thread(source=_spawned_by(parent.thread_id), parent_thread_id=parent.thread_id)
        grandchild = self.server.new_thread(source=_spawned_by(child.thread_id, depth=2), parent_thread_id=child.thread_id)
        self.server.new_thread(source="futureSourceKind", parent_thread_id=parent.thread_id)
        host = await self.opened()
        page = await self.call(host.list_codex_child_threads(parent.thread_id))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/list"])
        params = self.sent()[-1].params
        self.assertEqual(params["parentThreadId"], parent.thread_id)
        self.assertNotIn("ancestorThreadId", params)
        self.assertEqual(sorted(params["sourceKinds"]), sorted(EVERY_SOURCE_KIND))
        self.assertEqual([thread.thread_id for thread in page.threads], [child.thread_id])
        self.assertEqual(page.threads[0], await self.call(host.read_codex_thread(child.thread_id)))
        self.remark()
        deep = await self.call(host.list_codex_child_threads(parent.thread_id, descendants=True, cursor="cursor-2", limit=5))
        params = self.sent()[-1].params
        self.assertEqual(params["ancestorThreadId"], parent.thread_id)
        self.assertNotIn("parentThreadId", params)
        self.assertEqual((params.get("cursor"), params.get("limit")), ("cursor-2", 5))
        self.assertEqual(sorted(thread.thread_id for thread in deep.threads), sorted((child.thread_id, grandchild.thread_id)))

    async def test_an_unknown_parent_stops_at_the_exists_check_and_an_overloaded_listing_is_retried(self) -> None:
        # EC-50, INV-7: thread/list is typed and retried.
        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        error = await self.codex_error(host.list_codex_child_threads("thr-never"), "codex.session_not_found")
        self.assertEqual(error.operation, "list_codex_child_threads")
        self.assertEqual(self.sent_methods(), ["thread/read"])
        self.server.fail("thread/list", self.fakes.overloaded_error(), times=1)
        self.remark()
        await self.call(host.list_codex_child_threads(parent.thread_id))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/list", "thread/list"])

    async def test_bad_page_and_query_arguments_are_refused_before_any_request(self) -> None:
        # EC-48, EC-51: the listing rule for limit and cursor, and a non-blank query.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        rows = (
            ("query", lambda: host.search_codex_thread_content("   ")),
            ("query", lambda: host.search_codex_thread_content("")),
            ("limit", lambda: host.search_codex_thread_content("login", limit=0)),
            ("limit", lambda: host.list_codex_background_terminals(thread.thread_id, limit=1001)),
            ("limit", lambda: host.list_codex_child_threads(thread.thread_id, limit=0)),
            ("cursor", lambda: host.list_codex_child_threads(thread.thread_id, cursor=5)),
        )
        for field_name, call in rows:
            with self.subTest(field=field_name):
                await self.refused_locally(call(), field_name)


if __name__ == "__main__":
    unittest.main()
