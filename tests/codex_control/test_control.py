"""Native live-control acceptance pack.

PURPOSE: Prove real SDK method routing and bounded per-turn control lifetime.
ROLE IN CODEBASE: Executable feature contract for pytest and script verification.
ARCHITECTURE NOTE: Genuine native response models with offline transport seams.
COMMON MODIFICATION PATTERNS: Pair each command with stale and failed response cases.
KNOWN EDGE CASES: A native acknowledgment can arrive after terminal collection.
RELATED DOCS: docs/design/codex-live-control.md
TESTS: python scripts/test-codex-live-control.py
"""

import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("openai_codex")
from openai_codex.generated.v2_all import Turn, TurnCompletedNotification, TurnInterruptResponse, TurnSteerResponse
from openai_codex.models import Notification

from vidbyte import CodexControlSettings, CodexHarnessAgent, CodexHarnessAgentSettings, CodexRunControl
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.native_tools import CodexNativeTurnStream
from vidbyte.agents.codex.stream import CodexStreamRunner
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexForkRequest, CodexForkSettings, CodexObservation, CodexObservationSettings, CodexPrompt, CodexRunInput, CodexRunResult, CodexTextInput, CodexTransportRunRequest, CodexUsage
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.lib.util.concurrency import AsyncCapacityLimiter


class NativeTurn:
    """Native turn seam with real control acknowledgments and terminal events."""

    def __init__(self, *, fail_stream=False):
        # Retain lifecycle evidence separately from native command mocks.
        self.id = "turn"
        self.steer = AsyncMock(return_value=TurnSteerResponse(turn_id="turn"))
        self.interrupt = AsyncMock(return_value=TurnInterruptResponse())
        self.fail_stream = fail_stream
        self.closed = False

    async def stream(self):
        # Yield a real terminal model and expose generator cleanup.
        try:
            if self.fail_stream:
                raise RuntimeError("stream failed")
            yield Notification("turn/completed", TurnCompletedNotification(thread_id="thread", turn=Turn(id="turn", status="interrupted", items=[])))
        finally:
            self.closed = True


class Fixture:
    """Common native identity and request construction."""

    @staticmethod
    def request(control, observation=None):
        # Make control-only requests distinguishable from observation-enabled ones.
        return CodexTransportRunRequest("", "system", CodexPrompt((CodexTextInput("task"),), "task", "user", {}), CodexAgentSettings(), {}, observation=observation or CodexObservationSettings(), control=control)

    @staticmethod
    def handle(native=None, timeout=1):
        # Bind a controller to one known native identity.
        return CodexRunControl("thread", "turn", native or NativeTurn(), timeout)


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    """Native command polarity and lifetime races."""

    async def test_invalid_settings_and_input(self):
        # [Edge Case] Invalid callbacks, waits, and feedback fail before native requests.
        for timeout in (0, -1, True, float("inf"), float("nan")):
            with self.assertRaises(ConfigurationError):
                CodexControlSettings(AsyncMock(), timeout_seconds=timeout)
        with self.assertRaises(ConfigurationError):
            CodexControlSettings(None)
        native = NativeTurn()
        for text in ("", " ", None, 1):
            with self.assertRaises(CodexAgentError):
                await Fixture.handle(native).steer(text)
        native.steer.assert_not_awaited()

    async def test_real_steer_acknowledgment_and_interrupt(self):
        # [Silent Failure] Preserve exact feedback and await real native acknowledgments.
        native = NativeTurn()
        handle = Fixture.handle(native)
        await handle.steer("  Preserve this feedback.  ")
        await handle.interrupt()
        native.steer.assert_awaited_once_with("  Preserve this feedback.  ")
        native.interrupt.assert_awaited_once_with()
        self.assertTrue(handle.active)

    async def test_wrong_identity_and_native_errors(self):
        # [Hidden Failure] Wrong acknowledgment or native exceptions cannot look successful.
        native = NativeTurn()
        native.steer.return_value = TurnSteerResponse(turn_id="other")
        with self.assertRaises(CodexAgentError):
            await Fixture.handle(native).steer("feedback")
        native.interrupt.side_effect = RuntimeError("private provider details")
        with self.assertRaises(CodexAgentError) as error:
            await Fixture.handle(native).interrupt()
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(error.exception.failure_code, "codex.control_failed")

    async def test_timeout_and_cancellation(self):
        # [Hidden Failure] Bounded waits fail closed while cancellation retains asyncio semantics.
        native = NativeTurn()

        async def slow(text):
            # Cooperatively wait beyond the configured control bound.
            await asyncio.sleep(10)

        native.steer.side_effect = slow
        with self.assertRaises(CodexAgentError) as error:
            await Fixture.handle(native, timeout=0.01).steer("feedback")
        self.assertEqual(error.exception.safe_runtime_details["error_type"], "TimeoutError")
        native.interrupt.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await Fixture.handle(native).interrupt()

    async def test_closed_and_late_acknowledgments(self):
        # [Hidden Assumption] A completed handle cannot succeed even when native response arrives later.
        native = NativeTurn()
        handle = Fixture.handle(native)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(text):
            # Hold the acknowledgment until the collector closes its handle.
            entered.set()
            await release.wait()
            return TurnSteerResponse(turn_id="turn")

        native.steer.side_effect = delayed
        pending = asyncio.create_task(handle.steer("feedback"))
        await entered.wait()
        handle.close()
        release.set()
        with self.assertRaises(CodexAgentError):
            await pending
        with self.assertRaises(CodexAgentError):
            await handle.interrupt()
        native.interrupt.assert_not_awaited()

    async def test_concurrent_commands_serialize(self):
        # [Hidden Failure] Concurrent application callers cannot interleave command execution.
        native = NativeTurn()
        order = []

        async def steer(text):
            # Yield while a second command waits for the controller's lock.
            order.append(text + ":start")
            await asyncio.sleep(0)
            order.append(text + ":end")
            return TurnSteerResponse(turn_id="turn")

        native.steer.side_effect = steer
        handle = Fixture.handle(native)
        await asyncio.gather(handle.steer("first"), handle.steer("second"))
        self.assertEqual(order, ["first:start", "first:end", "second:start", "second:end"])

    async def test_capacity_cancellation_and_exception_release(self):
        # [Hidden Failure] Waiting cancellation and admitted exceptions cannot leak or invent permits.
        limiter = AsyncCapacityLimiter()
        entered = []

        async def operation():
            # Record only successful admission to distinguish waiting cancellation.
            async with limiter:
                entered.append(True)

        async with limiter:
            waiting = asyncio.create_task(operation())
            await asyncio.sleep(0)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            self.assertEqual(entered, [])
        with self.assertRaises(RuntimeError):
            async with limiter:
                raise RuntimeError("admitted failure")
        await asyncio.wait_for(operation(), 1)
        self.assertEqual(entered, [True])
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                AsyncCapacityLimiter(value)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Test collection and both SDK transport paths at their public seams."""

    async def test_control_only_stream_and_terminal_invalidation(self):
        # [Silent Failure] Control enables streaming, and terminal observers cannot use stale handles.
        handles = []
        native = NativeTurn()

        async def ready(handle):
            # Issue real handle commands before native event collection begins.
            handles.append(handle)
            await handle.steer("feedback")
            await handle.interrupt()

        async def observe(event):
            # The terminal notification must arrive after control deactivation.
            self.assertFalse(handles[0].active)

        request = Fixture.request(CodexControlSettings(ready), CodexObservationSettings(observers=(observe,)))
        thread = Mock(id="thread", turn=AsyncMock(return_value=native))
        result = await CodexTransport()._execute_turn(thread, request, sdk_input="task", turn_kwargs={})
        self.assertEqual(result.status, "interrupted")
        self.assertTrue(native.closed)
        self.assertFalse(handles[0].active)
        control_only = replace(request, observation=CodexObservationSettings())
        with patch.object(CodexStreamRunner, "run", new_callable=AsyncMock) as stream:
            await CodexTransport()._execute_turn(thread, control_only, sdk_input="task", turn_kwargs={})
        stream.assert_awaited_once()

    async def test_readiness_failure_timeout_and_stream_failure(self):
        # [Hidden Failure] Every readiness or collection failure closes the published capability.
        handles = []

        async def failing(handle):
            # Record the capability before failing the registration callback.
            handles.append(handle)
            raise RuntimeError("callback failed")

        async def slow(handle):
            # Exceed the bounded registration wait.
            handles.append(handle)
            await asyncio.sleep(10)

        for callback in (failing, slow):
            runner = CodexStreamRunner(Fixture.request(CodexControlSettings(callback, timeout_seconds=0.01)))
            with self.assertRaises(CodexAgentError):
                await runner.collect(NativeTurn(), CodexObservation(0, "", "thread", "turn"))
            self.assertFalse(handles[-1].active)
        ready = AsyncMock()
        runner = CodexStreamRunner(Fixture.request(CodexControlSettings(ready)))
        native = NativeTurn(fail_stream=True)
        with self.assertRaises(RuntimeError):
            await runner.collect(native, CodexObservation(0, "", "thread", "turn"))
        self.assertFalse(ready.call_args.args[0].active)
        self.assertTrue(native.closed)

    async def test_low_level_public_control_methods(self):
        # [Silent Failure] The experimental tool adapter uses exact public SDK identities.
        client = Mock()
        client.turn_steer.return_value = TurnSteerResponse(turn_id="turn")
        client.turn_interrupt.return_value = TurnInterruptResponse()
        native = CodexNativeTurnStream(client, "turn", "thread")
        handle = Fixture.handle(native)
        await handle.steer("new context")
        await handle.interrupt()
        client.turn_steer.assert_called_once_with("thread", "turn", "new context")
        client.turn_interrupt.assert_called_once_with("thread", "turn")

    async def test_readiness_failure_closes_native_client(self):
        # [Hidden Failure] Readiness fails before stream opening, so the transport owns queue cleanup.
        native = NativeTurn()
        thread = Mock(id="thread", turn=AsyncMock(return_value=native))
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.thread_start.return_value = thread
        sdk = replace(CodexTransport._load_sdk(), async_codex=Mock(return_value=client))
        request = Fixture.request(CodexControlSettings(AsyncMock(side_effect=RuntimeError("failed"))))
        with patch.object(CodexTransport, "_load_sdk", return_value=sdk), self.assertRaises(CodexAgentError):
            await CodexTransport().run(request)
        client.__aexit__.assert_awaited_once()

    async def test_fork_policy_and_facade_forwarding(self):
        # [Hidden Assumption] Forks and facade turns cannot lose configured control callbacks.
        control = CodexControlSettings(AsyncMock())
        parent = CodexHarnessAgentSettings("agent", "system", control=control)
        child = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings()))
        self.assertIs(child.control, control)
        replacement = CodexControlSettings(AsyncMock())
        child = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings(control=replacement)))
        self.assertIs(child.control, replacement)
        agent = CodexHarnessAgent(parent)
        agent._transport.run = AsyncMock(return_value=CodexRunResult("thread", "turn", "completed", "answer", None, CodexUsage(), ()))
        await agent.arun(CodexRunInput.text("task"))
        self.assertIs(agent._transport.run.call_args.args[0].control, control)
        with self.assertRaises(CodexAgentError):
            CodexHarnessAgent(replace(parent, control="invalid"))


if __name__ == "__main__":
    unittest.main()
