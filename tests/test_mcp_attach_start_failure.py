"""Context Protocol Header

Description:
    Tests that attach_mcp_server reports an MCP server that cannot start as a connection
    failure, not as a failed handshake.
Purpose:
    Verifies the documented contract of attach_mcp_server: a subprocess that fails to start
    raises McpConnectionError, while a program that starts but does not speak MCP still raises
    McpInitializeError, so callers can tell the two apart.
Architecture:
    - McpAttachStartFailureTests: IsolatedAsyncioTestCase driving the real McpStdioTransport
      (no mocks) with a missing executable and with a real program that exits at once.
Relations:
    - vidbyte/tools/mcp/attach.py
    - vidbyte/tools/mcp/transport.py
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
