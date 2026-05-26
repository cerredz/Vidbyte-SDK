# Context Protocol Header

<!--
Description:
    A comprehensive guide and developer skill document detailing how to configure, 
    run, and register the Vidbyte SDK as a Model Context Protocol (MCP) server 
    across various agentic and IDE platforms.
Purpose:
    Enables external LLM agents (such as Claude Code, Codex, and Cursor) to natively 
    discover and execute Vidbyte agents, tools, prompts, strategies, and pipelines 
    over the stdio JSON-RPC transport.
Architecture:
    - Setup & Installation Guide.
    - Configuration instructions for Claude Code, Cursor, Windsurf, and Codex.
    - Programmatic injection instructions for custom agents and tools.
    - Diagnostic and verification steps.
Relations:
    - Directly details the usage of the vidbyte.mcp_server package introduced in PR #47.
    - Relates to the root package imports exported in vidbyte/__init__.py.
    - Companion to existing MCP client configurations.
-->

# Installing Vidbyte SDK as an MCP Server

This guide explains how to expose the Vidbyte SDK as a consumable **Model Context Protocol (MCP) Server**. By registering Vidbyte as an MCP server, any external, MCP-compliant client (such as Claude Code, Cursor, Windsurf, or Codex) can spawn Vidbyte in a subprocess and consume its agents, tools, prompts, and strategies directly as standard native tools.

---

## 1. Quick Start: Standard CLI (Out-of-the-Box)

If you only need to explore the SDK's built-in capabilities or retrieve standard prompt templates from the `Prompts()` catalog, you can run the server directly using the default CLI entry point.

### Prerequisites
Make sure the SDK is installed in your current Python environment:
```bash
pip install -e .
```

### Server Command
The default server command is:
```bash
vidbyte-mcp-server
```
*(Alternatively, you can run `python -m vidbyte.mcp_server`)*

> [!NOTE]
> Running the server directly in the terminal will start an interactive `stdio` loop. It will wait silently for line-delimited JSON-RPC messages. Do not run this indefinitely in a background shell; instead, let your MCP client launch and terminate it automatically.

---

## 2. Recommended Setup: Programmatic Launcher

Since your custom agents and tools are defined in your own Python codebase, the standard CLI won't automatically know about them. The recommended approach is to write a short launcher script that loads your custom assets and instantiates `McpStudioServer`.

Create a file named `run_studio.py` in your project root:

```python
# run_studio.py
import asyncio
from vidbyte import McpStudioServer
from my_project.agents import code_agent, research_agent
from my_project.tools import database_tool

async def main():
    # Instantiate the MCP studio server with your custom agents and tools
    server = McpStudioServer(
        name="my-vidbyte-studio",
        version="0.1.0",
        agents={
            "coder": code_agent,
            "researcher": research_agent
        },
        tools=[database_tool],
        strategy_names=["chain_of_thought", "react"],
        pipeline_names=["sequential"]
    )
    # Start the standard I/O communication loop
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. Registering the Server across Platforms

Since the server uses standard input/output (`stdio`) transport, configuring it is as simple as defining the executable command and arguments within your platform's configuration.

### A. Claude Code
Add the server definition to your global Claude Code configuration file (located at `~/.claude.json` or `.claudecode.json`):

```json
{
  "mcpServers": {
    "vidbyte-sdk-studio": {
      "command": "python",
      "args": ["path/to/run_studio.py"]
    }
  }
}
```

### B. Cursor IDE
To register the server visually in the Cursor desktop application:
1. Navigate to **Cursor Settings** (Gear icon in the top-right corner).
2. Go to **Features** -> **MCP**.
3. Click the **"+ Add New MCP Server"** button.
4. Set the parameters:
   * **Name**: `vidbyte-sdk-studio`
   * **Type**: `command`
   * **Command**: `python path/to/run_studio.py`
5. Click **Save**. The server status should immediately turn green, indicating a successful connection handshake.

### C. Windsurf IDE
For Windsurf, add your studio definition to the user's config file (usually found at `~/.codeium/windsurf/mcp_config.json`):

```json
{
  "mcpServers": {
    "vidbyte-sdk-studio": {
      "command": "python",
      "args": ["path/to/run_studio.py"]
    }
  }
}
```

### D. Codex / OpenCode
For terminal workflows using Codex, you can configure it via your global config file at `~/.codex/config.json`:

```json
{
  "mcp": {
    "servers": {
      "vidbyte-sdk-studio": {
        "command": "python",
        "args": ["path/to/run_studio.py"]
      }
    }
  }
}
```
Alternatively, you can launch Codex and attach the server on the fly:
```bash
codex --mcp-server "python path/to/run_studio.py"
```

---

## 4. Under the Hood: How the Agent Sees It

When an external LLM agent connects, the following flow occurs transparently in the background:

1. **Discovery (`tools/list`)**: The client automatically requests all available tools. The agent's context window gets injected with schemas for all default and injected tools (e.g., `studio.agents.list`, `studio.agents.run`, and custom schemas like `database_tool`).
2. **Execution (`tools/call`)**: When the agent executes `studio.agents.run`, it generates a JSON-RPC message. The local process receives this, runs the Python code for your agent, and pipes the string response back to the client. The output is directly appended to the external agent's conversation history as a standard tool result.
3. **Automatic Termination**: When the parent editor or CLI client terminates, the subprocess's standard input pipe is closed (EOF). The server immediately shuts down cleanly, requiring no manual process management.

---

## 5. Troubleshooting & Diagnostics

If your IDE or client fails to discover the tools:

1. **Verify your paths**: Ensure the path to `run_studio.py` in your configuration is absolute.
2. **Check for Python Errors**: Run your launcher script directly in the terminal:
   ```bash
   python path/to/run_studio.py
   ```
   If there are import errors or syntax issues, they will print to stderr, which would normally crash the MCP connection handshake.
3. **Manual Handshake Test**: You can manually verify the server by running it and pasting the following initialization request:
   ```json
   {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}}
   ```
   If working correctly, the server will immediately output a JSON-RPC response containing `capabilities: {tools: {}, prompts: {}}` and exit cleanly when you close the terminal session.
