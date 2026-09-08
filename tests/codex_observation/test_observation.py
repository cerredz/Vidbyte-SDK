"""FILE: tests/codex_observation/test_observation.py
PURPOSE: Proves native streaming contracts with real SDK models and offline transport.
ROLE IN CODEBASE: Executed by pytest and the feature verification script.
TESTS: Each named test corresponds to a design Section 10 failure category.

COMMON MODIFICATION PATTERNS: Extend the native event contract with a matching acceptance case.
RELATED DOCS: docs/design/codex-live-observation.md
ARCHITECTURE NOTE: Real native models with an offline stream seam.
KNOWN EDGE CASES: Optional SDK is required to execute this pack.
"""

import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("openai_codex")
from openai_codex.generated.v2_all import ItemCompletedNotification, ItemStartedNotification, ThreadItem, ThreadTokenUsageUpdatedNotification, Turn, TurnCompletedNotification
from openai_codex.models import Notification

from vidbyte import CodexObservationSettings, Trace
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.observation import CodexTraceBridge
from vidbyte.agents.codex.stream import CodexStreamRunner
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexForkRequest, CodexForkSettings, CodexHarnessAgentSettings, CodexObservation, CodexPrompt, CodexTextInput, CodexTransportRunRequest
from vidbyte.lib.errors import ConfigurationError


class NativeFixture:
    """Creates genuine public native event models, never reflection-based fakes."""

    @staticmethod
    def message(text="answer", phase="final_answer"):
        # Build an actual completed native message for collector parity checks.
        item = ThreadItem.model_validate(dict(id=text, type="agentMessage", text=text, phase=phase))
        return Notification("item/completed", ItemCompletedNotification(completed_at_ms=1, thread_id="thread", turn_id="turn", item=item))

    @staticmethod
    def terminal(status="completed"):
        # Create completed or interrupted native terminal state without invented text.
        return Notification("turn/completed", TurnCompletedNotification(thread_id="thread", turn=Turn(id="turn", items=[], status=status)))

    @staticmethod
    def request(settings):
        # Supply a valid public transport request using caller-owned observers.
        prompt = CodexPrompt((CodexTextInput("hello"),), "hello", "user", {})
        return CodexTransportRunRequest("", "system", prompt, CodexAgentSettings(), {}, settings)

    @staticmethod
    def tool(method="item/started"):
        # Build command events with mandatory native fields fully validated.
        item = ThreadItem.model_validate(dict(id="cmd", type="commandExecution", command="echo hello", cwd="C:/tmp", commandActions=[], status="inProgress", source="agent"))
        kind = ItemStartedNotification if method == "item/started" else ItemCompletedNotification
        return Notification(method, kind.model_validate(dict(threadId="thread", turnId="turn", item=item, startedAtMs=0, completedAtMs=1)))


class NativeTurn:
    """Models SDK stream ownership and exposes cleanup for assertions."""

    id = "turn"

    def __init__(self, events):
        # Retain scripted events and record whether the native stream was closed.
        self.events = events
        self.closed = False

    async def stream(self):
        # Yield once in order and expose unwinding even on observer failure.
        try:
            for event in self.events:
                yield event
        finally:
            self.closed = True


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    """Behavioral tests exercised both directly and through the script runner."""

    async def execute(self, events, settings=None):
        # Construct the native turn seam without mocking observation collaborators.
        self.turn = NativeTurn(events)
        self.thread = AsyncMock(id="thread")
        self.thread.turn.return_value = self.turn
        runner = CodexStreamRunner(NativeFixture.request(settings or CodexObservationSettings()))
        return await runner.run(self.thread, "hello", kwargs={})

    async def test_ordered_callbacks_and_final_phase(self):
        # [Silent Failure] Await callbacks and preserve explicit final-answer priority.
        observations = []

        async def observe(value):
            # Finish asynchronous work before recording the next delivered event.
            await asyncio.sleep(0)
            observations.append(value)

        result = await self.execute([NativeFixture.message(), NativeFixture.message("commentary", "commentary"), NativeFixture.terminal()], CodexObservationSettings(observers=(observe,)))
        self.assertEqual(result.final_response, "answer")
        self.assertEqual([value.sequence for value in observations], [1, 2, 3])
        self.assertEqual(observations[0].item.fields["text"], "answer")
        self.assertFalse(result.usage_available)
        self.assertTrue(self.turn.closed)

    async def test_empty_and_failed_stream(self):
        # [Edge Case] Missing terminal events and failed turns never look successful.
        for events in ([], [NativeFixture.terminal("failed")]):
            with self.assertRaises(ValueError):
                await self.execute(events)
            self.assertTrue(self.turn.closed)

    async def test_interrupted_without_text(self):
        # [Edge Case] Interruption preserves absent timing and response values.
        result = await self.execute([NativeFixture.terminal("interrupted")])
        self.assertIsNone(result.final_response)
        self.assertIsNone(result.duration_ms)

    async def test_wrong_identity(self):
        # [Hidden Assumption] Cross-thread and cross-turn payloads must be rejected.
        for field in ("thread_id", "turn_id"):
            event = NativeFixture.message()
            setattr(event.payload, field, "foreign")
            with self.assertRaises(ValueError):
                await self.execute([event, NativeFixture.terminal()])

    async def test_wrong_terminal_identity(self):
        # [Hidden Assumption] A completion from another run cannot finalize this one.
        event = NativeFixture.terminal()
        event.payload.turn.id = "foreign"
        with self.assertRaises(ValueError):
            await self.execute([NativeFixture.message(), event])

    async def test_observer_snapshots_are_isolated(self):
        # [Silent Failure] One callback cannot corrupt the result or another observer.
        seen = []

        async def mutate(value):
            # Deliberately mutate nested item fields to exercise isolation.
            if value.item is not None:
                value.item.fields["text"] = "corrupted"

        async def record(value):
            # Record the second callback's independently copied view.
            seen.append(value)

        result = await self.execute([NativeFixture.message(), NativeFixture.terminal()], CodexObservationSettings(observers=(mutate, record)))
        self.assertEqual(seen[0].item.fields["text"], "answer")
        self.assertEqual(result.final_response, "answer")

    async def test_profile_tracer_parentage(self):
        # [Hidden Failure] Semantic profiles retain the explicit native tool parent.
        events = []
        tracer = Trace.profile(Trace.debug(events))
        await self.execute([NativeFixture.tool(), NativeFixture.tool("item/completed"), NativeFixture.message(), NativeFixture.terminal()], CodexObservationSettings(tracer))
        self.assertIs(events[1]["parent"], events[0]["context"])
        self.assertEqual([event["name"] for event in events if event["name"]], ["agent.run", "tool.call"])

    async def test_observer_failure_and_cancellation(self):
        # [Hidden Failure] Callback failure closes native and tracing lifecycles.
        for failure in (ValueError("sensitive"), asyncio.CancelledError()):
            trace_events = []

            async def observe(value):
                # Fail after the native tool started to test cleanup of open spans.
                raise failure

            with self.assertRaises(type(failure)):
                await self.execute([NativeFixture.tool()], CodexObservationSettings(Trace.debug(trace_events), (observe,)))
            self.assertTrue(self.turn.closed)
            self.assertEqual([value["type"] for value in trace_events], ["start_trace", "start_span", "end_span", "end_trace"])
            self.assertNotIn("sensitive", str(trace_events))

    async def test_synchronous_observer_rejected(self):
        # [Hidden Assumption] Callability alone does not establish async completion.
        with self.assertRaises(TypeError):
            await self.execute([NativeFixture.message()], CodexObservationSettings(observers=(lambda value: None,)))

    async def test_reasoning_and_unknown_payload_exclusion(self):
        # [Silent Failure] Unreviewed and private content never reaches observers.
        seen = []

        async def observe(value):
            # Retain only the translator output, as a caller would.
            seen.append(value)

        item = ThreadItem.model_validate(dict(id="r", type="reasoning", content=["private"], summary=["public"]))
        reasoning = Notification("item/completed", ItemCompletedNotification(completed_at_ms=1, thread_id="thread", turn_id="turn", item=item))
        unknown = Notification("future/event", {"content": "private"})
        await self.execute([reasoning, unknown, NativeFixture.terminal("interrupted")], CodexObservationSettings(observers=(observe,)))
        self.assertNotIn("content", seen[0].item.fields)
        self.assertIsNone(seen[1].item)
        self.assertNotIn("private", str(seen))

    async def test_zero_usage_available(self):
        # [Edge Case] Explicit zero native usage differs from absent usage.
        counts = dict(inputTokens=0, outputTokens=0, totalTokens=0, cachedInputTokens=0, reasoningOutputTokens=0)
        usage = ThreadTokenUsageUpdatedNotification.model_validate(dict(threadId="thread", turnId="turn", tokenUsage=dict(last=counts, total=counts)))
        result = await self.execute([Notification("thread/tokenUsage/updated", usage), NativeFixture.message(), NativeFixture.terminal()])
        self.assertTrue(result.usage_available)
        self.assertEqual(result.usage.total_tokens, 0)

    async def test_duplicate_start_and_unmatched_completion(self):
        # [Hidden Assumption] Repeated native events do not leak or invent spans.
        events = []
        await self.execute([NativeFixture.tool("item/completed"), NativeFixture.tool(), NativeFixture.tool(), NativeFixture.tool("item/completed"), NativeFixture.message(), NativeFixture.terminal()], CodexObservationSettings(Trace.debug(events)))
        self.assertEqual([value["type"] for value in events].count("start_span"), 1)
        self.assertEqual([value["type"] for value in events].count("end_span"), 1)

    def test_broken_tracer_fails_open(self):
        # [Hidden Failure] Tracing transport errors do not replace execution outcomes.
        tracer = Trace.debug()
        bridge = CodexTraceBridge(CodexObservationSettings(tracer))
        with patch.object(tracer, "start_trace", side_effect=RuntimeError("offline")):
            bridge.start(CodexObservation(0, "", "thread", "turn"))
        bridge.finish(None)
        self.assertEqual(bridge.error_count, 1)

    def test_invalid_settings(self):
        # [Edge Case] Malformed public configuration fails before native execution.
        for kwargs in (dict(tracer=None), dict(observers=[]), dict(observers=(None,))):
            with self.assertRaises(ConfigurationError):
                CodexObservationSettings(**kwargs)
        with self.assertRaises(ConfigurationError):
            CodexHarnessAgentSettings("agent", "system", observation=None)

    def test_fork_inherit_replace_disable(self):
        # [Hidden Assumption] Fork construction retains explicit observation policy.
        original = CodexObservationSettings(Trace.debug())
        parent = CodexHarnessAgentSettings("agent", "system", observation=original)
        for override in (None, CodexObservationSettings(), CodexObservationSettings(Trace.debug())):
            child = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings(observation=override)))
            self.assertIs(child.observation, original if override is None else override)

    async def test_transport_selects_stream(self):
        # [Hidden Assumption] Public transport invokes the native streaming collaborator.
        request = NativeFixture.request(CodexObservationSettings(Trace.debug()))
        transport = CodexTransport()
        sdk = transport._load_sdk()
        client_factory = unittest.mock.MagicMock()
        client_factory.return_value.__aenter__ = AsyncMock()
        client_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        native = AsyncMock(id="thread")
        native.turn.return_value = NativeTurn([NativeFixture.message(), NativeFixture.terminal()])
        with patch.object(transport, "_load_sdk", return_value=replace(sdk, async_codex=client_factory)), patch.object(transport, "_open_thread", return_value=native):
            result = await transport.run(request)
        self.assertEqual(result.final_response, "answer")
        native.turn.assert_awaited_once()
        native.run.assert_not_called()
