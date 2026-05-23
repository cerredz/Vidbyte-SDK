# Design Doc: MCP Server Attachment

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-20  
**Last Updated:** 2026-05-20  

---

## 1. Overview

This feature delivers a developer-friendly API for attaching Model Context Protocol (MCP) servers to both `BaseAgent` and `BaseHarness` in the Vidbyte SDK. By encapsulating low-level stdio transport and client mechanics from PR #6, it automates lifecycle management (i.e. starting and cleanly shutting down subprocesses), integrates MCP-bridged tools into the existing capability and tool inspection surface (`AgentCard`), and supports sync-based builder patterns that defer connection until the agent or harness execution begins.

---

## 2. Goals & Non-Goals

### Goals

- **Automated Lifecycle Management:** Enforce cleanup of MCP subprocess stdio transports on teardown via context manager or explicit close.
- **Unified Interface (Symmetry):** Provide an identical, ergonomic API for attaching and configuring MCP servers on both `BaseAgent` and `BaseHarness`.
- **Integrated Tool Surface:** Ensure MCP-bridged tools are fully represented in tool lists, specs, and `AgentCard` capabilities for registry search parity.
- **Builder Pattern Support:** Provide a synchronous builder method `with_mcp_server` that registers server configurations and connects lazily on execution.
- **Fail-Safe Startup:** Concurrently connect multiple servers and guarantee that if any server fails, all successfully started ones are cleaned up.

### Non-Goals

- **SSE/Network Transports:** We do not implement SSE/HTTP-based MCP connections; only subprocess stdio transport is supported.
- **Dynamic Server Lifecycle Modification During Run:** We do not support adding/removing servers mid-execution; servers are attached before execution begins.
- **Platform-Level Sandboxing of Subprocess Commands:** The commands executed by MCP transports run under the developer's permissions.

---

## 3. Background & Context

PR #6 introduced the foundational MCP architecture (`McpStdioTransport`, `McpClient`, and `bridge_mcp_tools`). However, it left developers to manually instantiate transports, initialize clients, bridge tools, and manage the underlying subprocess lifecycles. This leads to leaked/orphan subprocesses, breaks abstraction barriers, and leaves `BaseHarness` without any MCP capabilities. This design solves those issues by creating a clean attachment mixin and lifecycle coordinator.

---

## 4. Requirements

### Functional Requirements

1. **Async Attach:** `await agent.attach_mcp_server(...)` must start the MCP process, perform the initialize handshake, discover remote tools, wrap them in `McpBridgedTool`, and add them to the agent's tools.
2. **Concurrent Multi-Server Attach:** `await agent.attach_mcp_servers(...)` must run connections concurrently. On any failure, it must shut down all newly started servers cleanly before propagating the error.
3. **Builder Pattern:** `agent.with_mcp_server(...)` must store the configuration and lazily start the connection before the first `generate_reply` or `harness.run` call.
4. **Guaranteed Cleanup:** Subclasses must support context managers (`async with`) to automatically close all attached MCP transports.
5. **AgentCard Parity:** `AgentCard` must reflect bridged tools in `tool_names` and expose the subset `mcp_tool_names` and `mcp_server_names` for indexing and filtering.
6. **Error Hierarchy:** Custom failures (`McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpAttachmentError`) must inherit from `VidbyteSdkError` and offer structured cause tracing.

### Non-Functional Requirements

- **Subprocess Startup Timeout:** Enforce an immutable or configurable timeout (default 30s) on handshakes to prevent blocking the event loop.
- **Leak Prevention:** Subprocess standard pipes must be closed on any handshake failure, ensuring no dangling file descriptors or zombies.

---

## 5. High-Level Design

The feature consists of three distinct layers layered on top of PR #6:

```text
┌──────────────────────────────────────────────────────────┐
│  DEVELOPER SURFACE                                       │
│  agent.attach_mcp_server(...)  /  .with_mcp_server(...)  │
│  harness.attach_mcp_server(...)                          │
│                                                          │
│  Provided by: McpAttachableMixin (agents/mixins.py)      │
├──────────────────────────────────────────────────────────┤
│  ATTACHMENT LOGIC                                        │
│  McpServerConfig, McpServerHandle, attach_mcp_server()   │
│                                                          │
│  Provided by: tools/mcp/attach.py                        │
├──────────────────────────────────────────────────────────┤
│  LOW-LEVEL PLUMBING (PR #6, unchanged)                   │
│  McpStdioTransport, McpClient, bridge_mcp_tools()        │
│                                                          │
│  Provided by: tools/mcp/transport.py, client.py          │
└──────────────────────────────────────────────────────────┘
```

1. **Core Types (`types.py`):** Holds configurations and active handles.
2. **Attachment Free Function (`attach.py`):** Implements safe, isolated subprocess connections.
3. **The Mixin (`mixins.py`):** Adds state tracking, builders, and lifecycle context managers to any class.
4. **SDK Subclasses (`base.py`):** Integrates the mixin into `BaseAgent` and `BaseHarness`.

---

## 6. Detailed Design

### 6.1 MCP Types Modification

**File(s):** `vidbyte/tools/mcp/types.py`  
**Type:** Modified  

#### What it does
Extends the existing file with enum and dataclasses for configuration and connection handle management.

#### Interface / API
```python
from enum import Enum
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Self
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpTransport
from vidbyte.tools.base import BaseTool

class McpToolPermission(str, Enum):
    EXECUTE  = "execute"
    READONLY = "readonly"
    DISABLED = "disabled"

@dataclass(frozen=True, slots=True)
class McpServerConfig:
    command: tuple[str, ...]
    name: str | None = None
    permission: McpToolPermission = McpToolPermission.EXECUTE
    env: Mapping[str, str] | None = None
    timeout: float = 30.0

@dataclass(slots=True)
class McpServerHandle:
    config: McpServerConfig
    client: McpClient
    transport: McpTransport
    bridged_tools: tuple[BaseTool, ...]

    async def close(self) -> None:
        await self.transport.close()

    @property
    def name(self) -> str:
        return self.config.name or " ".join(self.config.command[:2])

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(t.spec().name for t in self.bridged_tools)
```

---

### 6.2 Attachment Logic

**File(s):** `vidbyte/tools/mcp/attach.py`  
**Type:** New file  

#### What it does
Houses the free function `attach_mcp_server` to start and coordinate a single server connection.

#### Interface / API
```python
"""Context Protocol Header
Description:
    Implements standard free functions for connecting, discovery, and bridging
    individual remote MCP servers.
...
"""
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle

async def attach_mcp_server(config: McpServerConfig) -> McpServerHandle:
    ...
```

#### Logic / Algorithm
1. Instantiate `McpStdioTransport` with the command and environment.
2. Initialize `McpClient`.
3. Wrap handshake in `asyncio.timeout(config.timeout)`.
4. Call `bridge_mcp_tools` with a temporary `ToolRegistry` and the client.
5. On any error, call `await transport.close()` and propagate corresponding `McpError` variants.

---

### 6.3 Attachable Mixin

**File(s):** `vidbyte/agents/mixins.py`  
**Type:** New file  

#### What it does
Provides shared state management (`_mcp_handles`, `_pending_mcp_configs`) and developer attachment methods.

#### Interface / API
```python
"""Context Protocol Header
Description:
    Defines the McpAttachableMixin that adds lifecycle-managed MCP servers
    to agents and harnesses.
...
"""
from typing import Self, Sequence
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle, McpToolPermission

class McpAttachableMixin:
    _mcp_handles: list[McpServerHandle]
    _pending_mcp_configs: list[McpServerConfig]
    tools: list[Any]  # Target class tool list

    async def attach_mcp_server(self, command: Sequence[str], ...) -> Self: ...
    async def attach_mcp_servers(self, servers: Sequence[McpServerConfig]) -> Self: ...
    def with_mcp_server(self, command: Sequence[str], ...) -> Self: ...
    async def _ensure_mcp_connected(self) -> None: ...
    def mcp_servers(self) -> tuple[McpServerHandle, ...]: ...
    def mcp_tool_names(self) -> tuple[str, ...]: ...
    async def close_mcp_servers(self) -> None: ...
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *_: Any) -> None: ...
```

---

### 6.4 SDK Agent & Harness Integration

**File(s):** `vidbyte/agents/base.py`, `vidbyte/harnesses/base.py`  
**Type:** Modified  

#### What it does
Integrates `McpAttachableMixin` and hooks connections into execution paths.

#### Logic / Algorithm
- Hook `await self._ensure_mcp_connected()` at the top of:
  - `BaseAgent.generate_reply`
  - `BaseHarness.run`
  - `BaseHarness.arun`
- Convert `self.tools` from tuple to list on initialization to conform to standard mixin mutation paths.

---

### 6.5 Error Classes

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`  
**Type:** Modified  

#### What it does
Adds typed errors to inherit cleanly under `VidbyteSdkError`.

#### Interface / API
```python
class McpError(VidbyteSdkError):
    """Base class for all MCP errors."""

class McpConnectionError(McpError):
    """Subprocess start failures."""

class McpInitializeError(McpError):
    """Handshake/handshake timeout failures."""

class McpToolDiscoveryError(McpError):
    """Invalid tool definitions."""

class McpToolExecutionError(McpError):
    """Execution error responses."""

class McpAttachmentError(McpError):
    """Tracks composite attachment errors in batch connections."""
    def __init__(self, message: str, *, causes: list[Exception], details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.causes = causes
```

---

## 7. Data Model Changes

### 7.1 AgentCard Extension

**Change Type:** Modified (in `vidbyte/lib/dataclasses/agents.py`)

```python
@dataclass(frozen=True, slots=True)
class AgentCard:
    name: str
    role: AgentRole
    description: str
    system_prompt: str = ""
    capabilities: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    mcp_tool_names: tuple[str, ...] = ()    # NEW
    mcp_server_names: tuple[str, ...] = ()  # NEW
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

---

## 8. API Changes

N/A - This is an internal SDK change with no HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/__init__.py` | Export public types and errors |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export new exceptions |
| MODIFY | `vidbyte/lib/errors/base.py` | Add custom exception classes under `VidbyteSdkError` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `mcp_tool_names` and `mcp_server_names` to `AgentCard` |
| MODIFY | `vidbyte/tools/mcp/__init__.py` | Export new types, configs, and handles |
| MODIFY | `vidbyte/tools/mcp/types.py` | Implement `McpToolPermission`, `McpServerConfig`, `McpServerHandle` |
| CREATE | `vidbyte/tools/mcp/attach.py` | Implement free function `attach_mcp_server` |
| CREATE | `vidbyte/agents/mixins.py` | Implement attachable mixin `McpAttachableMixin` |
| MODIFY | `vidbyte/agents/base.py` | Inherit mixin, call lazy connect, convert tools |
| MODIFY | `vidbyte/harnesses/base.py` | Inherit mixin, call lazy connect, convert tools |
| CREATE | `tests/test_mcp_attachment.py` | Integration tests using fakes |

---

## 10. Testing Plan

### Unit Tests

We will implement `tests/test_mcp_attachment.py` using standard mock/fake mechanics:

- `test_single_server_async_attach`: Connects a fake stdio transport, verifies discovery and addition of tools to tools list.
- `test_batch_attach_concurrency_and_fail_safe`: Simulates batch startup with one failing server; verifies all successfully started ones are cleanly closed.
- `test_lazy_builder_pattern`: Confirms no subprocess starts on `with_mcp_server`, and connects precisely when `generate_reply` is entered.
- `test_context_manager_cleanup`: Verifies `__aexit__` triggers transport shutdown even if exception is raised during block.
- `test_agent_card_mcp_parity`: Confirms `AgentCard` correctly segments mcp tool names and server names.

---

## 11. Dependencies & External Services

No new external dependencies. We build upon the internal `McpStdioTransport` and `McpClient`.

---

## 12. Rollout & Deployment

- **Backwards Compatibility:** All arguments are optional or default-valued; native tool handling is entirely unchanged.
- **Coexistence:** This branch integrates PR #5 (`ai/resolve-sdk-pr-5-comments`) and PR #6 (`ai/resolve-sdk-pr-6-comments`).

---

## 13. Open Questions

- [ ] **Timeout Default:** Should the default handshake timeout be 30 seconds or shorter (e.g., 10 seconds) to ensure responsive developer feedback?
- [ ] **Mixin Naming:** Is `McpAttachableMixin` descriptive enough, or should we use `McpServerAttachmentMixin`?

---

## 14. Alternatives Considered

### Alternative 1: Core Subprocess Ownership in Agent base
- **What:** Directly implement connection management inside `BaseAgent.py` and `BaseHarness.py`.
- **Why rejected:** Violates DRY and separation of concerns. Having duplicate close/connect code in agents and harnesses leads to drift and bugs.
