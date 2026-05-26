"""Context Protocol Header

Description:
    CLI entry point for starting the MCP Studio Server via `python -m vidbyte.mcp_server`.
Purpose:
    Allows external tools to spawn the server as a stdio subprocess without writing
    custom Python code.
Architecture:
    - Constructs a default McpStudioServer with empty registries.
    - Runs the asyncio event loop until stdin closes.
Relations:
    Uses vidbyte.mcp_server.server.McpStudioServer.
"""

from __future__ import annotations

import asyncio

from vidbyte.mcp_server import McpStudioServer


def main() -> None:
    server = McpStudioServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
