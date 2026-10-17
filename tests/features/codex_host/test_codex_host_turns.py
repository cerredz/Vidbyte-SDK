"""FILE: tests/features/codex_host/test_codex_host_turns.py

PURPOSE: Proves spawned turns over the in-memory app-server: the thread/start and turn/start params, preflight checks before any spending request, bounded waits and non-waiting gets, completed results with usage, the timeout and the output-token cap (one interrupt each, labelled only when Codex reports the turn interrupted), process death, the codexErrorInfo table, structured output, steer and interrupt, and per-turn usage with its cost.
ROLE IN CODEBASE: Turn layer of tests/features/codex_host/ (spec AC-5 to AC-13, AC-16, AC-17, INV-12 to INV-24, INV-36, D-7, D-19, D-27, D-28, EC-6 to EC-14, EC-23, EC-25, EC-27 to EC-34, EC-72). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake app-server answers as codex app-server 0.162 does, and each test drives its turns' notifications with complete_turn, emit_usage, die and send_raw, so the host's watchers, translators and pricing run unmocked. Exact interrupt counts use a barrier: with CODEX_HOST_WORKER_THREADS patched to 1, a later host call cannot return before an interrupt queued earlier has reached the fake.
COMMON MODIFICATION PATTERNS: Add a codexErrorInfo row to ERROR_INFO_ROWS when spec section 9.2 adds one; add a preflight case to PREFLIGHT_FAILURES with the state that triggers it.
KNOWN EDGE CASES: Usage notifications carry cumulative totals for the thread, so the cap test runs an uncapped first turn before the capped ones. A wait with a 50 ms bound returns RUNNING by design; nothing in this file sleeps.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-12 to INV-24, INV-36), 9.1 (Snapshot result), 9.2 (Preflight, Turn errors) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_turns.py
"""

from __future__ import annotations

import asyncio
import math
import unittest
from typing import Any

from pydantic import BaseModel

from tests.features.codex_host.codex_host_support import (
    LINE_SECRET,
    STDERR_SECRET,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    error_texts,
    input_texts,
    requires_sdk,
)
from vidbyte.lib.errors import ConfigurationError

SPENDING_METHODS = ("thread/start", "thread/resume", "turn/start", "review/start", "thread/goal/clear", "thread/goal/set")

# Spec section 9.2 "Turn errors": codexErrorInfo key -> code; every key not in the table maps to codex.api_error.
ERROR_INFO_ROWS: tuple[tuple[Any, str], ...] = (
    ("usageLimitExceeded", "codex.usage_limited"),
    ("rateLimitExceeded", "codex.usage_limited"),
    ("sessionBudgetExceeded", "codex.budget_exhausted"),
    ("contextWindowExceeded", "codex.budget_exhausted"),
    ("unauthorized", "codex.not_signed_in"),
    ("sandboxError", "codex.sandbox_not_ready"),
    ("tooManyDenials", "codex.permission_denied"),
    ("cyberPolicy", "codex.permission_denied"),
    ("misalignmentPolicyViolation", "codex.permission_denied"),
    ("serverOverloaded", "codex.api_error"),
    ("internalServerError", "codex.api_error"),
    ("badRequest", "codex.api_error"),
    ("flexUnavailable", "codex.api_error"),
    ("threadRollbackFailed", "codex.api_error"),
    ("other", "codex.api_error"),
    ("brandNewValue", "codex.api_error"),
    ({"httpConnectionFailed": {"httpStatusCode": 502}}, "codex.api_error"),
    ({"futureVariant": {"detail": "added later"}}, "codex.api_error"),
)


class ReadmeSummary(BaseModel):
    """The output schema of the structured-output test."""

    title: str


def _spends(server: Any) -> int:
    return sum(len(server.matching(method)) for method in SPENDING_METHODS)


def _rollup(model: str, deltas: tuple[tuple[int, int], ...]) -> Any:
    """The cost the repo's own pricing gives these per-turn deltas (spec D-19 names these two classes)."""
    from vidbyte.agents.codex.metrics import CodexMetricsTranslator
    from vidbyte.agents.pricing.tracker import UsageTracker
    from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexRunResult, CodexThreadSettings, CodexUsage, CodexUsageTranslationRequest

    tracker = UsageTracker()
    settings = CodexAgentSettings(thread=CodexThreadSettings(model=model))
    for input_tokens, output_tokens in deltas:
        delta = CodexUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)
        result = CodexRunResult(thread_id="oracle", turn_id="oracle", status="completed", final_response="", duration_ms=0, usage=delta, items=(), last_usage=delta, usage_available=True)
        CodexMetricsTranslator.record_usage(CodexUsageTranslationRequest(result=result, settings=settings, tracker=tracker))
    return tracker.rollup()


@requires_sdk
class CodexHostSpawnTests(HostTestCase):
    """AC-5, AC-6 and the D-28 preflight rules."""

    async def test_spawn_sends_the_section_9_2_params_and_returns_while_the_turn_runs(self) -> None:
        # AC-5, INV-13, INV-28, INV-30: no approval field set means on-request plus auto_review, and no agents config.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexReasoningEffort, CodexSandbox

        host = await self.open_host()
        handle = await self.spawn(
            host,
            "Summarize the readme in one sentence.",
            thread=CodexThreadSettings(model="gpt-5.5", sandbox=CodexSandbox.READ_ONLY),
            turn=CodexTurnSettings(effort=CodexReasoningEffort.LOW),
            developer_instructions="Answer in one sentence.",
            name="Readme summary",
            disabled_plugin_ids=("github",),
            output_schema=ReadmeSummary,
        )

        methods = self.server.methods()
        self.assertLess(methods.index("model/list"), methods.index("thread/start"))
        self.assertLess(methods.index("thread/start"), methods.index("thread/name/set"))
        self.assertLess(methods.index("thread/name/set"), methods.index("turn/start"))
        thread_start = self.server.matching("thread/start")[0].params
        self.assertEqual(thread_start["model"], "gpt-5.5")
        self.assertEqual(thread_start["sandbox"], "read-only")
        self.assertEqual(thread_start["approvalPolicy"], "on-request")
        self.assertEqual(thread_start["approvalsReviewer"], "auto_review")
        self.assertEqual(thread_start["developerInstructions"], "Answer in one sentence.")
        self.assertNotIn("agents", thread_start.get("config") or {})
        self.assertEqual(self.server.matching("thread/name/set")[0].params, {"threadId": handle.thread_id, "name": "Readme summary"})
        turn_start = self.server.matching("turn/start")[0].params
        self.assertEqual(turn_start["threadId"], handle.thread_id)
        self.assertEqual(input_texts(turn_start), [("text", "Summarize the readme in one sentence.")])
        self.assertEqual(turn_start["effort"], "low")
        self.assertEqual(turn_start["disabledPluginIds"], ["github"])
        self.assertEqual(turn_start["outputSchema"]["properties"]["title"]["type"], "string")
        # INV-13: the handle names the turn Codex accepted, which is still running.
        stored = self.server.threads[handle.thread_id].turns
        self.assertEqual([turn.turn_id for turn in stored], [handle.turn_id])
        self.assertEqual(stored[0].status, "inProgress")
        self.assert_problem(await host.get_codex_turn_result(handle), "inProgress", None)

    async def test_a_failed_preflight_check_stops_every_spending_operation_before_it_spends(self) -> None:
        # AC-6, INV-12, EC-6, EC-7, EC-9, EC-12: spawn, continue, review and launch, one failing check at a time.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        self.patch_platform("win32")
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)

        def operations(model: str) -> dict[str, Any]:
            request = CodexSpawnRequest(thread=CodexThreadSettings(model=model))
            return {
                "spawn": lambda: host.spawn_codex_thread(CodexSpawnRequest(prompt="Fix the bug.", thread=CodexThreadSettings(model=model))),
                "continue": lambda: host.continue_codex_thread(seeded.thread_id, "Carry on.", overrides=request),
                "review": lambda: host.start_codex_review(seeded.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)),
                "launch": lambda: host.launch_codex_subagents(["Part one.", "Part two."], request=request),
            }

        cases = (
            ("codex.not_signed_in", "gpt-5.5", lambda: setattr(self.server, "account", None)),
            ("codex.usage_limited", "gpt-5.5", lambda: setattr(self.server, "ordinary_usage_allowed", False)),
            ("codex.sandbox_not_ready", "gpt-5.5", lambda: setattr(self.server, "sandbox_status", "notConfigured")),
            ("codex.model_unknown", "gpt-unknown-9", lambda: None),
        )
        for code, model, break_one_check in cases:
            break_one_check()
            for name, start in operations(model).items():
                if code == "codex.model_unknown" and name == "review":
                    continue  # Section 9.2: review has no model check.
                with self.subTest(code=code, operation=name):
                    spends = _spends(self.server)
                    error = await self.assert_codex_error(start(), code)
                    self.assertEqual(_spends(self.server), spends, self.server.methods())
                    if code == "codex.model_unknown":
                        self.assertIn("gpt-5.5", error.message)
                        self.assertIn("gpt-5.5-codex-latest", error.message)
            self.server.account = {"type": "chatgpt", "email": "owner@example.invalid", "planType": "plus"}
            self.server.ordinary_usage_allowed = True
            self.server.sandbox_status = "ready"

    async def test_preflight_passes_on_unknown_states_and_skips_checks_that_do_not_apply(self) -> None:
        # D-28, EC-8, EC-10, EC-11, EC-13, EC-14: none of these may stop a spawn.
        from tests.features.codex_host.codex_host_fakes import FakeRpcError
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.enums.codex import CodexSandbox

        self.patch_platform("win32")
        host = await self.open_host()
        self.server.ordinary_usage_allowed = None
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5"))
        self.server.ordinary_usage_allowed = True
        self.server.fail("account/rateLimits/read", FakeRpcError(-32603, "rate limits are not available for API keys"), times=1)
        await self.spawn(host)
        self.server.fail("windowsSandbox/readiness", FakeRpcError(-32601, "method not found: windowsSandbox/readiness"), times=1)
        await self.spawn(host)
        self.server.sandbox_status = "notConfigured"
        readiness_reads = self.count("windowsSandbox/readiness")
        await self.spawn(host, thread=CodexThreadSettings(sandbox=CodexSandbox.FULL_ACCESS))
        self.assertEqual(self.count("windowsSandbox/readiness"), readiness_reads)
        self.server.sandbox_status = "ready"
        await self.spawn(host, thread=CodexThreadSettings(model="llama-local", model_provider="ollama"))
        # A model passes when it equals the id or the model of any listed model, hidden ones and later pages included.
        await self.spawn(host, thread=CodexThreadSettings(model="codex-auto-review"))
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5-codex"))
        await self.close_host(host)

        # EC-14: a cursor that repeats ends paging instead of looping (a fresh host, so no cached model list).
        self.server.repeat_last_cursor = True
        host = await self.open_host()
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5-codex"))
        models = await asyncio.wait_for(host.list_codex_models(), WAIT_SECONDS)
        self.assertEqual([model.model_id for model in models], ["gpt-5.5", "gpt-5.5-codex-latest"])


@requires_sdk
class CodexHostWaitTests(HostTestCase):
    """AC-7, AC-8, AC-9 and AC-10: bounded waits, results, the timeout and the output cap."""

    async def test_a_bounded_wait_returns_running_and_never_touches_the_turn(self) -> None:
        # AC-7, INV-11, INV-16: neither the bound nor a cancelled wait interrupts the turn.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        handle = await self.spawn(host)
        early = await asyncio.wait_for(host.wait_codex_turn(handle, timeout_seconds=0.05), WAIT_SECONDS)
        self.assert_problem(early, "inProgress", None)
        self.assertIsNone(early.result)
        for bad in (0, -1.0, math.nan):
            with self.subTest(timeout_seconds=bad):
                with self.assertRaises(ConfigurationError):
                    await asyncio.wait_for(host.wait_codex_turn(handle, timeout_seconds=bad), WAIT_SECONDS)
        waiter = asyncio.ensure_future(host.wait_codex_turn(handle))
        for _ in range(5):
            await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        # Barrier: with one host worker, this read returns only after any interrupt queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt"), 0)
        self.assert_problem(await host.get_codex_turn_result(handle), "inProgress", None)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="All set.")
        self.assert_problem(await self.wait_done(host, handle), "completed", None)

    async def test_a_completed_turn_reports_its_answer_and_usage_and_get_never_waits(self) -> None:
        # AC-8, INV-17, section 9.1: result.usage keeps the thread's cumulative totals.
        host = await self.open_host()
        handle = await self.spawn(host)
        self.server.emit_usage(handle.thread_id, handle.turn_id, total=(100, 20), last=(100, 20))
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="The answer.", usage=self.fakes.token_usage((250, 45), (150, 25)))
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.handle, handle)
        self.assertEqual(snapshot.result.final_response, "The answer.")
        self.assertEqual((snapshot.result.usage.input_tokens, snapshot.result.usage.output_tokens), (250, 45))
        self.assertTrue(snapshot.result.usage_available)
        self.assertEqual(await asyncio.wait_for(host.get_codex_turn_result(handle), WAIT_SECONDS), snapshot)
        running = await self.spawn(host, "A second question.")
        self.assert_problem(await asyncio.wait_for(host.get_codex_turn_result(running), 1.0), "inProgress", None)

    async def test_a_timeout_sends_one_interrupt_and_labels_only_a_turn_codex_reports_interrupted(self) -> None:
        # AC-9, INV-18, D-7, EC-27: a failed interrupt is not retried and leaves no label.
        from tests.features.codex_host.codex_host_fakes import FakeRpcError

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        handle = await self.spawn(host, timeout_seconds=0.2)
        self.assert_problem(await self.wait_done(host, handle), "interrupted", "codex.turn_timed_out")
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt", lambda params: params.get("turnId") == handle.turn_id), 1)

        self.server.fail("turn/interrupt", FakeRpcError(-32603, "interrupt failed"))
        second = await self.spawn(host, "Another task.", timeout_seconds=0.2)
        await self.wait_for_request("turn/interrupt", lambda params: params.get("turnId") == second.turn_id)
        self.server.complete_turn(second.thread_id, second.turn_id, final="Finished anyway.")
        self.assert_problem(await self.wait_done(host, second), "completed", None)
        await asyncio.wait_for(host.read_codex_thread(second.thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt", lambda params: params.get("turnId") == second.turn_id), 1)

    async def test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once(self) -> None:
        # AC-10, INV-19, EC-29: earlier turns' output on the same thread never counts toward a new turn's cap.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        first = await self.spawn(host)
        thread_id = first.thread_id
        self.server.complete_turn(thread_id, first.turn_id, final="First.", usage=self.fakes.token_usage((100, 90), (100, 90)))
        await self.wait_done(host, first)

        # Turn 2 produces 30, then 50 of its own output tokens: exactly the cap, so no interrupt. Codex then stops it itself.
        capped = CodexSpawnRequest(max_output_tokens=50)
        second = await asyncio.wait_for(host.continue_codex_thread(thread_id, "Second.", overrides=capped), WAIT_SECONDS)
        self.server.emit_usage(thread_id, second.turn_id, total=(130, 120), last=(30, 30))
        self.server.emit_usage(thread_id, second.turn_id, total=(150, 140), last=(20, 20))
        self.server.complete_turn(thread_id, second.turn_id, final=None, status="interrupted")
        self.assert_problem(await self.wait_done(host, second), "interrupted", None)
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt"), 0)

        # Turn 3 reaches 60 of its own output tokens, past the cap, so one interrupt goes out before any more usage.
        self.server.interrupt_completes = False
        third = await asyncio.wait_for(host.continue_codex_thread(thread_id, "Third.", overrides=capped), WAIT_SECONDS)
        self.server.emit_usage(thread_id, third.turn_id, total=(170, 160), last=(20, 20))
        self.server.emit_usage(thread_id, third.turn_id, total=(210, 200), last=(40, 40))
        await self.wait_for_request("turn/interrupt", lambda params: params.get("turnId") == third.turn_id)
        self.server.emit_usage(thread_id, third.turn_id, total=(240, 270), last=(30, 70))
        self.server.complete_turn(thread_id, third.turn_id, final=None, status="interrupted")
        self.assert_problem(await self.wait_done(host, third), "interrupted", "codex.budget_exhausted")
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt"), 1)
        # INV-19: tokens produced after the crossing still count toward the turn.
        usage = await asyncio.wait_for(host.track_codex_thread_usage(thread_id), WAIT_SECONDS)
        self.assertEqual([entry.usage.output_tokens for entry in usage.turns], [90, 50, 130])


@requires_sdk
class CodexHostTurnOutcomeTests(HostTestCase):
    """AC-11, AC-12 and AC-13: process death, failed turns and structured output."""

    async def test_process_death_fails_the_running_turn_and_later_calls_without_leaking_stderr(self) -> None:
        # AC-11, EC-34, D-27, INV-6, INV-9.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        handle = await self.spawn(host)
        self.server.die(f"thread 'main' panicked: {STDERR_SECRET}")
        # Precondition: openai-codex's own error carries the stderr text, so its absence below means something.
        await self.wait_until(lambda: any(STDERR_SECRET in str(error) for error in self.server.reader_errors), "the SDK reader to fail with the stderr tail")
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "failed", "codex.process_exited")
        self.assertIsNone(snapshot.result)
        # D-27: the host reaps the dead process on its own; from then on, calls that talk to Codex send nothing.
        await self.wait_until(lambda: self.server.closed >= 1, "the host to reap the dead app-server")
        sent = len(self.server.requests)
        errors = [
            await self.assert_codex_error(host.check_codex_ready(), "codex.process_exited"),
            await self.assert_codex_error(host.spawn_codex_thread(CodexSpawnRequest(prompt="Again.")), "codex.process_exited"),
            await self.assert_codex_error(host.steer_codex_turn(handle, "More."), "codex.process_exited"),
        ]
        self.assertEqual(len(self.server.requests), sent)
        self.assertEqual(self.server.kinds("write_after_close"), [])
        self.assertEqual(await host.get_codex_turn_result(handle), snapshot)
        assert_no_canary(self, [text for error in errors for text in error_texts(error)] + [repr(snapshot)])

    async def test_a_non_json_stdout_line_kills_the_host_without_leaking_the_line(self) -> None:
        # AC-11, EC-72: openai-codex quotes the bad line in its error; no host message may.
        host = await self.open_host()
        handle = await self.spawn(host)
        self.server.send_raw(f"warning: {LINE_SECRET}")
        await self.wait_until(lambda: any(LINE_SECRET in str(error) for error in self.server.reader_errors), "the SDK reader to fail on the bad line")
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "failed", "codex.process_exited")
        await self.wait_until(lambda: self.server.closed >= 1, "the host to reap the dead app-server")
        error = await self.assert_codex_error(host.read_codex_thread(handle.thread_id), "codex.process_exited")
        self.assertEqual(self.server.kinds("write_after_close"), [])
        assert_no_canary(self, error_texts(error) + [repr(snapshot)])

    async def test_a_failed_turn_maps_each_codex_error_info_to_its_code(self) -> None:
        # AC-12, INV-22, EC-33: object variants and unknown values take the default branch.
        host = await self.open_host()
        for info, code in ERROR_INFO_ROWS:
            with self.subTest(codex_error_info=info):
                handle = await self.spawn(host)
                message = f"Codex stopped: {info}."
                self.server.complete_turn(handle.thread_id, handle.turn_id, final=None, status="failed", error={"message": message, "codexErrorInfo": info})
                snapshot = await self.wait_done(host, handle)
                self.assert_problem(snapshot, "failed", code)
                self.assertIn(message, snapshot.problem.message)
                self.assertIsNotNone(snapshot.result)

    async def test_structured_output_is_validated_and_a_missing_answer_is_invalid(self) -> None:
        # AC-13, INV-20, INV-21, EC-31, EC-32: a bad answer stays COMPLETED with its raw text.
        host = await self.open_host()
        cases = (
            ('{"title": "Vidbyte SDK"}', None, ReadmeSummary(title="Vidbyte SDK")),
            ('{"name": 1}', "codex.schema_violation", None),
            ("The title is Vidbyte SDK.", "codex.schema_violation", None),
        )
        for final, code, structured in cases:
            with self.subTest(final=final):
                handle = await self.spawn(host, output_schema=ReadmeSummary)
                self.server.complete_turn(handle.thread_id, handle.turn_id, final=final)
                snapshot = await self.wait_done(host, handle)
                self.assert_problem(snapshot, "completed", code)
                self.assertEqual(snapshot.result.final_response, final)
                self.assertEqual(snapshot.result.structured, structured)
        handle = await self.spawn(host, output_schema=ReadmeSummary)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final=None)
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "failed", "codex.response_invalid")
        self.assertIsNone(snapshot.result)


@requires_sdk
class CodexHostSteerAndUsageTests(HostTestCase):
    """AC-16 and AC-17: steer, interrupt, handle ownership and usage tracking."""

    async def test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned(self) -> None:
        # AC-16, INV-23, EC-23, EC-25.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        host = await self.open_host()
        handle = await self.spawn(host)
        self.assertEqual(await asyncio.wait_for(host.steer_codex_turn(handle, "Also check the tests."), WAIT_SECONDS), handle)
        steer = self.server.matching("turn/steer")[0].params
        self.assertEqual((steer["threadId"], steer["expectedTurnId"]), (handle.thread_id, handle.turn_id))
        self.assertEqual(input_texts(steer), [("text", "Also check the tests.")])
        self.assertIsNone(await asyncio.wait_for(host.interrupt_codex_turn(handle), WAIT_SECONDS))
        self.assert_problem(await self.wait_done(host, handle), "interrupted", None)
        self.assertEqual(self.count("turn/interrupt"), 1)

        sent = len(self.server.requests)
        await self.assert_codex_error(host.steer_codex_turn(handle, "One more thing."), "codex.session_not_found")
        self.assertIsNone(await asyncio.wait_for(host.interrupt_codex_turn(handle), WAIT_SECONDS))
        foreign = CodexTurnHandle(thread_id=handle.thread_id, turn_id="turn-from-elsewhere")
        for call in (
            host.wait_codex_turn(foreign, timeout_seconds=1.0),
            host.get_codex_turn_result(foreign),
            host.steer_codex_turn(foreign, "Hello."),
            host.interrupt_codex_turn(foreign),
        ):
            await self.assert_codex_error(call, "codex.session_not_found")
        self.assertEqual(len(self.server.requests), sent)

    async def test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost(self) -> None:
        # AC-17, INV-36, D-19: the running turn is left out, and cost comes from the repo's own pricing.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        host = await self.open_host()
        first = await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5"))
        thread_id = first.thread_id
        self.server.complete_turn(thread_id, first.turn_id, final="One.", usage=self.fakes.token_usage((100, 20), (100, 20)))
        await self.wait_done(host, first)
        second = await asyncio.wait_for(host.continue_codex_thread(thread_id, "Two."), WAIT_SECONDS)
        self.server.complete_turn(thread_id, second.turn_id, final="Two.", usage=self.fakes.token_usage((300, 60), (200, 40)))
        await self.wait_done(host, second)
        await asyncio.wait_for(host.continue_codex_thread(thread_id, "Three."), WAIT_SECONDS)

        usage = await asyncio.wait_for(host.track_codex_thread_usage(thread_id), WAIT_SECONDS)
        self.assertEqual(usage.thread_id, thread_id)
        self.assertEqual([entry.turn_id for entry in usage.turns], [first.turn_id, second.turn_id])
        self.assertEqual([(entry.usage.input_tokens, entry.usage.output_tokens) for entry in usage.turns], [(100, 20), (200, 40)])
        self.assertEqual((usage.total.input_tokens, usage.total.output_tokens), (300, 60))
        expected = _rollup("gpt-5.5", ((100, 20), (200, 40)))
        self.assertGreater(expected.cost_usd, 0)
        self.assertAlmostEqual(usage.cost_usd, expected.cost_usd, places=12)
        self.assertTrue(usage.cost_complete)

        await self.assert_codex_error(host.track_codex_thread_usage(self.server.seed_thread().thread_id), "codex.session_not_found")
        custom = await self.spawn(host, thread=CodexThreadSettings(model="llama-local", model_provider="ollama"))
        self.server.complete_turn(custom.thread_id, custom.turn_id, final="Local.", usage=self.fakes.token_usage((50, 10), (50, 10)))
        await self.wait_done(host, custom)
        self.assertIsNone((await asyncio.wait_for(host.track_codex_thread_usage(custom.thread_id), WAIT_SECONDS)).cost_usd)
        silent = await self.spawn(host)
        self.server.complete_turn(silent.thread_id, silent.turn_id, final="No usage reported.")
        await self.wait_done(host, silent)
        unpriced = await asyncio.wait_for(host.track_codex_thread_usage(silent.thread_id), WAIT_SECONDS)
        self.assertEqual([entry.usage_available for entry in unpriced.turns], [False])
        self.assertFalse(unpriced.cost_complete)


if __name__ == "__main__":
    unittest.main()
