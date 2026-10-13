"""FILE: tests/features/claude_host/test_claude_host_turns.py

PURPOSE: Proves how one spawned turn runs and ends: the handle comes back live before the turn can finish, waits never alter the turn, a finished turn reports the result's fields, every failure condition and SDK exception maps to the one code the precedence table names, usage reports the latest cumulative figures, and injected results never end the prompt's turn.
ROLE IN CODEBASE: Turn layer of tests/features/claude_host/ (spec AC-3 to AC-6, AC-15, AC-28, AC-36, AC-39, INV-3, INV-7, INV-9, INV-19, INV-20, EC-8 to EC-18, EC-24, EC-56). Exercises vidbyte/harnesses/native/claude/{host,session,failures}.py and the records in vidbyte/lib/dataclasses/claude_host.py.
ARCHITECTURE NOTE: Turns run through the real host, session pump and failure mapper; only the vendor client is faked. The precedence and exception tables also call ClaudeFailureMapper directly, because some rows (two conditions at once) cannot be produced cleanly through a stream.
COMMON MODIFICATION PATTERNS: When the spec adds a classification row, add one case to ClassificationPrecedenceTests with the condition it must beat and the one it must lose to. When a new SDK exception class is mapped, add it to ExceptionMappingTests.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not wait on wall-clock sleeps; wait on recorded fake calls with eventually(). 3. Do not compare a reason with exact text; the spec fixes what a reason names, not its wording.
KNOWN EDGE CASES: A held prompt keeps its turn RUNNING until the test calls finish(). The fake stamps each message's empty session_id with its client's session, as the CLI does. A rejected window is only tested together with an error result, because the spec does not say how a rejected window and a success result combine beyond the precedence order.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.2, 9.1 and 9.2 ("Turn classification", "Exception mapping").
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_turns.py
"""

from __future__ import annotations

import asyncio
import unittest
import uuid
from pathlib import Path
from typing import Any

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    END_OF_STREAM,
    ERROR_MARKER,
    FAKE_CLI_PATH,
    FAR_FUTURE_RESET,
    HANG_GUARD_SECONDS,
    INVALID_ARGUMENT,
    INVALID_ARGUMENT_NEXT_STEP,
    LIVE_STATUSES,
    SHORT_TIMEOUT_SECONDS,
    START_FAILURE_NEXT_STEP,
    ClaudeHostCase,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    FakeClaudeSdk,
    MessageParseError,
    ProcessError,
    ResultError,
    answer_for,
    assistant_message,
    eventually,
    eventually_async,
    init_message,
    model_usage_entry,
    rate_limit_event,
    result_message,
    settle,
    task_notification,
    task_progress,
)

SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


async def audit_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    """A hook callback in the SDK's own shape."""
    return {}


class TurnCase(ClaudeHostCase):
    """Adds a helper that runs one scripted turn on a fresh host and returns its final result and client."""

    async def run_turn(self, prompt: str, messages: tuple[Any, ...], **fields: Any) -> tuple[Any, Any]:
        self.fake.reply(prompt, *messages)
        host = await self.open_host()
        handle = await self.spawn(host, prompt, **fields)
        result = await self.finished(host, handle)
        return result, await self.client_for(handle)

    def assert_failed(self, result: Any, code: str, next_step: str) -> None:
        self.assertEqual(result.status.value, "failed")
        self.assertIsNotNone(result.failure)
        self.assertEqual(result.failure.code.value, code)
        self.assertEqual(result.failure.next_step, next_step)
        self.assertTrue(result.failure.reason)
        self.assertNotIn(ERROR_MARKER, result.failure.reason)
        self.assertNotIn(ERROR_MARKER, result.failure.next_step)


class SpawnSnapshotTests(TurnCase):
    """AC-3, INV-3 and INV-10: spawn returns a live handle at once, and the client gets the host's resolved CLI path."""

    async def test_spawn_returns_a_live_handle_before_the_turn_can_finish(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        host = await self.open_host()
        # Call the host directly, with no wrapper task, so nothing else runs between the two calls.
        handle = await host.spawn_claude_session(ClaudeSpawnRequest(prompt=DEFAULT_PROMPT, cwd="C:/work/repo"))
        snapshot = await host.get_claude_turn_result(handle)
        self.assertIn(snapshot.status.value, LIVE_STATUSES)
        self.assertEqual((snapshot.handle_id, snapshot.session_id), (handle.handle_id, handle.session_id))
        self.assertEqual(uuid.UUID(handle.handle_id).version, 4)
        self.assertEqual(uuid.UUID(handle.session_id).version, 4)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")

    async def test_the_client_runs_the_prompt_with_the_hosts_cli_path(self) -> None:
        self.fake.hold(DEFAULT_PROMPT)
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        self.assertIsNotNone(client.options.cli_path)
        self.assertEqual(Path(client.options.cli_path), Path(FAKE_CLI_PATH))
        self.assertEqual(client.options.session_id, handle.session_id)
        self.assertLess(client.calls.index("connect"), client.calls.index("get_server_info"))
        self.assertLess(client.calls.index("get_server_info"), client.calls.index("query"))
        self.assertEqual(client.queries, [DEFAULT_PROMPT])
        client.finish("Done.")
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "Done."))
        self.assertEqual(client.disconnect_calls, 1)


class WaitTests(TurnCase):
    """AC-4, INV-9 and EC-24: a wait that times out or is cancelled never changes the turn."""

    async def test_a_timed_out_wait_returns_the_running_snapshot_and_the_turn_continues(self) -> None:
        self.fake.hold(DEFAULT_PROMPT)
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        early = await host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)
        self.assertEqual(early.status.value, "running")
        self.assertEqual((client.interrupt_calls, client.disconnect_calls), (0, 0))
        client.finish("All 42 tests pass.")
        final = await host.wait_claude_turn(handle, timeout_seconds=HANG_GUARD_SECONDS)
        self.assertEqual((final.status.value, final.result_text), ("completed", "All 42 tests pass."))

    async def test_cancelling_a_wait_leaves_the_turn_running(self) -> None:
        self.fake.hold(DEFAULT_PROMPT)
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        waiter = asyncio.create_task(host.wait_claude_turn(handle, timeout_seconds=HANG_GUARD_SECONDS))
        await settle()
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertEqual((await self.snapshot(host, handle)).status.value, "running")
        self.assertEqual((client.interrupt_calls, client.disconnect_calls), (0, 0))
        client.finish("Still finished.")
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "Still finished."))


class ResultFieldTests(TurnCase):
    """FR-11 and the ClaudeTurnResult fields: a completed turn reports what its own result said."""

    async def test_a_successful_turn_reports_the_result_fields(self) -> None:
        result, client = await self.run_turn(DEFAULT_PROMPT, (init_message(), assistant_message("Reading the tree."), result_message(result=answer_for(DEFAULT_PROMPT))))
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.session_id, client.session)
        self.assertEqual(result.result_text, answer_for(DEFAULT_PROMPT))
        self.assertIsNone(result.failure)
        self.assertEqual(result.num_turns, 1)
        self.assertEqual(result.duration_ms, 4200)
        self.assertEqual(result.total_cost_usd, 0.0123)
        self.assertEqual(result.stop_reason, "end_turn")
        self.assertEqual(result.terminal_reason, "completed")
        self.assertEqual(result.permission_denials, ())
        self.assertIsNone(result.structured_output)
        self.assertIsNone(result.hooks_applied)
        self.assertEqual(client.disconnect_calls, 1)
        self.assertEqual(self.fake.connected_now, 0)

    async def test_structured_output_is_returned_with_the_result(self) -> None:
        messages = (init_message(), result_message(result="Summary attached.", structured_output={"summary": "The parser drops trailing commas."}))
        result, _ = await self.run_turn(DEFAULT_PROMPT, messages, output_schema=SUMMARY_SCHEMA)
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.structured_output, {"summary": "The parser drops trailing commas."})
        self.assertIsNone(result.failure)


class FailureDetectionTests(TurnCase):
    """AC-5, AC-6, AC-39 and EC-8 to EC-18: each condition ends the turn with the code the classification names."""

    async def test_budget_subtypes_end_with_budget_exhausted(self) -> None:
        for subtype, terminal_reason in (("error_max_budget_usd", "budget_exhausted"), ("error_max_turns", "max_turns")):
            with self.subTest(subtype=subtype):
                messages = (init_message(), assistant_message("Still working."), result_message(result=None, subtype=subtype, is_error=True, terminal_reason=terminal_reason, stop_reason=None))
                result, client = await self.run_turn(f"Long task for {subtype}.", messages)
                self.assert_failed(result, "claude.budget_exhausted", CLAUDE_NEXT_STEPS["claude.budget_exhausted"])
                self.assertEqual(client.disconnect_calls, 1)

    async def test_each_stream_condition_maps_to_its_code(self) -> None:
        error_result = {"result": None, "subtype": "error_during_execution", "is_error": True, "terminal_reason": "api_error", "stop_reason": None}
        cases = (
            ("authentication_failed", (init_message(), assistant_message("Invalid API key.", error="authentication_failed"), result_message(result="Invalid API key. Please run /login.", is_error=True, api_error_status=401)), "claude.not_signed_in"),
            ("billing_error", (init_message(), assistant_message("Credit balance is too low.", error="billing_error"), result_message(**error_result, api_error_status=400)), "claude.billing_error"),
            ("rate_limit error", (init_message(), assistant_message("Rate limited.", error="rate_limit"), result_message(**error_result, api_error_status=429)), "claude.usage_limited"),
            ("rejected window", (init_message(), rate_limit_event("five_hour", "rejected", resets_at=FAR_FUTURE_RESET, overage_status="rejected"), result_message(**error_result)), "claude.usage_limited"),
            ("model_not_found", (init_message(), assistant_message("Model not found.", error="model_not_found"), result_message(**error_result, api_error_status=404)), "claude.model_unknown"),
            ("structured output retries", (init_message(), result_message(result=None, subtype="error_max_structured_output_retries", is_error=True, terminal_reason="structured_output_retry_exhausted")), "claude.schema_violation"),
            ("stream ended without a result", (init_message(), assistant_message("Working."), END_OF_STREAM), "claude.process_exited"),
            ("process died after the prompt", (init_message(), ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=ERROR_MARKER)), "claude.process_exited"),
            ("malformed JSON", (init_message(), CLIJSONDecodeError(f"{{not json {ERROR_MARKER}", ValueError(ERROR_MARKER))), "claude.protocol_mismatch"),
            ("unparsable message", (init_message(), MessageParseError(f"Unknown message type {ERROR_MARKER}", {"type": "mystery"})), "claude.protocol_mismatch"),
            ("other SDK error", (init_message(), ClaudeSDKError(f"Unexpected control response {ERROR_MARKER}")), "claude.protocol_mismatch"),
            ("bare control-protocol exception", (init_message(), Exception(f"Control request failed {ERROR_MARKER}")), "claude.protocol_mismatch"),
            ("result error for max turns", (init_message(), ResultError(f"Turn failed {ERROR_MARKER}", data={"subtype": "error_max_turns", "errors": [ERROR_MARKER]})), "claude.budget_exhausted"),
        )
        for label, messages, code in cases:
            with self.subTest(condition=label):
                result, client = await self.run_turn(f"Prompt for {label}.", messages)
                self.assert_failed(result, code, CLAUDE_NEXT_STEPS[code])
                self.assertEqual(len(client.queries), 1)
                self.assertEqual(client.disconnect_calls, 1)

    async def test_api_error_reason_names_the_cli_vocabulary_but_no_message_text(self) -> None:
        messages = (
            init_message(),
            assistant_message(f"API Error: 529 Overloaded {ERROR_MARKER}", error="overloaded"),
            result_message(result=None, subtype="error_during_execution", is_error=True, api_error_status=529, terminal_reason="model_error", stop_reason=None, errors=[f"529 Overloaded {ERROR_MARKER}"]),
        )
        result, _ = await self.run_turn(DEFAULT_PROMPT, messages)
        self.assert_failed(result, "claude.api_error", CLAUDE_NEXT_STEPS["claude.api_error"])
        for fact in ("error_during_execution", "model_error", "529", "overloaded"):
            with self.subTest(fact=fact):
                self.assertIn(fact, result.failure.reason)

    async def test_a_missing_structured_output_keeps_the_raw_text(self) -> None:
        messages = (init_message(), result_message(result="Here is the summary in prose.", structured_output=None))
        result, _ = await self.run_turn(DEFAULT_PROMPT, messages, output_schema=SUMMARY_SCHEMA)
        self.assert_failed(result, "claude.schema_violation", CLAUDE_NEXT_STEPS["claude.schema_violation"])
        self.assertEqual(result.result_text, "Here is the summary in prose.")

    async def test_denied_tools_complete_with_a_permission_failure(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudePermissionDenial

        denials = [{"tool_name": "Bash", "tool_use_id": "toolu_01", "tool_input": {"command": "rm -rf build"}}, {"tool_name": "mcp__vidbyte__close_ticket", "tool_use_id": "toolu_02", "tool_input": {"ticket": "T-7"}}]
        messages = (init_message(), result_message(result="I could not delete the build folder.", permission_denials=denials))
        result, _ = await self.run_turn(DEFAULT_PROMPT, messages)
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.failure.code.value, "claude.permission_denied")
        self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.permission_denied"])
        self.assertEqual(result.result_text, "I could not delete the build folder.")
        self.assertEqual(result.permission_denials, (ClaudePermissionDenial(tool_name="Bash", tool_use_id="toolu_01"), ClaudePermissionDenial(tool_name="mcp__vidbyte__close_ticket", tool_use_id="toolu_02")))

    async def test_connect_failures_map_by_exception_and_send_no_prompt(self) -> None:
        cases = (
            ("CLINotFoundError", lambda: CLINotFoundError("Claude Code not found", cli_path=FAKE_CLI_PATH), "claude.not_installed", CLAUDE_NEXT_STEPS["claude.not_installed"]),
            ("ValueError", lambda: ValueError(f"Invalid option {ERROR_MARKER}"), INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP),
            ("TypeError", lambda: TypeError(f"skills must be a list {ERROR_MARKER}"), INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP),
            ("ProcessError", lambda: ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=f"error: unknown option {ERROR_MARKER}"), "claude.process_exited", START_FAILURE_NEXT_STEP),
            ("CLIConnectionError", lambda: CLIConnectionError(f"Failed to start Claude Code: {ERROR_MARKER}"), "claude.process_exited", START_FAILURE_NEXT_STEP),
        )
        for label, factory, code, next_step in cases:
            with self.subTest(exception=label):
                self.fake.connect_error = factory
                host = await self.open_host()
                handle = await self.spawn(host, f"Prompt for {label}.")
                result = await self.finished(host, handle)
                self.assert_failed(result, code, next_step)
                client = await self.client_for(handle)
                self.assertEqual(client.queries, [])
                self.assertEqual(client.disconnect_calls, 1)

    async def test_a_start_failure_after_the_prompt_gets_the_usual_next_step(self) -> None:
        # AC-39: the same exception ending the stream after the prompt was sent is not a start failure.
        for factory in (lambda: ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1), lambda: CLIConnectionError(f"Connection lost {ERROR_MARKER}")):
            with self.subTest(exception=type(factory()).__name__):
                result, client = await self.run_turn(f"Prompt for {type(factory()).__name__}.", (init_message(), factory()))
                self.assert_failed(result, "claude.process_exited", CLAUDE_NEXT_STEPS["claude.process_exited"])
                self.assertEqual(len(client.queries), 1)

    async def test_a_failing_disconnect_leaves_the_classification_unchanged(self) -> None:
        self.fake.disconnect_error = lambda: CLIConnectionError(f"close failed {ERROR_MARKER}")
        result, client = await self.run_turn(DEFAULT_PROMPT, (init_message(), result_message(result="Finished before the close failed.")))
        self.assertEqual((result.status.value, result.result_text), ("completed", "Finished before the close failed."))
        self.assertIsNone(result.failure)
        self.assertEqual(client.disconnect_calls, 1)


class ExceptionMappingTests(unittest.TestCase):
    """Section 9.2 "Exception mapping": ClaudeFailureMapper.from_exception, row by row, naming only the operation and the class."""

    def test_each_exception_maps_to_its_code_and_next_step(self) -> None:
        from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
        from vidbyte.lib.errors import ClaudeOperationError

        sdk = FakeClaudeSdk().types()
        steps = CLAUDE_NEXT_STEPS
        cases = (
            (CLINotFoundError("Claude Code not found", cli_path=FAKE_CLI_PATH), "connect", "claude.not_installed", steps["claude.not_installed"]),
            (ResultError(f"failed {ERROR_MARKER}", data={"subtype": "error_max_turns", "errors": [ERROR_MARKER]}), "receive_messages", "claude.budget_exhausted", steps["claude.budget_exhausted"]),
            (ResultError(f"failed {ERROR_MARKER}", data={"subtype": "error_max_budget_usd"}), "receive_messages", "claude.budget_exhausted", steps["claude.budget_exhausted"]),
            (ResultError(f"failed {ERROR_MARKER}", data={"subtype": "error_max_structured_output_retries"}), "receive_messages", "claude.schema_violation", steps["claude.schema_violation"]),
            (ResultError(f"failed {ERROR_MARKER}", data={"subtype": "error_during_execution", "api_error_status": 500}), "receive_messages", "claude.api_error", steps["claude.api_error"]),
            (ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=ERROR_MARKER), "receive_messages", "claude.process_exited", steps["claude.process_exited"]),
            (ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=ERROR_MARKER), "connect", "claude.process_exited", START_FAILURE_NEXT_STEP),
            (CLIConnectionError(f"Failed to start Claude Code: {ERROR_MARKER}"), "connect", "claude.process_exited", START_FAILURE_NEXT_STEP),
            (CLIConnectionError(f"Not connected {ERROR_MARKER}"), "query", "claude.process_exited", steps["claude.process_exited"]),
            (CLIJSONDecodeError(f"{{bad {ERROR_MARKER}", ValueError(ERROR_MARKER)), "receive_messages", "claude.protocol_mismatch", steps["claude.protocol_mismatch"]),
            (MessageParseError(f"Unknown message type {ERROR_MARKER}"), "receive_messages", "claude.protocol_mismatch", steps["claude.protocol_mismatch"]),
            (ClaudeSDKError(f"sdk failure {ERROR_MARKER}"), "query", "claude.protocol_mismatch", steps["claude.protocol_mismatch"]),
            (ValueError(f"Invalid option {ERROR_MARKER}"), "connect", INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP),
            (TypeError(f"skills must be a list {ERROR_MARKER}"), "connect", INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP),
            (RuntimeError(f"control request timed out {ERROR_MARKER}"), "interrupt", "claude.protocol_mismatch", steps["claude.protocol_mismatch"]),
            (Exception(f"Control request failed {ERROR_MARKER}"), "query", "claude.protocol_mismatch", steps["claude.protocol_mismatch"]),
        )
        for exception, operation, code, next_step in cases:
            with self.subTest(exception=type(exception).__name__, operation=operation, code=code):
                error = ClaudeFailureMapper.from_exception(exception, operation=operation, sdk=sdk)
                self.assertIsInstance(error, ClaudeOperationError)
                self.assertEqual(error.failure_code, code)
                self.assertEqual(error.next_step, next_step)
                self.assertEqual(error.operation, operation)
                self.assertIn(operation, error.reason)
                self.assertIn(type(exception).__name__, error.reason)
                self.assertNotIn(ERROR_MARKER, error.reason)
                self.assertNotIn(ERROR_MARKER, str(error))

    def test_failure_takes_its_next_step_from_the_code(self) -> None:
        from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
        from vidbyte.lib.enums.failure import FailureCode

        failure = ClaudeFailureMapper.failure(FailureCode.CLAUDE_API_ERROR, "query ended with subtype error_during_execution.")
        self.assertEqual(failure.code, FailureCode.CLAUDE_API_ERROR)
        self.assertEqual(failure.reason, "query ended with subtype error_during_execution.")
        self.assertEqual(failure.next_step, "Retry with backoff.")


class ClassificationPrecedenceTests(unittest.TestCase):
    """INV-19 and D-20: ClaudeFailureMapper.classify_turn applies the fixed precedence; the first matching row wins."""

    def outcome(self, **changes: Any) -> Any:
        from vidbyte.lib.dataclasses.claude_host import ClaudeTurnOutcome

        fields = {
            "result_seen": True,
            "is_error": False,
            "subtype": "success",
            "terminal_reason": "completed",
            "api_error_status": None,
            "structured_output_missing": False,
            "permission_denials": (),
            "assistant_errors": (),
            "rate_limit_rejected": False,
            "interrupted": False,
            "budget_expired": False,
            "precondition_failure": None,
            "stream_failure": None,
        }
        fields.update(changes)
        return ClaudeTurnOutcome(**fields)

    def test_the_first_matching_row_wins(self) -> None:
        from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
        from vidbyte.lib.dataclasses.claude_host import ClaudePermissionDenial
        from vidbyte.lib.enums.failure import FailureCode

        version = ClaudeFailureMapper.failure(FailureCode.CLAUDE_VERSION_UNSUPPORTED, "initialize reported version 2.1.200, below 2.1.296.")
        auth_mode = ClaudeFailureMapper.failure(FailureCode.CLAUDE_AUTH_MODE_UNSUPPORTED, "betas need an API key login.")
        stream = ClaudeFailureMapper.failure(FailureCode.CLAUDE_PROTOCOL_MISMATCH, "receive_messages raised CLIJSONDecodeError.")
        denial = ClaudePermissionDenial(tool_name="Bash", tool_use_id="toolu_01")
        error_result = {"is_error": True, "subtype": "error_during_execution", "terminal_reason": "model_error", "api_error_status": 500}
        cases = (
            ("plain success", {}, "completed", None),
            ("version check beats every later row", {"result_seen": False, "precondition_failure": version, "budget_expired": True, "interrupted": True, "rate_limit_rejected": True}, "failed", version),
            ("auth-mode check beats an interrupt", {"result_seen": False, "precondition_failure": auth_mode, "interrupted": True}, "failed", auth_mode),
            ("time budget beats interrupt and rate limits", {"budget_expired": True, "interrupted": True, "rate_limit_rejected": True, "assistant_errors": ("rate_limit",), **error_result}, "failed", "claude.budget_exhausted"),
            ("time budget without a result", {"result_seen": False, "budget_expired": True}, "failed", "claude.budget_exhausted"),
            ("interrupt beats an aborted error result", {"interrupted": True, "is_error": True, "subtype": "error_during_execution", "terminal_reason": "aborted_streaming", "assistant_errors": ("billing_error",)}, "interrupted", None),
            ("interrupt without a result", {"result_seen": False, "interrupted": True}, "interrupted", None),
            ("rejected window beats billing", {"rate_limit_rejected": True, "assistant_errors": ("billing_error",), **error_result}, "failed", "claude.usage_limited"),
            ("rate_limit error kind", {"assistant_errors": ("rate_limit",), **error_result}, "failed", "claude.usage_limited"),
            ("billing beats sign-in", {"assistant_errors": ("authentication_failed", "billing_error"), **error_result}, "failed", "claude.billing_error"),
            ("sign-in beats unknown model", {"assistant_errors": ("model_not_found", "authentication_failed"), **error_result}, "failed", "claude.not_signed_in"),
            ("unknown model beats budget subtypes", {"assistant_errors": ("model_not_found",), "is_error": True, "subtype": "error_max_turns", "terminal_reason": "max_turns"}, "failed", "claude.model_unknown"),
            ("budget subtype", {"is_error": True, "subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"}, "failed", "claude.budget_exhausted"),
            ("turn subtype beats structured retries", {"is_error": True, "subtype": "error_max_turns", "terminal_reason": "max_turns", "structured_output_missing": True}, "failed", "claude.budget_exhausted"),
            ("structured retries beat api error", {"is_error": True, "subtype": "error_max_structured_output_retries", "terminal_reason": "structured_output_retry_exhausted", "api_error_status": 500}, "failed", "claude.schema_violation"),
            ("missing structured output beats denials", {"structured_output_missing": True, "permission_denials": (denial,)}, "failed", "claude.schema_violation"),
            ("other error result", {"assistant_errors": ("overloaded",), **error_result}, "failed", "claude.api_error"),
            ("stream failure without a result", {"result_seen": False, "stream_failure": stream}, "failed", stream),
            ("stream ended without a result", {"result_seen": False}, "failed", "claude.process_exited"),
            ("success with denials", {"permission_denials": (denial,)}, "completed", "claude.permission_denied"),
        )
        for label, changes, status, expected in cases:
            with self.subTest(case=label):
                actual_status, failure = ClaudeFailureMapper.classify_turn(self.outcome(**changes))
                self.assertEqual(actual_status.value, status)
                if expected is None:
                    self.assertIsNone(failure)
                elif isinstance(expected, str):
                    self.assertEqual(failure.code.value, expected)
                    self.assertEqual(failure.next_step, CLAUDE_NEXT_STEPS[expected])
                else:
                    self.assertEqual(failure, expected)

    def test_api_error_reason_names_subtype_terminal_reason_status_and_error_kind(self) -> None:
        from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper

        outcome = self.outcome(is_error=True, subtype="error_during_execution", terminal_reason="model_error", api_error_status=529, assistant_errors=("overloaded",))
        status, failure = ClaudeFailureMapper.classify_turn(outcome)
        self.assertEqual((status.value, failure.code.value), ("failed", "claude.api_error"))
        for fact in ("error_during_execution", "model_error", "529", "overloaded"):
            with self.subTest(fact=fact):
                self.assertIn(fact, failure.reason)


class UsageTests(TurnCase):
    """AC-15, INV-20 and section 9.1 "Task usage": the snapshot reports the latest cumulative result and the last figures per task."""

    async def test_usage_reports_the_latest_result_and_each_task(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeModelUsage, ClaudeTaskUsage

        steer_message = "Focus on the failing tests."
        first_usage = {"claude-sonnet-4-5": model_usage_entry(input_tokens=1200, output_tokens=300, cache_read=800, cache_creation=100, web_search=0, cost_usd=0.02)}
        final_usage = {
            "claude-sonnet-4-5": model_usage_entry(input_tokens=3000, output_tokens=900, cache_read=1600, cache_creation=200, web_search=1, cost_usd=0.04),
            "claude-haiku-4-5": model_usage_entry(input_tokens=500, output_tokens=100, cache_read=0, cache_creation=0, web_search=0, cost_usd=0.01),
        }
        self.fake.hold(DEFAULT_PROMPT)
        self.fake.interrupt_reply = lambda: result_message(result=None, subtype="error_during_execution", is_error=True, total_cost_usd=0.02, model_usage=first_usage, terminal_reason="aborted_streaming", stop_reason=None)
        self.fake.reply(
            steer_message,
            init_message(),
            task_progress("task-1", "Run the test suite", total_tokens=1500, tool_uses=3, duration_ms=2000),
            task_notification("task-1", "The suite passes.", usage={"total_tokens": 2100, "tool_uses": 4, "duration_ms": 2600}),
            task_progress("task-2", "Lint the package", total_tokens=300, tool_uses=1, duration_ms=500),
            task_notification("task-3", "Background indexing finished.", usage={"total_tokens": 50, "tool_uses": 0, "duration_ms": 10}),
            task_progress("task-4", "Index the docs", total_tokens=100, tool_uses=1, duration_ms=100),
            task_notification("task-4", "Indexed.", usage=None),
            result_message(result="The failing tests are fixed.", total_cost_usd=0.05, model_usage=final_usage),
        )
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        before = await host.track_claude_session_usage(handle)
        self.assertIsNone(before.total_cost_usd)
        self.assertEqual((before.models, before.tasks), ((), ()))
        await asyncio.wait_for(host.steer_claude_session(handle, steer_message), HANG_GUARD_SECONDS)
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The failing tests are fixed."))
        usage = await host.track_claude_session_usage(handle)
        self.assertEqual((usage.handle_id, usage.session_id), (handle.handle_id, handle.session_id))
        # The figures are cumulative, so the latest result wins: 0.05, never 0.02 + 0.05.
        self.assertEqual(usage.total_cost_usd, 0.05)
        models = {model.model: model for model in usage.models}
        self.assertEqual(len(usage.models), 2)
        self.assertEqual(models["claude-sonnet-4-5"], ClaudeModelUsage(model="claude-sonnet-4-5", input_tokens=3000, output_tokens=900, cache_read_input_tokens=1600, cache_creation_input_tokens=200, web_search_requests=1, cost_usd=0.04))
        self.assertEqual(models["claude-haiku-4-5"], ClaudeModelUsage(model="claude-haiku-4-5", input_tokens=500, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0, web_search_requests=0, cost_usd=0.01))
        tasks = {task.task_id: task for task in usage.tasks}
        self.assertEqual(len(usage.tasks), 4)
        self.assertEqual(tasks["task-1"], ClaudeTaskUsage(task_id="task-1", description="Run the test suite", total_tokens=2100, tool_uses=4, duration_ms=2600))
        self.assertEqual(tasks["task-2"], ClaudeTaskUsage(task_id="task-2", description="Lint the package", total_tokens=300, tool_uses=1, duration_ms=500))
        self.assertEqual(tasks["task-3"], ClaudeTaskUsage(task_id="task-3", description="", total_tokens=50, tool_uses=0, duration_ms=10))
        self.assertEqual(tasks["task-4"], ClaudeTaskUsage(task_id="task-4", description="Index the docs", total_tokens=100, tool_uses=1, duration_ms=100))


class InitializeAndInjectedResultTests(TurnCase):
    """AC-28, AC-36 and D-28: hooks_applied comes from initialize, and only the prompt's own result ends its turn."""

    async def test_hooks_applied_is_true_with_hooks_and_none_without(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeHookMatcher
        from vidbyte.lib.enums.claude import ClaudeHookEvent

        host = await self.open_host()
        with_hooks = await self.spawn(host, "Run with hooks.", hooks=(ClaudeHookMatcher(event=ClaudeHookEvent.PRE_TOOL_USE, callbacks=(audit_hook,)),))
        without_hooks = await self.spawn(host, "Run without hooks.")
        self.assertIs((await self.finished(host, with_hooks)).hooks_applied, True)
        self.assertIsNone((await self.finished(host, without_hooks)).hooks_applied)

    async def test_an_injected_result_updates_usage_while_the_turn_keeps_running(self) -> None:
        self.fake.hold(DEFAULT_PROMPT)
        host = await self.open_host()
        handle = await self.spawn(host)
        client = await self.client_for(handle)
        await eventually(lambda: len(client.queries) == 1, "the prompt was sent")
        client.emit(result_message(result="Background task finished.", origin={"kind": "task-notification"}, total_cost_usd=0.02))
        await eventually_async(lambda: host.track_claude_session_usage(handle), lambda usage: usage.total_cost_usd == 0.02, "the injected result's cost")
        snapshot = await self.snapshot(host, handle)
        self.assertEqual(snapshot.status.value, "running")
        self.assertEqual(snapshot.result_text, "")
        self.assertEqual(client.disconnect_calls, 0)
        client.finish("The prompt's own answer.", total_cost_usd=0.05)
        result = await self.finished(host, handle)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The prompt's own answer."))
        self.assertEqual((await host.track_claude_session_usage(handle)).total_cost_usd, 0.05)

    async def test_a_human_origin_result_is_the_prompts_own(self) -> None:
        messages = (
            init_message(),
            result_message(result="A channel message was answered.", origin={"kind": "channel"}, total_cost_usd=0.01),
            assistant_message("Back to the prompt."),
            result_message(result="The prompt's own answer.", origin={"kind": "human"}, total_cost_usd=0.03),
        )
        result, _ = await self.run_turn(DEFAULT_PROMPT, messages)
        self.assertEqual((result.status.value, result.result_text), ("completed", "The prompt's own answer."))
        self.assertEqual(result.total_cost_usd, 0.03)


if __name__ == "__main__":
    unittest.main()
