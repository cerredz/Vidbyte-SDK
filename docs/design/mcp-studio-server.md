# Design Doc: MCP Studio Server

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-25
**Last Updated:** 2026-05-25

---

## 1. Overview

Add MCP **server** capabilities to the Vidbyte SDK so that external MCP-compatible clients (Codex, Claude Code, OpenAI Agents SDK, etc.) can discover and invoke Vidbyte's agent/tool/strategy/pipeline management as MCP tools via stdio transport. Currently the SDK only has MCP **client** capabilities (connecting TO external MCP servers). This feature creates the reverse — the SDK itself becomes a consumable MCP server, analogous to how Codex exposes its CLI via `codex --mcp-server`.

---

## 2. Goals & Non-Goals

### Goals

- Expose a stdio-based MCP server that external clients can spawn and communicate with via JSON-RPC over stdin/stdout
- Expose SDK capabilities as MCP tools: `studio.agents.list`, `studio.agents.run`, `studio.tools.list`, `studio.strategies.list`, `studio.strategies.run`, `studio.prompts.list`, `studio.pipelines.list`
- Support programmatic construction (pass in agents, tools, strategies) AND a CLI entry point (`python -m vidbyte.mcp_server`)
- Match existing code conventions: Context Protocol Header, no external MCP dependency, same transport and error patterns as `vidbyte/tools/mcp/`
- Handle clean shutdown on stdin close, SIGTERM, or client disconnect

### Non-Goals

- SSE/Streamable HTTP transports (stdio only, matching existing SDK conventions)
- Resources or resource templates (MCP protocol extensions beyond tools/prompts)
- Automatic persistence of agents/tools between server restarts
- Multi-client support (single-client-per-process by design, per MCP spec)
- OAuth or authentication (runs as a local process)

---

## 3. Background & Context

The Vidbyte SDK currently implements the MCP client side (`vidbyte/tools/mcp/`) with self-contained JSON-RPC over subprocess stdio — no external `mcp` package dependency. The main Vidbyte web app (`vidbyte/backend/lib/agentic/mcp_server.py`) uses the third-party `mcp` package for its server-side MCP.

This design adds a minimal, zero-dependency MCP server to the SDK itself, modeled after:
- **Codex `--mcp-server`**: Exposes CLI capabilities as MCP tools
- **OpenAI Agents SDK `MCPServerStdio`**: The consumer pattern that would spawn this server
- **Existing `vidbyte/tools/mcp/transport.py`**: Reuse the same JSON-RPC line-delimited protocol

The relationship is:

```
External MCP Client (Codex / Claude / OpenAI Agents SDK)
    |
    | spawns subprocess: python -m vidbyte.mcp_server
    | JSON-RPC via stdin/stdout
    v
McpStudioServer (NEW — this feature)
    |
    | wraps
    v
Vidbyte SDK (agents, tools, strategies, prompts, pipelines)
```

---

## 4. Requirements

### Functional Requirements

1. `McpStudioServer` class that accepts a dict of named agents, a list of tools, and optionally strategies/prompts/pipelines on construction
2. `McpStudioServer.run()` async method that starts the stdio MCP server loop (reads JSON-RPC from stdin, writes responses to stdout)
3. MCP `initialize` handshake returning server capabilities (`tools`, `prompts`)
4. MCP `tools/list` returning SDK tool definitions (built-in tools + injected studio tools)
5. MCP `tools/call` executing the named tool and returning content
6. MCP `prompts/list` returning available prompt definitions
7. MCP `prompts/get` returning prompt content for a given name
8. CLI entry point `python -m vidbyte.mcp_server` that constructs a default server and runs it
9. Graceful shutdown when stdin closes or on SIGTERM
10. All errors surfaced as MCP error responses, not unhandled exceptions

### Non-Functional Requirements

- **No new mandatory dependencies**: Server transport uses `asyncio` and `json` (stdlib only)
- **Line-delimited JSON-RPC**: Same protocol as existing `McpStdioTransport`
- **Response latency < 500ms** for tool listing
- **Concurrent-safe**: Single client, but tool execution is async

---

## 5. High-Level Design

The feature adds a new `vidbyte/mcp_server/` package (parallel to `vidbyte/tools/mcp/`) that contains the server implementation. This is kept separate from the client-side MCP code to avoid confusion — the client package consumes MCP servers, the server package produces one.

### Architecture

```
vidbyte/mcp_server/
    __init__.py          # Exports McpStudioServer
    server.py            # McpStudioServer class + run loop
    handlers.py          # Tool/prompt handler registries and wiring
    schema.py            # MCP tool definition converters (SDK ToolSpec -> MCP schema)

tests/
    test_mcp_studio_server.py  # Full integration tests with fake stdin/stdout
```

### Data Flow

```
Client (stdin) --> JSON-RPC request --> McpStudioServer._dispatch()
    |
    | method routing
    v
handlers.py  -->  call SDK tool  -->  ToolResult
    |
    v
JSON-RPC response --> Client (stdout)
```

---

## 6. Detailed Design

### 6.1 McpStudioServer

**File(s):** `vidbyte/mcp_server/server.py`
**Type:** New file

#### What it does

Core MCP server class. Owns the tool registry, prompt registry, and the asyncio stdio read/write loop. Implements the full MCP server lifecycle: initialize handshake, request dispatch, graceful shutdown.

#### Interface / API

```python
class McpStudioServer:
    def __init__(
        self,
        *,
        name: str = "vidbyte-sdk-studio",
        version: str = "0.1.0",
        agents: Mapping[str, BaseAgent] | None = None,
        tools: Sequence[BaseTool] = (),
        strategies: Sequence[BaseStrategy] | None = None,
        pipelines: Sequence[BasePipeline] | None = None,
    ) -> None: ...

    async def run(self) -> None: ...
    async def close(self) -> None: ...
```

#### Logic / Algorithm

1. On `__init__`, create internal tool and prompt registries:
   a. Inject built-in studio tools: `studio.agents.list`, `studio.agents.run`, `studio.tools.list`, `studio.strategies.list`, `studio.strategies.run`, `studio.prompts.list`, `studio.pipelines.list`
   b. If `agents` provided, register them by name
   c. Add any caller-supplied `tools` to the tool registry
2. On `run()`:
   a. Attach `asyncio.StreamReader` to `sys.stdin.buffer`
   b. Loop reading one line at a time
   c. Parse JSON-RPC request: `{"jsonrpc": "2.0", "id": N, "method": "...", "params": {...}}`
   d. Route to handler based on method
   e. Write JSON-RPC response to `sys.stdout.buffer`
   f. On blank line or stdin EOF, break loop and shut down
3. On `close()`, set a shutdown flag so the read loop exits cleanly

#### Edge Cases & Error Handling

- Invalid JSON: Return JSON-RPC error with code `-32700` (Parse error)
- Unknown method: Return JSON-RPC error with code `-32601` (Method not found)
- Tool execution failure: Return MCP error in `tools/call` response with `isError: true`
- Stdin closes: Exit loop, no error

---

### 6.2 Tool/Prompt Handlers

**File(s):** `vidbyte/mcp_server/handlers.py`
**Type:** New file

#### What it does

Implements the actual logic behind each MCP tool. Converts MCP tool call arguments into SDK tool operations and formats results back into MCP content types.

#### Studio Tools

Each is a `BaseTool` subclass with explicit spec:

| Tool Name | Parameters | Behavior |
|-----------|-----------|----------|
| `studio.agents.list` | `filter_name` (optional) | Returns JSON array of AgentCards for all registered agents |
| `studio.agents.run` | `agent_name`, `prompt`, `modality` (optional) | Runs named agent, returns response |
| `studio.tools.list` | `category` (optional) | Returns JSON array of tool specs |
| `studio.strategies.list` | none | Returns JSON array of strategy names/descriptions |
| `studio.strategies.run` | `strategy_name`, `prompt` | Executes named strategy, returns result |
| `studio.prompts.list` | `family` (optional) | Returns JSON array of prompt keys/families |
| `studio.pipelines.list` | none | Returns JSON array of pipeline type names |

#### Interface

```python
class StudioToolRegistry:
    """Collects and manages studio tools."""
    def __init__(self, server: McpStudioServer) -> None: ...
    def all_tools(self) -> tuple[BaseTool, ...]: ...
    def find_tool(self, name: str) -> BaseTool | None: ...
    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...

class StudioPromptRegistry:
    """Collects and manages prompt definitions."""
    def __init__(self) -> None: ...
    def list_prompts(self) -> list[dict[str, Any]]: ...
    def get_prompt(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]: ...
```

---

### 6.3 MCP Schema Converters

**File(s):** `vidbyte/mcp_server/schema.py`
**Type:** New file

#### What it does

Converts SDK `ToolSpec` and `ToolParameter` definitions into MCP-compliant `inputSchema` (JSON Schema subset). Mirrors the reverse conversion already done in `McpBridgedTool._parameters`.

#### Interface

```python
def tool_spec_to_mcp_tool(spec: ToolSpec) -> dict[str, Any]:
    """Convert a ToolSpec into an MCP tools/list entry dict."""
    ...

def mcp_error_response(request_id: int | str, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response dict."""
    ...

def mcp_result_response(request_id: int | str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response dict."""
    ...
```

---

### 6.4 CLI Entry Point

**File(s):** `vidbyte/mcp_server/__main__.py`
**Type:** New file

#### What it does

Provides `python -m vidbyte.mcp_server` entry point. Constructs a default `McpStudioServer` with empty registries (callers can also instantiate programmatically to inject agents/tools).

#### Logic

```python
# __main__.py
import asyncio
from vidbyte.mcp_server import McpStudioServer

def main() -> None:
    server = McpStudioServer()
    asyncio.run(server.run())

if __name__ == "__main__":
    main()
```

---

### 6.5 Package Exports

**File(s):** `vidbyte/mcp_server/__init__.py`
**Type:** New file

Exports `McpStudioServer`, studio tool classes, and schema converters for programmatic use.

---

## 7. Data Model Changes

### 7.1 No schema changes

N/A — this feature adds no database tables, no persistent storage, and no modifications to existing dataclasses.

---

## 8. API Changes

### 8.1 MCP Server Protocol (internal, not HTTP)

The server speaks the MCP JSON-RPC 2.0 protocol over stdio:

#### `initialize`

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "...", "version": "..."}
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "prompts": {}
    },
    "serverInfo": {"name": "vidbyte-sdk-studio", "version": "0.1.0"}
  }
}
```

#### `tools/list`

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "studio.agents.list",
        "description": "List all registered agents and their capabilities.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "filter_name": {"type": "string", "description": "Optional name filter."}
          }
        }
      }
    ]
  }
}
```

#### `tools/call`

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "studio.agents.run",
    "arguments": {"agent_name": "my-agent", "prompt": "Hello"}
  }
}
```

**Response (success):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{"type": "text", "text": "Hello from agent..."}]
  }
}
```

**Response (error):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{"type": "text", "text": "Agent 'unknown' not found."}],
    "isError": true
  }
}
```

**Error cases:**
| Code | Condition |
|------|-----------|
| -32700 | Invalid JSON |
| -32601 | Unknown method |
| -32602 | Invalid params |
| -32603 | Internal error (tool execution failure) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/mcp_server/__init__.py` | Package exports for McpStudioServer and studio tools |
| CREATE | `vidbyte/mcp_server/server.py` | Core McpStudioServer class with stdio JSON-RPC loop |
| CREATE | `vidbyte/mcp_server/handlers.py` | Studio tool implementations (agents.list, agents.run, etc.) |
| CREATE | `vidbyte/mcp_server/schema.py` | MCP schema converters (ToolSpec -> MCP, JSON-RPC responses) |
| CREATE | `vidbyte/mcp_server/__main__.py` | CLI entry point `python -m vidbyte.mcp_server` |
| CREATE | `tests/test_mcp_studio_server.py` | Tests for server lifecycle, tool dispatch, error handling |
| MODIFY | `vidbyte/__init__.py` | Export McpStudioServer from root |
| MODIFY | `pyproject.toml` | Add `[project.scripts]` entry point for `vidbyte-mcp-server` |

---

## 10. Testing Plan

### Unit Tests

All in `tests/test_mcp_studio_server.py` using `unittest.IsolatedAsyncioTestCase`:

- `test_server_initialize_handshake` — Client sends `initialize`, server responds with capabilities
- `test_server_tools_list` — After initialize, `tools/list` returns studio tool definitions
- `test_server_tools_call_agents_list` — `tools/call` for `studio.agents.list` returns agent cards
- `test_server_tools_call_agents_run` — `tools/call` for `studio.agents.run` returns agent output
- `test_server_tools_call_tools_list` — `tools/call` for `studio.tools.list` returns tool specs
- `test_server_prompts_list` — `prompts/list` returns prompt definitions
- `test_server_prompts_get` — `prompts/get` returns prompt content
- `test_server_invalid_json` — Malformed JSON returns parse error
- `test_server_unknown_method` — Unknown method returns method-not-found
- `test_server_unknown_tool` — Calling non-existent tool returns isError
- `test_server_shutdown_on_eof` — Server exits cleanly when stdin closes
- `test_server_external_tools` — User-injected tools appear in `tools/list` and can be called

### Integration Tests

- Test with a real stdio subprocess: spawn `python -m vidbyte.mcp_server`, send handshake, list tools, call a tool, verify response format
- Test with the OpenAI Agents SDK `MCPServerStdio` (if available)

### Manual / QA Test Cases

1. Run `python -m vidbyte.mcp_server` and type JSON-RPC requests manually at stdin
2. Verify the server prints JSON-RPC responses to stdout
3. Verify Ctrl+C cleanly shuts down

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` | stdlib | Async I/O for stdio server loop | None |
| `json` | stdlib | JSON-RPC serialization | None |
| `sys` | stdlib | stdin/stdout streams | None |
| (no external deps) | — | — | — |

No new external dependencies. The server is built entirely on Python stdlib, matching the pattern in `vidbyte/tools/mcp/transport.py`.

---

## 12. Rollout & Deployment

- **Feature flag:** Not required — this is an additive feature with no impact on existing paths
- **Breaking change:** No. Existing MCP client code is untouched
- **Deployment order:** Single PR, single package addition
- **Rollback:** Delete `vidbyte/mcp_server/` directory, revert `vidbyte/__init__.py`

---

## 13. Open Questions

- [ ] Should `studio.agents.run` execute agents inline (same process) or fork a subprocess? **Recommendation:** Inline for simplicity, same process.
- [ ] Should `McpStudioServer` support resource endpoints (`resources/list`, `resources/read`) for exposing context items? **Recommendation:** Defer to future PR — tools/prompts cover the primary use case.
- [ ] Should we add a `--tools-dir` CLI flag to load tools from a filesystem path? **Recommendation:** Defer — programmatic construction is more flexible.

---

## 14. Alternatives Considered

### Alternative 1: Use the third-party `mcp` Python package

- **What**: Depend on `pip install mcp` and use `mcp.server.Server` + `mcp.server.stdio.stdio_server`
- **Why rejected**: Adds an external dependency; the existing MCP client code is already self-contained and this matches that pattern. The server protocol is simple enough (~200 lines for the loop) to implement directly.

### Alternative 2: Merge server code into existing `vidbyte/tools/mcp/`

- **What**: Put server classes alongside client classes in `vidbyte/tools/mcp/`
- **Why rejected**: Confuses client vs server responsibilities. A separate `vidbyte/mcp_server/` package makes the distinction clear and follows the pattern used by the main Vidbyte app (`backend/lib/agentic/mcp_server.py`).

### Alternative 3: SSE/HTTP transport instead of stdio

- **What**: Serve MCP over HTTP+SSE instead of stdio
- **Why rejected**: Non-goal for this feature. Stdio matches how Codex and other tools spawn MCP servers, and is simpler to implement and test.
