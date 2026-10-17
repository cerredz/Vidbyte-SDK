"""FILE: tests/features/codex_host/test_codex_host_observability.py

PURPOSE: Proves the redacted logs the hardening slice adds: one record per app-server call, success at DEBUG and failure at WARNING with its code, error type and origin; one INFO record per server request naming who answered and a short answer label; DEBUG records for turn items and one INFO record per turn end; one WARNING per tool failure; every message %-style with arguments; and no record carrying a privacy canary, a prompt, command text, a cwd, model output or any exception text.
ROLE IN CODEBASE: Observability layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-18, INV-7 to INV-10, INV-23, INV-42, D-12, D-13). The class needs the optional openai-codex extra, so CI skips it.
ARCHITECTURE NOTE: HostTestCase.capture_logs records every logger under vidbyte.harnesses.native.codex and vidbyte.tools.builtins.codex at DEBUG, so a record written to a wrongly named logger is missed and the event check fails. The canaries are seeded where a careless log line would pick them up: the account email, the client env, the prompt, the command and cwd of an approval, Codex's error text, the model's final answer and a tool exception's message.
COMMON MODIFICATION PATTERNS: A new log event adds one expectation here with its fields; a new private value adds one canary seeded where it flows.
KNOWN EDGE CASES: log_fields splits a message on spaces, so every field value is checked as one token; an empty value reads as "". The no-handler host answers routed requests with handled_by=default and no fallback WARNING, because INV-17 lists no fallback reason for a host without a handler.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1 (INV-7 to INV-10, INV-23) and 8.1 (D-12, D-13).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_observability.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import unittest
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    CANARIES,
    ENV_SECRET,
    HOST_LOGGER,
    TOOLS_LOGGER,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    log_events,
    log_fields,
    make_echo_tool,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolStatus

CONNECTION_LOGGER = "vidbyte.harnesses.native.codex.connection"
PROMPT_CANARY = "prompt-canary-4e71"
COMMAND_CANARY = "command-canary-58ab"
CWD_CANARY = os.path.abspath(os.path.join(os.sep, "cwd-canary-2f90"))
RPC_CANARY = "rpc-canary-a3c5"
FINAL_CANARY = "final-canary-7d18"
TOOL_CANARY = "tool-canary-c624"
QUESTION_CANARY = "question-canary-19be"
ALL_CANARIES = CANARIES + (PROMPT_CANARY, COMMAND_CANARY, CWD_CANARY, RPC_CANARY, FINAL_CANARY, TOOL_CANARY, QUESTION_CANARY)
EVENTS = (
    "codex_host_call",
    "codex_host_call_failed",
    "codex_host_server_request",
    "codex_host_server_request_fallback",
    "codex_host_turn_item",
    "codex_host_turn_ended",
    "codex_host_turn_event_failed",
    "codex_host_turn_lost",
    "codex_host_tool_failed",
)


@requires_sdk
class CodexObservabilityTests(HostTestCase):
    """AC-18, INV-7 to INV-10 and INV-23: each event once, with its fields, and nothing private."""

    def fields_of(self, records: list[logging.LogRecord], event: str, **match: str) -> list[dict[str, str]]:
        return [fields for fields in (log_fields(record) for record in log_events(records, event)) if all(fields.get(key) == value for key, value in match.items())]

    def assert_redacted(self, records: list[logging.LogRecord]) -> None:
        """INV-10: %-style with arguments, no exception attached, and no canary in any rendered message."""
        ours = [record for record in records if isinstance(record.msg, str) and record.msg.split(" ", 1)[0] in EVENTS]
        self.assertTrue(ours)
        for record in ours:
            with self.subTest(record=record.msg.split(" ", 1)[0]):
                self.assertIn("%", record.msg)
                self.assertIsInstance(record.args, tuple)
                self.assertTrue(record.args)
                self.assertIsNone(record.exc_info)
                self.assertTrue(record.name.startswith((HOST_LOGGER, TOOLS_LOGGER)), record.name)
        assert_no_canary(self, [record.getMessage() for record in records] + [repr(record.args) for record in records], ALL_CANARIES)

    async def test_a_spawn_a_failed_call_server_requests_and_a_tool_failure_log_each_event_with_its_fields(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexClientSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.tools.toolsets import CodexHostTools

        records = self.capture_logs()
        host = await self.open_host(CodexClientSettings(env={"VIDBYTE_CANARY_TOKEN": ENV_SECRET}))
        await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)

        # A spawn with a tool, and its turn ending with a final answer.
        handle = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt=f"Summarize {PROMPT_CANARY}.", tools=(make_echo_tool(),))), WAIT_SECONDS)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final=f"The summary is {FINAL_CANARY}.")
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        started = self.fields_of(records, "codex_host_call", method="turn/start")
        self.assertEqual([(fields["operation"], fields["thread_id"]) for fields in started], [("spawn_codex_thread", handle.thread_id)])
        self.assertTrue(started[0]["duration_ms"].isdigit(), started[0])
        self.assertEqual(len(self.fields_of(records, "codex_host_call", method="thread/start", operation="spawn_codex_thread")), 1)
        items = self.fields_of(records, "codex_host_turn_item", thread_id=handle.thread_id, turn_id=handle.turn_id)
        self.assertEqual([fields["item_type"] for fields in items], ["agentMessage"])
        self.assertTrue(items[0]["item_id"])
        ended = self.fields_of(records, "codex_host_turn_ended", thread_id=handle.thread_id, turn_id=handle.turn_id)
        self.assertEqual(ended, [{"thread_id": handle.thread_id, "turn_id": handle.turn_id, "status": "completed", "failure_code": ""}])

        # One successful read and one failed read: one record each, the failure at WARNING with its code, type and origin.
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)
        self.assertEqual(len(self.fields_of(records, "codex_host_call", method="thread/read", operation="read_codex_thread", thread_id=handle.thread_id)), 1)
        self.server.fail("thread/read", self.fakes.FakeRpcError(-32603, f"store failed for {RPC_CANARY}"), times=1)
        await self.assert_codex_error(host.read_codex_thread(handle.thread_id), "codex.api_error")
        failed = [record for record in log_events(records, "codex_host_call_failed")]
        self.assertEqual(len(failed), 1)
        self.assertEqual((failed[0].levelno, failed[0].name), (logging.WARNING, CONNECTION_LOGGER))
        fields = log_fields(failed[0])
        self.assertEqual(
            {key: fields[key] for key in ("operation", "method", "thread_id", "failure_code", "error_type")},
            {"operation": "read_codex_thread", "method": "thread/read", "thread_id": handle.thread_id, "failure_code": "codex.api_error", "error_type": "InternalRpcError"},
        )
        self.assertEqual(fields["origin"].count(":"), 2, fields)
        self.assertTrue(fields["duration_ms"].isdigit(), fields)
        self.assertEqual(len(self.fields_of(records, "codex_host_call", method="thread/read", thread_id=handle.thread_id)), 1)

        # Server requests on a host without a handler: one INFO each, with who answered and what.
        ids = {"threadId": handle.thread_id, "turnId": handle.turn_id}
        asks = (
            ("item/commandExecution/requestApproval", {**ids, "itemId": "item-cmd", "command": f"rm -rf {COMMAND_CANARY}", "cwd": CWD_CANARY, "reason": PROMPT_CANARY}, "default", "decline"),
            ("item/tool/requestUserInput", {**ids, "itemId": "item-q", "questions": [{"id": "q1", "header": "h", "question": QUESTION_CANARY}]}, "default", "answers"),
            ("item/permissions/requestApproval", {**ids, "itemId": "item-p"}, "default", "no_permissions"),
            ("currentTime/read", {}, "default", "current_time"),
            ("item/somethingNew/request", {**ids, "itemId": "item-new"}, "default", "empty"),
            ("item/tool/call", {**ids, "callId": "call-1", "tool": "echo_text", "arguments": {"text": PROMPT_CANARY}}, "tool", "success"),
            ("item/tool/call", {"threadId": "thr-unknown", "turnId": "turn-x", "callId": "call-2", "tool": "echo_text", "arguments": {}}, "tool", "failure"),
        )
        before = len(log_events(records, "codex_host_server_request"))
        for method, params, handled_by, answer in asks:
            with self.subTest(method=method, answer=answer):
                count = len(log_events(records, "codex_host_server_request"))
                await self.ask(method, params)
                new = [log_fields(record) for record in log_events(records, "codex_host_server_request")[count:]]
                self.assertEqual([(entry["method"], entry["handled_by"], entry["answer"]) for entry in new], [(method, handled_by, answer)])
                self.assertEqual(log_events(records, "codex_host_server_request")[-1].levelno, logging.INFO)
        command = self.fields_of(records, "codex_host_server_request", method="item/commandExecution/requestApproval")[0]
        self.assertEqual((command["thread_id"], command["turn_id"], command["item_id"]), (handle.thread_id, handle.turn_id, "item-cmd"))
        self.assertEqual(len(log_events(records, "codex_host_server_request")) - before, len(asks))
        self.assertEqual(log_events(records, "codex_host_server_request_fallback"), [])

        # A tool whose host call raises something unexpected: an error result and one WARNING on the tools' logger.
        tools = CodexHostTools(host, max_live_turns=2)
        tool = next(tool for tool in tools if tool.spec().name == "check_codex_ready")
        with mock.patch.object(host, "check_codex_ready", side_effect=RuntimeError(TOOL_CANARY)):
            result = await asyncio.wait_for(tool.execute(ToolCall(tool_name="check_codex_ready", arguments={})), WAIT_SECONDS)
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertNotIn(TOOL_CANARY, result.output)
        tool_failed = log_events(records, "codex_host_tool_failed")
        self.assertEqual(len(tool_failed), 1)
        self.assertEqual(tool_failed[0].levelno, logging.WARNING)
        self.assertTrue(tool_failed[0].name.startswith(TOOLS_LOGGER), tool_failed[0].name)
        tool_fields = log_fields(tool_failed[0])
        self.assertEqual((tool_fields["tool"], tool_fields["error_type"]), ("check_codex_ready", "RuntimeError"))
        self.assertEqual(tool_fields["origin"].count(":"), 2, tool_fields)

        self.assert_redacted(records)

    async def test_a_handler_answer_and_a_fallback_are_logged_with_their_labels(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer
        from vidbyte.lib.enums.codex import CodexApprovalDecision

        async def handler(request: Any) -> Any:
            if request.item_id == "item-bad":
                raise RuntimeError(TOOL_CANARY)
            return CodexServerAnswer(decision=CodexApprovalDecision.ACCEPT)

        records = self.capture_logs()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        ids = {"threadId": handle.thread_id, "turnId": handle.turn_id}
        self.assertEqual(await self.ask("item/commandExecution/requestApproval", {**ids, "itemId": "item-ok", "command": COMMAND_CANARY, "cwd": CWD_CANARY}), {"decision": "accept"})
        self.assertEqual(await self.ask("item/fileChange/requestApproval", {**ids, "itemId": "item-bad", "reason": PROMPT_CANARY}), {"decision": "decline"})
        requests = [(fields["item_id"], fields["handled_by"], fields["answer"]) for fields in self.fields_of(records, "codex_host_server_request", thread_id=handle.thread_id)]
        self.assertEqual([request[0] for request in requests], ["item-ok", "item-bad"])
        self.assertEqual(requests[0], ("item-ok", "handler", "accept"))
        # INV-8 does not say whether a request the handler failed on is handled_by handler or default; what was sent is.
        self.assertIn(requests[1][1], ("handler", "default"))
        self.assertEqual(requests[1][2], "decline")
        fallback = log_events(records, "codex_host_server_request_fallback")
        self.assertEqual(len(fallback), 1)
        self.assertEqual((fallback[0].levelno, fallback[0].name), (logging.WARNING, CONNECTION_LOGGER))
        self.assertEqual({key: log_fields(fallback[0])[key] for key in ("method", "thread_id", "reason", "error_type")}, {"method": "item/fileChange/requestApproval", "thread_id": handle.thread_id, "reason": "handler_failed", "error_type": "RuntimeError"})
        self.assert_redacted(records)


if __name__ == "__main__":
    unittest.main()
