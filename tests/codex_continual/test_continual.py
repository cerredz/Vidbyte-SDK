"""FILE: tests/codex_continual/test_continual.py
PURPOSE: Proves deterministic continual artifacts and native update constraints.
ROLE IN CODEBASE: Feature acceptance pack and script-verification source.
ARCHITECTURE NOTE: Real UpdateTraceTool, mocked native transport only.
COMMON MODIFICATION PATTERNS: Pair every new scheduler rule with a failure case.
KNOWN EDGE CASES: A failed schema patch must never partially update the artifact.
RELATED DOCS: docs/design/codex-continual-artifacts.md
TESTS: python scripts/test-codex-continual-artifacts.py
"""

import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from vidbyte import CodexContinualTraceSettings, CodexHarnessAgent, CodexHarnessAgentSettings
from vidbyte.agents.codex.continual import CodexContinualTraceBridge, CodexTraceUpdater
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexForkRequest, CodexForkSettings, CodexItem, CodexObservation, CodexRunInput, CodexRunResult, CodexTraceUpdateRequest, CodexUsage
from vidbyte.lib.dataclasses.trace import TraceField, TraceFieldType, TraceSchema
from vidbyte.lib.enums.codex import CodexApprovalMode, CodexSandbox
from vidbyte.lib.errors import ConfigurationError


class ContinualFixture:
    """Shared genuine schema and native-result fixtures."""

    @staticmethod
    def schema():
        # Include every merge category plus nested validation.
        return TraceSchema("work", {"steps": TraceField(description="Steps", type=TraceFieldType.ARRAY), "state": TraceField(description="State", type=TraceFieldType.OBJECT, fields={"count": TraceField(description="Count", type=TraceFieldType.INTEGER)}), "summary": TraceField(description="Summary")})

    @staticmethod
    def event(index):
        # Model distinct completed item identifiers for scheduling.
        return CodexObservation(index, "item/completed", "thread", "turn", CodexItem(str(index), "agentMessage", {"text": str(index)}))

    @staticmethod
    def result(text='{"trace":{"summary":"done"}}'):
        # Supply a normal typed native result without invented usage.
        return CodexRunResult("thread", "turn", "completed", text, None, CodexUsage(), ())


class ContinualTests(unittest.IsolatedAsyncioTestCase):
    """Named cases cover every design testing category."""

    def bridge(self, **kwargs):
        # Build real scheduler state with a controlled updater response.
        bridge = CodexContinualTraceBridge(CodexContinualTraceSettings(ContinualFixture.schema(), **kwargs), CodexAgentSettings())
        bridge.updater.update = AsyncMock(return_value={"summary": "done"})
        return bridge

    def test_invalid_configuration(self):
        # [Edge Case] Bounds reject booleans, nonfinite values, and invalid types.
        for name in ("every_n_completed_items", "max_update_attempts", "max_observations"):
            for value in (0, -1, True, 1.5):
                with self.assertRaises(ConfigurationError):
                    self.bridge(**{name: value})
        for value in (0, -1, True, float("inf"), float("nan")):
            with self.assertRaises(ConfigurationError):
                self.bridge(timeout_seconds=value)
        with self.assertRaises(ConfigurationError):
            self.bridge(max_update_attempts=4)

    async def test_cadence_duplicate_and_finalization(self):
        # [Edge Case] Exact intervals finalize once and duplicates do not advance count.
        bridge = self.bridge(every_n_completed_items=2)
        await bridge.observe(ContinualFixture.event(1))
        await bridge.observe(ContinualFixture.event(1))
        bridge.updater.update.assert_not_awaited()
        await bridge.observe(ContinualFixture.event(2))
        await bridge.finalize()
        await bridge.finalize()
        bridge.updater.update.assert_awaited_once()
        self.assertEqual(bridge.metadata()["completed_item_count"], 2)

    async def test_empty_finalization(self):
        # [Edge Case] A run with no completed items still gets one final trace attempt.
        bridge = self.bridge()
        await bridge.finalize()
        await bridge.finalize()
        bridge.updater.update.assert_awaited_once()

    async def test_window_truncation(self):
        # [Silent Failure] Bounded evidence loss is explicit in diagnostics.
        bridge = self.bridge(max_observations=1)
        await bridge.observe(ContinualFixture.event(1))
        await bridge.observe(ContinualFixture.event(2))
        await bridge.finalize()
        request = bridge.updater.update.call_args.args[0]
        self.assertEqual([item.item.id for item in request.observations], ["2"])
        self.assertEqual(bridge.metadata()["truncated_observation_count"], 1)

    async def test_real_merge_and_schema_rejection(self):
        # [Silent Failure] Existing array dedupe and shallow merge remain authoritative.
        bridge = self.bridge(max_update_attempts=1)
        bridge.updater.update.side_effect = [{"steps": [1], "state": {"count": 1}, "summary": "first"}, {"steps": [1, 2], "state": {"count": 2}, "summary": "second"}, {"state": {"count": "wrong"}, "summary": "must not commit"}]
        await bridge.update()
        await bridge.update()
        await bridge.update()
        self.assertEqual(bridge.artifact(), {"steps": [1, 2], "state": {"count": 2}, "summary": "second"})
        self.assertEqual(bridge.error_count, 1)

    async def test_failure_and_timeout_preserve_artifact(self):
        # [Hidden Failure] Native failure and timeout retain the previous accepted state.
        bridge = self.bridge(max_update_attempts=1, timeout_seconds=0.001)
        await bridge.update()
        before = bridge.artifact()
        bridge.updater.update.side_effect = RuntimeError("credential secret")
        await bridge.update()
        self.assertEqual(bridge.artifact(), before)
        self.assertEqual(bridge.last_error, "RuntimeError")

        async def slow(request):
            # Exceed the configured bound without making any external request.
            await asyncio.sleep(1)

        bridge.updater.update.side_effect = slow
        await bridge.update()
        self.assertEqual(bridge.last_error, "TimeoutError")
        self.assertNotIn("secret", str(bridge.metadata()))

    async def test_cancellation_propagates(self):
        # [Hidden Assumption] Caller cancellation is never converted to a trace failure.
        bridge = self.bridge()
        bridge.updater.update.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await bridge.update()
        self.assertEqual(bridge.error_count, 0)

    async def test_native_request_contract(self):
        # [Hidden Assumption] Native update retains authentication and model settings.
        settings = CodexAgentSettings()
        settings = replace(settings, turn=replace(settings.turn, model="test-model"))
        request = CodexTraceUpdateRequest(settings, ContinualFixture.schema(), {}, ())
        with patch("vidbyte.agents.codex.continual.CodexTransport.run", new_callable=AsyncMock, return_value=ContinualFixture.result()) as run:
            result = await CodexTraceUpdater().update(request)
        native = run.call_args.args[0]
        self.assertEqual(result, {"summary": "done"})
        self.assertIs(native.settings.client, settings.client)
        self.assertEqual(native.settings.turn.model, "test-model")
        self.assertEqual(native.settings.turn.sandbox, CodexSandbox.READ_ONLY)
        self.assertEqual(native.settings.thread.approval_mode, CodexApprovalMode.DENY_ALL)
        self.assertFalse(native.settings.subagents.enabled)
        self.assertFalse(native.observation.enabled)
        self.assertEqual(native.thread_id, "")
        self.assertIn("trace", native.output_schema["properties"])

    async def test_native_malformed_json(self):
        # [Hidden Failure] Native completed text still needs a valid trace envelope.
        request = CodexTraceUpdateRequest(CodexAgentSettings(), ContinualFixture.schema(), {}, ())
        for text in ("invalid", "null", '{"trace":null}', "[]"):
            with patch("vidbyte.agents.codex.continual.CodexTransport.run", new_callable=AsyncMock, return_value=ContinualFixture.result(text)), self.assertRaises(ValueError):
                await CodexTraceUpdater().update(request)

    async def test_agent_publishes_isolated_artifacts(self):
        # [Hidden Failure] Each real facade invocation gets fresh trace state.
        config = CodexContinualTraceSettings(ContinualFixture.schema())
        agent = CodexHarnessAgent(CodexHarnessAgentSettings("agent", "system", continual_trace=config))
        agent._transport.run = AsyncMock(return_value=ContinualFixture.result("answer"))
        with patch.object(CodexTraceUpdater, "update", new_callable=AsyncMock, side_effect=[{"steps": [1]}, {"steps": [2]}]):
            first = await agent.arun(CodexRunInput.text("task"))
            first.metadata["trace"]["steps"].append(99)
            self.assertEqual(agent.last_trace["steps"], [1])
            second = await agent.arun(CodexRunInput.text("task"))
        self.assertEqual(second.metadata["trace"]["steps"], [2])
        self.assertTrue(agent._transport.run.call_args.args[0].observation.enabled)

    def test_fork_inherit_replace_clear(self):
        # [Hidden Assumption] Fork policy resolves before any provider resource exists.
        config = CodexContinualTraceSettings(ContinualFixture.schema())
        parent = CodexHarnessAgentSettings("agent", "system", continual_trace=config)
        inherited = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings()))
        self.assertIs(inherited.continual_trace, config)
        cleared = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings(clear_continual_trace=True)))
        self.assertIsNone(cleared.continual_trace)
        replacement = replace(config, every_n_completed_items=1)
        child = CodexFork._prepare_child(CodexForkRequest(parent, "thread", CodexForkSettings(continual_trace=replacement)))
        self.assertIs(child.continual_trace, replacement)
