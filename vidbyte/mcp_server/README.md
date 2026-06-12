# MCP Server

The Vidbyte SDK can expose agents, tools, prompts, and pipelines through a
stdio Model Context Protocol server. This lets MCP-compatible clients launch a
Vidbyte Studio process and discover SDK capabilities through standard JSON-RPC
messages.

## Role In The SDK

`vidbyte.mcp_server` owns the `McpStudioServer` runtime and protocol schema
helpers. It converts SDK `ToolSpec` and `ToolResult` objects into MCP-compatible
tool list and tool call responses, and it routes MCP methods such as
`initialize`, `tools/list`, `tools/call`, `prompts/list`, and `prompts/get`.

## Design Philosophy

MCP support should be a boundary adapter, not a second agent framework. The SDK
keeps agent, tool, prompt, and pipeline logic in their native packages while the
server layer focuses on stdio transport, JSON-RPC dispatch, and schema
translation.

## Usage

Launch the default stdio server from an MCP client:

```bash
vidbyte-mcp-server
python -m vidbyte.mcp_server
```

Build a project-specific launcher when you want to expose local agents or tools:

```python
import asyncio
from vidbyte import McpStudioServer

async def main() -> None:
    server = McpStudioServer(
        name="my-vidbyte-studio",
        agents={"analyst": analyst_agent},
        tools=[lookup_metric],
        pipeline_names=["sequential", "parallel"],
    )
    await server.run()

asyncio.run(main())
```

## Key Modules

- `server/core.py`: stdio read-dispatch-write loop and `McpStudioServer`.
- `server/handlers/`: JSON-RPC method handlers.
- `schema.py`: SDK-to-MCP schema conversion helpers.
- `handlers.py`: Studio tool registry for agents, tools, prompts, strategies, and pipelines.

## Related Layers

The MCP server publishes [`agents`](../agents/README.md), [`tools`](../tools/README.md),
[`prompts`](../prompts/README.md), and [`pipelines`](../pipelines/README.md).
