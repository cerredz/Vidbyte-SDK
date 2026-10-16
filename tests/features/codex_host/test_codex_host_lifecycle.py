"""FILE: tests/features/codex_host/test_codex_host_lifecycle.py

PURPOSE: Proves the CodexHost lifecycle end to end over the in-memory app-server: the section 4 snippet's printed lines, codex binary resolution, the minimum-version gate, the call guards (not open, opened twice, closed, another event loop), the six close steps for a running turn, a running dynamic tool call and a running goal run, the host's own executor and close thread, and the six module functions.
ROLE IN CODEBASE: Lifecycle layer of tests/features/codex_host/ (spec AC-1, AC-3, AC-4, AC-31, AC-33, INV-2 to INV-7, INV-38, D-1, D-4, D-5, EC-2, EC-4, EC-58 to EC-60, EC-80, EC-81). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: HostTestCase patches the seam spec section 13 names with a subclass of the real openai-codex CodexClient whose process is in memory, so the SDK reader thread, router and goal routing run for real. The fake logs every request with the thread that wrote it, and every close and goal-cleanup call, which is how close order and thread use are observed.
COMMON MODIFICATION PATTERNS: Add a lifecycle case as its own test method; keep one host open at a time on one fake server unless the test is about concurrency.
KNOWN EDGE CASES: The close-time tool test patches CODEX_HOST_CLOSE_INTERRUPT_SECONDS to 60 s, so an interrupt sent while the reader is still blocked inside the tool call would hold close past the 30 s test bound; a correct close cancels the tool first and finishes at once. A goal watcher may stop reading as soon as its run is finalized, so the test checks that the thread exits, not how many reads it made.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 4, 6.1 (INV-1 to INV-7), 8.1 (D-1, D-4, D-5) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_lifecycle.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    CLOSE_SECONDS,
    FAKE_CODEX_PATH,
    MINIMUM_VERSION,
    NEXT_STEPS,
    UNREGISTERED_TOOL_TEXT,
    WAIT_SECONDS,
    HostTestCase,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.base import BaseTool

GOAL_CLEANUP = ("cancel_goal_operation", "finish", "wake_notification_reader", "unregister_goal_operation")


class _SlowTool(BaseTool):
    """A READ tool that runs until it is cancelled, and logs its cancellation on the fake app-server."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self.started = asyncio.Event()
        self._never = asyncio.Event()

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="slow_lookup",
            description="Looks something up slowly.",
            permission=ToolPermission.READ,
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        self.started.set()
        try:
            await self._never.wait()
        except asyncio.CancelledError:
            self._server.record("tool_cancelled", call.tool_name)
            raise
        return ToolResult.success("slow_lookup", "never reached")


def _log_index(server: Any, predicate: Any) -> list[int]:
    return [index for index, entry in enumerate(list(server.log)) if predicate(entry)]


@requires_sdk
class CodexHostSnippetTests(HostTestCase):
    """AC-1: the developer-usage snippet of spec section 4 prints its documented lines."""

    async def test_the_section_4_snippet_prints_its_three_lines(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexSandbox
        from vidbyte.tools.toolsets import CodexHostTools

        # Codex finishes the turn as soon as it starts, with a final answer and usage under the cap.
        self.server.autocomplete = {"final": "The readme describes the SDK.", "usage": self.fakes.token_usage((120, 30), (120, 30))}

        async def main() -> None:
            # Spec section 4, verbatim apart from asyncio.run, which the test loop replaces.
            async with CodexHost() as host:
                readiness = await host.check_codex_ready()
                print(readiness.ready)
                handle = await host.spawn_codex_thread(
                    CodexSpawnRequest(
                        prompt="Summarize the project readme in one sentence.",
                        thread=CodexThreadSettings(sandbox=CodexSandbox.READ_ONLY),
                        max_output_tokens=2_000,
                    )
                )
                outcome = await host.wait_codex_turn(handle, timeout_seconds=600.0)
                print(outcome.status.value, outcome.result.final_response)
                tools = CodexHostTools(host, max_live_turns=2)
                print(len(tools), tools.names()[0])

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            await asyncio.wait_for(main(), CLOSE_SECONDS)
        self.assertEqual(printed.getvalue().splitlines(), ["True", "completed The readme describes the SDK.", "26 check_codex_ready"])


@requires_sdk
class CodexHostOpenTests(HostTestCase):
    """AC-3 and AC-4: binary resolution and the minimum-version gate at open."""

    async def test_a_missing_codex_binary_is_not_installed_and_starts_nothing(self) -> None:
        # AC-3, EC-2, INV-3: shutil.which runs first, its name is in the message, and no process starts.
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        self.which_result = None
        for settings, name in ((None, "codex"), (CodexClientSettings(codex_bin="my-codex"), "my-codex")):
            with self.subTest(name=name):
                self.which_calls.clear()
                error = await self.assert_codex_error(CodexHost(settings).__aenter__(), "codex.not_installed")
                self.assertEqual(self.which_calls, [name])
                self.assertIn(name, error.message)
                self.assertEqual(self.server.started, 0)

    async def test_the_resolved_path_is_launched_and_a_launch_override_skips_resolution(self) -> None:
        # AC-3, D-4: the absolute path shutil.which returns is CodexConfig.codex_bin; an override is passed verbatim.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        host = await self.open_host()
        self.assertEqual(self.which_calls, ["codex"])
        self.assertEqual(self.server.config.codex_bin, FAKE_CODEX_PATH)
        await self.close_host(host)

        self.which_calls.clear()
        override = ("node", "codex.js", "app-server", "--listen", "stdio://")
        await self.open_host(CodexClientSettings(launch_args_override=override))
        self.assertEqual(self.which_calls, [])
        self.assertEqual(tuple(self.server.config.launch_args_override), override)

    async def test_a_process_that_cannot_start_is_not_installed_naming_the_path(self) -> None:
        # Section 9.2 exception table: FileNotFoundError or OSError while starting means codex.not_installed.
        from vidbyte.harnesses.native.codex import CodexHost

        for failure in (FileNotFoundError(2, "The system cannot find the file specified"), PermissionError(13, "Access is denied")):
            with self.subTest(failure=type(failure).__name__):
                self.server.start_error = failure
                error = await self.assert_codex_error(CodexHost().__aenter__(), "codex.not_installed")
                self.assertIn(FAKE_CODEX_PATH, error.message)

    async def test_versions_below_the_minimum_or_unparseable_are_refused_and_the_client_closed(self) -> None:
        # AC-4, EC-4, INV-4, INV-5, A-12: a refused open closes the client it started; 0.151.0 and up open.
        from vidbyte.harnesses.native.codex import CodexHost

        for version in ("0.150.9", "0.0.0", "", "garbage"):
            with self.subTest(version=version):
                self.server.version = version
                closed = self.server.closed
                error = await self.assert_codex_error(CodexHost().__aenter__(), "codex.version_unsupported")
                self.assertIn(MINIMUM_VERSION, error.message)
                if version:
                    self.assertIn(version, error.message)
                self.assertEqual(self.server.closed, closed + 1)
        for version, user_agent in (("0.151.0", None), ("0.162.1", None), (None, "codex-app-server/0.162.1")):
            with self.subTest(version=version, user_agent=user_agent):
                self.server.version, self.server.user_agent = version, user_agent
                host = await self.open_host()
                readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
                self.assertEqual(readiness.version, version or "0.162.1")
                await self.close_host(host)


@requires_sdk
class CodexHostGuardTests(HostTestCase):
    """AC-33, INV-2 and INV-6: the call guards run before anything else."""

    async def test_a_host_answers_only_while_open_and_opens_at_most_once(self) -> None:
        # INV-2, INV-6, EC-58, EC-60: not open, entered twice (also concurrently), and re-entered after a failed open.
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        idle = CodexHost()
        with self.assertRaises(ConfigurationError):
            await idle.check_codex_ready()
        with self.assertRaises(ConfigurationError):
            await idle.get_codex_turn_result(CodexTurnHandle(thread_id="thr-1", turn_id="turn-1"))
        self.assertEqual(self.server.clients_created, 0)

        host = await self.open_host()
        with self.assertRaises(ConfigurationError):
            await host.__aenter__()
        self.assertEqual(self.server.started, 1)

        racing = CodexHost()
        self.addAsyncCleanup(self.close_host, racing)
        entries = [asyncio.ensure_future(racing.__aenter__()), asyncio.ensure_future(racing.__aenter__())]
        done, _ = await asyncio.wait(entries, timeout=WAIT_SECONDS)
        self.assertEqual(len(done), 2)
        errors = [entry.exception() for entry in entries]
        self.assertEqual(sum(error is None for error in errors), 1, errors)
        self.assertEqual(sum(isinstance(error, ConfigurationError) for error in errors), 1, errors)
        self.assertEqual(self.server.started, 2)

        self.which_result = None
        failed = CodexHost()
        await self.assert_codex_error(failed.__aenter__(), "codex.not_installed")
        self.which_result = FAKE_CODEX_PATH
        with self.assertRaises(ConfigurationError):
            await failed.__aenter__()
        self.assertEqual(self.server.started, 2)

    async def test_a_closed_host_answers_local_reads_and_refuses_calls_that_talk_to_codex(self) -> None:
        # AC-33, INV-6, INV-7, EC-58: the turn running at close is FAILED, and later talking calls send nothing.
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.close_host(host)

        snapshot = await host.get_codex_turn_result(handle)
        self.assert_problem(snapshot, "failed", "codex.process_exited")
        sent = len(self.server.requests)
        await self.assert_codex_error(host.check_codex_ready(), "codex.process_exited")
        await self.assert_codex_error(host.continue_codex_thread(handle.thread_id, "Carry on."), "codex.process_exited")
        await self.assert_codex_error(host.interrupt_codex_turn(handle), "codex.process_exited")
        self.assertEqual(len(self.server.requests), sent)
        self.assertEqual(self.server.kinds("write_after_close"), [])
        self.assertEqual(await asyncio.wait_for(host.wait_codex_turn(handle, timeout_seconds=WAIT_SECONDS), WAIT_SECONDS), snapshot)
        usage = await asyncio.wait_for(host.track_codex_thread_usage(handle.thread_id), WAIT_SECONDS)
        self.assertEqual(usage.thread_id, handle.thread_id)

        # INV-7: a second __aexit__ does nothing, and INV-2: a closed host never reopens.
        closes = self.server.closed
        await self.close_host(host)
        self.assertEqual(self.server.closed, closes)
        with self.assertRaises(ConfigurationError):
            await host.__aenter__()

    async def test_a_call_from_another_event_loop_is_refused(self) -> None:
        # INV-6, EC-59: the loop that opened the host is the only one that may use it.
        host = await self.open_host()
        sent = len(self.server.requests)
        error = await self.run_in_other_loop(lambda: host.check_codex_ready())
        self.assertIsInstance(error, ConfigurationError)
        self.assertEqual(len(self.server.requests), sent)


@requires_sdk
class CodexHostCloseTests(HostTestCase):
    """AC-33 and INV-7: close cancels tool calls, finalizes and interrupts turns, closes goal streams, then closes."""

    async def test_close_interrupts_a_running_turn_once_then_closes_on_a_daemon_thread(self) -> None:
        # INV-7 steps 2, 3 and 5, and D-1: no host call ever runs on the loop thread or the default executor.
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.close_host(host)

        self.assert_problem(await host.get_codex_turn_result(handle), "failed", "codex.process_exited")
        interrupts = _log_index(self.server, lambda entry: entry[0] == "request" and entry[1] == "turn/interrupt" and entry[2].params.get("turnId") == handle.turn_id)
        closes = _log_index(self.server, lambda entry: entry[0] == "close")
        self.assertEqual(len(interrupts), 1)
        self.assertEqual(len(closes), 1)
        self.assertLess(interrupts[0], closes[0])
        _, close_thread, close_daemon = self.server.log[closes[0]]
        self.assertTrue(close_daemon, close_thread)
        for request in self.server.requests:
            with self.subTest(method=request.method):
                self.assertNotEqual(request.thread_name, "MainThread")
                self.assertFalse(request.thread_name.startswith("asyncio_"), request.thread_name)

    async def test_close_cancels_a_running_tool_call_before_sending_interrupts(self) -> None:
        # AC-33, EC-80, INV-7 step 1: the reader is freed first, so the interrupt is answered at once.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        slow = _SlowTool(self.server)
        host = await self.open_host()
        handle = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Look it up.", tools=(slow,))), WAIT_SECONDS)
        call = {"threadId": handle.thread_id, "turnId": handle.turn_id, "callId": "call-1", "tool": "slow_lookup", "arguments": {"text": "hi"}}
        answer = self.server.server_request("item/tool/call", call)
        await asyncio.wait_for(slow.started.wait(), WAIT_SECONDS)

        # An interrupt sent while the reader is still inside the tool call would now hold close for 60 s.
        self.patch_connection("CODEX_HOST_CLOSE_INTERRUPT_SECONDS", 60.0)
        await self.close_host(host)

        self.assertEqual(len(self.server.kinds("tool_cancelled")), 1)
        reply = await asyncio.wait_for(asyncio.wrap_future(answer), WAIT_SECONDS)
        self.assertIs(reply["success"], False)
        self.assertEqual(self.count("turn/interrupt", lambda params: params.get("turnId") == handle.turn_id), 1)
        later = await asyncio.to_thread(self.server.approval_handler, "item/tool/call", {**call, "callId": "call-2"})
        self.assertIs(later["success"], False)
        self.assertEqual(later["contentItems"][0]["text"], UNREGISTERED_TOOL_TEXT)

    async def test_close_ends_a_goal_run_in_openai_codex_order_and_its_watcher_exits(self) -> None:
        # AC-33, EC-81, INV-7 steps 3 and 4: cancel, then finish, wake and unregister, and no stranded watcher.
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        host = await self.open_host()
        handle = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(goal=CodexGoal(objective="Ship the release notes."))), WAIT_SECONDS)
        thread_id = handle.thread_id
        await self.wait_until(lambda: any(entry[0] == "next_goal_notification" and entry[1] == thread_id for entry in self.server.log), "the goal watcher to read")
        await self.close_host(host)

        cleanup = [entry[0] for entry in self.server.kinds(*GOAL_CLEANUP) if entry[1] == thread_id]
        self.assertEqual(cleanup[:4], list(GOAL_CLEANUP), cleanup)
        self.assertEqual(cleanup.count("cancel_goal_operation"), 1, cleanup)
        watchers = {entry[2] for entry in self.server.kinds("next_goal_notification") if entry[1] == thread_id}
        for watcher in watchers:
            await asyncio.to_thread(watcher.join, WAIT_SECONDS)
            self.assertFalse(watcher.is_alive(), watcher.name)
        self.assert_problem(await host.get_codex_turn_result(handle), "failed", "codex.process_exited")


@requires_sdk
class CodexHostModuleFunctionTests(HostTestCase):
    """AC-31 and INV-38: each module function opens its own host once and always closes it."""

    async def test_each_module_function_opens_and_closes_one_host_whether_it_succeeds_or_fails(self) -> None:
        from tests.features.codex_host.codex_host_fakes import FakeRpcError
        from vidbyte.harnesses.native import codex as native_codex

        seeded = self.server.seed_thread(completed_turns=1)
        calls = (
            ("check_codex_ready", ()),
            ("get_codex_rate_limits", ()),
            ("list_codex_models", ()),
            ("list_codex_threads", ()),
            ("read_codex_thread", (seeded.thread_id,)),
            ("fork_codex_thread", (seeded.thread_id,)),
        )
        for name, args in calls:
            with self.subTest(name=name, outcome="success"):
                started, closed = self.server.started, self.server.closed
                await asyncio.wait_for(getattr(native_codex, name)(*args), CLOSE_SECONDS)
                self.assertEqual((self.server.started - started, self.server.closed - closed), (1, 1))

        for method in ("account/read", "account/rateLimits/read", "model/list", "thread/list"):
            self.server.fail(method, FakeRpcError(-32603, f"{method} failed"))
        failures = (
            ("get_codex_rate_limits", (), "codex.api_error"),
            ("list_codex_models", (), "codex.api_error"),
            ("list_codex_threads", (), "codex.api_error"),
            ("read_codex_thread", ("thr-missing",), "codex.session_not_found"),
            ("fork_codex_thread", ("thr-missing",), "codex.session_not_found"),
        )
        for name, args, code in failures:
            with self.subTest(name=name, outcome="failure"):
                started, closed = self.server.started, self.server.closed
                await self.assert_codex_error(getattr(native_codex, name)(*args), code)
                self.assertEqual((self.server.started - started, self.server.closed - closed), (1, 1))

        # INV-38: the module check_codex_ready reports the failure in its result instead of raising it.
        started, closed = self.server.started, self.server.closed
        readiness = await asyncio.wait_for(native_codex.check_codex_ready(), CLOSE_SECONDS)
        self.assertFalse(readiness.ready)
        self.assertEqual([problem.code.value for problem in readiness.problems], ["codex.api_error"])
        self.assertEqual((self.server.started - started, self.server.closed - closed), (1, 1))

    async def test_module_check_codex_ready_reports_a_missing_binary_instead_of_raising(self) -> None:
        # AC-31: with no codex on PATH the result says not installed, and no process starts.
        from vidbyte.harnesses.native.codex import check_codex_ready

        self.which_result = None
        readiness = await asyncio.wait_for(check_codex_ready(), CLOSE_SECONDS)
        self.assertFalse(readiness.ready)
        self.assertEqual([problem.code.value for problem in readiness.problems], ["codex.not_installed"])
        self.assertEqual(readiness.problems[0].next_step, NEXT_STEPS["codex.not_installed"])
        self.assertEqual(self.server.started, 0)


if __name__ == "__main__":
    unittest.main()
