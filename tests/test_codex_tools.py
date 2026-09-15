"""FILE: tests/test_codex_tools.py

PURPOSE:
    Feature tests for Codex harness custom tools: the tools and
    tool_permission_policy settings, construction-time name and flag
    validation, the Codex dynamic-tool schema, the server-request handler that
    runs Vidbyte tools on the agent's event loop, the per-connection attach in
    CodexTransport, and fork inheritance. Locks the behavior
    docs/design/codex-harness-tools.md specifies.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/tools.py, the tool wiring in
    vidbyte/agents/codex/{config,transport,agent,fork}.py, the settings in
    vidbyte/lib/dataclasses/codex.py, and ToolsFormatter.to_codex_tool.

ARCHITECTURE NOTE:
    Every test runs offline and without the optional openai-codex extra.
    _FakeAsyncCodex reproduces the pinned SDK's private shape
    (_client._sync with _approval_handler and request) and answers scripted
    server requests from a worker thread while the event loop awaits, exactly
    as the SDK's reader thread does. Only the SDK contract test imports
    openai-codex, and it skips when the extra is absent.

FUNCTION INVENTORY:
    No production functions. _settings() builds agent settings; _bridge()
    builds a bridge over test tools; _call() answers one tool call through a
    handler from a worker thread; _run_transport() runs CodexTransport against
    the fake SDK.

COMMON MODIFICATION PATTERNS:
    Add a handler behavior to CodexToolCallHandler, then add its case to
    CodexToolCallHandlerTests and, if it crosses the transport, to
    CodexTransportToolIntegrationTests.

WHAT NOT TO DO IN THIS FILE:
    Do not call CodexToolCallHandler.handle on the event loop thread; the
    handler blocks on the loop and would deadlock, which is why the SDK calls
    it from its reader thread.

KNOWN EDGE CASES:
    Timeout tests patch CODEX_TOOL_CALL_TIMEOUT_SECONDS in the tools module,
    because the module binds the constant at import time.

RELATED DOCS: docs/design/codex-harness-tools.md
TESTS: python -m pytest tests/test_codex_tools.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import threading
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest import mock

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.codex.tools import (
    CodexToolBridge,
    CodexToolCallHandler,
    CodexToolTranslator,
)
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexForkRequest,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexPrompt,
    CodexRunResult,
    CodexSdkTypes,
    CodexTextInput,
    CodexTransportRunRequest,
    CodexUsage,
)
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError, ToolRegistrationError
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

TOOL_CALL = "item/tool/call"
APPROVAL = "item/commandExecution/requestApproval"


@tool
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


def shout(text: str) -> str:
    """Return the text in upper case."""
    return text.upper()


class _ProbeTool(BaseTool):
    """Async BaseTool that records the thread and call it executed with."""

    def __init__(self, name: str = "probe", permission: ToolPermission = ToolPermission.SAFE) -> None:
        # Stores the declared name and permission plus observation lists.
        self._name = name
        self._permission = permission
        self.thread_ids: list[int] = []
        self.calls: list[ToolCall] = []

    def spec(self) -> ToolSpec:
        # Declares one optional text argument under the configured permission.
        return ToolSpec(
            name=self._name,
            description="Records where it ran.",
            parameters=(ToolParameter(name="note", type="string", description="Free text.", required=False),),
            permission=self._permission,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Records the executing thread and call, then succeeds.
        self.thread_ids.append(threading.get_ident())
        self.calls.append(call)
        return ToolResult.success(self._name, f"ran:{call.arguments.get('note', '')}")


class _SlowTool(BaseTool):
    """Async BaseTool that blocks until cancelled."""

    def __init__(self) -> None:
        # Tracks start and cancellation for timeout and close tests.
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def spec(self) -> ToolSpec:
        # Declares a no-argument tool.
        return ToolSpec(name="slow", description="Sleeps for a long time.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sleeps until cancelled and records the cancellation.
        self.started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ToolResult.success("slow", "finished")


class _RaisingTool(BaseTool):
    """Async BaseTool whose execute raises."""

    def spec(self) -> ToolSpec:
        # Declares a no-argument tool.
        return ToolSpec(name="boom", description="Always raises.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Raises to prove the handler still answers Codex.
        raise RuntimeError("secret internal detail")


def _settings(**overrides: Any) -> CodexHarnessAgentSettings:
    # Builds harness settings with a fixed name and prompt.
    return CodexHarnessAgentSettings(name="codex-agent", system_prompt="You use tools.", **overrides)


def _bridge(*tools: Any, policy: PermissionPolicy | None = None) -> CodexToolBridge:
    # Builds a bridge over the given tools with the default or supplied policy.
    return CodexToolBridge(Tools(tools), policy or PermissionPolicy())


def _fallback(method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    # Mirrors the SDK default: accept approvals, answer anything else with an empty object.
    return {"decision": "accept"} if method.endswith("requestApproval") else {}


async def _call(handler: CodexToolCallHandler, params: Mapping[str, Any] | None, method: str = TOOL_CALL) -> dict[str, Any]:
    # Answers one server request from a worker thread while the loop stays free, as the SDK reader does.
    return await asyncio.to_thread(handler.handle, method, params)


class _FakeSyncClient:
    """Stands in for openai_codex.client.CodexClient's request and handler surface."""

    def __init__(self) -> None:
        # Records every client request and starts with the SDK-default handler.
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._approval_handler = _fallback

    def request(self, method: str, params: Mapping[str, Any] | None, *, response_model: Any = None) -> dict[str, Any]:
        # Records the request as sent on the wire.
        self.requests.append((method, dict(params or {})))
        return {}


class _FakeThread:
    """Native thread whose run replays scripted server requests from a worker thread."""

    def __init__(self, codex: _FakeAsyncCodex, thread_id: str) -> None:
        # Binds the owning fake client and the thread id.
        self._codex = codex
        self.id = thread_id

    async def run(self, input: object, **kwargs: object) -> object:
        # Answers each scripted server request through whatever handler is installed.
        sync = self._codex._client._sync
        for method, params in _FakeAsyncCodex.script:
            answer = await asyncio.to_thread(sync._approval_handler, method, params)
            _FakeAsyncCodex.answers.append(answer)
        return object()


class _FakeAsyncCodex:
    """Stands in for openai_codex.AsyncCodex, routing thread calls through the sync request."""

    script: list[tuple[str, dict[str, Any]]] = []
    answers: list[dict[str, Any]] = []
    instances: list[_FakeAsyncCodex] = []

    def __init__(self, config: object = None) -> None:
        # Exposes the private _client._sync shape the bridge attaches to.
        self._client = SimpleNamespace(_sync=_FakeSyncClient())
        _FakeAsyncCodex.instances.append(self)

    async def __aenter__(self) -> _FakeAsyncCodex:
        # Mirrors AsyncCodex entering an initialized connection.
        return self

    async def __aexit__(self, *exc: object) -> None:
        # Mirrors AsyncCodex closing its connection.
        return None

    async def thread_start(self, **kwargs: object) -> _FakeThread:
        # Sends thread/start through the sync request, as the real SDK does.
        self._client._sync.request("thread/start", {"developerInstructions": kwargs.get("developer_instructions")}, response_model=None)
        return _FakeThread(self, "th_new")

    async def thread_resume(self, thread_id: str, **kwargs: object) -> _FakeThread:
        # Sends thread/resume through the sync request, as the real SDK does.
        self._client._sync.request("thread/resume", {"threadId": thread_id}, response_model=None)
        return _FakeThread(self, thread_id)


def _fake_sdk(async_codex: type = _FakeAsyncCodex) -> CodexSdkTypes:
    # Builds SDK types whose constructors accept the adapter's default arguments.
    passthrough = SimpleNamespace
    return CodexSdkTypes(
        async_codex=async_codex,
        codex_config=passthrough,
        approval_mode=str,
        sandbox=str,
        personality=str,
        reasoning_effort=str,
        reasoning_summary=mock.Mock(),
        thread_source=str,
        thread_start_source=str,
        text_input=lambda text: text,
        image_input=lambda url: url,
        local_image_input=lambda path: path,
        skill_input=lambda name, path: name,
        mention_input=lambda name, path: name,
    )


def _run_result(thread_id: str) -> CodexRunResult:
    # Builds one completed native snapshot for the patched serializer.
    return CodexRunResult(
        thread_id=thread_id,
        turn_id="tu_1",
        status="completed",
        final_response="done",
        duration_ms=1,
        usage=CodexUsage(),
        items=(),
    )


async def _run_transport(bridge: CodexToolBridge | None, *, thread_id: str = "", async_codex: type = _FakeAsyncCodex) -> CodexRunResult:
    # Runs one CodexTransport turn against the fake SDK and returns its result.
    request = CodexTransportRunRequest(
        thread_id=thread_id,
        system_prompt="You use tools.",
        prompt=CodexPrompt(items=(CodexTextInput("hi"),), user_prompt="hi", recipient="codex-agent", metadata={}),
        settings=CodexAgentSettings(),
        output_schema={},
        tools=bridge,
    )
    with mock.patch.object(CodexTransport, "_load_sdk", return_value=_fake_sdk(async_codex)), mock.patch(
        "vidbyte.agents.codex.transport.CodexResultSerializer.from_sdk",
        side_effect=lambda tid, result: _run_result(tid),
    ):
        return await CodexTransport().run(request)


def _reset_fake(script: list[tuple[str, dict[str, Any]]] | None = None) -> None:
    # Clears fake SDK state between tests and installs a server-request script.
    _FakeAsyncCodex.script = list(script or [])
    _FakeAsyncCodex.answers = []
    _FakeAsyncCodex.instances = []


class CodexToolSettingsTests(unittest.TestCase):
    """Settings-level validation that runs before any translator."""

    def test_empty_tools_is_the_default(self) -> None:
        settings = _settings()
        self.assertEqual(settings.tools, ())
        self.assertIsInstance(settings.tool_permission_policy, PermissionPolicy)

    def test_list_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "tools must be a tuple"):
            _settings(tools=[add])

    def test_non_tool_item_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "tools must be a tuple"):
            _settings(tools=(add, 42))

    def test_non_policy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "tool_permission_policy"):
            _settings(tool_permission_policy="allow-all")


class CodexToolTranslatorTests(unittest.TestCase):
    """Construction-time normalization and Codex naming rules."""

    def test_no_tools_yields_no_bridge(self) -> None:
        self.assertIsNone(CodexToolTranslator.translate(_settings()))

    def test_mixed_inputs_normalize_in_declaration_order(self) -> None:
        probe = _ProbeTool()
        bridge = CodexToolTranslator.translate(_settings(tools=(probe, add, shout)))
        assert bridge is not None
        self.assertEqual(bridge.tools.names(), ("probe", "add", "shout"))
        self.assertEqual([spec["name"] for spec in bridge.dynamic_tools], ["probe", "add", "shout"])

    def test_invalid_characters_are_rejected(self) -> None:
        for name in ("context.create", "has space"):
            with self.subTest(name=name), self.assertRaisesRegex(ConfigurationError, "letters, digits"):
                CodexToolTranslator.translate(_settings(tools=(_ProbeTool(name),)))

    def test_name_length_boundary(self) -> None:
        self.assertIsNotNone(CodexToolTranslator.translate(_settings(tools=(_ProbeTool("a" * 128),))))
        with self.assertRaisesRegex(ConfigurationError, "1-128"):
            CodexToolTranslator.translate(_settings(tools=(_ProbeTool("a" * 129),)))

    def test_reserved_mcp_names_are_rejected(self) -> None:
        for name in ("mcp", "mcp__search"):
            with self.subTest(name=name), self.assertRaisesRegex(ConfigurationError, "reserved"):
                CodexToolTranslator.translate(_settings(tools=(_ProbeTool(name),)))

    def test_duplicate_names_are_rejected(self) -> None:
        with self.assertRaises(ToolRegistrationError):
            CodexToolTranslator.translate(_settings(tools=(_ProbeTool("dup"), _ProbeTool("dup"))))

    def test_experimental_api_off_is_rejected(self) -> None:
        codex = CodexAgentSettings(client=CodexClientSettings(experimental_api=False))
        with self.assertRaisesRegex(ConfigurationError, "experimental_api"):
            CodexToolTranslator.translate(_settings(tools=(add,), codex=codex))

    def test_agent_construction_classifies_translator_errors(self) -> None:
        with self.assertRaises(CodexAgentError) as caught:
            CodexHarnessAgent(_settings(tools=(_ProbeTool("bad.name"),)))
        self.assertEqual(caught.exception.failure_code, FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value)


class CodexToolFormatterTests(unittest.TestCase):
    """The Codex dynamic-tool declaration shape."""

    def test_codex_tool_matches_openai_schema(self) -> None:
        spec = add.spec()
        codex = ToolsFormatter.to_codex_tool(spec)
        self.assertEqual(set(codex), {"type", "name", "description", "inputSchema"})
        self.assertEqual(codex["type"], "function")
        self.assertEqual(codex["name"], "add")
        self.assertEqual(codex["description"], spec.description)
        self.assertEqual(codex["inputSchema"], ToolsFormatter.to_openai_tool(spec)["function"]["parameters"])


class CodexToolCallHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Server-request handling on the SDK reader thread."""

    def _handler(self, *tools: Any, policy: PermissionPolicy | None = None) -> CodexToolCallHandler:
        # Attaches a bridge to a fake client and returns the installed handler.
        codex = _FakeAsyncCodex()
        return _bridge(*tools, policy=policy).attach(codex, asyncio.get_running_loop())

    async def test_decorated_tool_succeeds(self) -> None:
        answer = await _call(self._handler(add), {"tool": "add", "arguments": {"a": 2, "b": 3}, "callId": "c1"})
        self.assertEqual(answer, {"success": True, "contentItems": [{"type": "inputText", "text": "5"}]})

    async def test_plain_callable_succeeds(self) -> None:
        answer = await _call(self._handler(shout), {"tool": "shout", "arguments": {"text": "hi"}})
        self.assertTrue(answer["success"])
        self.assertEqual(answer["contentItems"][0]["text"], "HI")

    async def test_async_tool_runs_on_the_agent_loop_with_call_id(self) -> None:
        probe = _ProbeTool()
        answer = await _call(self._handler(probe), {"tool": "probe", "arguments": {"note": "x"}, "callId": "c9"})
        self.assertTrue(answer["success"])
        self.assertEqual(probe.thread_ids, [threading.get_ident()])
        self.assertEqual(probe.calls[0].call_id, "c9")

    async def test_unknown_tool_fails_without_raising(self) -> None:
        answer = await _call(self._handler(add), {"tool": "missing", "arguments": {}})
        self.assertFalse(answer["success"])

    async def test_raising_tool_fails_without_raising(self) -> None:
        answer = await _call(self._handler(_RaisingTool()), {"tool": "boom", "arguments": {}})
        self.assertFalse(answer["success"])

    async def test_write_tool_is_denied_by_default_and_allowed_by_policy(self) -> None:
        params = {"tool": "writer", "arguments": {}}
        denied = await _call(self._handler(_ProbeTool("writer", ToolPermission.WRITE)), params)
        self.assertFalse(denied["success"])
        self.assertIn("Permission denied", denied["contentItems"][0]["text"])
        allowed = await _call(self._handler(_ProbeTool("writer", ToolPermission.WRITE), policy=PermissionPolicy.allow_all()), params)
        self.assertTrue(allowed["success"])

    async def test_null_arguments_become_empty_object(self) -> None:
        answer = await _call(self._handler(_ProbeTool()), {"tool": "probe", "arguments": None})
        self.assertEqual(answer["contentItems"][0]["text"], "ran:")

    async def test_non_object_arguments_fail(self) -> None:
        answer = await _call(self._handler(_ProbeTool()), {"tool": "probe", "arguments": "note=x"})
        self.assertFalse(answer["success"])
        self.assertIn("JSON object", answer["contentItems"][0]["text"])

    async def test_missing_tool_name_fails(self) -> None:
        for params in ({"arguments": {}}, None):
            with self.subTest(params=params):
                answer = await _call(self._handler(add), params)
                self.assertFalse(answer["success"])

    async def test_timeout_cancels_the_tool(self) -> None:
        slow = _SlowTool()
        with mock.patch("vidbyte.agents.codex.tools.CODEX_TOOL_CALL_TIMEOUT_SECONDS", 0.05):
            answer = await _call(self._handler(slow), {"tool": "slow", "arguments": {}})
        self.assertFalse(answer["success"])
        self.assertIn("timed out", answer["contentItems"][0]["text"])
        await asyncio.sleep(0.01)
        self.assertTrue(slow.cancelled.is_set())

    async def test_close_cancels_an_in_flight_call(self) -> None:
        slow = _SlowTool()
        handler = self._handler(slow)
        pending = asyncio.ensure_future(_call(handler, {"tool": "slow", "arguments": {}}))
        await asyncio.to_thread(slow.started.wait, 5)
        handler.close()
        answer = await pending
        self.assertFalse(answer["success"])
        await asyncio.sleep(0.01)
        self.assertTrue(slow.cancelled.is_set())

    async def test_raw_exception_text_is_not_disclosed_by_the_bridge(self) -> None:
        slow = _SlowTool()
        handler = self._handler(slow)
        pending = asyncio.ensure_future(_call(handler, {"tool": "slow", "arguments": {}}))
        await asyncio.to_thread(slow.started.wait, 5)
        handler.close()
        answer = await pending
        self.assertEqual(answer["contentItems"][0]["text"], "Tool call was cancelled or failed before returning a result.")

    async def test_approvals_are_delegated_unchanged(self) -> None:
        handler = self._handler(add)
        self.assertEqual(await _call(handler, {"command": "ls"}, method=APPROVAL), {"decision": "accept"})
        self.assertEqual(await _call(handler, {}, method="account/chatgptAuthTokens/refresh"), {})


class CodexToolCallHandlerClosedLoopTests(unittest.TestCase):
    """A handler whose agent loop has already closed."""

    def test_closed_loop_fails_without_raising(self) -> None:
        loop = asyncio.new_event_loop()
        loop.close()
        handler = _bridge(add).attach(_FakeAsyncCodex(), loop)
        answer = handler.handle(TOOL_CALL, {"tool": "add", "arguments": {"a": 1, "b": 1}})
        self.assertFalse(answer["success"])
        self.assertIn("event loop stopped", answer["contentItems"][0]["text"])


class CodexToolBridgeAttachTests(unittest.IsolatedAsyncioTestCase):
    """Installing the bridge on one SDK client."""

    async def test_only_thread_start_gains_dynamic_tools(self) -> None:
        codex = _FakeAsyncCodex()
        bridge = _bridge(add)
        bridge.attach(codex, asyncio.get_running_loop())
        original = {"model": "gpt"}
        sync = codex._client._sync
        sync.request("thread/start", original)
        sync.request("turn/start", {"threadId": "t"})
        self.assertEqual(sync.requests[0][1]["dynamicTools"], list(bridge.dynamic_tools))
        self.assertEqual(sync.requests[0][1]["model"], "gpt")
        self.assertNotIn("dynamicTools", sync.requests[1][1])
        self.assertEqual(original, {"model": "gpt"})

    async def test_missing_sdk_hooks_raise_typed_error(self) -> None:
        with self.assertRaises(CodexAgentError) as caught:
            _bridge(add).attach(SimpleNamespace(_client=SimpleNamespace()), asyncio.get_running_loop())
        self.assertEqual(caught.exception.failure_code, FailureCode.CODEX_SDK_UNAVAILABLE.value)


class CodexTransportToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """CodexTransport attaches tools per connection against the fake SDK."""

    async def test_new_thread_registers_and_executes_tools(self) -> None:
        _reset_fake([(TOOL_CALL, {"tool": "add", "arguments": {"a": 4, "b": 5}, "callId": "c1"})])
        bridge = _bridge(add)
        result = await _run_transport(bridge)
        method, params = _FakeAsyncCodex.instances[0]._client._sync.requests[0]
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["dynamicTools"], list(bridge.dynamic_tools))
        self.assertEqual(_FakeAsyncCodex.answers, [{"success": True, "contentItems": [{"type": "inputText", "text": "9"}]}])
        self.assertEqual(result.thread_id, "th_new")

    async def test_resume_keeps_handler_without_reregistering(self) -> None:
        _reset_fake([(TOOL_CALL, {"tool": "add", "arguments": {"a": 1, "b": 2}})])
        await _run_transport(_bridge(add), thread_id="th_saved")
        method, params = _FakeAsyncCodex.instances[0]._client._sync.requests[0]
        self.assertEqual(method, "thread/resume")
        self.assertNotIn("dynamicTools", params)
        self.assertTrue(_FakeAsyncCodex.answers[0]["success"])

    async def test_no_tools_leaves_the_client_untouched(self) -> None:
        _reset_fake([(APPROVAL, {"command": "ls"})])
        await _run_transport(None)
        sync = _FakeAsyncCodex.instances[0]._client._sync
        self.assertIs(sync._approval_handler, _fallback)
        self.assertEqual(sync.request.__func__, _FakeSyncClient.request)
        self.assertNotIn("dynamicTools", sync.requests[0][1])

    async def test_missing_sdk_hooks_fail_the_run(self) -> None:
        class _HooklessCodex(_FakeAsyncCodex):
            def __init__(self, config: object = None) -> None:
                super().__init__(config)
                self._client = SimpleNamespace()

        _reset_fake()
        with self.assertRaises(CodexAgentError) as caught:
            await _run_transport(_bridge(add), async_codex=_HooklessCodex)
        self.assertEqual(caught.exception.failure_code, FailureCode.CODEX_SDK_UNAVAILABLE.value)

    async def test_agent_passes_its_tools_to_the_transport(self) -> None:
        _reset_fake([(TOOL_CALL, {"tool": "shout", "arguments": {"text": "ok"}})])
        agent = CodexHarnessAgent(_settings(tools=(shout,)))
        with mock.patch.object(CodexTransport, "_load_sdk", return_value=_fake_sdk()), mock.patch(
            "vidbyte.agents.codex.transport.CodexResultSerializer.from_sdk",
            side_effect=lambda tid, result: _run_result(tid),
        ):
            reply = await agent.arun("shout ok")
        self.assertEqual(reply.content, "done")
        self.assertEqual(_FakeAsyncCodex.answers[0]["contentItems"][0]["text"], "OK")


class CodexToolForkTests(unittest.TestCase):
    """Forked children can execute the tools their native thread inherits."""

    def test_child_inherits_tools_and_policy(self) -> None:
        policy = PermissionPolicy.allow_all()
        parent = _settings(tools=(add, shout), tool_permission_policy=policy)
        child = CodexFork._prepare_child(CodexForkRequest(parent=parent, parent_thread_id="th_1", overrides=CodexForkSettings()))
        self.assertEqual(child.tools, parent.tools)
        self.assertIs(child.tool_permission_policy, policy)


@unittest.skipUnless(importlib.util.find_spec("openai_codex"), "requires the optional openai-codex extra")
class CodexSdkContractTests(unittest.TestCase):
    """The pinned openai-codex exposes the private hooks the bridge relies on."""

    def test_async_codex_exposes_sync_client_hooks(self) -> None:
        from openai_codex import AsyncCodex, CodexConfig

        sync = AsyncCodex(CodexConfig())._client._sync
        self.assertTrue(callable(sync._approval_handler))
        self.assertTrue(callable(sync.request))

    def test_thread_start_routes_through_request(self) -> None:
        from openai_codex.client import CodexClient

        self.assertIn("self.request(", inspect.getsource(CodexClient.thread_start))
        self.assertIn("self._approval_handler(", inspect.getsource(CodexClient._handle_server_request))


if __name__ == "__main__":
    unittest.main()
