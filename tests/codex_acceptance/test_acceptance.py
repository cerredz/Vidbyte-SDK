"""Final Codex acceptance feature pack.

PURPOSE: Prove successful publication depends on configured final evidence.
ROLE IN CODEBASE: Executable design cases for pytest and the feature script.
ARCHITECTURE NOTE: Real facade, artifact bridge, and schema validator; mocked model transport.
COMMON MODIFICATION PATTERNS: Include a rejected candidate for every new acceptance rule.
KNOWN EDGE CASES: Valid empty values differ from absent or stale artifacts.
RELATED DOCS: docs/design/codex-final-acceptance.md
TESTS: python scripts/test-codex-final-acceptance.py
"""

import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from pydantic import BaseModel

from vidbyte import (
    CodexAcceptanceRequest,
    CodexAcceptanceSettings,
    CodexHarnessAgent,
    CodexHarnessAgentSettings,
)
from vidbyte.agents.codex.acceptance import CodexAcceptanceGate
from vidbyte.agents.codex.continual import CodexContinualTraceBridge, CodexTraceUpdater
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexContinualTraceSettings,
    CodexForkRequest,
    CodexForkSettings,
    CodexMessageData,
    CodexRunInput,
    CodexRunResult,
    CodexUsage,
)
from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.lib.errors import CodexAgentError, ConfigurationError


class FinalTrace(BaseModel):
    """A final trace schema which permits legitimate empty values."""

    count: int
    active: bool
    items: list[str]


class Fixture:
    """Construct typed candidates without invoking an external model."""

    @staticmethod
    def candidate(status="completed", trace=None, fresh=False):
        # Keep native identity explicit for failure diagnostic checks.
        native = CodexMessageData("thread", "turn", status, None, CodexUsage(), (), ())
        reply = AgentMessage(sender="agent", recipient="user", content="answer", codex=native, metadata={"nested": {"value": "original"}})
        return CodexAcceptanceRequest(reply, trace, {"final_update_complete": fresh})

    @staticmethod
    def result():
        # Build the candidate returned from a mocked transport to the real facade.
        return CodexRunResult("thread", "turn", "completed", "answer", None, CodexUsage(), ())

    @staticmethod
    def trace_settings():
        # A simple actual trace producer for freshness and fork checks.
        return CodexContinualTraceSettings(TraceSchema.coerce({"summary": "Run summary"}), max_update_attempts=1)


class GateTests(unittest.IsolatedAsyncioTestCase):
    """Check acceptance polarity, immutable evidence, and failure cleanup."""

    async def test_invalid_bounds_and_requirement_types(self):
        # [Edge Case] Invalid policy cannot silently weaken the acceptance boundary.
        for timeout in (0, -1, True, float("inf"), float("nan")):
            with self.assertRaises(ConfigurationError):
                CodexAcceptanceSettings(timeout_seconds=timeout)
        for values in ({"require_trace": 1}, {"require_completed": None}, {"checks": []}, {"checks": (None,)}):
            with self.assertRaises(ConfigurationError):
                CodexAcceptanceSettings(**values)

    async def test_configuration_dependencies_reject_before_start(self):
        # [Hidden Assumption] Required artifacts need a producer and valid schema.
        for acceptance, trace in (("invalid", None), (CodexAcceptanceSettings(require_trace=True), None), (CodexAcceptanceSettings(trace_schema=FinalTrace), None), (CodexAcceptanceSettings(trace_schema=object), Fixture.trace_settings())):
            with self.assertRaises(CodexAgentError):
                CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", acceptance=acceptance, continual_trace=trace))

    async def test_interrupted_default_and_explicit_override(self):
        # [Silent Failure] Interruption is accepted only if the caller explicitly permits it.
        request = Fixture.candidate(status="interrupted")
        with self.assertRaises(CodexAgentError) as error:
            await CodexAcceptanceGate(CodexAcceptanceSettings()).accept(request)
        self.assertEqual(error.exception.failure_code, "codex.acceptance_failed")
        self.assertEqual(error.exception.safe_runtime_details["turn_id"], "turn")
        reply = await CodexAcceptanceGate(CodexAcceptanceSettings(require_completed=False)).accept(request)
        self.assertTrue(reply.metadata["acceptance"]["accepted"])

    async def test_stale_or_missing_trace_rejects(self):
        # [Hidden Failure] Earlier successful updates and forged reply metadata are insufficient.
        gate = CodexAcceptanceGate(CodexAcceptanceSettings(require_trace=True))
        for request in (Fixture.candidate(trace={"summary": "old"}), Fixture.candidate(fresh=True), Fixture.candidate(trace={}, fresh=True)):
            with self.assertRaises(CodexAgentError):
                await gate.accept(request)

    async def test_final_schema_preserves_empty_values(self):
        # [Edge Case] False, zero, and empty collections can be valid final artifacts.
        request = Fixture.candidate(trace={"count": 0, "active": False, "items": []}, fresh=True)
        reply = await CodexAcceptanceGate(CodexAcceptanceSettings(trace_schema=FinalTrace)).accept(request)
        self.assertEqual(reply.content, "answer")

    async def test_final_schema_rejects_missing_or_wrong_fields(self):
        # [Silent Failure] Native trace success cannot excuse a malformed final artifact.
        gate = CodexAcceptanceGate(CodexAcceptanceSettings(trace_schema=FinalTrace))
        for trace in ({"count": 0}, {"count": "bad", "active": False, "items": []}):
            with self.assertRaises(CodexAgentError):
                await gate.accept(Fixture.candidate(trace=trace, fresh=True))

    async def test_false_none_exception_and_timeout_reject(self):
        # [Hidden Failure] Every unsuccessful callback outcome rejects with safe diagnostics.
        for outcome in (False, None, 1, RuntimeError("private check content")):
            check = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
            with self.assertRaises(CodexAgentError) as error:
                await CodexAcceptanceGate(CodexAcceptanceSettings(checks=(check,))).accept(Fixture.candidate())
            self.assertNotIn("private", str(error.exception))

        async def slow(request):
            # Exceed the configured callback limit using cooperative waiting.
            await asyncio.sleep(10)
            return True

        with self.assertRaises(CodexAgentError) as error:
            await CodexAcceptanceGate(CodexAcceptanceSettings(checks=(slow,), timeout_seconds=0.01)).accept(Fixture.candidate())
        self.assertEqual(error.exception.safe_runtime_details["error_type"], "TimeoutError")

    async def test_checks_receive_isolated_snapshots(self):
        # [Hidden Assumption] One check cannot mutate another check's evidence or the published reply.
        request = Fixture.candidate(trace={"summary": "actual"}, fresh=True)

        async def mutate(candidate):
            # Attempt to alter nested evidence to expose accidental shared references.
            candidate.reply.metadata["nested"]["value"] = "forged"
            candidate.trace["summary"] = "forged"
            return True

        async def verify(candidate):
            # A later check must still see the original candidate state.
            self.assertEqual(candidate.reply.metadata["nested"]["value"], "original")
            self.assertEqual(candidate.trace["summary"], "actual")
            return True

        reply = await CodexAcceptanceGate(CodexAcceptanceSettings(checks=(mutate, verify))).accept(request)
        self.assertEqual(reply.metadata["nested"]["value"], "original")
        self.assertEqual(reply.metadata["acceptance"]["check_count"], 2)

    async def test_cancellation_propagates(self):
        # [Hidden Failure] Cancellation cannot be converted into success or a provider error.
        check = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await CodexAcceptanceGate(CodexAcceptanceSettings(checks=(check,))).accept(Fixture.candidate())


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise publication and actual artifact scheduling through existing collaborators."""

    async def test_acceptance_precedes_history_publication(self):
        # [Silent Failure] The facade commits only after its application check completes.
        async def check(candidate):
            # Observe facade state while the candidate is still pending acceptance.
            self.assertEqual(agent.history, [])
            self.assertIsNone(agent.last_reply)
            await asyncio.sleep(0)
            return True

        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", acceptance=CodexAcceptanceSettings(checks=(check,))))
        agent._transport.run = AsyncMock(return_value=Fixture.result())
        reply = await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(agent.history, [reply])
        self.assertIs(agent.last_reply, reply)
        self.assertTrue(reply.metadata["acceptance"]["accepted"])

    async def test_rejection_retains_native_identity_not_reply(self):
        # [Hidden Failure] Rejecting a later candidate preserves the last accepted reply.
        check = AsyncMock(side_effect=[True, False])
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", acceptance=CodexAcceptanceSettings(checks=(check,))))
        agent._transport.run = AsyncMock(return_value=Fixture.result())
        first = await agent.arun(CodexRunInput.text("first"))
        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text("second"))
        self.assertEqual(agent.thread_id, "thread")
        self.assertEqual(agent.history, [first])
        self.assertIs(agent.last_reply, first)
        self.assertIsNotNone(agent.get_usage())

    async def test_real_final_trace_freshness(self):
        # [Silent Failure] Actual bridge state distinguishes final success from earlier-only success.
        bridge = CodexContinualTraceBridge(Fixture.trace_settings(), CodexAgentSettings())
        bridge.updater.update = AsyncMock(return_value={"summary": "first"})
        await bridge.update()
        self.assertFalse(bridge.metadata()["final_update_complete"])
        bridge.seen.add("later-item")
        bridge.updater.update.side_effect = RuntimeError("update failed")
        await bridge.finalize()
        self.assertFalse(bridge.metadata()["final_update_complete"])
        empty = CodexContinualTraceBridge(Fixture.trace_settings(), CodexAgentSettings())
        empty.updater.update = AsyncMock(return_value={"summary": "empty run"})
        await empty.finalize()
        self.assertTrue(empty.metadata()["final_update_complete"])

    async def test_facade_uses_producer_receipt(self):
        # [Hidden Assumption] Input metadata cannot forge a required final trace receipt.
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", acceptance=CodexAcceptanceSettings(require_trace=True), continual_trace=Fixture.trace_settings()))
        agent._transport.run = AsyncMock(return_value=Fixture.result())
        with patch.object(CodexTraceUpdater, "update", new_callable=AsyncMock, side_effect=RuntimeError("failed")), self.assertRaises(CodexAgentError):
            await agent.arun(replace(CodexRunInput.text("task"), metadata={"trace": {"summary": "fake"}, "trace_metadata": {"final_update_complete": True}}))
        self.assertEqual(agent.history, [])

    async def test_fork_inheritance_replacement_and_dependency(self):
        # [Hidden Assumption] Clearing a required producer cannot weaken inherited acceptance silently.
        acceptance = CodexAcceptanceSettings(require_trace=True)
        parent = CodexHarnessAgentSettings("agent", "system", acceptance=acceptance, continual_trace=Fixture.trace_settings())
        inherited = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings()))
        self.assertIs(inherited.acceptance, acceptance)
        disabled = CodexAcceptanceSettings(require_completed=False)
        child = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings(acceptance=disabled, clear_continual_trace=True)))
        self.assertIs(child.acceptance, disabled)
        transport = Mock()
        with self.assertRaises(CodexAgentError):
            await CodexFork(transport).afork(CodexForkRequest(parent, "thread", CodexForkSettings(clear_continual_trace=True)))
        transport.fork_thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
