"""FILE: tests/features/claude_host/test_claude_host_review_gaps.py

PURPOSE: Pins the behaviours the S4 review of ClaudeHost found broken or unguarded: a steered prompt is classified by its own result, a steer that starts while the previous result is still unread is interrupted before its prompt is sent, a continue racing aclose starts nothing, an SDK record missing a declared field fails as a protocol mismatch, a rejected per-model window never refuses, D-29's overage and reset-time conditions hold, an unknown rate-limit status or overage value is skipped, a steer whose interrupt fails withdraws its message, and a cancelled aclose still waits for its close.
ROLE IN CODEBASE: Regression layer of tests/features/claude_host/ (spec D-3, D-4, D-29, EC-7, EC-8, EC-19, EC-52, FR-1, INV-8, AC-9, AC-16, section 9.2 rows 5 and 12, section 12.3 row 7; review R-1, R-2, R-3, R-5, R-6, R-7 and R-12). Exercises vidbyte/harnesses/native/claude/{host,session,failures,history}.py.
ARCHITECTURE NOTE: Every test drives a real ClaudeHost over the fake SDK from claude_host_fixtures.py, through the one seam the spec names. A drifted SDK record is a local dataclass that lacks a field a later 0.2.x release could rename, patched into ClaudeSdkTypes in place of the fake class. The continue race blocks the fake history read on a threading.Event, because that read runs in a worker thread.
COMMON MODIFICATION PATTERNS: Add one test per review finding, named for the behaviour it protects, and add one line for it under Historical Regressions in FEATURE.md.
WHAT NOT TO DO IN THIS FILE: 1. Do not sleep for a fixed time; wait on recorded fake calls with eventually(). 2. Do not change claude_host_fixtures.py; define a missing fake here. 3. Do not call aclose on a host without adding it to closed_hosts. 4. Do not wrap the EC-19 steer in asyncio.wait_for: on Python 3.11 that runs the steer in a new task, after the pump has already read the result.
KNOWN EDGE CASES: The EC-19 race needs the steer to start in the same step that queues the first result, so finish() and the steer call run with no await between them. The continue race releases the blocked read in a finally block, so a failing test never leaves a worker thread waiting.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.3, 8.1 (D-3, D-29) and 9.2; docs/spec/claude-host/review.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_review_gaps.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    END_OF_STREAM,
    FAR_FUTURE_RESET,
    HANG_GUARD_SECONDS,
    PRECONDITION_FAILED,
    PRECONDITION_NEXT_STEP,
    WORK_DIR,
    ClaudeHostCase,
    CLIConnectionError,
    eventually,
    init_message,
    rate_limit_event,
    result_message,
    settle,
)

STEER_MESSAGE = "focus on tests"
SECOND_STEER = "check the docs instead"
PER_MODEL_WINDOWS = ("seven_day_opus", "seven_day_sonnet")


@dataclass
class DriftedSessionInfo:
    """An SDKSessionInfo from a release that renamed summary: every other 0.2.165 field, and no summary."""

    session_id: str
    last_modified: int
    file_size: int | None = None
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None
    cwd: str | None = None
    tag: str | None = None
    created_at: int | None = None


@dataclass
class DriftedResultMessage:
    """A ResultMessage from a release that renamed result and terminal_reason: every other 0.2.165 field, and neither of those."""

    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    stop_reason: str | None = None
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    structured_output: Any = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[Any] | None = None
    deferred_tool_use: Any = None
    errors: list[str] | None = None
    api_error_status: int | None = None
    uuid: str | None = None
    origin: dict[str, Any] | None = None


class ReviewGapCase(ClaudeHostCase):
    """Adds the held-turn helper and the one-turn rate-limit run the review-gap tests share."""

    async def running_turn(self, host: Any) -> tuple[Any, Any]:
        """Spawn a held turn and return its handle and client once the prompt has been sent."""
        self.fake.hold(DEFAULT_PROMPT)
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        return handle, client

    async def turn_seeing(self, host: Any, prompt: str, event: Any) -> Any:
        """Run one turn that sees this rate-limit event before its success result, and return its terminal snapshot."""
        self.fake.reply(prompt, init_message(), event, result_message(result="Parser fixed."))
        return await self.finished(host, await self.spawn(host, prompt))


class SteeredTurnOwnResultTests(ReviewGapCase):
    """D-3 and section 9.2 row 12 (review R-1): a steered prompt with no result of its own is classified by how its stream ended."""

    async def steer_whose_stream_dies(self, ending: Any) -> Any:
        """Steer a held turn whose steered prompt gets only its init message and then this ending; return the terminal snapshot."""
        self.fake.reply(STEER_MESSAGE, init_message(), ending)
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        await asyncio.wait_for(host.steer_claude_session(handle, STEER_MESSAGE), HANG_GUARD_SECONDS)
        result = await self.finished(host, handle)
        self.assertEqual(client.queries, [DEFAULT_PROMPT, STEER_MESSAGE])
        self.assertEqual(client.disconnect_calls, 1)
        return result

    async def test_a_steered_prompt_whose_output_ends_reports_process_exited(self) -> None:
        result = await self.steer_whose_stream_dies(END_OF_STREAM)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.process_exited", result.failure.reason)
        self.assertEqual(result.failure.reason, "Claude Code's output ended before the turn's result arrived.")
        self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.process_exited"])

    async def test_a_steered_prompt_whose_stream_breaks_reports_the_mapped_error(self) -> None:
        result = await self.steer_whose_stream_dies(CLIConnectionError("stream broke"))
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.process_exited", result.failure.reason)
        self.assertEqual(result.failure.reason, "receive_messages raised CLIConnectionError.")


class SteerInResultWindowTests(ReviewGapCase):
    """EC-19 and AC-9 (review R-2): a steer that starts while the prompt's result is queued but unread still interrupts before the steered prompt is sent."""

    async def test_a_steer_after_the_result_was_queued_runs_the_steered_prompt(self) -> None:
        self.fake.hold(DEFAULT_PROMPT, STEER_MESSAGE)
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        # Queue the first result and steer in the same step, so the
        # pump wakes for the result before the steer's interrupt task
        # runs.
        client.finish("The first answer.")
        self.assertIsNone(await host.steer_claude_session(handle, STEER_MESSAGE))
        await eventually(lambda: len(client.queries) == 2, "the steered prompt was sent")
        queries = [index for index, call in enumerate(client.calls) if call == "query"]
        self.assertLess(client.calls.index("interrupt"), queries[1], f"the steered prompt went out before its interrupt: {client.calls}")
        client.finish("The steered answer.")
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The steered answer."), result.failure)
        self.assertEqual(client.queries, [DEFAULT_PROMPT, STEER_MESSAGE])
        self.assertEqual(client.interrupt_calls, 1)


class ContinueRacingCloseTests(ReviewGapCase):
    """FR-1 (review R-5): a continue still reading its session file when aclose runs is refused, and no client starts after aclose returns."""

    patch_sdk = False

    async def test_a_continue_reading_the_session_file_is_refused_after_aclose(self) -> None:
        entered, release = threading.Event(), threading.Event()
        read = self.fake.history.get_session_info

        def blocked_read(session_id: str, directory: str | None = None) -> Any:
            # Hold the read in its worker thread until the host closed.
            entered.set()
            release.wait(HANG_GUARD_SECONDS)
            return read(session_id, directory)

        # The seam binds the history functions when it is patched, so
        # the blocked read goes in first.
        self.fake.history.get_session_info = blocked_read
        self.enterContext(self.fake.patched())
        session_id = self.fake.history.add_session(cwd=WORK_DIR)
        host = await self.open_host()
        continuing = asyncio.create_task(host.continue_claude_session(session_id, "Run the tests again."))
        try:
            await eventually(entered.is_set, "the continue is reading the session file")
            self.closed_hosts.append(host)
            await asyncio.wait_for(host.aclose(), HANG_GUARD_SECONDS)
        finally:
            release.set()
        error = await self.raises(continuing, PRECONDITION_FAILED)
        self.assertEqual(error.next_step, PRECONDITION_NEXT_STEP)
        await settle()
        self.assertEqual(self.fake.clients, [])
        self.assertEqual(self.fake.connected_now, 0)


class SdkRecordDriftTests(ReviewGapCase):
    """Field guide class-bound-helpers (review R-3): a record missing a field the pinned SDK declares fails as claude.protocol_mismatch."""

    async def test_session_info_without_a_summary_is_a_protocol_mismatch(self) -> None:
        host = await self.open_host()
        session_id = self.fake.history.add_session(cwd=WORK_DIR)
        self.fake.history.infos[session_id] = DriftedSessionInfo(session_id=session_id, last_modified=1_760_000_000_000, cwd=WORK_DIR)
        error = await self.raises(host.get_claude_session_info(session_id), "claude.protocol_mismatch")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.protocol_mismatch"])

    async def test_a_result_without_its_declared_fields_is_a_protocol_mismatch(self) -> None:
        from vidbyte.harnesses.native.claude.sdk import ClaudeSdkLoader

        drifted = dataclasses.replace(self.fake.types(), result_message=DriftedResultMessage)
        self.enterContext(mock.patch.object(ClaudeSdkLoader, "load", return_value=drifted))
        self.fake.reply(DEFAULT_PROMPT, init_message(), DriftedResultMessage(subtype="success", duration_ms=4200, duration_api_ms=3100, is_error=False, num_turns=1, session_id=""))
        host = await self.open_host()
        result = await self.finished(host, await self.spawn(host))
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.failure.code.value, "claude.protocol_mismatch", result.failure.reason)
        self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.protocol_mismatch"])


class RateLimitRuleTests(ReviewGapCase):
    """D-29, EC-7, EC-8 and EC-52 as revised in spec r5 (review R-6, R-7 and R-12): only a live, account-wide rejection without allowed overage refuses."""

    async def test_a_rejected_window_with_allowed_warning_overage_or_no_reset_time_refuses_nothing(self) -> None:
        cases = (
            ("rejected, overage allowed_warning", rate_limit_event("five_hour", "rejected", resets_at=FAR_FUTURE_RESET, overage_status="allowed_warning")),
            ("rejected, no reset time", rate_limit_event("seven_day", "rejected")),
        )
        for label, event in cases:
            with self.subTest(window=label):
                host = await self.open_host()
                first = await self.turn_seeing(host, f"Use the quota ({label}).", event)
                self.assertEqual((first.status.value, first.failure), ("completed", None))
                follow = await self.spawn(host, f"Next task ({label}).")
                self.assertEqual((await self.finished(host, follow)).status.value, "completed")

    async def test_a_rejected_per_model_window_is_recorded_but_never_refuses_a_spawn(self) -> None:
        for kind in PER_MODEL_WINDOWS:
            with self.subTest(window=kind):
                host = await self.open_host()
                await self.turn_seeing(host, f"Use the {kind} quota.", rate_limit_event(kind, "rejected", resets_at=FAR_FUTURE_RESET))
                windows = await host.get_claude_rate_limits()
                self.assertEqual([(window.rate_limit_type.value, window.status.value) for window in windows], [(kind, "rejected")])
                follow = await self.spawn(host, f"Next task after {kind}.")
                self.assertEqual((await self.finished(host, follow)).status.value, "completed")

    async def test_only_a_window_covering_every_model_fails_a_successful_turn(self) -> None:
        cases = (*((kind, "completed", None) for kind in PER_MODEL_WINDOWS), ("five_hour", "failed", "claude.usage_limited"))
        for kind, status, code in cases:
            with self.subTest(window=kind):
                host = await self.open_host()
                result = await self.turn_seeing(host, f"Finish the work ({kind}).", rate_limit_event(kind, "rejected", resets_at=FAR_FUTURE_RESET))
                self.assertEqual((result.status.value, None if result.failure is None else result.failure.code.value), (status, code))
                self.assertEqual(result.result_text, "Parser fixed.")

    async def test_a_window_with_an_unknown_status_or_overage_value_is_skipped(self) -> None:
        # EC-52 (review R-12): a value this host cannot key is skipped,
        # like an unknown window type, and never fails the turn.
        cases = (
            ("unknown status", rate_limit_event("five_hour", "throttled", resets_at=FAR_FUTURE_RESET)),
            ("unknown overage status", rate_limit_event("five_hour", "rejected", resets_at=FAR_FUTURE_RESET, overage_status="blocked")),
        )
        for label, event in cases:
            with self.subTest(window=label):
                host = await self.open_host()
                result = await self.turn_seeing(host, f"Read the window ({label}).", event)
                self.assertEqual((result.status.value, result.failure, result.result_text), ("completed", None, "Parser fixed."))
                self.assertEqual(await host.get_claude_rate_limits(), ())


class SteerWithdrawalTests(ReviewGapCase):
    """Section 12.3 row 7 and INV-18 (review R-7): a steer whose interrupt raises withdraws its own message, and the turn takes a later steer."""

    async def test_a_steer_whose_interrupt_fails_is_never_sent_and_frees_the_next_steer(self) -> None:
        self.fake.interrupt_error = lambda: CLIConnectionError("control channel closed")
        self.fake.reply(SECOND_STEER, init_message(), result_message(result="The docs are checked."))
        host = await self.open_host()
        handle, client = await self.running_turn(host)
        await self.raises(host.steer_claude_session(handle, STEER_MESSAGE), "claude.process_exited")
        await settle()
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        self.fake.interrupt_error = None
        self.assertIsNone(await asyncio.wait_for(host.steer_claude_session(handle, SECOND_STEER), HANG_GUARD_SECONDS))
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The docs are checked."))
        self.assertEqual(client.queries, [DEFAULT_PROMPT, SECOND_STEER])


class CancelledCloseTests(ReviewGapCase):
    """INV-8 and D-4 (review R-7): cancelling aclose stops only its wait; the cancellation surfaces after the one disconnect finishes."""

    async def test_a_cancelled_aclose_waits_for_the_close_it_started(self) -> None:
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        _, client = await self.running_turn(host)
        self.closed_hosts.append(host)
        closing = asyncio.create_task(host.aclose())
        await eventually(lambda: client.disconnect_calls == 1, "aclose started the close")
        closing.cancel()
        await settle()
        self.assertFalse(closing.done(), "the cancelled aclose returned before its close finished")
        self.assertFalse(client.disconnect_finished)
        self.fake.disconnect_gate.set()
        done, _ = await asyncio.wait({closing}, timeout=HANG_GUARD_SECONDS)
        self.assertEqual(done, {closing})
        self.assertTrue(closing.cancelled())
        self.assertTrue(client.disconnect_finished)
        self.assertFalse(client.disconnect_cancelled)
        self.assertEqual(self.fake.connected_now, 0)


if __name__ == "__main__":
    unittest.main()
