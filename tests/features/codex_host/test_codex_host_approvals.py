"""FILE: tests/features/codex_host/test_codex_host_approvals.py

PURPOSE: Proves the approval_handler a developer gives CodexHost, end to end through the real openai-codex reader thread: the section 4 snippet runs and prints completed then 1; a host without a handler answers every server request with its fixed fail-closed default; a host with one routes only command, file-change and user-input requests to it, as parsed records, on the host's own loop; every answer that does not fit, every handler that raises, hangs or returns the wrong thing, and every request that cannot be parsed falls back to the default with one WARNING; a USER reviewer is refused before any request only where nothing can answer it; and close cancels a pending handler and declines what arrives after.
ROLE IN CODEBASE: Server-request layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-1, AC-10 to AC-15, AC-38, INV-15 to INV-21, EC-3 to EC-9, EC-48, EC-49, EC-51, D-1, D-3, D-4, D-5). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Requests reach the client through the fake's stdout and HostTestCase.ask, so the SDK reader thread calls the real router, which must schedule the handler on the test's loop and wait for it there (INV-17). The handler is a test double that records what it saw and answers by item id; nothing in the router, the connection or the SDK is mocked. Fallbacks are observed through the connection logger's records (INV-8).
COMMON MODIFICATION PATTERNS: A new routed kind adds one row to the routing test and one to the fallback table; a new never-routed method adds one entry to NEVER_ROUTED with its default.
KNOWN EDGE CASES: The reader thread is blocked while a handler runs, so a test sends the next request only after the previous answer arrived. The handler-timeout row shortens CODEX_TOOL_CALL_TIMEOUT_SECONDS where row 12 reads it at call time, in the connection module. A decline answer equals the default, so each routing check also sends a request whose fitting answer is not the default.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 4, 6.1 (INV-15 to INV-21), 6.3 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_approvals.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import time
import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    APPROVAL_HANDLER_MESSAGE,
    CLOSE_SECONDS,
    DEFAULT_ANSWERS,
    USER_REVIEWER_MESSAGE,
    USER_REVIEWER_TEXT,
    WAIT_SECONDS,
    HostTestCase,
    log_events,
    log_fields,
    mapped_summary,
    requires_sdk,
)
from vidbyte.lib.errors import ConfigurationError

WORKSPACE = os.path.abspath(os.path.join(os.sep, "approvals-workspace"))
GRANT_ROOT = os.path.abspath(os.path.join(os.sep, "approvals-workspace", "release"))
STARTED_AT_MS = 1_760_000_000_456
COMMAND = "item/commandExecution/requestApproval"
FILE_CHANGE = "item/fileChange/requestApproval"
USER_INPUT = "item/tool/requestUserInput"
FALLBACK = "codex_host_server_request_fallback"
# An exec-policy amendment: an object decision the handler can never choose (EC-5).
OBJECT_DECISION = {"acceptWithExecpolicyAmendment": {"execpolicyAmendment": ["git", "status"]}}
# INV-15: the four methods that are never routed, even on a host with a handler.
NEVER_ROUTED = ("item/permissions/requestApproval", "mcpServer/elicitation/request", "applyPatchApproval", "execCommandApproval")
# INV-15 and EC-10: methods with no schema-defined refusal get an empty answer.
EMPTY_ANSWER_METHODS = ("account/chatgptAuthTokens/refresh", "attestation/generate", "item/somethingNew/request")
HANDLER_CANARY = "handler-canary-91d4"
QUESTION_ONE = {"id": "q1", "header": "Deploy", "question": "Ship it?", "options": [{"label": "yes", "description": "Ship now."}, {"label": "no", "description": "Wait."}], "isOther": False, "isSecret": False}
# AC-11: options null and no isOther or isSecret must reach the handler as (), False and False.
QUESTION_TWO = {"id": "q2", "header": "Notes", "question": "Anything else?", "options": None}


async def answer(request: Any) -> Any:
    """The section 4 snippet's handler, verbatim apart from its imports, which load lazily here."""
    from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer
    from vidbyte.lib.enums.codex import CodexApprovalDecision, CodexCommandApprovalKind, CodexServerRequestKind

    # Allow `git status` as a new command; decline terminal input, every other command, file change and question.
    if request.kind is CodexServerRequestKind.COMMAND_EXECUTION and request.approval_kind is CodexCommandApprovalKind.COMMAND and request.command == "git status":
        return CodexServerAnswer(decision=CodexApprovalDecision.ACCEPT)
    return CodexServerAnswer(decision=CodexApprovalDecision.DECLINE)


async def snippet_main() -> None:
    """The section 4 snippet's main(), verbatim apart from its imports."""
    from vidbyte.harnesses.native.codex import CodexHost
    from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
    from vidbyte.lib.enums.codex import CodexApprovalsReviewer

    async with CodexHost(approval_handler=answer) as host:
        spawn = CodexSpawnRequest(prompt="Run git status and summarize it.", approvals_reviewer=CodexApprovalsReviewer.USER)
        handle = await host.spawn_codex_thread(spawn)
        snapshot = await host.wait_codex_turn(handle)
        print(snapshot.status.value)
        print(await host.forget_codex_turns(handle.thread_id))


def _sync_handler(request: Any) -> Any:
    return None


class _SyncCallable:
    def __call__(self, request: Any) -> Any:
        return None


class RecordingHandler:
    """An async approval_handler that records each request and its loop, and answers by the request's item id.

    plan maps an item id to a behaviour; any other item is accepted. A hung call waits until the router cancels it.
    """

    def __init__(self) -> None:
        self.plan: dict[str, str] = {}
        self.seen: list[Any] = []
        self.loops: list[asyncio.AbstractEventLoop] = []
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def __call__(self, request: Any) -> Any:
        self.seen.append(request)
        self.loops.append(asyncio.get_running_loop())
        self.entered.set()
        try:
            return await self.respond(self.plan.get(request.item_id, "accept"))
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def respond(self, behaviour: str) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer, CodexUserInputAnswer
        from vidbyte.lib.enums.codex import CodexApprovalDecision

        if behaviour == "raise":
            raise RuntimeError(HANDLER_CANARY)
        if behaviour == "hang":
            await asyncio.Event().wait()
        if behaviour == "dict":
            return {"decision": "accept"}
        if behaviour == "none":
            return None
        answers = {
            "answer_q1": (CodexUserInputAnswer(question_id="q1", answers=("yes",)),),
            "answers_on_approval": (CodexUserInputAnswer(question_id="q1", answers=("yes",)),),
            "unknown_question": (CodexUserInputAnswer(question_id="q9", answers=("yes",)),),
        }.get(behaviour, ())
        decisions = {"accept_for_session": CodexApprovalDecision.ACCEPT_FOR_SESSION, "cancel": CodexApprovalDecision.CANCEL, "decline": CodexApprovalDecision.DECLINE}
        return CodexServerAnswer(decision=decisions.get(behaviour, CodexApprovalDecision.ACCEPT), answers=answers)


def _ids(handle: Any, item_id: str, **changes: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"threadId": handle.thread_id, "turnId": handle.turn_id, "itemId": item_id}
    params.update(changes)
    return params


class ApprovalTestCase(HostTestCase):
    """HostTestCase plus the fallback-record reads these tests share."""

    def fallbacks(self, records: list[Any]) -> list[dict[str, str]]:
        return [log_fields(record) for record in log_events(records, FALLBACK)]

    async def assert_accepted_next(self, handle: Any, handler: RecordingHandler, item_id: str) -> None:
        """The next routed request still reaches the handler, and its accept (never the default) comes back."""
        handler.plan[item_id] = "accept"
        self.assertEqual(await self.ask(COMMAND, _ids(handle, item_id)), {"decision": "accept"})

    async def settle(self, task: Any, held: Any) -> None:
        """Cleanup for a test that fails while a task waits on a held request: release it, then let the task end."""
        held.release()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)


@requires_sdk
class CodexApprovalSnippetTests(ApprovalTestCase):
    """AC-1 and EC-51: the section 4 snippet, as a developer would run it."""

    async def test_the_section_4_snippet_prints_completed_then_1(self) -> None:
        self.server.autocomplete = {}
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            await asyncio.wait_for(snippet_main(), WAIT_SECONDS + CLOSE_SECONDS)
        self.assertEqual(printed.getvalue().splitlines(), ["completed", "1"])
        started = self.server.matching("thread/start")
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].params.get("approvalsReviewer"), "user")
        self.assertEqual((self.server.started, self.server.closed), (1, 1))

    async def test_the_snippet_handler_allows_git_status_and_declines_terminal_input(self) -> None:
        host = await self.open_host(approval_handler=answer)
        handle = await self.spawn(host)
        command = {"command": "git status", "cwd": WORKSPACE}
        self.assertEqual(await self.ask(COMMAND, _ids(handle, "item-1", kind="command", **command)), {"decision": "accept"})
        # EC-51: the same text typed into a running terminal is not a new command.
        self.assertEqual(await self.ask(COMMAND, _ids(handle, "item-2", kind="writeStdin", **command)), {"decision": "decline"})
        self.assertEqual(await self.ask(COMMAND, _ids(handle, "item-3", kind="command", command="git push --force", cwd=WORKSPACE)), {"decision": "decline"})
        self.assertEqual(await self.ask(FILE_CHANGE, _ids(handle, "item-4", grantRoot=GRANT_ROOT)), {"decision": "decline"})
        self.assertEqual(self.server.reader_errors, [])


@requires_sdk
class CodexDefaultAnswerTests(ApprovalTestCase):
    """AC-10, AC-15, INV-15, INV-16, EC-9 and EC-10: the fixed answers, with and without a handler."""

    async def assert_fixed_answers(self, host: Any, handle: Any, methods: tuple[str, ...]) -> None:
        for method in methods:
            with self.subTest(method=method):
                self.assertEqual(await self.ask(method, _ids(handle, f"item-{method}")), DEFAULT_ANSWERS[method])
        before = int(time.time())
        current = await self.ask("currentTime/read", {})
        after = int(time.time())
        self.assertEqual(set(current), {"currentTimeAt"})
        self.assertIs(type(current["currentTimeAt"]), int)
        self.assertTrue(before <= current["currentTimeAt"] <= after, (before, current, after))
        for method in EMPTY_ANSWER_METHODS:
            with self.subTest(method=method):
                self.assertEqual(await self.ask(method, {"threadId": handle.thread_id}), {})
        # The reader thread survived every answer, so the host still talks to Codex.
        self.assertEqual(self.server.reader_errors, [])
        await asyncio.wait_for(host.read_codex_thread(handle.thread_id), WAIT_SECONDS)

    async def test_a_host_without_a_handler_answers_every_server_request_with_its_default(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.assert_fixed_answers(host, handle, tuple(DEFAULT_ANSWERS))
        # A user-input request with questions is still refused with empty answers (INV-16).
        with_questions = _ids(handle, "item-questions", questions=[QUESTION_ONE, QUESTION_TWO], isBlocking=True)
        self.assertEqual(await self.ask(USER_INPUT, with_questions), {"answers": {}})

    async def test_a_host_with_a_handler_never_routes_the_fixed_methods(self) -> None:
        handler = RecordingHandler()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        await self.assert_fixed_answers(host, handle, NEVER_ROUTED)
        self.assertEqual(handler.seen, [])
        # The handler is live, so the empty list above is the router's choice, not a dead handler.
        await self.assert_accepted_next(handle, handler, "item-routed")
        self.assertEqual(len(handler.seen), 1)


@requires_sdk
class CodexHandlerRoutingTests(ApprovalTestCase):
    """AC-11, INV-17, INV-18, D-4, EC-5 and EC-6: what the handler sees, where it runs, and how its answer is encoded."""

    async def test_the_handler_sees_each_request_as_sent_and_its_answer_is_encoded(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexServerRequest, CodexUserInputOption, CodexUserInputQuestion
        from vidbyte.lib.enums.codex import CodexApprovalDecision, CodexCommandApprovalKind, CodexServerRequestKind

        handler = RecordingHandler()
        handler.plan = {"item-command": "accept", "item-stdin": "accept_for_session", "item-file": "accept", "item-input": "answer_q1"}
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        command = _ids(
            handle,
            "item-command",
            approvalId="approval-1",
            environmentId="env-1",
            kind="command",
            startedAtMs=STARTED_AT_MS,
            reason="Check the tree.",
            command="git status",
            cwd=WORKSPACE,
            availableDecisions=["accept", "acceptForSession", OBJECT_DECISION, "decline", "cancel"],
            commandActions=[{"type": "unknown", "command": "git status"}],
        )
        # No availableDecisions, so any decision valid for a command fits (EC-6).
        stdin = _ids(handle, "item-stdin", approvalId="approval-2", kind="writeStdin", command="yes", cwd=WORKSPACE)
        file_change = _ids(handle, "item-file", reason="Edit the release notes.", grantRoot=GRANT_ROOT, startedAtMs=STARTED_AT_MS, availableDecisions=["accept", "decline"])
        user_input = _ids(handle, "item-input", questions=[QUESTION_ONE, QUESTION_TWO], isBlocking=True)

        self.assertEqual(await self.ask(COMMAND, command), {"decision": "accept"})
        self.assertEqual(await self.ask(COMMAND, stdin), {"decision": "acceptForSession"})
        self.assertEqual(await self.ask(FILE_CHANGE, file_change), {"decision": "accept"})
        self.assertEqual(await self.ask(USER_INPUT, user_input), {"answers": {"q1": {"answers": ["yes"]}}})

        ids = {"thread_id": handle.thread_id, "turn_id": handle.turn_id}
        decision = CodexApprovalDecision
        expected = [
            CodexServerRequest(
                kind=CodexServerRequestKind.COMMAND_EXECUTION,
                item_id="item-command",
                approval_kind=CodexCommandApprovalKind.COMMAND,
                approval_id="approval-1",
                environment_id="env-1",
                started_at_ms=STARTED_AT_MS,
                reason="Check the tree.",
                command="git status",
                cwd=WORKSPACE,
                available_decisions=(decision.ACCEPT, decision.ACCEPT_FOR_SESSION, decision.DECLINE, decision.CANCEL),
                **ids,
            ),
            CodexServerRequest(kind=CodexServerRequestKind.COMMAND_EXECUTION, item_id="item-stdin", approval_kind=CodexCommandApprovalKind.WRITE_STDIN, approval_id="approval-2", command="yes", cwd=WORKSPACE, **ids),
            CodexServerRequest(kind=CodexServerRequestKind.FILE_CHANGE, item_id="item-file", started_at_ms=STARTED_AT_MS, reason="Edit the release notes.", grant_root=GRANT_ROOT, available_decisions=(decision.ACCEPT, decision.DECLINE), **ids),
            CodexServerRequest(
                kind=CodexServerRequestKind.USER_INPUT,
                item_id="item-input",
                questions=(
                    CodexUserInputQuestion(question_id="q1", header="Deploy", question="Ship it?", options=(CodexUserInputOption(label="yes", description="Ship now."), CodexUserInputOption(label="no", description="Wait."))),
                    CodexUserInputQuestion(question_id="q2", header="Notes", question="Anything else?"),
                ),
                is_blocking=True,
                **ids,
            ),
        ]
        self.assertEqual(handler.seen, expected)
        second = handler.seen[3].questions[1]
        self.assertEqual((second.options, second.is_other, second.is_secret), ((), False, False))
        # INV-17: the handler runs on the host's own loop, the one this test awaits on.
        self.assertEqual(handler.loops, [asyncio.get_running_loop()] * 4)
        self.assertEqual(self.server.reader_errors, [])


@requires_sdk
class CodexHandlerFallbackTests(ApprovalTestCase):
    """AC-12, INV-17, INV-18, EC-4, EC-5 and EC-48: every misfit falls back to the default with one WARNING."""

    async def test_every_misbehaving_handler_gets_the_default_answer_and_one_warning(self) -> None:
        records = self.capture_logs()
        self.patch_connection("CODEX_TOOL_CALL_TIMEOUT_SECONDS", 0.2)
        handler = RecordingHandler()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        decline = {"decision": "decline"}
        no_answers = {"answers": {}}
        questions = {"questions": [QUESTION_ONE]}
        rows: tuple[tuple[str, str, dict[str, Any], str, dict[str, Any], str], ...] = (
            ("raises", COMMAND, {}, "raise", decline, "handler_failed"),
            ("sleeps past the bound", COMMAND, {}, "hang", decline, "handler_timed_out"),
            ("returns a dict", FILE_CHANGE, {}, "dict", decline, "answer_invalid"),
            ("returns None", COMMAND, {}, "none", decline, "answer_invalid"),
            ("a decision Codex did not offer", COMMAND, {"availableDecisions": ["accept", "decline"]}, "accept_for_session", decline, "answer_invalid"),
            ("accept when only object decisions are offered", COMMAND, {"availableDecisions": [OBJECT_DECISION]}, "accept", decline, "answer_invalid"),
            ("answers on a command approval", COMMAND, {}, "answers_on_approval", decline, "answer_invalid"),
            ("answers on a file-change approval", FILE_CHANGE, {}, "answers_on_approval", decline, "answer_invalid"),
            ("an answer to an unknown question", USER_INPUT, questions, "unknown_question", no_answers, "answer_invalid"),
            ("accept for session on a question", USER_INPUT, questions, "accept_for_session", no_answers, "answer_invalid"),
        )
        for index, (label, method, extra, behaviour, default, reason) in enumerate(rows):
            with self.subTest(row=label):
                handler.plan[f"bad-{index}"] = behaviour
                before = len(self.fallbacks(records))
                self.assertEqual(await self.ask(method, _ids(handle, f"bad-{index}", **extra)), default)
                new = self.fallbacks(records)[before:]
                self.assertEqual(len(new), 1, new)
                self.assertEqual((new[0]["method"], new[0]["thread_id"], new[0]["reason"]), (method, handle.thread_id, reason))
                if behaviour == "raise":
                    self.assertEqual(new[0]["error_type"], "RuntimeError")
                    self.assertTrue(new[0]["origin"].startswith("test_codex_host_approvals.py:respond:"), new[0])
                if behaviour == "hang":
                    # The hung call does not outlive its bound: the router cancelled it.
                    await asyncio.wait_for(handler.cancelled.wait(), WAIT_SECONDS)
                await self.assert_accepted_next(handle, handler, f"next-{index}")
                self.assertEqual(len(self.fallbacks(records)), before + 1)
        # Fitting answers that are not accept: CANCEL with only object decisions offered (EC-5), DECLINE on a question.
        handler.plan.update({"fit-cancel": "cancel", "fit-decline": "decline"})
        self.assertEqual(await self.ask(COMMAND, _ids(handle, "fit-cancel", availableDecisions=[OBJECT_DECISION])), {"decision": "cancel"})
        self.assertEqual(await self.ask(USER_INPUT, _ids(handle, "fit-decline", **questions)), no_answers)
        self.assertEqual(len(self.fallbacks(records)), len(rows))
        self.assertFalse(any(HANDLER_CANARY in record.getMessage() for record in records))
        self.assertEqual(self.server.reader_errors, [])

    async def test_a_request_that_cannot_be_parsed_is_declined_without_calling_the_handler(self) -> None:
        # EC-4: the parse runs before the handler is scheduled, and its failure is the parse_failed fallback.
        records = self.capture_logs()
        handler = RecordingHandler()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        rows = (
            ("no turnId", COMMAND, {"threadId": handle.thread_id, "itemId": "item-1"}, {"decision": "decline"}),
            ("a numeric threadId", FILE_CHANGE, {"threadId": 7, "turnId": handle.turn_id, "itemId": "item-2"}, {"decision": "decline"}),
            ("an unknown command kind", COMMAND, _ids(handle, "item-3", kind="sudo"), {"decision": "decline"}),
            ("questions that are not a list", USER_INPUT, _ids(handle, "item-4", questions="q1"), {"answers": {}}),
        )
        for label, method, params, default in rows:
            with self.subTest(row=label):
                before = len(self.fallbacks(records))
                self.assertEqual(await self.ask(method, params), default)
                new = self.fallbacks(records)[before:]
                self.assertEqual([(entry["method"], entry["reason"], entry["error_type"]) for entry in new], [(method, "parse_failed", "ConfigurationError")])
        self.assertEqual(handler.seen, [])
        await self.assert_accepted_next(handle, handler, "item-after")


@requires_sdk
class CodexHostSetupHostTests(ApprovalTestCase):
    """AC-13 and INV-19: a bad handler or bad settings is refused by CodexHost(...) itself, so no process starts."""

    async def test_a_bad_handler_or_settings_starts_no_client_and_no_process(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        for label, handler, kind in (("sync function", _sync_handler, "function"), ("lambda", lambda request: None, "function"), ("an int", 5, "int"), ("sync __call__", _SyncCallable(), "_SyncCallable")):
            with self.subTest(handler=label):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexHost(approval_handler=handler)
                self.assertEqual(str(caught.exception), APPROVAL_HANDLER_MESSAGE.format(kind=kind))
                self.assertEqual(caught.exception.details.get("field"), "approval_handler")
        with self.assertRaises(ConfigurationError) as caught:
            CodexHost("x")
        self.assertIn("CodexHost settings", str(caught.exception))
        self.assertEqual((self.server.clients_created, self.server.started, self.which_calls), (0, 0, []))


@requires_sdk
class CodexUserReviewerTests(ApprovalTestCase):
    """AC-14, INV-20, D-5 and EC-49: a USER reviewer needs a handler, and is refused before any request without one."""

    async def test_without_a_handler_each_operation_refuses_a_user_reviewer_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexForkRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        host = await self.open_host()
        seeded = self.server.seed_thread()
        user = CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.USER)
        # Both records build: the refusal belongs to the host call, not to the record (D-5).
        CodexForkRequest(thread_id=seeded.thread_id, overrides=user)
        rows: tuple[tuple[str, Callable[[], Awaitable[Any]]], ...] = (
            ("spawn_codex_thread", lambda: host.spawn_codex_thread(CodexSpawnRequest(prompt="Run it.", approvals_reviewer=CodexApprovalsReviewer.USER))),
            ("continue_codex_thread", lambda: host.continue_codex_thread(seeded.thread_id, "Go on.", overrides=user)),
            ("launch_codex_subagents", lambda: host.launch_codex_subagents(("Check a.", "Check b."), request=user)),
            ("fork_codex_thread", lambda: host.fork_codex_thread(seeded.thread_id, overrides=user)),
            ("run_codex_goal", lambda: host.run_codex_goal("Ship the fix.", request=user)),
            ("run_codex_skill", lambda: host.run_codex_skill("openai-docs", "Find it.", request=user)),
            ("run_codex_openai_docs", lambda: host.run_codex_openai_docs("Which event?", request=user)),
        )
        for operation, start in rows:
            with self.subTest(operation=operation):
                before = len(self.server.requests)
                error = await self.assert_codex_error(start(), "configuration.unsupported_combination")
                self.assertEqual(error.operation, operation)
                self.assertTrue(mapped_summary(self, error).startswith(USER_REVIEWER_MESSAGE), error.message)
                self.assertEqual(error.next_step, USER_REVIEWER_TEXT)
                self.assertEqual(self.server.methods()[before:], [])

    async def test_with_a_handler_a_user_reviewer_starts_and_continues_and_its_approvals_reach_the_handler(self) -> None:
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        handler = RecordingHandler()
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host, approvals_reviewer=CodexApprovalsReviewer.USER)
        self.assertTrue(handle.thread_id)
        self.assertEqual(self.server.matching("thread/start")[0].params.get("approvalsReviewer"), "user")
        await self.assert_accepted_next(handle, handler, "item-spawned")
        # INV-20: Codex reporting a user reviewer after thread/resume no longer stops a host that has a handler.
        stored = self.server.seed_thread(reviewer="user")
        continued = await asyncio.wait_for(host.continue_codex_thread(stored.thread_id, "Go on."), WAIT_SECONDS)
        self.assertEqual(continued.thread_id, stored.thread_id)
        self.assertEqual(self.count("turn/start", lambda params: params.get("threadId") == stored.thread_id), 1)


@requires_sdk
class CodexCloseHandlerTests(ApprovalTestCase):
    """AC-38, INV-21 and EC-3: close stops the handler first, and nothing routed after that reaches it."""

    async def test_close_cancels_a_pending_handler_and_declines_a_late_request_for_a_turn_awaiting_cleanup(self) -> None:
        records = self.capture_logs()
        handler = RecordingHandler()
        handler.plan["item-pending"] = "hang"
        host = await self.open_host(approval_handler=handler)
        handle = await self.spawn(host)
        pending = self.server.server_request(COMMAND, _ids(handle, "item-pending"))
        await asyncio.wait_for(handler.entered.wait(), WAIT_SECONDS)
        # Hold the cleanup interrupt, so close is still running while the two answers are written.
        held = self.server.hold("turn/interrupt")
        closing = asyncio.ensure_future(host.__aexit__(None, None, None))
        self.addAsyncCleanup(self.settle, closing, held)
        await asyncio.to_thread(held.wait_arrived)
        # The pending call was cancelled and its request got the default answer.
        self.assertEqual(await asyncio.wait_for(asyncio.wrap_future(pending), WAIT_SECONDS), {"decision": "decline"})
        await asyncio.wait_for(handler.cancelled.wait(), WAIT_SECONDS)
        # A request for the turn still awaiting its cleanup interrupt is declined without the handler.
        before = len(self.fallbacks(records))
        self.assertEqual(await self.ask(COMMAND, _ids(handle, "item-late")), {"decision": "decline"})
        self.assertEqual([request.item_id for request in handler.seen], ["item-pending"])
        self.assertEqual([entry["reason"] for entry in self.fallbacks(records)[before:]], ["closing"])
        held.release()
        await asyncio.wait_for(closing, CLOSE_SECONDS)
        from openai_codex.errors import TransportClosedError

        # Close ends the process, so the SDK reader records its normal end-of-file TransportClosedError; any other entry
        # means the router raised on the reader thread (INV-15, INV-16).
        self.assertEqual(self.server.closed, 1)
        self.assertEqual([type(error).__name__ for error in self.server.reader_errors if type(error) is not TransportClosedError], [])
        self.assertEqual(self.count("turn/interrupt"), 1)


if __name__ == "__main__":
    unittest.main()
