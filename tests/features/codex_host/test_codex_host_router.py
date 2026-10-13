"""FILE: tests/features/codex_host/test_codex_host_router.py

PURPOSE: Proves CodexServerRequestRouter answers every server request the app-server sends, on the openai-codex reader thread, without ever raising: a registered thread's tool runs, an unregistered thread's tool call fails with the fixed text, both approval methods get accept, any other method gets an empty answer, and a tool that raises or a call with no params gets a failed tool response.
ROLE IN CODEBASE: Router layer of tests/features/codex_host/ (spec AC-30, INV-28, INV-29, D-18, EC-47). The class needs the optional openai-codex extra, so CI skips it.
ARCHITECTURE NOTE: Each request goes through the fake's stdout to the real SDK reader thread, which calls the approval_handler the host gave CodexClient (the router, spec section 13) and writes its answer back; the test reads that answer. A router that raised would kill the reader, which the fake records in reader_errors.
COMMON MODIFICATION PATTERNS: Add a server-request method as one more ask() with its expected answer.
KNOWN EDGE CASES: openai-codex passes params as None when they are not a JSON object, so the router must treat a None tool call as malformed rather than index into it.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-28, INV-29) and 8.1 (D-18).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_router.py
"""

from __future__ import annotations

import asyncio
import unittest

from tests.features.codex_host.codex_host_support import (
    UNREGISTERED_TOOL_TEXT,
    WAIT_SECONDS,
    HostTestCase,
    make_echo_tool,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.tools.base import BaseTool

APPROVAL_METHODS = ("item/commandExecution/requestApproval", "item/fileChange/requestApproval")


class _ExplodingTool(BaseTool):
    """A READ tool whose execution raises, as a buggy developer tool would."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="explode",
            description="Always fails.",
            permission=ToolPermission.READ,
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        raise RuntimeError("the developer tool crashed")


@requires_sdk
class CodexHostRouterTests(HostTestCase):
    """AC-30: the router answers every server request and never raises."""

    async def test_the_router_answers_every_server_request_and_never_raises(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        tooled = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Use the tools.", tools=(make_echo_tool(), _ExplodingTool()))), WAIT_SECONDS)
        plain = await self.spawn(host)
        call = {"threadId": tooled.thread_id, "turnId": tooled.turn_id, "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}}

        # A registered thread's tool runs on the host's loop and its output reaches Codex.
        self.assertEqual(await self.ask("item/tool/call", call), {"success": True, "contentItems": [{"type": "inputText", "text": "echo: hi"}]})
        # EC-47: a thread with no tools on this host gets the fixed text, not an exception.
        unregistered = {**call, "threadId": plain.thread_id, "turnId": plain.turn_id, "callId": "call-2"}
        self.assertEqual(await self.ask("item/tool/call", unregistered), {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]})
        # INV-28: the SDK's fallback answers, for approvals that still reach the host and for unknown requests.
        for method in APPROVAL_METHODS:
            with self.subTest(method=method):
                params = {"threadId": tooled.thread_id, "turnId": tooled.turn_id, "itemId": "item-1"}
                self.assertEqual(await self.ask(method, params), {"decision": "accept"})
        self.assertEqual(await self.ask("item/somethingNew/request", {"threadId": tooled.thread_id}), {})
        # A tool that raises, and a tool call with no params, both get a failed tool response.
        exploding = await self.ask("item/tool/call", {**call, "callId": "call-3", "tool": "explode", "arguments": {}})
        self.assertIs(exploding["success"], False)
        self.assertIs((await self.ask("item/tool/call", None))["success"], False)

        # The reader thread survived every answer, so the host still talks to Codex.
        self.assertEqual(self.server.reader_errors, [])
        await asyncio.wait_for(host.read_codex_thread(tooled.thread_id), WAIT_SECONDS)


if __name__ == "__main__":
    unittest.main()
