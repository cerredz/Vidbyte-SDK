"""Native Vidbyte tool enforcement acceptance pack.

PURPOSE: Prove native registration and permission execution at the SDK boundary.
ROLE IN CODEBASE: Executed by pytest and the feature verification script.
ARCHITECTURE NOTE: Real tool executor and native models; fake process transport.
COMMON MODIFICATION PATTERNS: Add a rejected action alongside each allowed action.
KNOWN EDGE CASES: Native callbacks run on another thread while tools await the owner loop.
RELATED DOCS: docs/design/codex-native-tools.md
TESTS: python scripts/test-codex-native-tools.py
"""

import asyncio
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("openai_codex")
from openai_codex.generated.v2_all import ItemCompletedNotification, ThreadItem, Turn, TurnCompletedNotification
from openai_codex.models import Notification

from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings, CodexToolBridgeSettings
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.tool_dispatch import CodexToolDispatcher
from vidbyte.agents.codex.tool_wire import CodexToolWire
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexClientSettings, CodexForkRequest, CodexForkSettings, CodexImageInput, CodexLocalImageInput, CodexMentionInput, CodexObservationSettings, CodexPrompt, CodexSkillInput, CodexTextInput, CodexThreadSettings, CodexTransportRunRequest, CodexTurnSettings
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.codex import CodexApprovalMode, CodexSandbox
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolParameter, ToolPermission, ToolResult, ToolSpec


class BoundTool(BaseTool):
    """Stateful existing tool whose effects expose permission/duplicate mistakes."""

    def __init__(self, *, permission=ToolPermission.SAFE, mode="success"):
        # Keep state on the original instance to verify bound-tool preservation.
        self.permission = permission
        self.mode = mode
        self.calls = []
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()

    def spec(self):
        # Declare a required argument and caller-selected permission.
        return ToolSpec("remember", "Record one fact", (ToolParameter("fact", "string", "Fact to retain"),), permission=self.permission)

    async def execute(self, call):
        # Exercise async ownership, intended errors, unexpected errors, and cancellation.
        self.calls.append(call)
        self.entered.set()
        if self.mode == "wait":
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        if self.mode == "raise":
            raise RuntimeError("sensitive exception content")
        if self.mode == "error":
            return ToolResult.error("remember", "Fact rejected")
        return ToolResult.success("remember", "Fact retained")


class Fixture:
    """Real records and native messages shared across boundary tests."""

    @staticmethod
    def call(**overrides):
        # Build a valid experimental request with explicit native identity.
        return {"threadId": "thread", "turnId": "turn", "callId": "call", "tool": "remember", "arguments": {"fact": "keep"}, **overrides}

    @staticmethod
    def request(tool=None, **overrides):
        # Use explicit experimental registration and a fresh thread.
        return CodexTransportRunRequest(thread_id="", system_prompt="help", prompt=CodexPrompt((CodexTextInput("hello"),), "hello", "user", {}), settings=CodexAgentSettings(client=CodexClientSettings(experimental_api=True)), output_schema={}, tool_bridge=CodexToolBridgeSettings(Tools([tool or BoundTool()])), **overrides)

    @staticmethod
    def events(status="completed"):
        # Build real generated item and terminal notification models.
        item = ThreadItem.model_validate({"type": "agentMessage", "id": "message", "text": "done", "phase": "final_answer"})
        return [Notification("item/completed", ItemCompletedNotification(thread_id="thread", turn_id="turn", item=item, completed_at_ms=1)), Notification("turn/completed", TurnCompletedNotification(thread_id="thread", turn=Turn(id="turn", items=[], status=status)))]


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    """The native callback must pass the actual existing executor contract."""

    def bridge(self, tool=None, **kwargs):
        # Bind the known native thread and schedule cleanup for each test.
        result = CodexToolDispatcher(CodexToolBridgeSettings(Tools([tool or BoundTool()]), **kwargs))
        result.thread_id = "thread"
        self.addCleanup(result.close)
        return result

    async def call(self, bridge, **values):
        # Simulate the SDK's blocking reader callback without blocking the tool loop.
        return await asyncio.to_thread(bridge.handle, "item/tool/call", Fixture.call(**values))

    async def test_permissions_and_argument_validation(self):
        # [Hidden Failure] Neither denied permissions nor missing arguments execute tools.
        denied = BoundTool(permission=ToolPermission.WRITE)
        self.assertFalse((await self.call(self.bridge(denied)))["success"])
        self.assertEqual(denied.calls, [])
        invalid = BoundTool()
        self.assertFalse((await self.call(self.bridge(invalid), arguments={}))["success"])
        self.assertEqual(invalid.calls, [])

    async def test_success_and_intended_failure(self):
        # [Silent Failure] Preserve actual tool identity, output, and success polarity.
        for mode, success, text in (("success", True, "Fact retained"), ("error", False, "Fact rejected")):
            tool = BoundTool(mode=mode)
            response = await self.call(self.bridge(tool))
            self.assertEqual(response, {"contentItems": [{"type": "inputText", "text": text}], "success": success})
            self.assertEqual(tool.calls[0].call_id, "call")

    async def test_duplicate_and_conflicting_calls(self):
        # [Hidden Failure] Duplicate native delivery cannot repeat effects or change arguments.
        tool = BoundTool()
        bridge = self.bridge(tool)
        first = await self.call(bridge)
        self.assertEqual(first, await self.call(bridge))
        first["contentItems"].clear()
        self.assertTrue((await self.call(bridge))["contentItems"])
        self.assertFalse((await self.call(bridge, arguments={"fact": "changed"}))["success"])
        self.assertEqual(len(tool.calls), 1)

    async def test_invalid_routing_and_shapes(self):
        # [Hidden Assumption] Invalid identity or schemas must fail without invoking a tool.
        tool = BoundTool()
        bridge = self.bridge(tool)
        for values in ({"threadId": "other"}, {"callId": ""}, {"turnId": " "}, {"tool": "unknown"}, {"namespace": "external"}, {"arguments": []}, {"arguments": None}):
            self.assertFalse((await self.call(bridge, **values))["success"])
        self.assertFalse(bridge.handle("item/tool/call", None)["success"])
        self.assertEqual(tool.calls, [])

    async def test_timeout_and_sanitized_exception(self):
        # [Hidden Failure] Timed-out tools cancel and unexpected exceptions stay out of native output.
        tool = BoundTool(mode="wait")
        bridge = self.bridge(tool, timeout_seconds=0.01)
        self.assertFalse((await self.call(bridge))["success"])
        await asyncio.wait_for(tool.cancelled.wait(), 1)
        self.assertFalse((await self.call(bridge))["success"])
        self.assertEqual(len(tool.calls), 1)
        response = await self.call(self.bridge(BoundTool(mode="raise")))
        self.assertFalse(response["success"])
        self.assertNotIn("sensitive", str(response))

    async def test_close_cancels_pending_and_rejects_new(self):
        # [Hidden Failure] Client shutdown releases the reader's pending future.
        tool = BoundTool(mode="wait")
        bridge = self.bridge(tool)
        task = asyncio.create_task(self.call(bridge))
        await tool.entered.wait()
        bridge.close()
        self.assertFalse((await asyncio.wait_for(task, 1))["success"])
        await asyncio.wait_for(tool.cancelled.wait(), 1)
        self.assertFalse((await self.call(bridge, callId="later"))["success"])
        self.assertEqual(len(tool.calls), 1)

    async def test_native_approvals_fail_closed(self):
        # [Hidden Assumption] Native approvals and unknown requests cannot authorize execution.
        bridge = self.bridge()
        for method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            self.assertEqual(bridge.handle(method, {}), {"decision": "decline"})
        with self.assertRaises(ValueError):
            bridge.handle("unknown", {})


class TranslationTests(unittest.IsolatedAsyncioTestCase):
    """Review actual generated native parameter models and configuration boundaries."""

    async def test_invalid_settings_and_empty_catalog(self):
        # [Edge Case] Reject empty catalogs and invalid bounds before process creation.
        for value in (0, -1, True, float("inf"), float("nan")):
            with self.assertRaises(ConfigurationError):
                CodexToolBridgeSettings(Tools([BoundTool()]), timeout_seconds=value)
        with self.assertRaises(CodexAgentError):
            CodexHarnessAgent(CodexHarnessAgentSettings(name="test", system_prompt="help", tool_bridge=CodexToolBridgeSettings(Tools([]))))
        with self.assertRaises(ConfigurationError):
            CodexToolBridgeSettings(Tools([BoundTool()]), permission_policy="allow")

    async def test_invalid_catalog_and_experimental_opt_in(self):
        # [Hidden Assumption] Invalid collaborators and missing experimental registration reject.
        for bridge, codex in ((CodexToolBridgeSettings("wrong"), CodexAgentSettings()), (CodexToolBridgeSettings(Tools([BoundTool()])), CodexAgentSettings(client=CodexClientSettings(experimental_api=False)))):
            with self.assertRaises(CodexAgentError):
                CodexHarnessAgent(CodexHarnessAgentSettings(name="test", system_prompt="help", codex=codex, tool_bridge=bridge))

    async def test_native_schema_and_controls(self):
        # [Silent Failure] Registration and generated native controls retain exact semantics.
        request = Fixture.request()
        request = replace(request, settings=replace(request.settings, thread=CodexThreadSettings(approval_mode=CodexApprovalMode.DENY_ALL, sandbox=CodexSandbox.FULL_ACCESS), turn=CodexTurnSettings(sandbox=CodexSandbox.READ_ONLY)), output_schema={"type": "object"})
        sdk = CodexTransport._load_sdk()
        thread = CodexToolWire.thread(request, sdk, request.tool_bridge.tools)
        self.assertEqual(thread["approvalPolicy"], "never")
        self.assertEqual(thread["sandbox"], "danger-full-access")
        self.assertEqual(thread["dynamicTools"][0]["inputSchema"], request.tool_bridge.tools.provider_schemas("openai")[0]["function"]["parameters"])
        self.assertEqual(thread["dynamicTools"][0]["description"], "Record one fact")
        turn = CodexToolWire.turn(request, sdk, "thread")
        self.assertEqual(turn["sandboxPolicy"]["type"], "readOnly")
        self.assertEqual(turn["outputSchema"], {"type": "object"})

    async def test_input_modalities_and_default_approval(self):
        # [Edge Case] Every supported native modality survives raw parameter conversion.
        request = Fixture.request()
        items = (CodexTextInput("text"), CodexImageInput("https://example.com/a.png"), CodexLocalImageInput("a.png"), CodexSkillInput("skill", "skill.md"), CodexMentionInput("mention", "file.md"))
        request = replace(request, prompt=replace(request.prompt, items=items))
        sdk = CodexTransport._load_sdk()
        turn = CodexToolWire.turn(request, sdk, "thread")
        self.assertEqual([item["type"] for item in turn["input"]], ["text", "image", "localImage", "skill", "mention"])
        self.assertEqual(CodexToolWire.thread(request, sdk, request.tool_bridge.tools)["approvalsReviewer"], "auto_review")

    async def test_resume_and_fork_reject_before_native_calls(self):
        # [Hidden Assumption] Unsupported registration continuity cannot silently lose tools.
        request = Fixture.request()
        with patch("openai_codex.client.CodexClient") as client:
            with self.assertRaises(ConfigurationError):
                await CodexTransport().run(replace(request, thread_id="saved"))
            client.assert_not_called()
        parent = CodexHarnessAgentSettings(name="test", system_prompt="help", codex=request.settings, tool_bridge=request.tool_bridge)
        transport = Mock()
        with self.assertRaises(CodexAgentError):
            await CodexFork(transport).afork(CodexForkRequest(parent=parent, parent_thread_id="thread", overrides=CodexForkSettings()))
        transport.fork_thread.assert_not_called()


class NativeTransportTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the full public SDK seam using actual native result models."""

    def client(self, tool, events):
        # Simulate a native server requesting a registered tool during turn/start.
        client = Mock()
        client.thread_start.return_value = SimpleNamespace(thread=SimpleNamespace(id="thread"))
        client.next_turn_notification.side_effect = events

        def factory(config, approval_handler):
            # Capture the actual injected handler and invoke it from the worker thread.
            def turn_start(thread_id, input_items, params):
                # Native turn startup waits for the real executor-backed callback.
                client.tool_response = approval_handler("item/tool/call", Fixture.call())
                return SimpleNamespace(turn=SimpleNamespace(id="turn"))

            client.turn_start.side_effect = turn_start
            return client

        return client, factory

    async def test_native_registration_execution_observation_result(self):
        # [Silent Failure] The real transport registers schemas, executes tools, and delivers observations.
        tool = BoundTool()
        observations = []

        async def observe(event):
            # Retain the reviewed native snapshot for result-path verification.
            observations.append(event)

        request = Fixture.request(tool, observation=CodexObservationSettings(observers=(observe,)))
        client, factory = self.client(tool, Fixture.events())
        with patch("openai_codex.client.CodexClient", side_effect=factory):
            result = await CodexTransport().run(request)
        self.assertEqual(result.final_response, "done")
        self.assertTrue(client.tool_response["success"])
        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(len(observations), 2)
        self.assertEqual(client.thread_start.call_args.args[0]["dynamicTools"][0]["name"], "remember")
        client.unregister_turn_notifications.assert_called_once_with("turn")
        client.close.assert_called_once()

    async def test_native_failure_closes_and_unregisters(self):
        # [Hidden Failure] Failed native terminal status cannot return success or leak the process.
        tool = BoundTool()
        client, factory = self.client(tool, Fixture.events("failed"))
        with patch("openai_codex.client.CodexClient", side_effect=factory), self.assertRaises(CodexAgentError):
            await CodexTransport().run(Fixture.request(tool))
        client.close.assert_called_once()
        client.unregister_turn_notifications.assert_called_once_with("turn")

    async def test_native_cancellation_closes_pending_tool(self):
        # [Hidden Failure] Cancelling a turn cancels its callback and closes the native process.
        tool = BoundTool(mode="wait")
        client, factory = self.client(tool, Fixture.events())
        with patch("openai_codex.client.CodexClient", side_effect=factory):
            task = asyncio.create_task(CodexTransport().run(Fixture.request(tool)))
            await tool.entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        await asyncio.wait_for(tool.cancelled.wait(), 1)
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
