"""FILE: tests/test_mcp_attach_start_failure.py

PURPOSE: Prove attach_mcp_server reports an MCP server that cannot start as McpConnectionError, not as a failed handshake.
ROLE IN CODEBASE: Drives the public vidbyte.tools.mcp.attach.attach_mcp_server with the real McpStdioTransport and no mocks.
ARCHITECTURE NOTE: The subprocess is spawned lazily by McpStdioTransport.start(), which attach now calls before the handshake.
COMMON MODIFICATION PATTERNS: Add a case when attach gains another documented failure; keep the McpInitializeError control.
KNOWN EDGE CASES: A program that starts and exits at once without speaking MCP must still raise McpInitializeError.
RELATED DOCS: vidbyte/tools/mcp/README.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.errors import McpConnectionError, McpError, McpInitializeError
from vidbyte.tools.mcp.attach import attach_mcp_server
from vidbyte.tools.mcp.types import McpServerConfig


class McpAttachStartFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_executable_raises_connection_error(self) -> None:
        config = McpServerConfig(command=("vidbyte-no-such-mcp-server-program",), timeout=10)

        with self.assertRaises(McpConnectionError) as caught:
            await attach_mcp_server(config)

        # The connection error is still an McpError, so broad MCP handlers keep catching it.
        self.assertIsInstance(caught.exception, McpError)
        self.assertNotIsInstance(caught.exception, McpInitializeError)

    async def test_program_that_starts_but_does_not_speak_mcp_raises_initialize_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "exit_at_once.py"
            script.write_text("pass\n", encoding="utf-8")
            config = McpServerConfig(command=(sys.executable, str(script)), timeout=10)

            with self.assertRaises(McpInitializeError):
                await attach_mcp_server(config)


if __name__ == "__main__":
    unittest.main()
