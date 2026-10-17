"""FILE: tests/features/codex_host/test_codex_host_resilience.py

PURPOSE: Proves how the hardened CodexHost behaves when Codex fails part-way: a spawn or launch whose turn start fails names the thread it left and leaves no tool registration behind; only the four idempotent reads are retried on overload, and every spending call is sent once with retryable set; a thread/read that fails for any reason but a refusal is an API error, not a missing thread, including inside a lineage walk; a turn being stopped cannot be steered, and a refused steer means the turn is gone; and an error escaping a run wrapper carries the wrapper's own operation with every other field kept.
ROLE IN CODEBASE: Failure-path layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-2, AC-3, AC-4, AC-6, AC-24, AC-26, INV-1, INV-3 to INV-6, INV-26, INV-31, EC-12, EC-13, EC-15, EC-40, D-7, D-8, D-11, D-22, D-23). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Failures are scripted on the fake app-server with fail(...), so the real openai-codex retry helper, the real connection and the real CodexErrorMapper run; FieldCarryingMapper only records what the real mapper built, so the wrapper rows can compare the relabelled error with the original. The overload rows run the SDK's own retry with its real backoff, which adds under a second per exhausted read.
COMMON MODIFICATION PATTERNS: A method that joins CODEX_HOST_RETRIED_METHODS moves from SENT_ONCE to RETRIED with the host call that sends it.
KNOWN EDGE CASES: The fake numbers threads in creation order, so the third thread of a fresh launch is thr-3. A goal spawn starts no turn/start (Codex starts goal turns), so its wrapper row fails thread/start instead.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1 (INV-1 to INV-6, INV-26, INV-31) and 9.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_resilience.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    STEER_STOPPING_MESSAGE,
    UNREGISTERED_TOOL_TEXT,
    WAIT_SECONDS,
    FieldCarryingMapper,
    HostTestCase,
    changed_error_fields,
    make_echo_tool,
    mapped_summary,
    requires_sdk,
    thread_suffix,
)

SKILL_PATH = os.path.abspath(os.path.join(os.sep, "skills", "s", "SKILL.md"))
DOCS_SKILL_PATH = os.path.abspath(os.path.join(os.sep, "skills", "openai-docs", "SKILL.md"))
UNREGISTERED = {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]}


def _tool_call(thread_id: str, turn_id: str = "turn-x") -> dict[str, Any]:
    return {"threadId": thread_id, "turnId": turn_id, "callId": f"call-{thread_id}", "tool": "echo_text", "arguments": {"text": "hi"}}


def _on(thread_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda params: params.get("threadId") == thread_id


class ResilienceTestCase(HostTestCase):
    """HostTestCase plus the request-count and error-field checks these tests share."""

    def assert_relabelled(self, error: Any, original: Any, wrapper: str, suffix: str = "") -> None:
        """INV-31 and D-22: only the operation, the message head and the fields derived from the operation changed."""
        self.assertEqual(error.operation, wrapper)
        head = f"{original.operation} failed with {original.failure_code}. "
        self.assertTrue(original.message.startswith(head), original.message)
        self.assertEqual(error.message, f"{wrapper} failed with {original.failure_code}. " + original.message[len(head) :] + suffix)
        derived = {"operation", "expected", "safe_runtime_details"}
        self.assertEqual({name: pair for name, pair in changed_error_fields(error, original).items() if name not in derived}, {})
        self.assertEqual({key: value for key, value in error.safe_runtime_details.items() if key != "operation"}, {key: value for key, value in original.safe_runtime_details.items() if key != "operation"})
        self.assertEqual(error.method, original.method)

    async def settle(self, task: Any, held: Any) -> None:
        """Cleanup for a test that fails while a task waits on a held request: release it, then let the task end."""
        held.release()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)


@requires_sdk
class CodexSpawnCleanupTests(ResilienceTestCase):
    """AC-2, AC-3, INV-1 and INV-26: a failed start names its thread and leaves no tool registration behind."""

    async def test_a_spawn_whose_turn_or_name_fails_names_the_thread_and_unregisters_its_tools(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        for failing, fields in (("turn/start", {}), ("thread/name/set", {"name": "Named run"})):
            with self.subTest(failing=failing):
                self.server.fail(failing, self.fakes.FakeRpcError(-32603, f"{failing} failed"), times=1)
                request = CodexSpawnRequest(prompt="Use the tool.", tools=(make_echo_tool(),), **fields)
                error = await self.assert_codex_error(host.spawn_codex_thread(request), "codex.api_error")
                thread_id = list(self.server.threads)[-1]
                self.assertEqual(error.thread_id, thread_id)
                self.assertIn(thread_suffix(thread_id), error.message)
                # INV-26: the failed thread's tool calls get the unregistered-tool answer, not the developer's tool.
                self.assertEqual(await self.ask("item/tool/call", _tool_call(thread_id)), UNREGISTERED)
        self.assertEqual(self.server.reader_errors, [])

    async def test_a_launch_whose_third_turn_fails_stops_the_two_started_turns_and_unregisters_the_third(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        self.server.fail("turn/start", self.fakes.FakeRpcError(-32603, "turn start failed"), predicate=_on("thr-3"))
        request = CodexSpawnRequest(tools=(make_echo_tool(),))
        error = await self.assert_codex_error(host.launch_codex_subagents(("Check a.", "Check b.", "Check c."), request=request), "codex.api_error")
        self.assertEqual(error.thread_id, "thr-3")
        self.assertIn(thread_suffix("thr-3"), error.message)
        for started in ("thr-1", "thr-2"):
            await self.wait_for_request("turn/interrupt", _on(started))
        await asyncio.wait_for(host.read_codex_thread("thr-3"), WAIT_SECONDS)
        self.assertEqual([self.count("turn/interrupt", _on(thread_id)) for thread_id in ("thr-1", "thr-2", "thr-3")], [1, 1, 0])
        self.assertEqual(await self.ask("item/tool/call", _tool_call("thr-3")), UNREGISTERED)


@requires_sdk
class CodexOverloadRetryTests(ResilienceTestCase):
    """AC-4, INV-3, D-7, EC-12 and EC-13: the four idempotent reads are retried once overloaded; spending calls are sent once."""

    async def test_each_idempotent_read_is_retried_after_one_overload_and_succeeds(self) -> None:
        host = await self.open_host()
        stored = self.server.seed_thread()
        rows: tuple[tuple[str, Callable[[], Awaitable[Any]]], ...] = (
            ("account/read", lambda: host.check_codex_ready()),
            ("thread/read", lambda: host.read_codex_thread(stored.thread_id)),
            ("thread/list", lambda: host.list_codex_threads()),
            ("thread/name/set", lambda: self.spawn(host, name="Named run")),
        )
        for method, call in rows:
            with self.subTest(method=method):
                before = self.count(method)
                self.server.fail(method, self.fakes.overloaded_error(), times=1)
                await asyncio.wait_for(call(), WAIT_SECONDS)
                self.assertEqual(self.count(method) - before, 2)

    async def test_each_spending_or_state_changing_call_is_sent_once_and_raises_a_retryable_api_error(self) -> None:
        host = await self.open_host()
        running = await self.spawn(host)
        rows: tuple[tuple[str, Callable[[str], Awaitable[Any]]], ...] = (
            ("thread/start", lambda thread_id: self.spawn(host)),
            ("thread/resume", lambda thread_id: host.continue_codex_thread(thread_id, "Go on.")),
            ("thread/fork", lambda thread_id: host.fork_codex_thread(thread_id)),
            ("thread/compact/start", lambda thread_id: host.compact_codex_thread(thread_id)),
            ("turn/start", lambda thread_id: self.spawn(host)),
            ("turn/steer", lambda thread_id: host.steer_codex_turn(running, "Also check the tests.")),
        )
        for method, call in rows:
            with self.subTest(method=method):
                stored = self.server.seed_thread()
                before = self.count(method)
                self.server.fail(method, self.fakes.overloaded_error(), times=1)
                error = await self.assert_codex_error(call(stored.thread_id), "codex.api_error")
                self.assertEqual(self.count(method) - before, 1)
                self.assertIs(error.retryable, True)


@requires_sdk
class CodexThreadReadFailureTests(ResilienceTestCase):
    """AC-6, INV-4, INV-5, D-8 and EC-15: only a refused thread/read means the thread is missing."""

    def functions(self, host: Any) -> tuple[tuple[str, Callable[[str], Awaitable[Any]]], ...]:
        return (
            ("read_codex_thread", lambda thread_id: host.read_codex_thread(thread_id)),
            ("continue_codex_thread", lambda thread_id: host.continue_codex_thread(thread_id, "Go on.")),
            ("compact_codex_thread", lambda thread_id: host.compact_codex_thread(thread_id)),
            ("delete_codex_thread", lambda thread_id: host.delete_codex_thread(thread_id)),
            ("get_codex_goal", lambda thread_id: host.get_codex_goal(thread_id)),
        )

    async def test_an_internal_or_lasting_overload_error_is_an_api_error_and_a_refusal_is_not_found(self) -> None:
        host = await self.open_host()
        rows = (
            ("internal error", self.fakes.FakeRpcError(-32603, "thread store unavailable"), "codex.api_error"),
            ("overloaded on every attempt", self.fakes.overloaded_error(), "codex.api_error"),
            ("invalid request", self.fakes.FakeRpcError(-32600, "thread not found"), "codex.session_not_found"),
            ("invalid params", self.fakes.FakeRpcError(-32602, "malformed thread id"), "codex.session_not_found"),
        )
        for label, rpc_error, code in rows:
            stored = self.server.seed_thread()
            self.server.fail("thread/read", rpc_error, predicate=_on(stored.thread_id))
            for operation, call in self.functions(host):
                with self.subTest(error=label, operation=operation):
                    error = await self.assert_codex_error(call(stored.thread_id), code)
                    self.assertEqual((error.operation, error.method, error.thread_id), (operation, "thread/read", stored.thread_id))
                    self.assertIs(error.retryable, code == "codex.api_error")

    async def test_an_exhausted_overload_is_read_three_times_and_ends_a_lineage_walk_with_an_error(self) -> None:
        # INV-3: the SDK's default policy is three attempts. INV-5: only a missing parent ends the walk early.
        host = await self.open_host()
        stored = self.server.seed_thread()
        self.server.fail("thread/read", self.fakes.overloaded_error(), predicate=_on(stored.thread_id))
        await self.assert_codex_error(host.read_codex_thread(stored.thread_id), "codex.api_error")
        self.assertEqual(self.count("thread/read", _on(stored.thread_id)), 3)
        parent = self.server.new_thread()
        child = self.server.new_thread(forked_from=parent.thread_id)
        self.server.fail("thread/read", self.fakes.overloaded_error(), predicate=_on(parent.thread_id))
        error = await self.assert_codex_error(host.get_codex_thread_lineage(child.thread_id), "codex.api_error")
        self.assertEqual((error.operation, error.method), ("get_codex_thread_lineage", "thread/read"))
        self.assertEqual(self.count("thread/read", _on(parent.thread_id)), 3)


@requires_sdk
class CodexSteerStoppingTests(ResilienceTestCase):
    """AC-24, INV-6 and D-23: a turn being stopped is refused locally; a steer Codex refuses means the turn ended."""

    async def test_a_turn_whose_interrupt_is_in_flight_is_refused_without_a_request(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        held = self.server.hold("turn/interrupt")
        interrupting = asyncio.ensure_future(host.interrupt_codex_turn(handle))
        self.addAsyncCleanup(self.settle, interrupting, held)
        await asyncio.to_thread(held.wait_arrived)
        error = await self.assert_codex_error(host.steer_codex_turn(handle, "Also check the tests."), "codex.session_not_found")
        self.assertEqual(error.operation, "steer_codex_turn")
        self.assertTrue(mapped_summary(self, error).startswith(STEER_STOPPING_MESSAGE.format(turn_id=handle.turn_id)), error.message)
        self.assertEqual(self.count("turn/steer"), 0)
        held.release()
        await asyncio.wait_for(interrupting, WAIT_SECONDS)

    async def test_a_steer_codex_refuses_as_invalid_is_not_found_and_a_malformed_one_is_a_protocol_mismatch(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        for rpc_code, failure_code in ((-32600, "codex.session_not_found"), (-32602, "codex.protocol_mismatch")):
            with self.subTest(rpc_code=rpc_code):
                self.server.fail("turn/steer", self.fakes.FakeRpcError(rpc_code, "expected active turn"), times=1)
                error = await self.assert_codex_error(host.steer_codex_turn(handle, "Also check the tests."), failure_code)
                self.assertEqual((error.method, error.thread_id), ("turn/steer", handle.thread_id))


@requires_sdk
class CodexWrapperOperationTests(ResilienceTestCase):
    """AC-26, INV-31 and D-22: every error escaping a run wrapper carries the wrapper's operation, all else kept."""

    async def opened(self) -> tuple[Any, FieldCarryingMapper]:
        self.server.skills[self.fakes.DEFAULT_CWD] = [self.fakes.skill_entry("s", SKILL_PATH), self.fakes.skill_entry("openai-docs", DOCS_SKILL_PATH)]
        host = await self.open_host()
        mapper = FieldCarryingMapper()
        self.patch_connection("CodexErrorMapper", mapper)
        return host, mapper

    async def test_a_spawn_failure_inside_each_wrapper_is_relabelled(self) -> None:
        host, mapper = await self.opened()
        rows: tuple[tuple[str, str, Callable[[], Awaitable[Any]]], ...] = (
            # A goal spawn starts no turn/start, so its thread start fails instead.
            ("run_codex_goal", "thread/start", lambda: host.run_codex_goal("Ship the fix.", token_budget=500)),
            ("run_codex_skill", "turn/start", lambda: host.run_codex_skill("s", "Do it.")),
            ("run_codex_openai_docs", "turn/start", lambda: host.run_codex_openai_docs("Which event?")),
        )
        for wrapper, failing, start in rows:
            with self.subTest(wrapper=wrapper):
                mapper.mapped.clear()
                self.server.fail(failing, self.fakes.FakeRpcError(-32603, f"{failing} failed"), times=1)
                error = await self.assert_codex_error(start(), "codex.api_error")
                original = mapper.only("spawn_codex_thread")
                self.assertEqual(original.method, failing)
                self.assert_relabelled(error, original, wrapper)
                if failing == "turn/start":
                    self.assertEqual(error.thread_id, list(self.server.threads)[-1])
                    self.assertIn(thread_suffix(error.thread_id), error.message)

    async def test_a_skill_listing_failure_is_relabelled_and_starts_no_thread(self) -> None:
        host, mapper = await self.opened()
        for wrapper, start in (("run_codex_skill", lambda: host.run_codex_skill("s", "Do it.")), ("run_codex_openai_docs", lambda: host.run_codex_openai_docs("Which event?"))):
            with self.subTest(wrapper=wrapper):
                mapper.mapped.clear()
                self.server.fail("skills/list", self.fakes.FakeRpcError(-32603, "skills unavailable"), times=1)
                error = await self.assert_codex_error(start(), "codex.api_error")
                self.assert_relabelled(error, mapper.only("list_codex_skills"), wrapper)
                self.assertEqual(self.count("thread/start"), 0)


if __name__ == "__main__":
    unittest.main()
