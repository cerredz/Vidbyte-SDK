"""FILE: tests/features/codex_host/test_codex_host_goal_control.py

PURPOSE: Proves the four goal controls over the in-memory app-server: pause_codex_goal sending one user-origin paused set and ending a tracked goal run through its finish rule; resume_codex_goal resuming a paused, blocked, usage-limited or raised budget-limited goal with a status-only set under connection.start and tracking the run, refusing an active, complete or spent goal before thread/resume, and cleaning up a failed start exactly once; edit_codex_goal changing only the objective or budget; and clear_codex_goal clearing a stored goal on an idle thread.
ROLE IN CODEBASE: Goal layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-25 to AC-29, INV-7, INV-30 to INV-34, D-17, D-38, EC-37 to EC-41, EC-58, EC-64). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake's thread/goal/set answers a status-only active set on a goal that was not active by starting a goal turn, as Codex does (A-1, A-19); goal_resume_starts_turn turns that off to elapse the start window. RecordingGoalState logs finish and the fake client logs cancel_goal_operation and unregister_goal_operation, so the cleanup order is read from server.kinds. The no-goal packet is checked with the text of CODEX_HOST_NO_STORED_GOAL_MESSAGE (section 9.2, r4) through codex_host_feature_support; test_codex_host_feature_constants.py pins the name, and run_codex_goal keeps the older CODEX_HOST_NO_GOAL_MESSAGE.
COMMON MODIFICATION PATTERNS: Add a goal status to RESUMABLE or NOT_RESUMABLE when CODEX_HOST_GOAL_RESUME_FROM_STATUSES changes. Keep each request sequence whole; section 9.2 calls its order normative.
KNOWN EDGE CASES: The resume start window is patched to 0.2 seconds in vidbyte.harnesses.native.codex.turn_starts, where section 13 says it is read at call time; that test waits for the window by design. The SDK's own goal cancel sends its pause set without an origin, so the cancel is counted by status, not by origin.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3, 9.1 ("a stored goal under this slice's calls") and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_goal_control.py
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_feature_support import (
    BUDGET_CLEAR_CONFLICT_MESSAGE,
    GOAL_BUDGET_SPENT_CAUSE,
    GOAL_BUDGET_SPENT_MESSAGE,
    GOAL_BUDGET_SPENT_NEXT_STEP,
    GOAL_EDIT_EMPTY_MESSAGE,
    GOAL_NOT_RESUMABLE_CAUSE,
    GOAL_NOT_RESUMABLE_MESSAGE,
    GOAL_NOT_RESUMABLE_NEXT_STEP,
    NO_GOAL_CAUSE,
    NO_GOAL_NEXT_STEP,
    NO_STORED_GOAL_MESSAGE,
    OBJECTIVE_CANARY,
    THREAD_RUNNING_MESSAGE,
    assert_packet,
)
from tests.features.codex_host.codex_host_support import BUSY_TEXT, WAIT_SECONDS, FeatureHostCase, assert_no_canary, mapped_summary, requires_sdk, thread_suffix

PREFLIGHT = ["account/read", "account/rateLimits/read"]
RESUME_SEQUENCE = [*PREFLIGHT, "thread/read", "thread/goal/get", "thread/resume", "thread/goal/set"]
START_FAILURE_CLEANUP = ["cancel_goal_operation", "finish", "unregister_goal_operation"]
RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
BUDGET_ECHO_TEXT = "Codex did not keep the goal token budget it was sent: it reported {stored} after {sent} was set."
# INV-31 step 4: CODEX_HOST_GOAL_RESUME_FROM_STATUSES; budgetLimited resumes only once its budget is above its use.
RESUMABLE = (("paused", {}), ("blocked", {}), ("usageLimited", {}), ("budgetLimited", {"token_budget": 1000, "tokens_used": 500}))
NOT_RESUMABLE = ("active", "complete")


class _GoalCase(FeatureHostCase):
    """Shared steps: a stored thread with a goal, the goal calls the fake logged for a thread, and a goal's set requests."""

    def with_goal(self, status: str | None, **numbers: Any) -> Any:
        thread = self.server.seed_thread(completed_turns=1)
        if status is not None:
            thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", status, **numbers)
        return thread

    def goal_calls(self, thread_id: str) -> list[str]:
        return [entry[0] for entry in self.server.kinds("cancel_goal_operation", "finish", "unregister_goal_operation") if entry[1] == thread_id]

    def goal_sets(self, thread_id: str) -> list[dict[str, Any]]:
        return [request.params for request in self.server.matching("thread/goal/set") if request.params.get("threadId") == thread_id]

    async def refused_record(self, awaitable: Any, message: str) -> None:
        """A ConfigurationError with the exact message and no request (EC-41)."""
        from vidbyte.lib.errors import ConfigurationError

        sent = len(self.server.requests)
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(awaitable, WAIT_SECONDS)
        self.assertEqual(str(caught.exception), message)
        self.assertEqual(len(self.server.requests), sent)


@requires_sdk
class CodexGoalPauseHostTests(_GoalCase):
    """AC-25, INV-7, INV-30 and EC-40."""

    async def test_pausing_a_tracked_goal_run_sends_one_user_set_and_the_run_ends_paused(self) -> None:
        # AC-25: the echoed goal comes back, and the run ends through its finish rule once its physical turn finishes.
        from vidbyte.lib.dataclasses.codex_host import CodexThreadGoal
        from vidbyte.lib.enums.codex import CodexGoalStatus

        host = await self.opened()
        handle = await self.call(host.run_codex_goal("Ship the fix."))
        thread_id = handle.thread_id
        self.remark()
        goal = await self.call(host.pause_codex_goal(thread_id))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get", "thread/goal/set"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread_id, "status": "paused", "origin": "user"})
        self.assertIsInstance(goal, CodexThreadGoal)
        self.assertEqual((goal.thread_id, goal.objective, goal.status), (thread_id, "Ship the fix.", CodexGoalStatus.PAUSED))
        self.server.complete_turn(thread_id, handle.turn_id, final="Paused after the first step.")
        snapshot = await self.wait_done(host, handle)
        self.assertIs(snapshot.goal_status, CodexGoalStatus.PAUSED)

    async def test_a_thread_without_a_stored_goal_is_refused_after_the_goal_read(self) -> None:
        # EC-40, INV-30: codex.session_not_found with the stored-goal message, its cause and its next step.
        thread = self.with_goal(None)
        host = await self.opened()
        error = await self.codex_error(host.pause_codex_goal(thread.thread_id), "codex.session_not_found")
        assert_packet(
            self,
            error,
            operation="pause_codex_goal",
            code="codex.session_not_found",
            message=NO_STORED_GOAL_MESSAGE.format(operation="pause_codex_goal"),
            cause=NO_GOAL_CAUSE,
            next_step=NO_GOAL_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])

    async def test_an_overloaded_goal_set_is_sent_once(self) -> None:
        # INV-7: thread/goal/set is in CODEX_HOST_SPENDING_RAW_METHODS, so it is single-attempt.
        thread = self.with_goal("active")
        self.server.fail("thread/goal/set", self.fakes.overloaded_error(), times=1)
        host = await self.opened()
        error = await self.codex_error(host.pause_codex_goal(thread.thread_id), "codex.api_error")
        self.assertEqual(error.operation, "pause_codex_goal")
        self.assertEqual(len(self.goal_sets(thread.thread_id)), 1)


@requires_sdk
class CodexGoalResumeHostTests(_GoalCase):
    """AC-26, AC-27, INV-31, D-17, D-38, EC-37 to EC-39, EC-58 and EC-64."""

    async def test_a_resumable_goal_is_resumed_with_a_status_only_set_and_its_run_is_tracked(self) -> None:
        # AC-26: no objective, no tokenBudget and no clear; the handle follows the goal run to its end.
        from vidbyte.lib.enums.codex import CodexGoalStatus

        host = await self.opened()
        for status, numbers in RESUMABLE:
            with self.subTest(goal=status):
                thread = self.with_goal(status, **numbers)
                self.remark()
                handle = await self.call(host.resume_codex_goal(thread.thread_id))
                self.assertEqual(self.sent_methods(), RESUME_SEQUENCE)
                self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "status": "active", "origin": "user"})
                self.assertEqual(self.count("thread/goal/clear", lambda params, thread_id=thread.thread_id: params["threadId"] == thread_id), 0)
                self.assertEqual((handle.thread_id, handle.turn_id), (thread.thread_id, thread.turns[-1].turn_id))
                self.assertEqual(thread.goal.get("tokenBudget"), numbers.get("token_budget"))
                self.server.emit([self.server.goal_update(thread.thread_id, "complete")])
                self.server.complete_turn(thread.thread_id, handle.turn_id, final="Shipped.")
                snapshot = await self.wait_done(host, handle)
                self.assertIs(snapshot.goal_status, CodexGoalStatus.COMPLETE)
                self.assertEqual(snapshot.result.final_response, "Shipped.")

    async def test_an_active_or_complete_goal_is_refused_before_thread_resume(self) -> None:
        # AC-26, INV-31 step 4: configuration.invalid_argument with the not-resumable packet, after the preflight and the goal read.
        host = await self.opened()
        for status in NOT_RESUMABLE:
            with self.subTest(goal=status):
                thread = self.with_goal(status)
                self.remark()
                error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "configuration.invalid_argument")
                assert_packet(
                    self,
                    error,
                    operation="resume_codex_goal",
                    code="configuration.invalid_argument",
                    message=GOAL_NOT_RESUMABLE_MESSAGE.format(status=status),
                    cause=GOAL_NOT_RESUMABLE_CAUSE,
                    next_step=GOAL_NOT_RESUMABLE_NEXT_STEP,
                    thread_id=thread.thread_id,
                )
                self.assertEqual(self.sent_methods(), [*PREFLIGHT, "thread/read", "thread/goal/get"])
                self.assertIn("pause_codex_goal", GOAL_NOT_RESUMABLE_NEXT_STEP)

    async def test_a_spent_budget_is_refused_until_edit_raises_it_then_the_goal_resumes(self) -> None:
        # EC-58, D-38: Codex would only stop the goal again; the order is edit_codex_goal, then resume_codex_goal.
        from vidbyte.lib.enums.codex import CodexGoalStatus

        thread = self.with_goal("budgetLimited", token_budget=500, tokens_used=500)
        host = await self.opened()
        error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "configuration.invalid_argument")
        assert_packet(
            self,
            error,
            operation="resume_codex_goal",
            code="configuration.invalid_argument",
            message=GOAL_BUDGET_SPENT_MESSAGE.format(used=500, budget=500),
            cause=GOAL_BUDGET_SPENT_CAUSE,
            next_step=GOAL_BUDGET_SPENT_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.sent_methods(), [*PREFLIGHT, "thread/read", "thread/goal/get"])
        edited = await self.call(host.edit_codex_goal(thread.thread_id, token_budget=2000))
        self.assertIs(edited.status, CodexGoalStatus.BUDGET_LIMITED)
        self.remark()
        handle = await self.call(host.resume_codex_goal(thread.thread_id))
        self.assertEqual(self.sent_methods(), RESUME_SEQUENCE)
        self.assertEqual(handle.thread_id, thread.thread_id)

    async def test_a_thread_without_a_goal_or_unknown_to_codex_is_refused_before_thread_resume(self) -> None:
        # Section 9.2 resume row: "not found, no goal".
        host = await self.opened()
        thread = self.with_goal(None)
        error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "codex.session_not_found")
        assert_packet(
            self,
            error,
            operation="resume_codex_goal",
            code="codex.session_not_found",
            message=NO_STORED_GOAL_MESSAGE.format(operation="resume_codex_goal"),
            cause=NO_GOAL_CAUSE,
            next_step=NO_GOAL_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.count("thread/resume"), 0)
        await self.codex_error(host.resume_codex_goal("thr-never"), "codex.session_not_found")
        self.assertEqual(self.count("thread/resume"), 0)

    async def test_a_resume_whose_start_window_elapses_is_cancelled_once_and_cleaned_up(self) -> None:
        # AC-27, INV-31 "When the start fails": the status was set, so one cancel, then finish and unregister; no turn is registered.
        patcher = mock.patch("vidbyte.harnesses.native.codex.turn_starts.CODEX_HOST_GOAL_RESUME_START_SECONDS", 0.2)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server.goal_resume_starts_turn = False
        thread = self.with_goal("paused")
        host = await self.opened()
        error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "codex.api_error")
        self.assertEqual(error.operation, "resume_codex_goal")
        self.assertEqual(self.goal_calls(thread.thread_id), START_FAILURE_CLEANUP)
        self.assertEqual([params.get("status") for params in self.goal_sets(thread.thread_id)], ["active", "paused"])
        self.assertLessEqual(self.count("turn/interrupt", lambda params: params["threadId"] == thread.thread_id), 1)
        self.assertIsNone(host._registry.usage(thread.thread_id))
        self.assertFalse(host._registry.busy(thread.thread_id))

    async def test_a_refused_resume_set_sends_no_cancel_and_still_cleans_up(self) -> None:
        # EC-37, D-17: the status was never set, so the operation is only finished and unregistered.
        thread = self.with_goal("paused")
        self.server.fail("thread/goal/set", self.fakes.FakeRpcError(-32600, "goal is locked by another client"), times=1, predicate=lambda params: params.get("status") == "active")
        host = await self.opened()
        error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "codex.api_error")
        self.assertIn(RPC_ERROR_TEXT.format(method="thread/goal/set", code=-32600, message="goal is locked by another client"), error.message)
        self.assertEqual(self.goal_calls(thread.thread_id), ["finish", "unregister_goal_operation"])
        self.assertEqual(len(self.goal_sets(thread.thread_id)), 1)
        self.assertFalse(host._registry.busy(thread.thread_id))

    async def test_a_resume_set_codex_applied_but_answered_badly_is_cancelled_once_and_cleaned_up(self) -> None:
        # EC-64, INV-31 (spec r6, review R-4): Codex applies the active set, but its answer does not validate. That is not
        # a JSON-RPC refusal (EC-37), so the set counts as sent: one pause set, at most one interrupt, finish, unregister.
        thread = self.with_goal("paused")

        def answer_badly(params: dict[str, Any], result: Any) -> list[Any]:
            # The set was applied; the echoed goal carries a status the SDK does not know.
            result["goal"]["status"] = "notAStatus"
            return []

        self.server.before_response("thread/goal/set", answer_badly, predicate=lambda params: params.get("status") == "active")
        host = await self.opened()
        error = await self.codex_error(host.resume_codex_goal(thread.thread_id), "codex.protocol_mismatch")
        self.assertEqual(error.operation, "resume_codex_goal")
        self.assertEqual(self.goal_calls(thread.thread_id), START_FAILURE_CLEANUP)
        self.assertEqual([params.get("status") for params in self.goal_sets(thread.thread_id)], ["active", "paused"])
        self.assertEqual(thread.goal["status"], "paused")
        self.assertLessEqual(self.count("turn/interrupt", lambda params: params["threadId"] == thread.thread_id), 1)
        # The goal turn the applied set started is not left running untracked.
        self.assertNotEqual(thread.turns[-1].status, "inProgress")
        self.assertIsNone(host._registry.usage(thread.thread_id))
        self.assertFalse(host._registry.busy(thread.thread_id))

    async def test_a_resume_cancelled_after_its_set_was_sent_adopts_the_late_run_and_stops_it_once(self) -> None:
        # EC-38: connection.start's hand-over adopts the late goal run and stops it once, as for run_codex_goal.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        thread = self.with_goal("paused")
        host = await self.opened()
        goal_set = self.server.hold("thread/goal/set", lambda params: params.get("status") == "active")
        task = asyncio.ensure_future(host.resume_codex_goal(thread.thread_id))
        await asyncio.to_thread(goal_set.wait_arrived)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        goal_set.release()

        def cancels() -> int:
            return self.goal_calls(thread.thread_id).count("cancel_goal_operation")

        await self.wait_until(lambda: cancels() >= 1, "the late goal run's cancel")
        await asyncio.wait_for(host.read_codex_thread(thread.thread_id), WAIT_SECONDS)
        self.assertEqual(cancels(), 1)
        snapshot = await self.wait_done(host, CodexTurnHandle(thread_id=thread.thread_id, turn_id=thread.turns[-1].turn_id))
        self.assert_problem(snapshot, "interrupted", None)

    async def test_a_thread_this_host_is_running_is_refused_before_any_request(self) -> None:
        # EC-39, INV-31 step 2: require_idle runs before the preflight.
        host = await self.opened()
        handle = await self.spawn(host)
        self.remark()
        error = await self.codex_error(host.resume_codex_goal(handle.thread_id), "codex.session_busy")
        self.assertEqual(mapped_summary(self, error), BUSY_TEXT + thread_suffix(handle.thread_id))
        self.assertEqual(self.sent_methods(), [])


@requires_sdk
class CodexGoalEditClearHostTests(_GoalCase):
    """AC-28, AC-29, INV-7, INV-32 to INV-34 and EC-41."""

    async def test_an_edit_sends_only_the_objective_or_the_budget_with_the_user_origin(self) -> None:
        # AC-28, INV-32: no status is ever sent, so the goal keeps its status; the objective reaches no log.
        from vidbyte.lib.enums.codex import CodexGoalStatus

        records = self.capture_logs()
        thread = self.with_goal("paused", token_budget=500, tokens_used=120)
        host = await self.opened()
        goal = await self.call(host.edit_codex_goal(thread.thread_id, objective=OBJECTIVE_CANARY))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get", "thread/goal/set"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "objective": OBJECTIVE_CANARY, "origin": "user"})
        self.assertEqual((goal.objective, goal.status, goal.token_budget), (OBJECTIVE_CANARY, CodexGoalStatus.PAUSED, 500))
        cleared = await self.call(host.edit_codex_goal(thread.thread_id, clear_token_budget=True))
        self.assertEqual(self.server.matching("thread/goal/set")[-1].params, {"threadId": thread.thread_id, "tokenBudget": None, "origin": "user"})
        self.assertIsNone(cleared.token_budget)
        raised = await self.call(host.edit_codex_goal(thread.thread_id, token_budget=900))
        self.assertEqual(self.server.matching("thread/goal/set")[-1].params, {"threadId": thread.thread_id, "tokenBudget": 900, "origin": "user"})
        self.assertEqual((raised.token_budget, raised.status), (900, CodexGoalStatus.PAUSED))
        self.assertTrue(all("status" not in params for params in self.goal_sets(thread.thread_id)))
        # An edit never starts a goal turn: the thread still holds only its one seeded turn.
        self.assertEqual(len(thread.turns), 1)
        assert_no_canary(self, [record.getMessage() for record in records], (OBJECTIVE_CANARY,))

    async def test_a_budget_codex_did_not_keep_is_a_protocol_mismatch(self) -> None:
        # AC-28, INV-32: the echoed budget must be the one sent.
        thread = self.with_goal("paused", token_budget=500)
        self.server.budget_echo = 400
        host = await self.opened()
        error = await self.codex_error(host.edit_codex_goal(thread.thread_id, token_budget=900), "codex.protocol_mismatch")
        self.assertEqual(error.operation, "edit_codex_goal")
        self.assertTrue(mapped_summary(self, error).startswith(BUDGET_ECHO_TEXT.format(stored=400, sent=900)), error.message)

    async def test_an_edit_that_changes_nothing_or_sets_and_clears_the_budget_is_refused(self) -> None:
        # EC-41: the record refuses both, before any request.
        thread = self.with_goal("paused", token_budget=500)
        host = await self.opened()
        await self.refused_record(host.edit_codex_goal(thread.thread_id), GOAL_EDIT_EMPTY_MESSAGE)
        await self.refused_record(host.edit_codex_goal(thread.thread_id, token_budget=900, clear_token_budget=True), BUDGET_CLEAR_CONFLICT_MESSAGE)

    async def test_an_edit_without_a_stored_goal_is_refused_after_the_goal_read(self) -> None:
        thread = self.with_goal(None)
        host = await self.opened()
        error = await self.codex_error(host.edit_codex_goal(thread.thread_id, objective="New aim."), "codex.session_not_found")
        assert_packet(
            self,
            error,
            operation="edit_codex_goal",
            code="codex.session_not_found",
            message=NO_STORED_GOAL_MESSAGE.format(operation="edit_codex_goal"),
            cause=NO_GOAL_CAUSE,
            next_step=NO_GOAL_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])

    async def test_clearing_an_idle_threads_goal_returns_codexs_cleared(self) -> None:
        # AC-29, INV-33: one user-origin clear after the status read; False when Codex had no goal to clear.
        thread = self.with_goal("paused")
        host = await self.opened()
        self.assertIs(await self.call(host.clear_codex_goal(thread.thread_id)), True)
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/clear"])
        self.assertEqual(self.sent()[-1].params, {"threadId": thread.thread_id, "origin": "user"})
        self.assertIsNone(thread.goal)
        self.assertIs(await self.call(host.clear_codex_goal(thread.thread_id)), False)

    async def test_clearing_a_running_thread_is_refused_and_no_clear_is_sent(self) -> None:
        # AC-29, INV-34: active from another client after the read; running on this host before any request.
        active = self.server.seed_thread(completed_turns=1, running_turn=True)
        active.goal = self.fakes.goal_record(active.thread_id, "Ship the fix.", "active")
        host = await self.opened()
        error = await self.codex_error(host.clear_codex_goal(active.thread_id), "codex.session_busy")
        self.assertTrue(mapped_summary(self, error).startswith(THREAD_RUNNING_MESSAGE.format(operation="clear_codex_goal")), error.message)
        self.assertEqual(self.sent_methods(), ["thread/read"])
        handle = await self.spawn(host)
        self.remark()
        error = await self.codex_error(host.clear_codex_goal(handle.thread_id), "codex.session_busy")
        self.assertEqual(mapped_summary(self, error), BUSY_TEXT + thread_suffix(handle.thread_id))
        self.assertEqual(self.sent_methods(), [])
        self.assertEqual(self.count("thread/goal/clear"), 0)

    async def test_an_overloaded_clear_is_retried(self) -> None:
        # INV-7: the clear keeps openai-codex's overload retries, because a second clear ends the same way.
        thread = self.with_goal("paused")
        self.server.fail("thread/goal/clear", self.fakes.overloaded_error(), times=1)
        host = await self.opened()
        self.assertIs(await self.call(host.clear_codex_goal(thread.thread_id)), True)
        self.assertEqual(self.count("thread/goal/clear"), 2)


if __name__ == "__main__":
    unittest.main()
