"""FILE: tests/features/codex_host/test_codex_host_review_goals.py

PURPOSE: Proves reviews and goal runs over the in-memory app-server: one review/start with no retry, the two registration races a raw review/start opens (a turn finished before the host subscribed, and a final item dropped before it subscribed), detached delivery, the goal start and budget order, the goal table, openai-codex's two goal cleanup orders, and a runtime that never activates goal mode.
ROLE IN CODEBASE: Review and goal layer of tests/features/codex_host/ (spec AC-19, AC-20, INV-25, D-8, D-23, EC-39 to EC-42, EC-44, EC-46, EC-74). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake's before_response hook writes notifications ahead of the review/start answer, which is exactly when the real openai-codex router drops them, and a Hold on the registration read-back fixes the order of the second race. Goal states are real openai-codex _GoalOperationState objects that log finish() and wake_notification_reader(), so cleanup order is read from the fake's log.
COMMON MODIFICATION PATTERNS: Add a goal status row to GOAL_TABLE when spec section 9.2 changes the goal table; add a review race by scripting the notes the fake writes before or after the review/start answer.
KNOWN EDGE CASES: The SDK's own goal cursor may call finish() itself, so a finished run's log is checked for finish, wake and unregister as its last three goal calls rather than as the only ones. Review turns get no usage in these scripts, so their usage is reported unavailable.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-25), 8.1 (D-8, D-23) and 9.2 (goal finish rule and goal table).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_review_goals.py
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import WAIT_SECONDS, HostTestCase, requires_sdk

GOAL_CALLS = ("cancel_goal_operation", "finish", "wake_notification_reader", "unregister_goal_operation")
STREAM_CLOSE = ["finish", "wake_notification_reader", "unregister_goal_operation"]
START_FAILURE_CLEANUP = ["cancel_goal_operation", "finish", "unregister_goal_operation"]

# Spec section 9.2 goal table: goal status at finish -> (snapshot status, goal_status value, problem code).
GOAL_TABLE = (
    ("complete", "completed", "complete", None),
    ("budgetLimited", "interrupted", "budgetLimited", "codex.budget_exhausted"),
    ("usageLimited", "interrupted", "usageLimited", "codex.usage_limited"),
    ("paused", "interrupted", "paused", None),
    ("blocked", "interrupted", "blocked", None),
)


def _goal_calls(server: Any, thread_id: str) -> list[str]:
    return [entry[0] for entry in server.kinds(*GOAL_CALLS) if entry[1] == thread_id]


def _include_turns_reads_after_review(server: Any, thread_id: str) -> int:
    methods = [(request.method, request.params) for request in server.requests]
    start = next(index for index, (method, _) in enumerate(methods) if method == "review/start")
    return sum(1 for method, params in methods[start:] if method == "thread/read" and params.get("threadId") == thread_id and params.get("includeTurns"))


@requires_sdk
class CodexHostReviewTests(HostTestCase):
    """AC-19, D-23: a raw review/start, sent once, tracked to a terminal snapshot."""

    def _commit_target(self) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        return CodexReviewTarget(kind=CodexReviewTargetKind.COMMIT, sha="0a1b2c3", title="Fix the parser")

    async def test_a_review_is_sent_once_with_its_target_and_tracked_to_completion(self) -> None:
        # AC-19, D-2: review has no model check, and an overloaded answer is not retried.
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        handle = await asyncio.wait_for(host.start_codex_review(seeded.thread_id, self._commit_target()), WAIT_SECONDS)
        review = self.server.matching("review/start")[0].params
        self.assertEqual(review["threadId"], seeded.thread_id)
        self.assertEqual(review["target"], {"type": "commit", "sha": "0a1b2c3", "title": "Fix the parser"})
        self.assertEqual(self.count("model/list"), 0)
        self.assertEqual((handle.thread_id, handle.turn_id), (seeded.thread_id, seeded.turns[-1].turn_id))
        self.server.complete_turn(seeded.thread_id, handle.turn_id, final="Looks good to merge.")
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.result.final_response, "Looks good to merge.")

        other = self.server.seed_thread(completed_turns=1)
        self.server.fail("review/start", self.fakes.overloaded_error(), times=1)
        await self.assert_codex_error(host.start_codex_review(other.thread_id, self._commit_target()), "codex.api_error")
        self.assertEqual(self.count("review/start", lambda params: params["threadId"] == other.thread_id), 1)

    async def test_a_review_turn_that_finished_before_registration_is_read_back(self) -> None:
        # AC-19, EC-44, D-23: the router drops events written before the review/start answer.
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        self.server.before_response(
            "review/start",
            lambda params, result: self.server.completion_notes(params["threadId"], result["turn"]["id"], final="Already reviewed: no issues."),
        )
        handle = await asyncio.wait_for(host.start_codex_review(seeded.thread_id, self._commit_target()), WAIT_SECONDS)
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.result.final_response, "Already reviewed: no issues.")
        self.assertFalse(snapshot.result.usage_available)

    async def test_a_review_whose_final_item_was_dropped_is_completed_from_the_completion_read_back(self) -> None:
        # AC-19, EC-44, D-23: turn/completed arrives after registration, but its final item/completed did not.
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        dropped: dict[str, Any] = {}

        def write_only_the_item(params: dict[str, Any], result: Any) -> list[Any]:
            dropped["turn_id"], dropped["item"] = result["turn"]["id"], self.server.final_item("Two issues found.")
            return [self.server.item_note(params["threadId"], dropped["turn_id"], dropped["item"])]

        self.server.before_response("review/start", write_only_the_item)
        read_back = self.server.hold("thread/read", lambda params: bool(params.get("includeTurns")) and bool(self.server.matching("review/start")))
        task = asyncio.ensure_future(host.start_codex_review(seeded.thread_id, self._commit_target()))
        await asyncio.to_thread(read_back.wait_arrived)
        read_back.release()
        await asyncio.to_thread(read_back.wait_responded)
        handle = await asyncio.wait_for(task, WAIT_SECONDS)
        self.assertEqual(handle.turn_id, dropped["turn_id"])

        # Codex stores the item and completes the turn only now, after the registration read-back saw it running.
        seeded.find_turn(dropped["turn_id"]).items.append(dropped["item"])
        self.server.complete_turn(seeded.thread_id, dropped["turn_id"], final=None)
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.result.final_response, "Two issues found.")
        self.assertFalse(snapshot.result.usage_available)
        self.assertEqual(_include_turns_reads_after_review(self.server, seeded.thread_id), 2)

    async def test_a_detached_review_is_tracked_on_the_new_review_thread(self) -> None:
        # EC-46: Codex reviews in a new thread, which the handle names.
        from vidbyte.lib.enums.codex import CodexReviewDelivery

        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        handle = await asyncio.wait_for(host.start_codex_review(seeded.thread_id, self._commit_target(), delivery=CodexReviewDelivery.DETACHED), WAIT_SECONDS)
        self.assertEqual(self.server.matching("review/start")[0].params["delivery"], "detached")
        self.assertNotEqual(handle.thread_id, seeded.thread_id)
        self.assertEqual(handle.turn_id, self.server.threads[handle.thread_id].turns[0].turn_id)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Reviewed in its own thread.")
        self.assert_problem(await self.wait_done(host, handle), "completed", None)


@requires_sdk
class CodexHostGoalTests(HostTestCase):
    """AC-20, INV-25 and D-8: goal start, budget, the goal table and both cleanup orders."""

    async def _spawn_goal(self, host: Any, token_budget: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        request = CodexSpawnRequest(goal=CodexGoal(objective="Ship the release notes.", token_budget=token_budget))
        return await asyncio.wait_for(host.spawn_codex_thread(request), WAIT_SECONDS)

    async def test_a_goal_spawn_starts_goal_mode_then_sets_the_budget_once(self) -> None:
        # AC-20, INV-25, D-8: no turn/start; the budget set is the raw {threadId, tokenBudget}; the handle names the first goal turn.
        host = await self.open_host()
        handle = await self._spawn_goal(host, token_budget=5000)
        thread_id = handle.thread_id
        on_thread = [request for request in self.server.requests if request.params.get("threadId") == thread_id]
        self.assertEqual([request.method for request in on_thread], ["thread/read", "thread/goal/clear", "thread/goal/set", "thread/goal/set"])
        self.assertEqual((on_thread[2].params.get("objective"), on_thread[2].params.get("status")), ("Ship the release notes.", "active"))
        self.assertEqual(on_thread[3].params, {"threadId": thread_id, "tokenBudget": 5000})
        self.assertEqual(self.count("turn/start"), 0)
        self.assertEqual(handle.turn_id, self.server.threads[thread_id].turns[0].turn_id)

        # A goal without a token budget sends no budget request.
        unbudgeted = await self._spawn_goal(host)
        sets = [request.params for request in self.server.matching("thread/goal/set") if request.params["threadId"] == unbudgeted.thread_id]
        self.assertEqual([("tokenBudget" in params) for params in sets], [False])

    async def test_a_finished_goal_run_maps_the_goal_table_and_closes_its_stream(self) -> None:
        # Section 9.2 goal table, EC-42, INV-25 "Goal close": finish, wake, then unregister, and the watcher exits.
        host = await self.open_host()
        for status, snapshot_status, goal_status, code in GOAL_TABLE:
            with self.subTest(goal_status=status):
                handle = await self._spawn_goal(host)
                thread_id = handle.thread_id
                self.server.emit([self.server.goal_update(thread_id, status)])
                self.server.complete_turn(thread_id, handle.turn_id, final="Release notes shipped.")
                snapshot = await self.wait_done(host, handle)
                self.assert_problem(snapshot, snapshot_status, code)
                self.assertEqual(snapshot.goal_status.value, goal_status)
                self.assertEqual(snapshot.result.final_response, "Release notes shipped.")
                await self.wait_until(lambda thread_id=thread_id: "unregister_goal_operation" in _goal_calls(self.server, thread_id), "the goal stream to close")
                calls = _goal_calls(self.server, thread_id)
                self.assertEqual(calls[-3:], STREAM_CLOSE, calls)
                self.assertNotIn("cancel_goal_operation", calls)
                watchers = {entry[2] for entry in self.server.kinds("next_goal_notification") if entry[1] == thread_id}
                self.assertTrue(watchers)
                for watcher in watchers:
                    await asyncio.to_thread(watcher.join, WAIT_SECONDS)
                    self.assertFalse(watcher.is_alive(), watcher.name)

    async def test_a_goal_update_after_the_last_completion_finishes_the_run(self) -> None:
        # Goal finish rule, fourth trigger: a completed turn while the goal is still active is remembered, not final.
        host = await self.open_host()
        handle = await self._spawn_goal(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Release notes drafted.")
        self.assert_problem(await asyncio.wait_for(host.wait_codex_turn(handle, timeout_seconds=0.2), WAIT_SECONDS), "inProgress", None)
        self.server.emit([self.server.goal_update(handle.thread_id, "complete")])
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.goal_status.value, "complete")
        self.assertEqual(snapshot.result.final_response, "Release notes drafted.")

    async def test_a_failed_budget_set_cleans_up_in_openai_codex_start_failure_order(self) -> None:
        # AC-20, EC-40, EC-74, INV-25: cancel, finish, unregister, no watcher, and the thread is free for a continue.
        from tests.features.codex_host.codex_host_fakes import FakeRpcError

        host = await self.open_host()
        cases = (
            ("budget echo differs", "codex.protocol_mismatch", lambda: setattr(self.server, "budget_echo", 4000)),
            ("budget request fails", "codex.api_error", lambda: self.server.fail("thread/goal/set", FakeRpcError(-32603, "budget rejected"), times=1, predicate=lambda params: "tokenBudget" in params)),
        )
        for label, code, arrange in cases:
            with self.subTest(case=label):
                arrange()
                starts = self.count("thread/start")
                await self.assert_codex_error(self._spawn_goal(host, token_budget=5000), code)
                self.assertEqual(self.count("thread/start"), starts + 1)
                thread_id = list(self.server.threads)[-1]
                self.assertEqual(_goal_calls(self.server, thread_id), START_FAILURE_CLEANUP)
                self.assertEqual([entry for entry in self.server.kinds("next_goal_notification") if entry[1] == thread_id], [])
                self.server.budget_echo = self.fakes._UNSET
                handle = await asyncio.wait_for(host.continue_codex_thread(thread_id, "Write the notes without a goal."), WAIT_SECONDS)
                self.assertEqual(handle.thread_id, thread_id)

    async def test_a_runtime_that_never_activates_goal_mode_fails_the_run(self) -> None:
        # EC-39: a completed turn while the goal status is unknown and never cleared is a protocol mismatch.
        host = await self.open_host()
        self.server.goal_updates = False
        handle = await self._spawn_goal(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done without goal mode.")
        self.assert_problem(await self.wait_done(host, handle), "failed", "codex.protocol_mismatch")


if __name__ == "__main__":
    unittest.main()
