"""FILE: tests/features/codex_host/test_codex_host_observability.py

PURPOSE: Proves the redacted logs the hardening slice adds: one record per app-server call, success at DEBUG and failure at WARNING with its code, error type and origin, including a call whose caller was cancelled after it was sent and a start handed over on cancel, one only for a call whose bound ran out, and none for a call refused before it was sent; no asyncio or concurrent.futures record carrying the text of a handed-over start that failed; one INFO record per server request naming who answered and a short answer label; DEBUG records for turn items and one INFO record per turn end; one WARNING per tool failure; every message %-style with arguments; and no record carrying a privacy canary, a prompt, command text, a cwd, model output or any exception text.
ROLE IN CODEBASE: Observability layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-18, INV-7 to INV-10, INV-23, INV-42, D-12, D-13, EC-57, EC-58, the S4 review rows R-4, R-9 and R-10, and the S5 re-review rows R-11 and R-12). The class needs the optional openai-codex extra, so CI skips it.
ARCHITECTURE NOTE: HostTestCase.capture_logs records every logger under vidbyte.harnesses.native.codex and vidbyte.tools.builtins.codex at DEBUG, so a record written to a wrongly named logger is missed and the event check fails. The canaries are seeded where a careless log line would pick them up: the account email, the client env, the prompt, the command and cwd of an approval, Codex's error text, the model's final answer and a tool exception's message.
COMMON MODIFICATION PATTERNS: A new log event adds one expectation here with its fields; a new private value adds one canary seeded where it flows.
KNOWN EDGE CASES: The hostile-id rows name each Codex-made thread and turn through FakeAppServer.name_next, so those ids keep the fake's thr- and turn- prefixes; their expected tokens are literals worked out by hand from LogToken's two rules. CodexCallRecordTests runs the host on one worker thread, so a call that returns is the barrier after which every earlier worker has returned and run its done-callbacks. log_fields splits a message on spaces, so every field value is checked as one token; an empty value reads as "", and a word with no "=" fails the test. The R-11 rows also record the asyncio and concurrent.futures loggers and collect garbage before reading them, because asyncio reports a failure nothing read from Future.__del__; the R-12 rows compile a function under the file name "my handler.py" and read the raw words of each record. The no-handler host answers routed requests with handled_by=default and no fallback WARNING, because INV-17 lists no fallback reason for a host without a handler.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1 (INV-7 to INV-10, INV-23) and 8.1 (D-12, D-13).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_observability.py
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import time
import traceback
import unittest
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    CANARIES,
    ENV_SECRET,
    HOST_LOGGER,
    STDERR_SECRET,
    TOOLS_LOGGER,
    TURN_EVENTS_MODULE,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    log_events,
    log_fields,
    make_echo_tool,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolStatus
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

CONNECTION_LOGGER = "vidbyte.harnesses.native.codex.connection"
PROMPT_CANARY = "prompt-canary-4e71"
COMMAND_CANARY = "command-canary-58ab"
CWD_CANARY = os.path.abspath(os.path.join(os.sep, "cwd-canary-2f90"))
RPC_CANARY = "rpc-canary-a3c5"
FINAL_CANARY = "final-canary-7d18"
TOOL_CANARY = "tool-canary-c624"
QUESTION_CANARY = "question-canary-19be"
ANSWER_CANARY = "answer-canary-91f3"
ALL_CANARIES = CANARIES + (PROMPT_CANARY, COMMAND_CANARY, CWD_CANARY, RPC_CANARY, FINAL_CANARY, TOOL_CANARY, QUESTION_CANARY, ANSWER_CANARY)
TRANSLATOR = "vidbyte.harnesses.native.codex.wire.CodexResponseTranslator"
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
# Spec r5 INV-7 to INV-9: the keys of each host event, in order, read from its format string.
EVENT_KEYS = {
    "codex_host_call": ("operation", "method", "thread_id", "duration_ms"),
    "codex_host_call_failed": ("operation", "method", "thread_id", "failure_code", "error_type", "origin", "duration_ms"),
    "codex_host_server_request": ("method", "thread_id", "turn_id", "item_id", "handled_by", "answer"),
    "codex_host_server_request_fallback": ("method", "thread_id", "reason", "error_type", "origin"),
    "codex_host_turn_item": ("thread_id", "turn_id", "item_id", "item_type"),
    "codex_host_turn_ended": ("thread_id", "turn_id", "status", "failure_code"),
    "codex_host_turn_event_failed": ("thread_id", "turn_id", "error_type", "origin"),
    "codex_host_turn_lost": ("thread_id", "turn_id"),
}
# Spec r5 INV-10 (S4 R-9): values a compromised Codex or a caller can send, and the one token each must log as. Each token
# is worked out by hand from the two LogToken.of rules, so it does not come from the code under test. The fake names a thread
# thr-<suffix> and a turn turn-<suffix>, so the Codex-made ids keep those prefixes.
HOSTILE_THREAD = "thr-1 handled_by=handler %s answer=accept"
HOSTILE_THREAD_TOKEN = "thr-1_handled_by_handler__s_answer_accept"
HOSTILE_TURN = 'turn-1\r\nforged=1 "quoted" \u00e9'
HOSTILE_TURN_TOKEN = "turn-1__forged_1__quoted___"
# The INV-10 example, verbatim.
FORGED_ITEM = "item-1 handled_by=handler answer=accept\ncodex_host_server_request"
FORGED_ITEM_TOKEN = "item-1_handled_by_handler_answer_accept_codex_host_server_request"
HOSTILE_METHOD = "x/y handled_by=handler answer=accept\r\nmethod=forged"
HOSTILE_METHOD_TOKEN = "x/y_handled_by_handler_answer_accept__method_forged"
LONG_ID = "t" * 100_000
LONG_ID_TOKEN = "t" * 128 + "..."
# A caller-supplied thread id must be one line (CodexThreadReadRequest), so only spaces, "=" and "%" are left to it.
HOSTILE_CALLER_ID = "thr-404 failure_code=none %d"
HOSTILE_CALLER_TOKEN = "thr-404_failure_code_none__d"
EVENT_THREAD = "thr-2\r\nthread_id=forged turn_id=forged"
EVENT_THREAD_TOKEN = "thr-2__thread_id_forged_turn_id_forged"
EVENT_TURN = "turn-2 status=completed\tfailure_code="
EVENT_TURN_TOKEN = "turn-2_status_completed_failure_code_"


# Spec r6 INV-10 and EC-58 (S5 R-11): loggers the host never writes to, where asyncio and concurrent.futures report a
# future's failure that nothing read.
STRAY_LOGGERS = ("asyncio", "concurrent.futures")
# Spec r6 INV-7 and row 9 (S5 R-12): compile names a frame's file, so a frame "in" a file whose name has a space needs no
# file on disk. Line 2 of the source raises.
SPACED_FILE = "my handler.py"
SPACED_SOURCE = "def read_setting(*args, **kwargs):\n    raise KeyError('setting')\n"
SPACED_ORIGIN = "my_handler.py:read_setting:2"


def _on(thread_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda params: params.get("threadId") == thread_id


def _rendered(record: logging.LogRecord) -> str:
    """All a handler could print for a record: its message, its traceback with every chained exception, and its stack."""
    text = record.getMessage()
    if record.exc_info:
        text += "\n" + "".join(traceback.format_exception(*record.exc_info))
    return text + ("\n" + record.stack_info if record.stack_info else "")


def _raiser_in_a_spaced_file() -> Callable[..., Any]:
    """A function whose frame is in SPACED_FILE; whatever calls it gets a KeyError from line 2."""
    namespace: dict[str, Any] = {}
    exec(compile(SPACED_SOURCE, SPACED_FILE, "exec"), namespace)  # noqa: S102 - the source is a literal of this module
    return namespace["read_setting"]


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

    async def test_a_handler_answer_to_a_secret_question_reaches_codex_and_no_record(self) -> None:
        # AC-18, T-6, EC-7 and INV-10 (S4 R-4, mutant M40): an answer is private even when the developer's handler wrote it.
        # Codex gets the handler's answer to an isSecret question, and no record's message or arguments carry it.
        from vidbyte.lib.dataclasses.codex_host import (
            CodexServerAnswer,
            CodexUserInputAnswer,
        )
        from vidbyte.lib.enums.codex import CodexApprovalDecision

        async def handler(request: Any) -> Any:
            return CodexServerAnswer(decision=CodexApprovalDecision.ACCEPT, answers=(CodexUserInputAnswer(question_id="q1", answers=(ANSWER_CANARY,)),))

        records = self.capture_logs()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        question = {"id": "q1", "header": "Token", "question": "Paste the token.", "options": None, "isOther": False, "isSecret": True}
        answer = await self.ask("item/tool/requestUserInput", {"threadId": handle.thread_id, "turnId": handle.turn_id, "itemId": "item-secret", "questions": [question]})
        self.assertIn(ANSWER_CANARY, json.dumps(answer))
        logged = self.fields_of(records, "codex_host_server_request", item_id="item-secret")
        self.assertEqual([(fields["handled_by"], fields["answer"]) for fields in logged], [("handler", "answers")])
        self.assert_redacted(records)


@requires_sdk
class CodexLogTokenRecordTests(HostTestCase):
    """INV-10 (spec r5, S4 R-9): an id from Codex or from a caller logs as one bounded token, in every record that renders it."""

    def fields(self, records: list[logging.LogRecord], event: str) -> list[dict[str, str]]:
        return [log_fields(record) for record in log_events(records, event)]

    def assert_one_token_each(self, records: list[logging.LogRecord]) -> None:
        """Every host event renders on one line as its event name followed by exactly its own key=value words."""
        checked = 0
        for record in records:
            event = record.msg.split(" ", 1)[0] if isinstance(record.msg, str) else ""
            if event not in EVENT_KEYS:
                continue
            checked += 1
            text = record.getMessage()
            with self.subTest(event=event):
                self.assertNotIn("\n", text)
                self.assertNotIn("\r", text)
                self.assertEqual([word.split("=", 1)[0] for word in text.split(" ")[1:]], list(EVENT_KEYS[event]), text[:300])
        self.assertTrue(checked)

    async def test_hostile_ids_from_codex_log_as_one_token_in_each_record(self) -> None:
        # The router's method and its three ids, a call's thread_id, a turn item's id and the turn end, on a host without a
        # handler. The S4 R-9 row: a forged itemId gives one record with exactly the six INV-8 keys and the true answer.
        records = self.capture_logs()
        host = await self.open_host()
        self.server.name_next(thread_suffix=HOSTILE_THREAD.removeprefix("thr-"), turn_suffix=HOSTILE_TURN.removeprefix("turn-"))
        handle = await self.spawn(host)
        # Only the log argument changes: the host hands back, routes and reads the raw ids.
        self.assertEqual((handle.thread_id, handle.turn_id), (HOSTILE_THREAD, HOSTILE_TURN))
        self.server.emit([self.server.item_note(handle.thread_id, handle.turn_id, self.fakes.agent_message(FORGED_ITEM, "Working.", None))])
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        self.assert_problem(await self.wait_done(host, handle), "completed", None)
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)
        ids = {"threadId": handle.thread_id, "turnId": handle.turn_id}
        self.assertEqual(await self.ask("item/commandExecution/requestApproval", {**ids, "itemId": FORGED_ITEM}), {"decision": "decline"})
        await self.ask(HOSTILE_METHOD, {**ids, "itemId": "item-m"})
        await self.ask("item/permissions/requestApproval", {"threadId": LONG_ID, "turnId": "turn-x", "itemId": "item-p"})

        self.assert_one_token_each(records)
        calls = [(fields["method"], fields["thread_id"]) for fields in self.fields(records, "codex_host_call") if fields["method"] in ("turn/start", "thread/read")]
        self.assertEqual(calls, [("turn/start", HOSTILE_THREAD_TOKEN), ("thread/read", HOSTILE_THREAD_TOKEN)])
        self.assertIn({"thread_id": HOSTILE_THREAD_TOKEN, "turn_id": HOSTILE_TURN_TOKEN, "item_id": FORGED_ITEM_TOKEN, "item_type": "agentMessage"}, self.fields(records, "codex_host_turn_item"))
        self.assertEqual(self.fields(records, "codex_host_turn_ended"), [{"thread_id": HOSTILE_THREAD_TOKEN, "turn_id": HOSTILE_TURN_TOKEN, "status": "completed", "failure_code": ""}])
        self.assertEqual(
            self.fields(records, "codex_host_server_request"),
            [
                {"method": "item/commandExecution/requestApproval", "thread_id": HOSTILE_THREAD_TOKEN, "turn_id": HOSTILE_TURN_TOKEN, "item_id": FORGED_ITEM_TOKEN, "handled_by": "default", "answer": "decline"},
                {"method": HOSTILE_METHOD_TOKEN, "thread_id": HOSTILE_THREAD_TOKEN, "turn_id": HOSTILE_TURN_TOKEN, "item_id": "item-m", "handled_by": "default", "answer": "empty"},
                {"method": "item/permissions/requestApproval", "thread_id": LONG_ID_TOKEN, "turn_id": "turn-x", "item_id": "item-p", "handled_by": "default", "answer": "no_permissions"},
            ],
        )
        # CODEX_HOST_LOG_TOKEN_MAX_CHARS bounds the record a 100,000-character id once filled.
        self.assertLess(max(len(record.getMessage()) for record in records), 1000)

    async def test_a_hostile_id_in_a_fallback_or_passed_by_a_caller_logs_as_one_token(self) -> None:
        # The fallback WARNING's thread_id on a host with a handler, and a failed call's thread_id that a caller chose.
        async def handler(request: Any) -> Any:
            raise RuntimeError(TOOL_CANARY)

        records = self.capture_logs()
        host = await self.open_host(approval_handler=handler)
        answer = await self.ask("item/commandExecution/requestApproval", {"threadId": HOSTILE_THREAD, "turnId": HOSTILE_TURN, "itemId": FORGED_ITEM})
        self.assertEqual(answer, {"decision": "decline"})
        with self.assertRaises(CodexAgentError):
            await asyncio.wait_for(host.read_codex_thread(HOSTILE_CALLER_ID), WAIT_SECONDS)

        self.assert_one_token_each(records)
        fallback = self.fields(records, "codex_host_server_request_fallback")
        self.assertEqual([(fields["method"], fields["thread_id"]) for fields in fallback], [("item/commandExecution/requestApproval", HOSTILE_THREAD_TOKEN)])
        request = self.fields(records, "codex_host_server_request")
        self.assertEqual([(fields["thread_id"], fields["turn_id"], fields["item_id"], fields["answer"]) for fields in request], [(HOSTILE_THREAD_TOKEN, HOSTILE_TURN_TOKEN, FORGED_ITEM_TOKEN, "decline")])
        failed = [(fields["operation"], fields["thread_id"]) for fields in self.fields(records, "codex_host_call_failed") if fields["method"] == "thread/read"]
        self.assertEqual(failed, [("read_codex_thread", HOSTILE_CALLER_TOKEN)])
        assert_no_canary(self, [record.getMessage() for record in records], (TOOL_CANARY,))

    async def test_hostile_handle_ids_log_as_one_token_when_a_turn_event_fails(self) -> None:
        # codex_host_turn_event_failed and codex_host_turn_ended render the handle's ids, which only have to be non-empty.
        records = self.capture_logs()
        host = await self.open_host()
        self.server.name_next(thread_suffix=EVENT_THREAD.removeprefix("thr-"), turn_suffix=EVENT_TURN.removeprefix("turn-"))
        handle = await self.spawn(host)
        with mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=RuntimeError(TOOL_CANARY)):
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
            snapshot = await asyncio.wait_for(host.wait_codex_turn(handle), WAIT_SECONDS)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        self.assert_one_token_each(records)
        failed = self.fields(records, "codex_host_turn_event_failed")
        self.assertEqual([(fields["thread_id"], fields["turn_id"]) for fields in failed], [(EVENT_THREAD_TOKEN, EVENT_TURN_TOKEN)])
        ended = self.fields(records, "codex_host_turn_ended")
        self.assertEqual(ended, [{"thread_id": EVENT_THREAD_TOKEN, "turn_id": EVENT_TURN_TOKEN, "status": "failed", "failure_code": "codex.protocol_mismatch"}])

    async def test_hostile_handle_ids_log_as_one_token_when_a_watcher_is_lost(self) -> None:
        # codex_host_turn_lost renders the handle's ids too.
        patcher = mock.patch(f"{TURN_EVENTS_MODULE}.CODEX_HOST_LOST_TURN_GRACE_SECONDS", 0.05)
        patcher.start()
        self.addCleanup(patcher.stop)
        records = self.capture_logs()
        host = await self.open_host()
        self.server.name_next(thread_suffix=EVENT_THREAD.removeprefix("thr-"), turn_suffix=EVENT_TURN.removeprefix("turn-"))
        with mock.patch.object(self.server.client, "next_turn_notification", side_effect=RuntimeError(TOOL_CANARY)):
            handle = await self.spawn(host)
            snapshot = await asyncio.wait_for(host.wait_codex_turn(handle), WAIT_SECONDS)
        self.assert_problem(snapshot, "failed", "codex.api_error")
        self.assert_one_token_each(records)
        self.assertEqual(self.fields(records, "codex_host_turn_lost"), [{"thread_id": EVENT_THREAD_TOKEN, "turn_id": EVENT_TURN_TOKEN}])
        ended = self.fields(records, "codex_host_turn_ended")
        self.assertEqual(ended, [{"thread_id": EVENT_THREAD_TOKEN, "turn_id": EVENT_TURN_TOKEN, "status": "failed", "failure_code": "codex.api_error"}])

    # Spec r6 INV-7, INV-10 and row 9 (S5 R-12): an origin is one token in each of the four records that carry one, even when
    # the frame's file name has a space. These rows read the raw words, because a split origin is what a key=value reader hides.

    def words(self, records: list[logging.LogRecord], event: str) -> list[list[str]]:
        return [record.getMessage().split(" ") for record in log_events(records, event)]

    async def test_an_origin_in_a_file_whose_name_has_a_space_logs_as_one_token_in_a_fallback(self) -> None:
        read_setting = _raiser_in_a_spaced_file()

        async def handler(request: Any) -> Any:
            return read_setting(request)

        records = self.capture_logs()
        await self.open_host(approval_handler=handler)
        answer = await self.ask("item/commandExecution/requestApproval", {"threadId": "thr-1", "turnId": "turn-1", "itemId": "item-1"})
        self.assertEqual(answer, {"decision": "decline"})
        expected = ["codex_host_server_request_fallback", "method=item/commandExecution/requestApproval", "thread_id=thr-1", "reason=handler_failed", "error_type=KeyError", f"origin={SPACED_ORIGIN}"]
        self.assertEqual(self.words(records, "codex_host_server_request_fallback"), [expected])

    async def test_an_origin_in_a_file_whose_name_has_a_space_logs_as_one_token_in_a_tool_failure(self) -> None:
        from vidbyte.tools.toolsets import CodexHostTools

        records = self.capture_logs()
        host = await self.open_host()
        tool = next(tool for tool in CodexHostTools(host, max_live_turns=2) if tool.spec().name == "check_codex_ready")
        with mock.patch.object(host, "check_codex_ready", side_effect=_raiser_in_a_spaced_file()):
            result = await asyncio.wait_for(tool.execute(ToolCall(tool_name="check_codex_ready", arguments={})), WAIT_SECONDS)
        self.assertEqual(result.status, ToolStatus.ERROR)
        expected = ["codex_host_tool_failed", "tool=check_codex_ready", "error_type=KeyError", f"origin={SPACED_ORIGIN}"]
        self.assertEqual(self.words(records, "codex_host_tool_failed"), [expected])

    async def test_an_origin_in_a_file_whose_name_has_a_space_logs_as_one_token_in_a_turn_event_failure(self) -> None:
        records = self.capture_logs()
        host = await self.open_host()
        handle = await self.spawn(host)
        with mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=_raiser_in_a_spaced_file()):
            self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
            snapshot = await asyncio.wait_for(host.wait_codex_turn(handle), WAIT_SECONDS)
        self.assert_problem(snapshot, "failed", "codex.protocol_mismatch")
        expected = ["codex_host_turn_event_failed", f"thread_id={handle.thread_id}", f"turn_id={handle.turn_id}", "error_type=KeyError", f"origin={SPACED_ORIGIN}"]
        self.assertEqual(self.words(records, "codex_host_turn_event_failed"), [expected])

    async def test_an_origin_in_a_file_whose_name_has_a_space_logs_as_one_token_in_a_failed_call(self) -> None:
        # The client is the section 13 seam; its thread read raises from the spaced file on the host's worker.
        records = self.capture_logs()
        host = await self.open_host()
        stored = self.server.seed_thread()
        with mock.patch.object(self.server.client, "thread_read", side_effect=_raiser_in_a_spaced_file()), self.assertRaises(CodexAgentError):
            await asyncio.wait_for(host.read_codex_thread(stored.thread_id), WAIT_SECONDS)
        failed = self.words(records, "codex_host_call_failed")
        self.assertEqual(len(failed), 1, failed)
        self.assertEqual([word.split("=", 1)[0] for word in failed[0][1:]], list(EVENT_KEYS["codex_host_call_failed"]), failed[0])
        self.assertIn(f"origin={SPACED_ORIGIN}", failed[0])


@requires_sdk
class CodexCallRecordTests(HostTestCase):
    """INV-7 and EC-57 (spec r5, S4 R-10): one record for each call sent, whoever still waits for it; none for one never sent.

    INV-10 and EC-58 (spec r6, S5 R-11): a handed-over start that fails puts its text in no asyncio or concurrent.futures
    record, whether its caller was cancelled or ran out of time, the process died, the host closed, or the loop closed.
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        # One host worker runs every call in order, so a call that returns proves that each earlier call's worker returned
        # and ran its done-callbacks. That is the barrier these rows read the records after.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        self.records = self.capture_logs(CONNECTION_LOGGER)

    def written(self, method: str, thread_id: str) -> list[logging.LogRecord]:
        """The INV-7 records of one method on one thread, in order."""
        records = log_events(self.records, "codex_host_call") + log_events(self.records, "codex_host_call_failed")
        return [record for record in records if (log_fields(record).get("method"), log_fields(record).get("thread_id")) == (method, thread_id)]

    def shape(self, records: list[logging.LogRecord]) -> list[tuple[str, int]]:
        return [(record.msg.split(" ", 1)[0], record.levelno) for record in records]

    async def barrier(self, host: Any, thread_id: str) -> None:
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)

    async def cancel_while_held(self, task: Any, held: Any, method: str) -> str:
        """Cancel the caller once its request reached Codex and is held, then let Codex answer; return the request's thread."""
        try:
            thread_id = str((await asyncio.to_thread(held.wait_arrived)).params["threadId"])
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            # The record waits for the call's outcome, which Codex has not sent yet.
            self.assertEqual(self.written(method, thread_id), [])
        finally:
            held.release()
        await asyncio.to_thread(held.wait_responded)
        return thread_id

    def outcomes(self) -> tuple[tuple[str, Any, str, int, str], ...]:
        """(label, scripted error, event, level, failure_code) for an answer and for a failure."""
        return (
            ("success", None, "codex_host_call", logging.DEBUG, ""),
            ("failure", self.fakes.FakeRpcError(-32603, f"store failed for {RPC_CANARY}"), "codex_host_call_failed", logging.WARNING, "codex.api_error"),
        )

    def capture_strays(self) -> list[logging.LogRecord]:
        """Also record the two loggers the host never writes to, at DEBUG, for the rest of the test (EC-58)."""
        return self.capture_logs(*STRAY_LOGGERS)

    async def settle(self) -> None:
        """Let the loop run and collect what nothing holds: asyncio reports a failure nothing read from Future.__del__."""
        for _ in range(3):
            await asyncio.sleep(0)
            gc.collect()
        await asyncio.sleep(0)

    async def until_written(self, method: str, thread_id: str) -> None:
        """Wait for a handed-over start's one record on a host that is dead or closed, so no barrier call can be sent."""
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.written(method, thread_id):
            self.assertLess(time.monotonic(), deadline, f"the late record of {method} on {thread_id} was never written")
            await asyncio.sleep(0.01)

    def assert_no_failure_text(self, strays: list[logging.LogRecord], canary: str) -> None:
        """INV-10 and EC-58: no stray record carries the failure's text, in its message or anywhere in its traceback."""
        carrying = [(record.name, record.levelname, (record.getMessage().splitlines() or [""])[0]) for record in list(strays) if canary in _rendered(record)]
        self.assertEqual(carrying, [], "a logger the host does not own wrote the failed start's text")

    def spawn_task(self, host: Any) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        return asyncio.ensure_future(host.spawn_codex_thread(CodexSpawnRequest(prompt="Summarize the readme.")))

    async def cancel_mid_start(self, spawn: Any, held: Any) -> str:
        """Cancel a spawn whose turn/start Codex holds, so the start is handed over; return its thread. The hold stays."""
        thread_id = str((await asyncio.to_thread(held.wait_arrived)).params["threadId"])
        spawn.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await spawn
        return thread_id

    async def test_a_call_cancelled_after_it_was_sent_writes_one_record_once_its_worker_returns(self) -> None:
        host = await self.open_host()
        other = self.server.seed_thread()
        for label, error, event, level, code in self.outcomes():
            with self.subTest(outcome=label):
                stored = self.server.seed_thread()
                if error is not None:
                    self.server.fail("thread/read", error, times=1, predicate=_on(stored.thread_id))
                held = self.server.hold("thread/read", _on(stored.thread_id))
                await self.cancel_while_held(asyncio.ensure_future(host.read_codex_thread(stored.thread_id)), held, "thread/read")
                await self.barrier(host, other.thread_id)
                written = self.written("thread/read", stored.thread_id)
                self.assertEqual(self.shape(written), [(event, level)])
                fields = log_fields(written[0])
                self.assertEqual(fields["operation"], "read_codex_thread")
                self.assertTrue(fields["duration_ms"].isdigit(), fields)
                self.assertEqual(fields.get("failure_code", ""), code)
                self.assertEqual(self.count("thread/read", _on(stored.thread_id)), 1)
        assert_no_canary(self, [record.getMessage() for record in self.records], (RPC_CANARY,))

    async def test_a_spending_start_handed_over_on_cancel_writes_one_record_for_its_late_outcome(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        other = self.server.seed_thread()
        for label, error, event, level, code in self.outcomes():
            with self.subTest(outcome=label):
                if error is not None:
                    self.server.fail("turn/start", error, times=1)
                held = self.server.hold("turn/start")
                spawn = asyncio.ensure_future(host.spawn_codex_thread(CodexSpawnRequest(prompt="Summarize the readme.")))
                thread_id = await self.cancel_while_held(spawn, held, "turn/start")
                await self.barrier(host, other.thread_id)
                written = self.written("turn/start", thread_id)
                self.assertEqual(self.shape(written), [(event, level)])
                fields = log_fields(written[0])
                self.assertEqual(fields["operation"], "spawn_codex_thread")
                self.assertTrue(fields["duration_ms"].isdigit(), fields)
                self.assertEqual(fields.get("failure_code", ""), code)
                self.assertEqual(self.count("turn/start", _on(thread_id)), 1)
                if error is None:
                    # Codex accepted and charged the start, so the host adopted the turn and stopped it (INV-11).
                    await self.wait_for_request("turn/interrupt", _on(thread_id))
        assert_no_canary(self, [record.getMessage() for record in self.records], (RPC_CANARY,))

    async def test_a_call_whose_bound_ran_out_writes_one_record_even_after_its_worker_returns(self) -> None:
        host = await self.open_host()
        other = self.server.seed_thread()
        stored = self.server.seed_thread()
        self.patch_connection("CODEX_HOST_REQUEST_TIMEOUT_SECONDS", 0.5)
        held = self.server.hold("thread/read", _on(stored.thread_id))
        try:
            with self.assertRaises(CodexAgentError):
                await asyncio.wait_for(host.read_codex_thread(stored.thread_id), WAIT_SECONDS)
            timed_out = self.written("thread/read", stored.thread_id)
            self.assertEqual(self.shape(timed_out), [("codex_host_call_failed", logging.WARNING)])
        finally:
            held.release()
        await asyncio.to_thread(held.wait_responded)
        await self.barrier(host, other.thread_id)
        # Its late outcome writes no second record.
        self.assertEqual(self.written("thread/read", stored.thread_id), timed_out)

    async def test_a_call_refused_before_it_was_sent_writes_no_record(self) -> None:
        # EC-57: a queued call withdrawn by its cancelled caller, the call guard on another loop, the dead check, and the call
        # guard of a closed host. Codex received none of them, so none is logged.
        host = await self.open_host()
        busy_thread = self.server.seed_thread()
        queued_thread = self.server.seed_thread()
        held = self.server.hold("thread/read", _on(busy_thread.thread_id))
        busy = asyncio.ensure_future(host.read_codex_thread(busy_thread.thread_id))
        try:
            await asyncio.to_thread(held.wait_arrived)
            # The one worker is busy, so this read waits in the executor's queue until its caller leaves.
            queued = asyncio.ensure_future(host.read_codex_thread(queued_thread.thread_id))
            for _ in range(10):
                await asyncio.sleep(0)
            queued.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await queued
        finally:
            held.release()
        await asyncio.wait_for(busy, WAIT_SECONDS)
        await self.barrier(host, busy_thread.thread_id)
        self.assertEqual((self.count("thread/read", _on(queued_thread.thread_id)), self.written("thread/read", queued_thread.thread_id)), (0, []))
        self.assertEqual(self.shape(self.written("thread/read", busy_thread.thread_id)), [("codex_host_call", logging.DEBUG)] * 2)

        refused = await self.run_in_other_loop(lambda: host.read_codex_thread(busy_thread.thread_id))
        self.assertIsInstance(refused, ConfigurationError)
        handle = await self.spawn(host)
        self.server.die("the app-server crashed")
        self.assert_problem(await self.wait_done(host, handle), "failed", "codex.process_exited")
        await self.assert_codex_error(host.read_codex_thread(busy_thread.thread_id), "codex.process_exited")
        await self.close_host(host)
        with self.assertRaises((ConfigurationError, CodexAgentError)):
            await asyncio.wait_for(host.read_codex_thread(busy_thread.thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("thread/read", _on(busy_thread.thread_id)), 2)
        self.assertEqual(len(self.written("thread/read", busy_thread.thread_id)), 2)

    # Spec r6 INV-10 and EC-58 (S5 R-11). Each row plants a canary in the error that ends a handed-over start, lets the
    # start fail, collects, and then reads every asyncio and concurrent.futures record, message and traceback alike. The
    # start's one INV-7 record is still checked, because hiding the failure must not drop that record.

    async def test_a_spending_start_handed_over_on_cancel_that_fails_writes_its_text_to_no_other_logger(self) -> None:
        # The R-10 hand-over: Codex's JSON-RPC error text is the canary.
        strays = self.capture_strays()
        host = await self.open_host()
        other = self.server.seed_thread()
        self.server.fail("turn/start", self.fakes.FakeRpcError(-32603, f"store failed for {RPC_CANARY}"), times=1)
        held = self.server.hold("turn/start")
        thread_id = await self.cancel_while_held(self.spawn_task(host), held, "turn/start")
        await self.barrier(host, other.thread_id)
        await self.settle()
        self.assertEqual(self.shape(self.written("turn/start", thread_id)), [("codex_host_call_failed", logging.WARNING)])
        self.assert_no_failure_text(strays, RPC_CANARY)

    async def test_a_start_handed_over_when_its_bound_ran_out_that_fails_writes_its_text_to_no_other_logger(self) -> None:
        # The timeout hand-over: the WARNING the timeout wrote stays the start's one record.
        strays = self.capture_strays()
        host = await self.open_host()
        other = self.server.seed_thread()
        self.patch_connection("CODEX_HOST_REQUEST_TIMEOUT_SECONDS", 0.5)
        self.server.fail("turn/start", self.fakes.FakeRpcError(-32603, f"store failed for {RPC_CANARY}"), times=1)
        held = self.server.hold("turn/start")
        try:
            with self.assertRaises(CodexAgentError):
                await asyncio.wait_for(self.spawn_task(host), WAIT_SECONDS)
            thread_id = str((await asyncio.to_thread(held.wait_arrived)).params["threadId"])
            timed_out = self.written("turn/start", thread_id)
            self.assertEqual(self.shape(timed_out), [("codex_host_call_failed", logging.WARNING)])
        finally:
            held.release()
        await asyncio.to_thread(held.wait_responded)
        await self.barrier(host, other.thread_id)
        await self.settle()
        self.assertEqual(self.written("turn/start", thread_id), timed_out)
        self.assert_no_failure_text(strays, RPC_CANARY)

    async def test_a_handed_over_start_that_dies_with_the_process_writes_the_stderr_tail_to_no_other_logger(self) -> None:
        # The process dies while the start is in flight; openai-codex puts Codex's stderr tail in the start's error.
        strays = self.capture_strays()
        host = await self.open_host()
        held = self.server.hold("turn/start")
        thread_id = await self.cancel_mid_start(self.spawn_task(host), held)
        self.server.die(STDERR_SECRET)
        await self.until_written("turn/start", thread_id)
        await self.settle()
        self.assertEqual(self.shape(self.written("turn/start", thread_id)), [("codex_host_call_failed", logging.WARNING)])
        self.assert_no_failure_text(strays, STDERR_SECRET)

    async def test_a_handed_over_start_that_fails_when_the_host_closes_writes_the_stderr_tail_to_no_other_logger(self) -> None:
        # No crash is needed: Codex wrote one stderr line, the caller cancelled its spawn mid-start, and the host closed,
        # which ends the start with an error that carries that line.
        strays = self.capture_strays()
        host = await self.open_host()
        self.server.process.stderr.write_line(STDERR_SECRET)
        await asyncio.to_thread(self.server.process.stderr.wait_drained)
        held = self.server.hold("turn/start")
        thread_id = await self.cancel_mid_start(self.spawn_task(host), held)
        await self.close_host(host)
        await self.until_written("turn/start", thread_id)
        await self.settle()
        self.assertEqual(self.shape(self.written("turn/start", thread_id)), [("codex_host_call_failed", logging.WARNING)])
        self.assert_no_failure_text(strays, STDERR_SECRET)

    async def test_a_handed_over_start_that_fails_after_its_loop_closed_writes_its_text_to_no_other_logger(self) -> None:
        # The caller's loop is gone when the start fails: the caller cancelled its spawn mid-start and returned without
        # closing the host, so asyncio.run closed that loop. The start's worker still writes its one record.
        from vidbyte.harnesses.native.codex import CodexHost

        strays = self.capture_strays()
        self.server.fail("turn/start", self.fakes.FakeRpcError(-32603, f"store failed for {RPC_CANARY}"), times=1)
        held = self.server.hold("turn/start")

        async def leave_mid_start() -> None:
            host = CodexHost()
            await host.__aenter__()
            spawn = self.spawn_task(host)
            await asyncio.to_thread(held.wait_arrived)
            spawn.cancel()
            with suppress(asyncio.CancelledError):
                await spawn

        try:
            self.assertIsNone(await self.run_in_other_loop(leave_mid_start))
            thread_id = str((await asyncio.to_thread(held.wait_arrived)).params["threadId"])
        finally:
            held.release()
        # That host can never be closed now; ending its process after the test stops its reader threads.
        self.addCleanup(self.server.die, "")
        await asyncio.to_thread(held.wait_responded)
        await self.until_written("turn/start", thread_id)
        await self.settle()
        self.assertEqual(self.shape(self.written("turn/start", thread_id)), [("codex_host_call_failed", logging.WARNING)])
        self.assert_no_failure_text(strays, RPC_CANARY)


if __name__ == "__main__":
    unittest.main()
