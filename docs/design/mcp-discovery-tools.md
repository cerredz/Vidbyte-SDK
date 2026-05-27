# Design Doc: MCP Discovery Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This feature adds two new built-in tools — `SearchMcpServersTool` and `AttachMcpServerTool` — to the `vidbyte/tools/builtins/mcp/` namespace. When added to an agent's tool list, these tools allow the agent to autonomously discover MCP servers from the global Smithery registry (via `registry.smithery.ai`) and attach them to itself at runtime, causing their bridged tools to appear in subsequent agent loop iterations. This closes the gap between static developer-configured MCP attachment and fully dynamic, model-driven MCP expansion.

---

## 2. Goals & Non-Goals

### Goals
- Provide a `SearchMcpServersTool` that queries the Smithery global MCP registry and returns structured server metadata including a ready-to-use command.
- Provide an `AttachMcpServerTool` that calls `agent.attach_mcp_server()` on its owning agent at runtime, bridging the discovered server's tools into the agent's live tool catalog.
- Follow the existing `bind_context_getter` agent-binding pattern so both tools compose naturally with `BaseAgent.add_tool()`.
- Use the existing `HttpTransport` from `vidbyte.lib.http.transport` — no new HTTP dependencies.
- Write tests using `unittest.IsolatedAsyncioTestCase`, consistent with the existing test suite.

### Non-Goals
- Support for SSE/HTTP MCP transports (only stdio is supported by the existing transport layer).
- Support for a developer-provided local catalog as a supplement to Smithery — Smithery only for this iteration.
- Pagination across multiple Smithery result pages — a single page of results (configurable limit, default 10) is sufficient.
- Persisting or caching Smithery responses between agent turns.
- Attaching multiple servers in a single `attach_mcp_server` tool call — one server per call keeps the tool atomic and rollback-safe.

---

## 3. Background & Context

The existing `McpAttachableMixin` gives developers three ways to attach MCP servers to an agent: `attach_mcp_server()` (immediate async), `attach_mcp_servers()` (concurrent batch), and `with_mcp_server()` (lazy). All three require the developer to know the server command before constructing the agent.

The missing capability is agent-driven discovery: the model itself identifying that it needs a new capability, searching for the right MCP server, and dynamically expanding its own tool set mid-run — without the developer hardcoding the command upfront. This is especially valuable in agentic loops where the required tools are not known at agent construction time.

Newly attached tools appear in the model's context on the next LLM call within the agentic loop (not the current one), because tool specs are serialized at the start of each loop iteration. This is expected and correct behavior.

---

## 4. Requirements

### Functional Requirements

1. `SearchMcpServersTool` must accept a `query` string parameter and an optional `limit` integer parameter (default 10, max 25).
2. `SearchMcpServersTool` must query `https://registry.smithery.ai/servers?q={query}&pageSize={limit}` using `HttpTransport`.
3. `SearchMcpServersTool` must return a JSON string containing an array of objects, each with `name`, `description`, and `command` fields. The `command` field must be a JSON array string ready to pass directly to `AttachMcpServerTool`.
4. `SearchMcpServersTool` must derive the `command` from the Smithery `qualifiedName` field as `["npx", "-y", "{qualifiedName}"]`.
5. `SearchMcpServersTool` must return a `ToolResult.error()` (not raise an exception) when the HTTP request fails, times out, or returns a non-200 response.
6. `SearchMcpServersTool` must return a `ToolResult.success()` with an empty array `[]` when Smithery returns zero results — not an error.
7. `AttachMcpServerTool` must accept a `command` parameter as a JSON-encoded string (e.g., `'["npx", "-y", "@mcp/server-filesystem", "/tmp"]'`) and parse it into a list of strings.
8. `AttachMcpServerTool` must accept optional `name` (string), `permission` (string: `"execute"`, `"readonly"`, or `"disabled"`), and `timeout` (number, default 30.0) parameters.
9. `AttachMcpServerTool` must call `await self._agent.attach_mcp_server(command=[...])` on its bound agent and return a `ToolResult.success()` containing a JSON summary of the bridged tool names.
10. `AttachMcpServerTool` must expose a `bind_agent(agent)` method that stores an agent reference. If `execute()` is called without a bound agent, it must return `ToolResult.error()`.
11. `BaseAgent._bind_agent_tool_context()` must be modified to detect `AttachMcpServerTool` instances and call `tool.bind_agent(self)` when they are added via `add_tool()`.
12. Both tools must be exported from `vidbyte.tools.builtins.mcp` and re-exported from `vidbyte.tools.builtins`.

### Non-Functional Requirements

- **Latency**: Smithery search calls block the event loop briefly since `HttpTransport` is synchronous; they must be offloaded with `asyncio.to_thread()` to avoid starving the event loop during agentic execution.
- **Security**: The `command` parameter in `AttachMcpServerTool` is parsed by the tool — the model supplies a JSON array string. The tool must validate that the parsed value is a non-empty list of strings before passing it to the attach machinery. Empty commands or non-string elements must return `ToolResult.error()`.
- **Reliability**: Smithery HTTP failures must be surfaced as `ToolResult.error()` output so the model can reason about the failure and try an alternative, rather than crashing the agentic loop.
- **Observability**: Both tools must include a `source` metadata key in their `ToolResult` so callers can distinguish MCP discovery results from other tool outputs.

---

## 5. High-Level Design

Two new `BaseTool` subclasses are created in a new `vidbyte/tools/builtins/mcp/` subpackage. `SearchMcpServersTool` owns a `SmitheryRegistryClient` helper class that wraps `HttpTransport` and handles the Smithery API contract (request construction, JSON parsing, command derivation). `AttachMcpServerTool` holds an optional `_agent` reference injected via `bind_agent()` and delegates to the existing `McpAttachableMixin.attach_mcp_server()` machinery.

The agent-binding mechanism follows the exact pattern already established by `AgentTool` and `StrategyTool`. A single `isinstance` check for `AttachMcpServerTool` is added to `BaseAgent._bind_agent_tool_context()`, calling `tool.bind_agent(self)`. No new base classes or protocols are introduced — the pattern is already proven.

```
Developer adds SearchMcpServersTool and AttachMcpServerTool to agent
  → add_tool() detects AttachMcpServerTool, calls tool.bind_agent(agent)

Agent turn N:
  Model calls search_mcp_servers(query="filesystem")
    → SmitheryRegistryClient.search()
    → asyncio.to_thread(HttpTransport.request, GET registry.smithery.ai/servers?q=...)
    → parse response, derive commands
    → ToolResult.success(json([{name, description, command}, ...]))

  Model calls attach_mcp_server(command='["npx", "-y", "@mcp/server-filesystem", "/tmp"]')
    → parse JSON command
    → await self._agent.attach_mcp_server(command=[...])
    → McpStdioTransport → McpClient → McpToolBridge
    → tools added to agent._agent_tool_items and agent.tools

Agent turn N+1:
  LLM call includes read_file, write_file, list_directory in tool list
  Model can invoke these as native tools
```

The `HttpTransport` is synchronous (stdlib `urllib`) so `asyncio.to_thread()` is used inside `execute()` to avoid blocking the event loop. This is consistent with Python 3.11+ (required by `pyproject.toml`) and requires no new dependencies.

---

## 6. Detailed Design

### 6.1 SmitheryRegistryClient

**File:** `vidbyte/tools/builtins/mcp/search.py`
**Type:** New file

#### What it does
Encapsulates all Smithery API communication: constructs the request URL, sends it via `HttpTransport`, parses the JSON response, and converts each `qualifiedName` into a usable command list.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class SmitheryServerResult:
    name: str
    description: str
    command: list[str]   # ["npx", "-y", qualifiedName]
    qualified_name: str

class SmitheryRegistryClient:
    REGISTRY_URL = "https://registry.smithery.ai/servers"

    def __init__(self, transport: HttpTransport | None = None, *, timeout: float = 10.0) -> None: ...

    def search(self, query: str, *, limit: int = 10) -> list[SmitheryServerResult]: ...
    # synchronous — caller wraps with asyncio.to_thread()

    def _build_url(self, query: str, limit: int) -> str: ...
    def _send_request(self, url: str) -> dict[str, Any]: ...
    def _parse_servers(self, data: dict[str, Any]) -> list[SmitheryServerResult]: ...
    def _derive_command(self, qualified_name: str) -> list[str]: ...
```

#### Logic / Algorithm
1. `search(query, limit)` calls `_build_url()` to produce `https://registry.smithery.ai/servers?q={encoded_query}&pageSize={limit}`.
2. Calls `_send_request(url)` which uses `self._transport.request(method="GET", url=url, headers={"Accept": "application/json"}, timeout_seconds=self._timeout)`.
3. If `response.status_code != 200`, raises `ValueError(f"Smithery returned {status_code}")` — caller converts to `ToolResult.error()`.
4. Parses `response.body` as JSON, extracts the `servers` list (defaulting to `[]` for missing keys).
5. Calls `_parse_servers()` which iterates server dicts, extracts `qualifiedName`, `displayName`, `description`, and calls `_derive_command()`.
6. `_derive_command(qualified_name)` returns `["npx", "-y", qualified_name]`.
7. Skips entries where `qualifiedName` is empty or missing.

#### Edge Cases & Error Handling
- Smithery returns `{}` with no `servers` key → `_parse_servers` defaults to `[]`, returns empty list.
- Smithery returns malformed JSON → `json.loads` raises `ValueError` → propagated to caller.
- HTTP timeout → `HttpTransport` raises `ProviderRequestError` → propagated to caller.
- `qualifiedName` is empty string → entry is skipped in `_parse_servers`.
- `limit` > 25 → clamped to 25 inside `search()` to avoid abusing the API.

---

### 6.2 SearchMcpServersTool

**File:** `vidbyte/tools/builtins/mcp/search.py`
**Type:** New file (same file as SmitheryRegistryClient)

#### What it does
Exposes Smithery search as a `BaseTool` the model can invoke. Offloads the synchronous HTTP call to a thread pool, then formats results as a JSON string for model consumption.

#### Interface / API
```python
class SearchMcpServersTool(BaseTool):
    def __init__(self, *, client: SmitheryRegistryClient | None = None, timeout: float = 10.0) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    async def _run_search(self, query: str, limit: int) -> list[SmitheryServerResult]: ...
    def _format_results(self, results: list[SmitheryServerResult]) -> str: ...
```

#### Logic / Algorithm
1. `spec()` returns `ToolSpec(name="search_mcp_servers", ...)` with parameters:
   - `query` (string, required): keywords to search for in the Smithery registry.
   - `limit` (integer, optional, default 10): max number of results to return.
2. `execute(call)` extracts `query` and `limit` from `call.arguments`.
3. Validates `query` is non-empty string; returns `ToolResult.error()` if blank.
4. Clamps `limit` to `[1, 25]`.
5. Calls `await self._run_search(query, limit)`.
6. `_run_search()` uses `await asyncio.to_thread(self._client.search, query, limit=limit)` to avoid blocking the event loop.
7. On any exception from `_run_search`, returns `ToolResult.error(self.name, f"Smithery search failed: {exc}", metadata={"source": "smithery"})`.
8. Calls `_format_results()` which `json.dumps` the list of dicts and returns it.
9. Returns `ToolResult.success(self.name, formatted_json, metadata={"source": "smithery", "result_count": len(results)})`.

#### Output format (model-facing)
```json
[
  {
    "name": "Filesystem",
    "description": "Read and write local files securely.",
    "qualified_name": "@modelcontextprotocol/server-filesystem",
    "command": "[\"npx\", \"-y\", \"@modelcontextprotocol/server-filesystem\"]"
  }
]
```

The `command` field is a JSON-encoded string, ready to pass directly as the `command` argument to `attach_mcp_server`.

#### Edge Cases & Error Handling
- Empty query → `ToolResult.error()` before any HTTP call.
- Zero search results → `ToolResult.success()` with `[]` (not an error).
- Smithery unavailable → `ToolResult.error()` with message from exception.
- `limit` < 1 → clamped to 1.

---

### 6.3 AttachMcpServerTool

**File:** `vidbyte/tools/builtins/mcp/attach_tool.py`
**Type:** New file

#### What it does
Gives the model a tool call surface to invoke `agent.attach_mcp_server()` on the owning agent. Parses the `command` JSON string, validates it, and delegates to the existing `McpAttachableMixin` machinery. Returns a summary of what was bridged.

#### Interface / API
```python
class AttachMcpServerTool(BaseTool):
    def __init__(self) -> None: ...
    def bind_agent(self, agent: McpAttachableMixin) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _parse_command(self, raw: str) -> list[str]: ...
    def _parse_permission(self, raw: str) -> McpToolPermission: ...
    def _format_summary(self, server_name: str, tool_names: tuple[str, ...]) -> str: ...
```

#### Logic / Algorithm
1. `bind_agent(agent)` stores `self._agent = agent`.
2. `spec()` returns `ToolSpec(name="attach_mcp_server", permission=ToolPermission.EXECUTE, ...)` with parameters:
   - `command` (string, required): JSON array of command parts, e.g. `'["npx", "-y", "@mcp/server-filesystem", "/tmp"]'`.
   - `name` (string, optional): human-readable name for this server.
   - `permission` (string, optional, default `"execute"`): `"execute"`, `"readonly"`, or `"disabled"`.
   - `timeout` (number, optional, default `30.0`): seconds to wait for handshake.
3. `execute(call)` first checks `self._agent is None`; if so, returns `ToolResult.error()`.
4. Calls `_parse_command(raw)` which `json.loads` the string and validates it is a non-empty list of strings. Returns `ToolResult.error()` on validation failure.
5. Calls `_parse_permission(raw)` which maps string → `McpToolPermission` enum, defaulting to `EXECUTE`.
6. Records `before_count = len(self._agent.mcp_servers())` to identify the newly added handle.
7. Calls `await self._agent.attach_mcp_server(command=command, name=name, permission=permission, timeout=timeout)`.
8. Retrieves the new handle via `self._agent.mcp_servers()[-1]`.
9. On `McpError` or any exception, returns `ToolResult.error(self.name, str(exc), metadata={"source": "mcp_attach"})`.
10. Calls `_format_summary(handle.name, handle.tool_names)` which returns a JSON string `{"attached": true, "server_name": ..., "tools_added": [...]}`.
11. Returns `ToolResult.success(self.name, summary, metadata={"source": "mcp_attach", "tool_count": len(handle.tool_names)})`.

#### Edge Cases & Error Handling
- `bind_agent()` not called → `ToolResult.error("attach_mcp_server", "No agent bound to this tool.")`.
- `command` is not valid JSON → `ToolResult.error()` with parse error.
- `command` parses to empty list → `ToolResult.error()`.
- `command` contains non-string elements → `ToolResult.error()`.
- MCP server subprocess fails to start → `McpConnectionError` caught → `ToolResult.error()`.
- MCP handshake times out → `McpInitializeError` caught → `ToolResult.error()`.

---

### 6.4 vidbyte/tools/builtins/mcp/__init__.py

**File:** `vidbyte/tools/builtins/mcp/__init__.py`
**Type:** New file

Exports `SearchMcpServersTool`, `AttachMcpServerTool`, and `SmitheryRegistryClient` from the subpackage.

---

### 6.5 vidbyte/tools/builtins/__init__.py

**File:** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

Adds imports and `__all__` entries for `SearchMcpServersTool` and `AttachMcpServerTool`.

---

### 6.6 vidbyte/agents/base.py — _bind_agent_tool_context

**File:** `vidbyte/agents/base.py`
**Type:** Modified

Adds an `isinstance` check for `AttachMcpServerTool` in `_bind_agent_tool_context()`, calling `tool.bind_agent(self)`.

---

## 7. Data Model Changes

### 7.1 SmitheryServerResult

**Change type:** New — local dataclass inside `vidbyte/tools/builtins/mcp/search.py`. Not added to `vidbyte/lib/dataclasses/` as it is internal to the tool only.

---

## 8. API Changes

N/A — this feature adds two tool classes; there are no HTTP API endpoints owned by this SDK.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/builtins/mcp/__init__.py` | New subpackage init exporting both tools |
| CREATE | `vidbyte/tools/builtins/mcp/search.py` | `SmitheryRegistryClient` + `SearchMcpServersTool` |
| CREATE | `vidbyte/tools/builtins/mcp/attach_tool.py` | `AttachMcpServerTool` with `bind_agent()` |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Add exports for both new tools |
| MODIFY | `vidbyte/agents/base.py` | Detect `AttachMcpServerTool` in `_bind_agent_tool_context` |
| CREATE | `tests/test_mcp_discovery_tools.py` | All unit and integration tests |

---

## 10. Testing Plan

### Unit Tests

- `SearchMcpServersToolTests` → `test_returns_empty_list_when_smithery_returns_no_servers` — [Edge Case]
- `SearchMcpServersToolTests` → `test_blank_query_returns_error_before_http_call` — [Hidden Assumption]
- `SearchMcpServersToolTests` → `test_smithery_http_failure_returns_tool_result_error_not_exception` — [Silent Failure]
- `SearchMcpServersToolTests` → `test_smithery_non_200_returns_error` — [Hidden Failure]
- `SearchMcpServersToolTests` → `test_command_field_is_json_encoded_npx_string` — [Silent Failure]
- `SearchMcpServersToolTests` → `test_limit_clamped_to_25` — [Edge Case]
- `SearchMcpServersToolTests` → `test_entries_with_empty_qualified_name_skipped` — [Hidden Failure]
- `SmitheryRegistryClientTests` → `test_malformed_json_response_raises_value_error` — [Hidden Assumption]
- `AttachMcpServerToolTests` → `test_execute_without_bind_returns_error` — [Hidden Assumption]
- `AttachMcpServerToolTests` → `test_invalid_json_command_returns_error` — [Edge Case]
- `AttachMcpServerToolTests` → `test_empty_command_list_returns_error` — [Edge Case]
- `AttachMcpServerToolTests` → `test_non_string_elements_in_command_returns_error` — [Hidden Assumption]
- `AttachMcpServerToolTests` → `test_successful_attach_returns_tool_names_in_summary` — [Silent Failure]
- `AttachMcpServerToolTests` → `test_mcp_connection_error_returns_tool_result_error_not_exception` — [Silent Failure]
- `AttachMcpServerToolTests` → `test_permission_string_maps_correctly` — [Silent Failure]
- `AgentBindingTests` → `test_add_tool_binds_agent_to_attach_tool` — [Hidden Assumption]
- `AgentBindingTests` → `test_search_tool_does_not_require_binding` — [Hidden Assumption]
- `AgentBindingTests` → `test_constructor_tools_list_also_binds_agent` — [Hidden Failure]

### Integration Tests

- Happy path: mocked Smithery + mocked MCP subprocess. Search → attach → verify tool list grows.
- Silent failure: Smithery returns server with missing `displayName` → falls back to `qualifiedName` not `None`.

### Manual / QA Test Cases

1. Given agent with `SearchMcpServersTool`, when calling `search_mcp_servers(query="github")`, then response contains at least one entry with valid `command` field. — [Hidden Failure]
2. Given agent with both tools, when `attach_mcp_server` called with filesystem server command, then `agent.mcp_servers()` grows by 1. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Smithery Registry | `https://registry.smithery.ai/servers` | Global MCP server search | API may rate-limit or change schema |
| `vidbyte.lib.http.transport.HttpTransport` | Internal (stdlib urllib) | HTTP GET to Smithery | Synchronous, must be thread-offloaded |
| `asyncio.to_thread` | Python 3.9+ (stdlib) | Non-blocking HTTP in async execute | Safe on Python 3.11+ |
| `vidbyte.tools.mcp.attach.attach_mcp_server` | Internal | MCP subprocess lifecycle | Existing, tested, stable |

---

## 12. Rollout & Deployment

- No breaking changes. Both tools are additive.
- No feature flags. Tools are opt-in — developers must explicitly add them to an agent.
- No migration needed.
- Rollback: remove the three new files, revert the two modified files.

---

## 13. Open Questions

- [ ] Should Smithery API calls include an `Authorization` header or API key in future?
- [ ] Should `AttachMcpServerTool` return newly bridged tool names only, or all MCP tool names on the agent?
- [ ] When tool name collisions occur on attach, should the error message identify the conflicting names?

---

## 14. Alternatives Considered

### Alternative 1: Developer-provided local catalog
- What: `SearchMcpServersTool` filters a developer-supplied list at construction time.
- Why rejected: Requires developer to maintain catalog. Defeats model-driven discovery goal.

### Alternative 2: AgentBound protocol instead of isinstance check
- What: A shared `AgentBound` protocol with `bind_agent()` checked via `hasattr`.
- Why rejected: Existing codebase uses explicit `isinstance` for `AgentTool`/`StrategyTool`. Introducing a protocol now is inconsistent.

### Alternative 3: Single combined McpDiscoveryTool
- What: One tool with a `mode` parameter (`"search"` or `"attach"`).
- Why rejected: Violates single-responsibility; harder for models to reason about.

### Alternative 4: aiohttp / httpx for async HTTP
- What: Add native async HTTP dependency.
- Why rejected: `pyproject.toml` has only `pydantic`. `asyncio.to_thread` achieves the same result with zero new deps.
