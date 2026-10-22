"""FILE: tests/features/codex_host/test_codex_host_bridge.py

PURPOSE: Proves the two behaviour-preserving extractions CodexHost reuses from CodexHarnessAgent's tools module: CodexToolTranslator.validate_names raises the two existing name messages, and CodexToolBridge.handler(loop, fallback) builds a CodexToolCallHandler that runs tool calls through the bridge's own executor and permission policy and hands every other server request to the fallback.
ROLE IN CODEBASE: Extraction layer of tests/features/codex_host/ (spec INV-29, INV-39, EC-49, D-18; section 12.3 row 7; AC-28 and AC-30's basis). It needs neither a host nor openai-codex, so CI runs it. The unchanged translate and attach paths stay covered by tests/test_codex_tools.py.
ARCHITECTURE NOTE: The handler blocks its calling thread until the tool coroutine finishes on the loop, the way the SDK reader thread calls it, so each handle() call runs in a worker thread while the test's loop stays free to run the tool.
COMMON MODIFICATION PATTERNS: Keep the messages literal: they are the existing translate messages that both CodexHarnessAgent and CodexHost raise.
KNOWN EDGE CASES: The Tools catalog itself accepts names Codex rejects (spaces, the mcp prefix, 129 characters), so validate_names is the only gate. A WRITE tool is denied by the default PermissionPolicy, which proves the handler uses the bridge's policy rather than a permissive one.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md section 8.5 (vidbyte.agents.codex.tools) and section 12.3 row 7.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_bridge.py
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import make_echo_tool
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.tools import ToolPermission
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.catalog import Tools

LONG_NAME = "x" * 129


def _charset_message(name: str) -> str:
    return f"Codex tool name {name!r} must be 1-128 characters of letters, digits, '_' or '-'."


def _reserved_message(name: str) -> str:
    return f"Codex tool name {name!r} is reserved for MCP tools."


class CodexToolTranslatorValidateNamesTests(unittest.TestCase):
    """INV-29 and INV-39: validate_names is the existing name loop, with its two messages."""

    def test_validate_names_raises_the_two_existing_messages(self) -> None:
        from vidbyte.agents.codex.tools import CodexToolTranslator

        cases = (
            ("bad name!", _charset_message("bad name!")),
            (LONG_NAME, _charset_message(LONG_NAME)),
            ("mcp", _reserved_message("mcp")),
            ("mcp__files", _reserved_message("mcp__files")),
        )
        for name, message in cases:
            with self.subTest(name=name[:20]):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexToolTranslator.validate_names(Tools([make_echo_tool("echo_text"), make_echo_tool(name)]))
                self.assertEqual(caught.exception.message, message)
        self.assertIsNone(CodexToolTranslator.validate_names(Tools([make_echo_tool("echo_text"), make_echo_tool("read-file_2")])))


class CodexToolBridgeHandlerTests(unittest.IsolatedAsyncioTestCase):
    """D-18: handler(loop, fallback) answers tool calls with the bridge's executor and policy."""

    async def test_handler_runs_tools_under_the_bridge_policy_and_falls_back_otherwise(self) -> None:
        from vidbyte.agents.codex.tools import CodexToolBridge, CodexToolCallHandler

        fallback_calls: list[tuple[str, Any]] = []

        def fallback(method: str, params: Any) -> dict[str, Any]:
            fallback_calls.append((method, params))
            return {"decision": "decline"}

        catalog = Tools([make_echo_tool("echo_text"), make_echo_tool("write_note", ToolPermission.WRITE)])
        handler = CodexToolBridge(catalog, PermissionPolicy()).handler(asyncio.get_running_loop(), fallback)
        self.assertIsInstance(handler, CodexToolCallHandler)

        call = {"threadId": "thr-1", "turnId": "turn-1", "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}}
        allowed = await asyncio.to_thread(handler.handle, "item/tool/call", call)
        self.assertEqual(allowed, {"success": True, "contentItems": [{"type": "inputText", "text": "echo: hi"}]})

        denied = await asyncio.to_thread(handler.handle, "item/tool/call", {**call, "callId": "call-2", "tool": "write_note"})
        self.assertFalse(denied["success"])
        self.assertIn("Permission denied for tool 'write_note' requiring write", denied["contentItems"][0]["text"])

        approval = {"threadId": "thr-1", "itemId": "item-1"}
        answer = await asyncio.to_thread(handler.handle, "item/commandExecution/requestApproval", approval)
        self.assertEqual(answer, {"decision": "decline"})
        self.assertEqual(fallback_calls, [("item/commandExecution/requestApproval", approval)])


if __name__ == "__main__":
    unittest.main()
