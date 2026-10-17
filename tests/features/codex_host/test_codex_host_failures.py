"""FILE: tests/features/codex_host/test_codex_host_failures.py

PURPOSE: Proves late acceptance and privacy: a spawn or review whose start returns after its caller was cancelled, or after the request bound elapsed, is owned (registered and interrupted exactly once, and a review is read back); a start still queued behind a blocked host worker is withdrawn and never sent; a start that returns after close began is registered FAILED and nothing more is sent; and no error, record or tool output carries the account email, an environment value, the app-server's stderr or a raw stdout line.
ROLE IN CODEBASE: Failure layer of tests/features/codex_host/ (spec AC-32, AC-34, INV-8, INV-9, INV-11, D-1, D-3, D-23, EC-36, EC-67, EC-72, EC-78, EC-79). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Holds on the fake app-server keep a start request unanswered while the test cancels its caller, lets a bound elapse, blocks the host's only worker, or begins close. Exact interrupt counts use the one-worker barrier: with CODEX_HOST_WORKER_THREADS patched to 1, a later host call cannot return before an interrupt queued earlier has reached the fake. Privacy canaries are unique strings, so finding one anywhere is a leak.
COMMON MODIFICATION PATTERNS: Add a late-acceptance case by holding the start request it sends; add a privacy source by planting a new canary where Codex would put it and adding the outputs that could carry it.
KNOWN EDGE CASES: The queued-start test cannot observe the host's executor queue, so it yields to the loop generously before cancelling; if the spawn had not queued its turn/start by then, the test passes without exercising the withdrawal, but it can never fail falsely. A start that returns after close began is registered by a callback a host worker posts to the loop, so that test polls get_codex_turn_result, bounded by WAIT_SECONDS, until the turn appears. Error texts include the visible exception chain, because spec section 12.3 row 10 has every caller raise the mapped error from None, so a chained SDK exception carrying a canary is a leak.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-8, INV-9, INV-11), 8.1 (D-1, D-3, D-23), 9.2 (exception table) and 10.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_failures.py
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    CONNECTION_MODULE,
    ENV_SECRET,
    FAKE_CODEX_PATH,
    LINE_SECRET,
    STDERR_SECRET,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    error_texts,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult

# Enough loop turns for a coroutine to move from one awaited result to its next executor submission.
LOOP_TURNS = 200
# How often a late registration is polled for; the wait is bounded by WAIT_SECONDS, so it only slows a failure.
POLL_SECONDS = 0.01


async def _yield_to_the_loop() -> None:
    for _ in range(LOOP_TURNS):
        await asyncio.sleep(0)


async def _call_tool(tools: Any, name: str, arguments: dict[str, Any]) -> ToolResult:
    tool = next(tool for tool in tools if tool.spec().name == name)
    return await asyncio.wait_for(tool.execute(ToolCall(tool_name=name, arguments=arguments)), WAIT_SECONDS)


async def _snapshot_once_registered(host: Any, handle: Any) -> Any:
    """Read a late turn's snapshot, polling while the host has not yet registered it.

    A start that returns after its caller is gone is registered by a callback a host worker posts to the
    loop (spec section 12.3 row 12), so nothing the fake can observe marks the moment it lands.
    """
    from vidbyte.lib.errors import CodexAgentError

    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    while True:
        try:
            return await asyncio.wait_for(host.get_codex_turn_result(handle), WAIT_SECONDS)
        except CodexAgentError as error:
            if error.failure_code != "codex.session_not_found" or loop.time() > deadline:
                raise
        await asyncio.sleep(POLL_SECONDS)


@requires_sdk
class CodexHostLateAcceptanceTests(HostTestCase):
    """AC-32 and INV-11: no turn Codex accepts is ever left without an owner."""

    def _request(self) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        return CodexSpawnRequest(prompt="Fix the failing test.")

    async def _assert_owned_and_interrupted_once(self, host: Any, thread_id: str, turn_id: str) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        await self.wait_for_request("turn/interrupt", lambda params: params["turnId"] == turn_id)
        # Barrier: with one host worker, this read returns only after any interrupt queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt", lambda params: params["turnId"] == turn_id), 1)
        # EC-67: the host registered the turn, so a later wait or get reports how it ended.
        snapshot = await self.wait_done(host, CodexTurnHandle(thread_id=thread_id, turn_id=turn_id))
        self.assertEqual(snapshot.status.value, "interrupted")
        self.assertEqual(await host.get_codex_turn_result(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id)), snapshot)

    async def test_a_spawn_cancelled_while_turn_start_is_in_flight_owns_the_turn(self) -> None:
        # AC-32, EC-67, INV-11 "A start already sent is owned": the caller sees CancelledError at once.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        hold = self.server.hold("turn/start")
        task = asyncio.ensure_future(host.spawn_codex_thread(self._request()))
        thread_id = (await asyncio.to_thread(hold.wait_arrived)).params["threadId"]
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        hold.release()
        await self.wait_until(lambda: bool(self.server.threads[thread_id].turns), "Codex to accept the late turn")
        await self._assert_owned_and_interrupted_once(host, thread_id, self.server.threads[thread_id].turns[0].turn_id)

    async def test_a_spawn_whose_start_outlives_the_request_bound_gets_api_error_and_the_turn_is_owned(self) -> None:
        # AC-32, EC-36, D-3, INV-8: the error names the thread already created; the late turn still gets one interrupt.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        hold = self.server.hold("turn/start")
        with mock.patch(f"{CONNECTION_MODULE}.CODEX_HOST_REQUEST_TIMEOUT_SECONDS", 0.3):
            task = asyncio.ensure_future(host.spawn_codex_thread(self._request()))
            thread_id = (await asyncio.to_thread(hold.wait_arrived)).params["threadId"]
            error = await self.assert_codex_error(task, "codex.api_error")
        self.assertIn(thread_id, error.message)
        hold.release()
        await self.wait_until(lambda: bool(self.server.threads[thread_id].turns), "Codex to accept the late turn")
        await self._assert_owned_and_interrupted_once(host, thread_id, self.server.threads[thread_id].turns[0].turn_id)

    async def test_a_review_cancelled_in_flight_is_interrupted_once_and_read_back(self) -> None:
        # AC-32, D-23: a late review also gets the registration read-back of its thread with turns.
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        hold = self.server.hold("review/start")
        task = asyncio.ensure_future(host.start_codex_review(seeded.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)))
        await asyncio.to_thread(hold.wait_arrived)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        hold.release()
        await self.wait_until(lambda: len(seeded.turns) == 2, "Codex to accept the late review")
        await self.wait_for_request("thread/read", lambda params: params["threadId"] == seeded.thread_id and bool(params.get("includeTurns")))
        await self._assert_owned_and_interrupted_once(host, seeded.thread_id, seeded.turns[-1].turn_id)

    async def test_a_start_still_queued_behind_a_blocked_worker_is_never_sent(self) -> None:
        # EC-78, INV-11 "A start still queued is withdrawn": the thread exists, but no paid turn ever starts.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        blocker = self.server.seed_thread(completed_turns=1)
        start_hold = self.server.hold("thread/start")
        spawn = asyncio.ensure_future(host.spawn_codex_thread(self._request()))
        await asyncio.to_thread(start_hold.wait_arrived)

        # Queue a read behind thread/start, then let thread/start finish: the only worker moves on to the held read.
        read_hold = self.server.hold("thread/read", lambda params: params["threadId"] == blocker.thread_id)
        reader = asyncio.ensure_future(host.read_codex_thread(blocker.thread_id))
        await _yield_to_the_loop()
        start_hold.release()
        await asyncio.to_thread(read_hold.wait_arrived)
        # The spawn now queues its turn/start behind the blocked read; cancel it while it waits there.
        await _yield_to_the_loop()
        spawn.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(spawn, WAIT_SECONDS)
        read_hold.release()
        await asyncio.wait_for(reader, WAIT_SECONDS)

        created = list(self.server.threads)[-1]
        # Barrier: a turn/start still in the queue would reach the fake before this read returns.
        await asyncio.wait_for(host.read_codex_thread(created), WAIT_SECONDS)
        self.assertEqual(self.count("turn/start"), 0)
        self.assertEqual(self.server.threads[created].turns, [])

    async def test_a_start_that_returns_after_close_began_is_registered_failed_and_sends_nothing(self) -> None:
        # EC-79, INV-11 "Close wins": the waiting caller gets process_exited naming the thread; no interrupt follows.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        host = await self.open_host()
        hold = self.server.hold("turn/start")
        task = asyncio.ensure_future(host.spawn_codex_thread(self._request()))
        thread_id = (await asyncio.to_thread(hold.wait_arrived)).params["threadId"]

        def answer_the_start_while_closing() -> None:
            hold.release()
            hold.wait_responded()

        self.server.before_close = answer_the_start_while_closing
        await self.close_host(host)
        error = await self.assert_codex_error(task, "codex.process_exited")
        self.assertIn(thread_id, error.message)
        turn_id = self.server.threads[thread_id].turns[0].turn_id
        snapshot = await _snapshot_once_registered(host, CodexTurnHandle(thread_id=thread_id, turn_id=turn_id))
        self.assert_problem(snapshot, "failed", "codex.process_exited")
        self.assertEqual(self.count("turn/interrupt"), 0)
        self.assertEqual(self.server.kinds("write_after_close"), [])


@requires_sdk
class CodexHostPrivacyTests(HostTestCase):
    """AC-34 and INV-9: private values never reach an error, a record or a tool output."""

    async def test_no_error_record_or_tool_output_carries_a_private_value(self) -> None:
        # AC-34, INV-9, EC-72, section 9.2 exception table: SDK texts that quote private data become fixed messages.
        from openai_codex.errors import CodexError, TransportClosedError

        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.dataclasses.codex import CodexClientSettings
        from vidbyte.tools.toolsets import CodexHostTools

        settings = CodexClientSettings(env={"VIDBYTE_CANARY_TOKEN": ENV_SECRET})
        texts: list[str] = []

        # Failed opens with the secret in the environment.
        self.server.version = "0.150.9"
        texts += error_texts(await self.assert_codex_error(CodexHost(settings).__aenter__(), "codex.version_unsupported"))
        self.server.version = "0.162.1"
        self.which_result = None
        texts += error_texts(await self.assert_codex_error(CodexHost(settings).__aenter__(), "codex.not_installed"))
        self.which_result = FAKE_CODEX_PATH

        # Records from an open host whose account has an email and whose client has the secret in its env.
        host = await self.open_host(settings)
        self.assertEqual(dict(self.server.config.env)["VIDBYTE_CANARY_TOKEN"], ENV_SECRET)
        handle = await self.spawn(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.", usage=self.fakes.token_usage((100, 20), (100, 20)))
        records = [
            await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS),
            await self.wait_done(host, handle),
            await asyncio.wait_for(host.get_codex_rate_limits(), WAIT_SECONDS),
            await asyncio.wait_for(host.read_codex_thread(handle.thread_id, include_turns=True), WAIT_SECONDS),
            await asyncio.wait_for(host.track_codex_thread_usage(handle.thread_id), WAIT_SECONDS),
        ]
        texts += [repr(record) for record in records]

        tools = CodexHostTools(host, max_live_turns=2)
        tool_calls = (
            ("check_codex_ready", {}),
            ("get_codex_rate_limits", {}),
            ("list_codex_threads", {}),
            ("read_codex_thread", {"thread_id": handle.thread_id, "include_turns": True}),
            ("track_codex_thread_usage", {"thread_id": handle.thread_id}),
        )
        for name, arguments in tool_calls:
            texts.append((await _call_tool(tools, name, arguments)).output)

        # SDK exceptions whose text carries a private value; the plain CodexError is how a reader death quotes a raw line.
        failures = (
            (RuntimeError(f"env dump: {ENV_SECRET}"), "codex.api_error"),
            (CodexError(f"Invalid JSON from app-server: {LINE_SECRET}"), "codex.protocol_mismatch"),
        )
        for exc, code in failures:
            with self.subTest(exception=type(exc).__name__):
                with mock.patch.object(self.server.client, "account_read", side_effect=exc):
                    error = await self.assert_codex_error(host.check_codex_ready(), code)
                    failed_tool = await _call_tool(tools, "check_codex_ready", {})
                texts += error_texts(error) + [failed_tool.output, str(failed_tool.metadata)]
                if isinstance(exc, RuntimeError):
                    self.assertIn("RuntimeError", error.message)
        with mock.patch.object(self.server.client, "account_read", side_effect=TransportClosedError(f"app-server exited; stderr: {STDERR_SECRET}")):
            texts += error_texts(await self.assert_codex_error(host.check_codex_ready(), "codex.process_exited"))

        assert_no_canary(self, texts)


if __name__ == "__main__":
    unittest.main()
