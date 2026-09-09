"""Codex observed trajectory export acceptance pack.

PURPOSE: Prove explicit export scope, redaction, and required sink acknowledgment.
ROLE IN CODEBASE: Executable design cases for pytest and the verification script.
ARCHITECTURE NOTE: Real shared sinks and facade; native model execution is mocked.
COMMON MODIFICATION PATTERNS: Add both a redacted record and failed-write case per field.
KNOWN EDGE CASES: A timed-out write may have persisted; never automatically retry it.
RELATED DOCS: docs/design/codex-trajectory-capture.md
TESTS: python scripts/test-codex-trajectory-capture.py
"""

import asyncio
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from vidbyte import CodexAcceptanceSettings, CodexCaptureSettings, CodexHarnessAgent, CodexHarnessAgentSettings
from vidbyte.agents.codex.capture import CodexTrajectoryCapture
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.types import AgentMessage
from vidbyte.harnesses.stores.file import FileTrajectorySink
from vidbyte.harnesses.stores.memory import InMemoryTrajectorySink
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexClientSettings, CodexForkRequest, CodexForkSettings, CodexItem, CodexMessageData, CodexObservation, CodexObservationSettings, CodexRunInput, CodexRunResult, CodexUsage
from vidbyte.lib.errors import CodexAgentError, ConfigurationError, OutputSchemaViolationError


class Fixture:
    """Typed reviewed native evidence for storage and facade verification."""

    @staticmethod
    def reply():
        # Preserve legitimate empty values and common secret patterns for redaction checks.
        native = CodexMessageData("thread", "turn", "completed", None, CodexUsage(), (), ())
        return AgentMessage(sender="agent", recipient="user", content="answer", codex=native, metadata={"trace": {"summary": "done"}, "values": [0, False, "", " "], "api_key": "must-drop"})

    @staticmethod
    def result(text="answer"):
        # Return a reviewed native result without any hidden model fields.
        return CodexRunResult("thread", "turn", "completed", text, None, CodexUsage(), ())

    @staticmethod
    def event(index):
        # Produce mutable nested fields to test snapshot isolation.
        return CodexObservation(index, "item/completed", "thread", "turn", CodexItem(str(index), "agentMessage", {"text": "password=do-not-export", "nested": [index]}))

    @staticmethod
    def agent(sink, **kwargs):
        # Enable capture on a real facade with deterministic native output.
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", capture=CodexCaptureSettings(sink, **kwargs)))
        agent._transport.run = AsyncMock(return_value=Fixture.result())
        return agent


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    """Per-run export invariants using the existing trajectory interfaces."""

    def capture(self, sink=None, **kwargs):
        # Build independent capture state without constructing a native process.
        return CodexTrajectoryCapture(CodexCaptureSettings(sink or InMemoryTrajectorySink(), **kwargs), CodexHarnessAgentSettings("agent", "system"), CodexRunInput.text("task"))

    async def test_invalid_settings(self):
        # [Edge Case] Invalid collaborators and bounds reject before execution.
        for values in ({"required": 1}, {"max_observations": 0}, {"max_observations": True}, {"max_observations": 1.5}, {"timeout_seconds": 0}, {"timeout_seconds": True}, {"timeout_seconds": float("inf")}, {"timeout_seconds": float("nan")}, {"redactor": "invalid"}):
            with self.assertRaises(ConfigurationError):
                CodexCaptureSettings(InMemoryTrajectorySink(), **values)
        for capture in ("invalid", CodexCaptureSettings(object())):
            with self.assertRaises(CodexAgentError):
                CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", capture=capture))

    async def test_record_scope_and_empty_values(self):
        # [Silent Failure] Shared records state observed scope and never invent rewards or steps.
        sink = InMemoryTrajectorySink()
        capture = self.capture(sink)
        reply = await capture.finish(Fixture.reply())
        record = sink.records()[0]
        self.assertIsNone(record.reward)
        self.assertEqual(record.agents[0]["thread_id"], "thread")
        self.assertEqual(record.agents[0]["turn_id"], "turn")
        self.assertEqual(record.agents[0]["capture_scope"], "reviewed_native_events")
        self.assertIn("hidden_reasoning", record.agents[0]["unavailable"])
        self.assertEqual(record.agents[0]["observations"], [])
        self.assertEqual(record.output["metadata"]["values"], [0, False, "", " "])
        self.assertTrue(reply.metadata["capture"]["saved"])
        self.assertEqual(record.run_id, reply.metadata["capture"]["run_id"])

    async def test_window_bound_and_snapshot_isolation(self):
        # [Hidden Failure] Truncation is visible and later caller mutation cannot rewrite evidence.
        sink = InMemoryTrajectorySink()
        capture = self.capture(sink, max_observations=2)
        for index in range(3):
            event = Fixture.event(index)
            await capture.observe(event)
            event.item.fields["nested"].append("mutated")
        await capture.finish(Fixture.reply())
        evidence = sink.records()[0].agents[0]
        self.assertEqual(evidence["observed_event_count"], 3)
        self.assertEqual(evidence["dropped_event_count"], 1)
        self.assertEqual([item["sequence"] for item in evidence["observations"]], [1, 2])
        self.assertNotIn("mutated", str(evidence))

    async def test_process_secrets_and_text_are_redacted(self):
        # [Hidden Assumption] Never traverse process env/config; scrub keys and common text secrets.
        sink = InMemoryTrajectorySink()
        settings = CodexCaptureSettings(sink)
        codex = CodexAgentSettings(client=CodexClientSettings(env={"CUSTOM": "process-secret"}, config_overrides=("opaque=process-secret",)))
        parent = CodexHarnessAgentSettings("agent", "password=instruction-secret", codex=codex)
        capture = CodexTrajectoryCapture(settings, parent, CodexRunInput.text("token=task-secret"))
        await capture.observe(Fixture.event(1))
        await capture.finish(Fixture.reply())
        text = json.dumps(asdict(sink.records()[0]))
        for secret in ("process-secret", "instruction-secret", "task-secret", "do-not-export", "must-drop"):
            self.assertNotIn(secret, text)
        self.assertIn("<redacted>", text)

    async def test_custom_redactor_cannot_bypass_baseline(self):
        # [Hidden Failure] Tenant output still passes mandatory baseline scrubbing.
        sink = InMemoryTrajectorySink()

        def redactor(value):
            # Deliberately add credentials to prove baseline redaction runs afterward.
            return {"api_key": "tenant-secret", "text": "password=tenant-text", "empty": ""}

        capture = self.capture(sink, redactor=redactor)
        await capture.finish(Fixture.reply())
        text = json.dumps(asdict(sink.records()[0]))
        self.assertNotIn("tenant-secret", text)
        self.assertNotIn("tenant-text", text)
        self.assertEqual(sink.records()[0].output["empty"], "")

    async def test_required_optional_failure_and_no_duplicate_attempt(self):
        # [Hidden Failure] Unacknowledged writes never look saved or trigger a second write.
        for required in (True, False):
            sink = Mock(write=AsyncMock(side_effect=RuntimeError("private sink details")))
            capture = self.capture(sink, required=required)
            if required:
                with self.assertRaises(CodexAgentError) as error:
                    await capture.finish(Fixture.reply())
                self.assertNotIn("private", str(error.exception))
            else:
                reply = await capture.finish(Fixture.reply())
                self.assertFalse(reply.metadata["capture"]["saved"])
            await capture.failed(RuntimeError("secondary"))
            sink.write.assert_awaited_once()

    async def test_sink_timeout_is_unacknowledged(self):
        # [Hidden Failure] A write timeout does not promise storage rollback or acknowledgment.
        async def slow(record):
            # Exceed the configured storage wait while preserving cooperative cancellation.
            await asyncio.sleep(10)

        capture = self.capture(Mock(write=AsyncMock(side_effect=slow)), required=False, timeout_seconds=0.01)
        reply = await capture.finish(Fixture.reply())
        self.assertFalse(reply.metadata["capture"]["saved"])
        self.assertEqual(reply.metadata["capture"]["error_type"], "TimeoutError")

    async def test_new_cancellation_during_diagnostic_export_propagates(self):
        # [Hidden Failure] A fresh cancellation cannot be swallowed by best-effort recording.
        sink = Mock(write=AsyncMock(side_effect=asyncio.CancelledError()))
        capture = self.capture(sink)
        with self.assertRaises(asyncio.CancelledError):
            await capture.failed(RuntimeError("original failure"))
        self.assertFalse(capture.receipt()["saved"])

    async def test_real_file_sink_jsonl(self):
        # [Silent Failure] The existing file sink produces a readable shared record.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            capture = self.capture(FileTrajectorySink(path))
            await capture.finish(Fixture.reply())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["run_id"], capture.run_id)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Facade ordering and failure capture with real shared sinks."""

    async def test_capture_before_publication_and_observation_forwarding(self):
        # [Silent Failure] Required storage runs before accepted reply publication.
        records = []

        async def write(record):
            # Storage sees a pending candidate, never an already committed reply.
            self.assertEqual(agent.history, [])
            self.assertIsNone(agent.last_reply)
            records.append(record)

        agent = Fixture.agent(Mock(write=AsyncMock(side_effect=write)))

        async def native(request):
            # Exercise the real capture observer attached to the transport request.
            self.assertTrue(request.observation.enabled)
            await request.observation.observers[-1](Fixture.event(1))
            return Fixture.result()

        agent._transport.run.side_effect = native
        reply = await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(len(records[0].agents[0]["observations"]), 1)
        self.assertIs(agent.last_reply, reply)
        self.assertTrue(agent.last_capture["saved"])
        self.assertEqual(agent.history, [reply])

    async def test_required_failure_preserves_prior_reply(self):
        # [Hidden Failure] Failed capture cannot publish its candidate or repeat storage writes.
        sink = Mock(write=AsyncMock(side_effect=[None, RuntimeError("sink failed")]))
        agent = Fixture.agent(sink)
        first = await agent.arun(CodexRunInput.text("first"))
        with self.assertRaises(CodexAgentError) as error:
            await agent.arun(CodexRunInput.text("second"))
        self.assertEqual(error.exception.failure_code, "codex.capture_failed")
        self.assertEqual(agent.history, [first])
        self.assertIs(agent.last_reply, first)
        self.assertFalse(agent.last_capture["saved"])
        self.assertEqual(sink.write.await_count, 2)

    async def test_event_retained_before_downstream_observer_failure(self):
        # [Hidden Failure] A failed application observer cannot erase the event that triggered it.
        sink = InMemoryTrajectorySink()
        failing = AsyncMock(side_effect=RuntimeError("observer failed"))
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", capture=CodexCaptureSettings(sink), observation=CodexObservationSettings(observers=(failing,))))

        async def native(request):
            # Deliver the reviewed native event in the actual configured callback order.
            for observer in request.observation.observers:
                await observer(Fixture.event(1))

        agent._transport.run = AsyncMock(side_effect=native)
        with self.assertRaises(RuntimeError):
            await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(sink.records()[0].agents[0]["observed_event_count"], 1)
        self.assertEqual(sink.records()[0].agents[0]["turn_id"], "turn")

    async def test_primary_failure_and_cancellation_survive_sink_error(self):
        # [Hidden Assumption] Diagnostic export failure cannot replace native failure or cancellation.
        for original in (RuntimeError("native failure"), asyncio.CancelledError()):
            sink = Mock(write=AsyncMock(side_effect=RuntimeError("sink failed")))
            agent = Fixture.agent(sink)
            agent._transport.run.side_effect = original
            with self.assertRaises(type(original)) as error:
                await agent.arun(CodexRunInput.text("task"))
            self.assertIs(error.exception, original)
            sink.write.assert_awaited_once()
            self.assertEqual(agent.history, [])

    async def test_acceptance_and_output_validation_failures_are_exported(self):
        # [Hidden Failure] Failed application/output validation still retains the actual native candidate.
        sink = InMemoryTrajectorySink()
        acceptance = CodexAcceptanceSettings(checks=(AsyncMock(return_value=False),))
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", capture=CodexCaptureSettings(sink), acceptance=acceptance))
        agent._transport.run = AsyncMock(return_value=Fixture.result())
        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(sink.records()[0].status, "failed")
        self.assertEqual(sink.records()[0].output["content"], "answer")
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", capture=CodexCaptureSettings(sink), output_schema={"type": "object"}))
        agent._transport.run = AsyncMock(return_value=Fixture.result("not-json"))
        with self.assertRaises(OutputSchemaViolationError):
            await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(sink.records()[1].output["final_response"], "not-json")
        self.assertEqual(sink.records()[1].agents[0]["turn_id"], "turn")

    async def test_fork_inheritance_and_run_isolation(self):
        # [Hidden Assumption] Shared sinks cannot cause shared run identity or observation state.
        sink = InMemoryTrajectorySink()
        agent = Fixture.agent(sink)
        inherited = CodexFork._prepare_child(CodexForkRequest(agent.settings, "thread", CodexForkSettings()))
        self.assertIs(inherited.capture, agent.settings.capture)
        replacement = CodexCaptureSettings(InMemoryTrajectorySink())
        child = CodexFork._prepare_child(CodexForkRequest(agent.settings, "thread", CodexForkSettings(capture=replacement)))
        self.assertIs(child.capture, replacement)
        await agent.arun(CodexRunInput.text("first"))
        await agent.arun(CodexRunInput.text("second"))
        self.assertNotEqual(sink.records()[0].run_id, sink.records()[1].run_id)
        ordinary = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system"))
        ordinary._transport.run = AsyncMock(return_value=Fixture.result())
        reply = await ordinary.arun(CodexRunInput.text("task"))
        self.assertNotIn("capture", reply.metadata)
        self.assertIsNone(ordinary.last_capture)


if __name__ == "__main__":
    unittest.main()
