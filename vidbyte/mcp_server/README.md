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

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). The same agent, prompt, and tool
surfaces that support website workflows can be exposed to MCP-compatible clients
when developers want local or editor-integrated access.

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

Expose prompt content explicitly when a project owns custom prompt assets:

```python
from vidbyte import McpStudioServer, Prompts

prompts = Prompts()
server = McpStudioServer(
    agents={"analyst": analyst_agent},
    tools=[lookup_metric],
    prompt_content={key.value: text for key, text in prompts.all().items()},
)
```

## Feature Coverage

- Stdio JSON-RPC server loop for MCP clients that launch subprocesses.
- `initialize`, `tools/list`, `tools/call`, `prompts/list`, and `prompts/get` handlers.
- Studio tools for listing and running agents, listing and calling tools, listing strategies, fetching prompts, and listing pipelines.
- SDK `ToolSpec` to MCP `inputSchema` translation.
- SDK `ToolResult` to MCP content conversion.
- Programmatic server construction for project-local agents, tools, pipelines, and prompts.
- Error response helpers for JSON-RPC parse, invalid request, method, parameter, and internal failures.

## Key Modules

- `server/core.py`: stdio read-dispatch-write loop and `McpStudioServer`.
- `server/handlers/`: JSON-RPC method handlers.
- `schema.py`: SDK-to-MCP schema conversion helpers.
- `handlers.py`: Studio tool registry for agents, tools, prompts, strategies, and pipelines.

## Related Layers

The MCP server publishes [`agents`](../agents/README.md), [`tools`](../tools/README.md),
[`prompts`](../prompts/README.md), and [`pipelines`](../pipelines/README.md).
