# Design Doc: Harness SDK Tool Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

Expand the vidbyte-sdk from 9 built-in tool primitives to 35+ across 6 tool families, adding table-stakes tools found in every major open-source agent framework (web search, web fetch, shell, git, HTTP client, SQL), high-value additions (browser automation, PDF parsing, todo tracking, plan mode, image generation, GitHub), and unique differentiators (LSP code intelligence, background monitor, verification loops, persistent memory, approval workflows, loop detection, orphan repair, secret redaction). Every new tool follows the existing `BaseTool` / `FunctionTool` / `@tool` pattern. Third-party service backends live in `vidbyte/lib/providers/` following the driver/backend abstraction already established by `BaseFileSystemBackend`.

---

## 2. Goals & Non-Goals

### Goals

- Ship the 6 table-stakes tools every other framework has (web search, web fetch, shell, git, HTTP, SQL)
- Ship 6 high-value additions (browser, PDF, todos, plan mode, image gen, GitHub)
- Ship 4 unique differentiators (LSP, monitor, verification loop, memory)
- Ship 5 reliability & infrastructure primitives (approval workflows, loop detection, orphan repair, secret redaction, context providers)
- Ship sandbox abstraction for isolated code execution
- Every tool follows the existing `BaseTool.spec()/execute()` or `@tool` decorator contract
- Every external service gets a `Base*Backend(ABC)` in `vidbyte/lib/providers/` with at least one concrete implementation and an `auto` provider that works zero-config
- Zero breaking changes to existing public API
- Full test coverage for every new tool and middleware

### Non-Goals

- SaaS-specific integrations (Gmail, Slack, Jira, Notion, Salesforce) — these belong in MCP servers, not the SDK
- Modifying existing tool infrastructure (`BaseTool`, `ToolRegistry`, `ToolExecutor`, `ToolsFormatter`)
- Modifying existing agent loop or strategy system
- Audio/video generation tools (TTS, STT, video generation) — deferred to future PR
- Real-time streaming of large tool outputs — follow-up optimization, not in this PR
- Aider-style edit formats — vidbyte-sdk uses discrete tools, not output-format-based primitives
- DSPy-style prompt optimization — outside scope of tool primitives

---

## 3. Background & Context

A comprehensive audit of 34 open-source AI agent and coding frameworks (Claude Code, Codex CLI, Gemini CLI, Aider, SWE-agent, Cline, Roo Code, Continue, Smolagents, DSPy, Agno, CrewAI, AutoGPT, LangChain agents, OpenHands, MetaGPT, ChatDev, Goose, PraisonAI, Griptape, Magentic, Mirascope, Pydantic AI, Atomic Agents, Archon, Instructor, Outlines, Hermes Tools, Browserbase, Stagehand, Composio, Firecrawl, E2B, Tavily) revealed that vidbyte-sdk is missing 6 table-stakes tools found in every single framework, and lacks key primitives that would differentiate it.

**Current state**: vidbyte-sdk has excellent infrastructure (tool registry, executor, formatter, decorator, middleware pipeline, strategies, pipelines, MCP bridge) but only 9 built-in tools: calculator, code execution (simulated), document retrieval (simulated), glob, grep, semantic search, patch edit, context compaction, reasoning trace — plus 22 filesystem tools.

**Gap**: The 6 table-stakes tools (web search, web fetch, shell, git, HTTP client, SQL) are universal across all 34 frameworks. Their absence makes vidbyte-sdk non-viable as a standalone harness for most agent use cases.

**Opportunity**: No framework has all the unique differentiators (LSP, monitor, verification loop, memory, approval workflows, loop detection, orphan repair, secret redaction) in a single SDK. vidbyte-sdk can leapfrog by shipping them all as first-class primitives alongside the table-stakes tools.

**Key constraints**:
- The SDK uses Python 3.11+, setuptools, Pydantic >=2,<3
- Tools follow `BaseTool(ABC)` with `spec()` → `ToolSpec` and `async execute(call: ToolCall)` → `ToolResult`
- Function-based tools use `@tool` decorator wrapping `FunctionTool`
- Existing backend pattern: abstract `Base*Backend(ABC)` in `vidbyte/lib/` + concrete implementations
- Permission model: `ToolPermission.SAFE`, `READ`, `WRITE`, `EXECUTE`
- Context Header Protocol: every new file must follow the comment-header convention

---

## 4. Requirements

### Functional Requirements

1. **Web Search**: Agent can search the web via Tavily, Brave, DDG, Serper, or Exa with auto-detection
2. **Web Fetch**: Agent can fetch any URL and receive content as markdown or plain text
3. **Shell**: Agent can execute real shell commands with timeout, workdir, and output truncation
4. **Git**: Agent can query git status, diff, log; create branches; stage, commit, and push changes
5. **HTTP Client**: Agent can make arbitrary GET, POST, PUT, DELETE requests
6. **SQL**: Agent can query SQLite, Postgres, and MySQL databases with read-only safety defaults
7. **Browser**: Agent can navigate pages, take screenshots, click, type, scroll, extract structured data
8. **PDF**: Agent can extract text and tables from PDF files
9. **Todo**: Agent can create, update, list, and visualize task trees with dependencies
10. **Plan Mode**: Agent can enter/exit a read-only planning mode gated by middleware
11. **Image Generation**: Agent can generate, edit, and create variations of images via DALL-E, Replicate, Stability
12. **GitHub**: Agent can list/create issues/PRs, get diffs, and add review comments
13. **LSP**: Agent can query definitions, references, hover info, diagnostics, symbols, and formatting via language servers
14. **Monitor**: Agent can start background commands, read accumulated output, list/stop monitors
15. **Verification Loop**: Middleware that auto-runs lint/tests after file changes and feeds failures back to agent
16. **Memory**: Agent can save/load/delete/search persistent key-value facts across sessions
17. **Approval Workflows**: Middleware that gates EXECUTE/WRITE tools behind human approval
18. **Stuck Loop Detection**: Middleware that detects and breaks repetitive tool-call loops
19. **Tool Orphan Repair**: Middleware that fixes orphaned tool calls in conversation history
20. **Secret Redaction**: Middleware that detects and redacts API keys/secrets in I/O
21. **Context Providers**: Dynamic context injection (datetime, git status, repo structure) without tool calls
22. **Sandbox**: Abstract backend for isolated code execution (Docker, E2B, local, Seatbelt)

### Non-Functional Requirements

- **Performance**: Web search/fetch must complete within 10s default timeout. Shell commands default 120s timeout. LSP must reuse server connections (not spawn per-call).
- **Security**: All network tools are `READ` or `WRITE` permission. Shell is `EXECUTE`. Git push/clone is `EXECUTE`. SQL defaults to read-only. Approval middleware gates high-risk operations.
- **Observability**: All tool executions log via existing middleware pipeline. Tool results include structured metadata.
- **Zero-config**: `auto` provider backends work without API keys (DDG for search, httpx for fetch, subprocess for shell/git, SQLite for SQL).
- **Extensibility**: Every backend category follows the `Base*Backend(ABC)` pattern. Users can register custom backends.

---

## 5. High-Level Design

### Architecture

The expansion follows a two-layer architecture already proven in the codebase:

```
vidbyte/tools/builtins/<tool>.py          # Thin tool wrapper (BaseTool or @tool decorator)
        │
        ▼
vidbyte/lib/providers/<category>/base.py  # Abstract backend (ABC)
vidbyte/lib/providers/<category>/<impl>.py # Concrete backend
vidbyte/lib/providers/<category>/auto.py  # Auto-detection factory
```

This mirrors the existing `vidbyte/lib/tools/filesystem/backends/` → `BaseFileSystemBackend` → `LocalFileSystemBackend` pattern.

New middleware follows the existing `AgentMiddleware` → `MiddlewareHook` → `MiddlewarePipeline` pattern used by `AuditLogMiddleware`, `TokenRateLimitMiddleware`, etc.

### Data Flow

```
Agent Loop
  │
  ├─ Middleware Pipeline (before_tool_call hooks)
  │   ├─ ApprovalMiddleware ── if EXECUTE/WRITE → pause for human
  │   ├─ SecretRedactionMiddleware ── scan args for secrets
  │   └─ StuckLoopDetectionMiddleware ── check for repeat calls
  │
  ├─ ToolExecutor → BaseTool.execute()
  │   └─ Tool → Backend (auto-detected or configured)
  │       ├─ WebSearchTool → TavilyBackend / BraveBackend / DDGBackend
  │       ├─ ShellTool → SubprocessBackend / DockerBackend / E2BBackend
  │       └─ etc.
  │
  ├─ Middleware Pipeline (after_tool_call hooks)
  │   ├─ SecretRedactionMiddleware ── scan output for secrets
  │   ├─ ToolOrphanRepairMiddleware ── detect and fix orphans
  │   └─ VerificationLoopMiddleware ── if file changed → lint+test
  │
  └─ Context Providers ── inject datetime, git status before next model call
```

### Key Design Decisions

1. **Backend abstraction over direct implementation**: Every tool category that talks to an external service uses a backend abstraction. This lets users swap providers without changing tool code (e.g., Tavily → Brave → DDG). Follows the Griptape driver pattern already adopted by vidbyte-sdk's filesystem backends.

2. **`auto` provider for zero-config**: Every category has an auto-detection backend that checks env vars for API keys and falls back to a free/no-auth provider. This matches Pydantic AI's provider-adaptive pattern.

3. **Tool-as-thin-wrapper**: Tools in `vidbyte/tools/builtins/` are thin wrappers that handle `ToolSpec` generation, argument validation, and `ToolResult` formatting. Business logic lives in backends. This keeps tools testable and swappable.

4. **Git as discrete tools, not one `git(command)` tool**: Discrete tools (`git_status`, `git_diff`, `git_commit`, etc.) enable per-operation permission gating. A single `git` tool with a `command` argument would make permission gating coarse-grained.

5. **Middleware for cross-cutting concerns**: Plan mode, verification loops, approval workflows, loop detection, orphan repair, and secret redaction are all middleware — not tools. This means they work transparently with any tool, require no changes to tool implementations, and can be composed.

6. **Context Providers as a new injection point**: Dynamic context (datetime, git status) is injected before each model call without consuming tool-call slots. This matches Atomic Agents' `BaseDynamicContextProvider` pattern.

---

## 6. Detailed Design

### 6.1 Web Search — `vidbyte/tools/builtins/web_search.py`

**File(s):** `vidbyte/tools/builtins/web_search.py`
**Type:** New file

#### What it does

Provides a single `@tool`-decorated async function that searches the web and returns title/url/snippet results. Backend auto-detection picks the best available provider.

#### Interface / API

```python
# vidbyte/tools/builtins/web_search.py
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

@tool(permission=ToolPermission.READ, description="Search the web and return results with title, url, and snippet.")
async def web_search(query: str, max_results: int = 10) -> str:
    """Search the web for the given query. Returns JSON array of {title, url, snippet}."""
    backend = _get_backend()  # auto-detects from env vars
    results = await backend.search(query, max_results)
    return _format_results(results)
```

#### Backend Hierarchy

```python
# vidbyte/lib/providers/web_search/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

class BaseWebSearchBackend(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...

# vidbyte/lib/providers/web_search/auto.py
class AutoWebSearchBackend(BaseWebSearchBackend):
    """Tries Tavily → Brave → Serper → Exa → DuckDuckGo (zero-config fallback)."""
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...

# vidbyte/lib/providers/web_search/tavily.py - needs TAVILY_API_KEY
# vidbyte/lib/providers/web_search/brave.py - needs BRAVE_API_KEY
# vidbyte/lib/providers/web_search/serper.py - needs SERPER_API_KEY
# vidbyte/lib/providers/web_search/exa.py - needs EXA_API_KEY
# vidbyte/lib/providers/web_search/duckduckgo.py - zero-config, rate-limited
```

#### Edge Cases & Error Handling

- **No API keys configured**: Falls back to DuckDuckGo (rate-limited, returns 10 results max)
- **Search provider returns error**: Falls through to next provider in priority chain
- **All providers fail**: Returns `ToolResult.error()` with diagnostic message
- **Empty query**: Returns validation error (Pydantic model ensures non-empty string)

---

### 6.2 Web Fetch — `vidbyte/tools/builtins/web_fetch.py`

**File(s):** `vidbyte/tools/builtins/web_fetch.py`
**Type:** New file

#### What it does

Fetches a URL and returns its content as markdown (default) or plain text. Supports basic HTML→markdown conversion, JS-rendered page fetching via Browserbase/Firecrawl, and PDF detection with deferred handling.

#### Interface / API

```python
@tool(permission=ToolPermission.READ)
async def web_fetch(
    url: str,
    format: str = "markdown",  # "markdown" or "text"
    timeout_ms: int = 30000,
) -> str:
    """Fetch a URL and return its content as markdown or plain text."""
    backend = _get_backend()
    result = await backend.fetch(url, format, timeout_ms)
    return result.content
```

#### Backends

```python
# vidbyte/lib/providers/web_fetch/base.py
@dataclass
class FetchResult:
    content: str
    content_type: str  # text/html, text/plain, application/pdf
    status_code: int
    url: str  # final URL after redirects

class BaseWebFetchBackend(ABC):
    @abstractmethod
    async def fetch(self, url: str, format: str, timeout_ms: int) -> FetchResult: ...

# vidbyte/lib/providers/web_fetch/httpx_backend.py - uses existing lib/http transport
# vidbyte/lib/providers/web_fetch/browserbase_backend.py - JS rendering via Browserbase
# vidbyte/lib/providers/web_fetch/firecrawl_backend.py - AI-optimized extraction
```

#### Edge Cases

- **PDF URL**: Returns `"Content is a PDF. Use the pdf_read tool to extract text."` with metadata
- **Redirects**: Follows up to 5 redirects, returns final URL in result
- **Large pages**: Truncated to 100K chars, with truncation noted in output
- **Non-200 status**: Returns error with status code and response body excerpt

---

### 6.3 Shell — `vidbyte/tools/builtins/shell.py`

**File(s):** `vidbyte/tools/builtins/shell.py`
**Type:** New file (BaseTool subclass)

#### What it does

Executes real shell commands with configurable timeout, working directory, and background mode. Output is truncated at 30K characters (matching Claude Code's limit). Uses sandbox backends for isolation.

#### Interface / API

```python
class ShellTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell",
            description="Execute a shell command and return stdout/stderr.",
            permission=ToolPermission.EXECUTE,
            parameters=(
                ToolParameter("command", "string", "The shell command to execute."),
                ToolParameter("timeout_ms", "integer", "Timeout in milliseconds.", required=False),
                ToolParameter("workdir", "string", "Working directory.", required=False),
                ToolParameter("background", "boolean", "Run in background, return immediately.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        backend = _get_sandbox_backend()
        result = await backend.execute(
            command=call.arguments["command"],
            timeout_ms=call.arguments.get("timeout_ms", 120000),
            workdir=call.arguments.get("workdir", "."),
            env={**os.environ},  # filtered for safety
        )
        return ToolResult.success(self.name, result.output[:30000], metadata=result.metadata)
```

#### Backends (`vidbyte/lib/providers/sandbox/`)

```python
# vidbyte/lib/providers/sandbox/base.py
@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    truncated: bool
    metadata: dict

class BaseSandboxBackend(ABC):
    @abstractmethod
    async def execute(self, command: str, timeout_ms: int, workdir: str, env: dict) -> SandboxResult: ...
    @abstractmethod
    async def write_file(self, path: str, content: str | bytes) -> None: ...
    @abstractmethod
    async def read_file(self, path: str) -> str: ...
    async def cleanup(self) -> None: ...

# vidbyte/lib/providers/sandbox/local_backend.py - subprocess, no isolation
# vidbyte/lib/providers/sandbox/docker_backend.py - container isolation
# vidbyte/lib/providers/sandbox/e2b_backend.py - cloud sandbox
```

#### Edge Cases

- **Interactive commands** (vim, nano, less): Blocked via allowlist — returns error
- **Timeout**: Kills process, returns partial output with `truncated: true`
- **Non-zero exit**: Returns `ToolResult.error()` with exit code and stderr
- **Background mode**: Returns immediately with monitor_id; agent uses Monitor tool to read output

---

### 6.4 Git — `vidbyte/tools/builtins/git/`

**File(s):** `vidbyte/tools/builtins/git/{__init__,status,diff,log,branch,commit,push,clone}.py`
**Type:** New files (10 discrete tools)

#### What it does

Ten discrete tools for git operations, each with its own permission level. Uses subprocess backend by default, with optional pygit2 backend for performance.

#### Interface / API (representative subset)

```python
# vidbyte/tools/builtins/git/status.py
@tool(permission=ToolPermission.READ)
async def git_status(repo_path: str = ".") -> str: ...

# vidbyte/tools/builtins/git/diff.py
@tool(permission=ToolPermission.READ)
async def git_diff(
    repo_path: str = ".",
    staged: bool = False,
    file_path: str | None = None,
) -> str: ...

# vidbyte/tools/builtins/git/commit.py
@tool(permission=ToolPermission.WRITE)
async def git_commit(repo_path: str, message: str, files: list[str] | None = None) -> str: ...

# vidbyte/tools/builtins/git/push.py
@tool(permission=ToolPermission.EXECUTE)
async def git_push(repo_path: str, remote: str = "origin", branch: str | None = None) -> str: ...

# vidbyte/tools/builtins/git/clone.py
@tool(permission=ToolPermission.EXECUTE)
async def git_clone(url: str, target_dir: str, branch: str | None = None) -> str: ...
```

#### Backends

```python
# vidbyte/lib/providers/git/base.py
class BaseGitBackend(ABC):
    @abstractmethod
    async def status(self, repo_path: str) -> str: ...
    @abstractmethod
    async def diff(self, repo_path: str, staged: bool, file_path: str | None) -> str: ...
    # ... one method per git operation

# vidbyte/lib/providers/git/subprocess_backend.py - calls git CLI
# vidbyte/lib/providers/git/pygit2_backend.py - libgit2 bindings
```

---

### 6.5 HTTP Client — `vidbyte/tools/builtins/http_client.py`

**File(s):** `vidbyte/tools/builtins/http_client.py`
**Type:** New file

#### What it does

Four tools (GET, POST, PUT, DELETE) wrapping the existing `vidbyte/lib/http/transport.py`. Minimal new code — reuses what's already there.

```python
@tool(permission=ToolPermission.READ)
async def http_get(url: str, headers: dict[str, str] | None = None) -> str:
    transport = HttpTransport()
    response = transport.request(method="GET", url=url, headers=headers or {})
    return response.body[:100000]
```

---

### 6.6 SQL — `vidbyte/tools/builtins/sql.py`

**File(s):** `vidbyte/tools/builtins/sql.py`
**Type:** New file

#### What it does

Three tools: `sql_query` (read-only by default), `sql_list_tables`, `sql_describe_table`. SQLite is the zero-config default. Postgres and MySQL are optional.

```python
@tool(permission=ToolPermission.READ)
async def sql_query(connection_string: str, query: str) -> str: ...

@tool(permission=ToolPermission.READ)
async def sql_list_tables(connection_string: str) -> str: ...

@tool(permission=ToolPermission.READ)
async def sql_describe_table(connection_string: str, table: str) -> str: ...
```

#### Safety

- Blocks `DROP`, `DELETE` (unless `WHERE` present), `TRUNCATE`, `ALTER`, `CREATE`, `INSERT`, `UPDATE` in default read-only mode
- Configurable `sql_read_only: bool = True` in config
- Row limit: 1000 rows max

---

### 6.7 Browser Automation — `vidbyte/tools/builtins/browser/`

**File(s):** `vidbyte/tools/builtins/browser/{__init__,navigate,screenshot,content,interaction,extraction,session}.py`
**Type:** New files (13 tools)

13 tools modeled after SWE-agent's 16 browser tools + Stagehand's `act()/extract()` pattern:

```python
# Navigation
@tool(permission=ToolPermission.READ)
async def browser_navigate(url: str) -> str: ...

@tool(permission=ToolPermission.READ)
async def browser_screenshot(filename: str | None = None) -> str: ...

@tool(permission=ToolPermission.READ)
async def browser_get_content(format: str = "markdown") -> str: ...

# Interaction
@tool(permission=ToolPermission.WRITE)
async def browser_click(selector: str) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_type(selector: str, text: str) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_press_key(key: str) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_scroll(direction: str = "down", amount: int = 300) -> str: ...

# Stagehand-style NL commands
@tool(permission=ToolPermission.READ)
async def browser_extract(instruction: str, schema: dict | None = None) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_act(instruction: str) -> str: ...

# Session management
@tool(permission=ToolPermission.READ)
async def browser_list_tabs() -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_new_tab(url: str | None = None) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_switch_tab(tab_index: int) -> str: ...

@tool(permission=ToolPermission.WRITE)
async def browser_close_tab(tab_index: int) -> str: ...
```

#### Backends

```python
# vidbyte/lib/providers/browser/base.py
class BaseBrowserBackend(ABC):
    @abstractmethod
    async def navigate(self, url: str) -> str: ...
    @abstractmethod
    async def screenshot(self) -> bytes: ...
    @abstractmethod
    async def get_content(self, format: str) -> str: ...
    # ... etc.

# vidbyte/lib/providers/browser/playwright_backend.py - local Playwright (heavy dep)
# vidbyte/lib/providers/browser/browserbase_backend.py - cloud, stealth
# vidbyte/lib/providers/browser/stagehand_backend.py - NL act/extract
```

#### Note on Playwright dependency

Playwright is ~300MB. This should be an optional extra: `pip install vidbyte-sdk[browser]`. The zero-config default is Browserbase cloud (API key required) with a clear error message if neither is available.

---

### 6.8 PDF Parsing — `vidbyte/tools/builtins/pdf.py`

**File(s):** `vidbyte/tools/builtins/pdf.py`
**Type:** New file

3 tools: `pdf_read`, `pdf_read_tables`, `pdf_metadata`. Uses PyMuPDF as primary backend (fast, comprehensive), PDFPlumber for table extraction.

---

### 6.9 Todo Tracking — `vidbyte/tools/builtins/todo.py`

**File(s):** `vidbyte/tools/builtins/todo.py`
**Type:** New file

5 SAFE-permission tools: `todo_create`, `todo_update`, `todo_list`, `todo_add_dependency`, `todo_visualize`. Persistent via `.vidbyte/todos.json`. The `todo_visualize` tool renders an ASCII tree of the task dependency graph (Gemini CLI style).

---

### 6.10 Plan Mode — `vidbyte/tools/builtins/plan.py` + `vidbyte/middleware/plan_mode.py`

**File(s):** `vidbyte/tools/builtins/plan.py`, `vidbyte/middleware/plan_mode.py`
**Type:** New files

Two tools (`enter_plan_mode`, `exit_plan_mode`) + a middleware that gates WRITE/EXECUTE tools when plan mode is active. The middleware intercepts `before_tool_call` and returns `MiddlewareDecision.block("Plan mode is active. Only READ tools are allowed.")` for blocked tools.

---

### 6.11 Image Generation — `vidbyte/tools/builtins/image_gen.py`

**File(s):** `vidbyte/tools/builtins/image_gen.py`
**Type:** New file

3 tools: `generate_image`, `edit_image` (inpainting/outpainting), `image_variation`. Backends: OpenAI DALL-E, Replicate (Stable Diffusion/Flux), Stability AI.

---

### 6.12 GitHub — `vidbyte/tools/builtins/github/`

**File(s):** `vidbyte/tools/builtins/github/{__init__,issues,prs}.py`
**Type:** New files

8 tools: `github_list_issues`, `github_get_issue`, `github_create_issue`, `github_list_prs`, `github_get_pr`, `github_create_pr`, `github_get_pr_diff`, `github_add_pr_comment`.

Uses `gh` CLI backend as primary (zero additional deps if `gh` is installed), REST API as fallback.

---

### 6.13 LSP — `vidbyte/tools/builtins/lsp.py`

**File(s):** `vidbyte/tools/builtins/lsp.py`
**Type:** New file

#### What it does

Provides code intelligence via Language Server Protocol. This is the highest-differentiation tool — only Claude Code ships LSP natively. Eight tools for definitions, references, hover, diagnostics, symbols, call hierarchy, type definition, and formatting.

#### Interface / API

```python
class LspTool:
    """Manages LSP server lifecycle. Individual operations are @tool functions."""

    _servers: dict[str, BaseLspBackend] = {}  # language → server connection

@tool(permission=ToolPermission.READ)
async def lsp_definition(file_path: str, line: int, character: int) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_references(file_path: str, line: int, character: int, include_declaration: bool = False) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_hover(file_path: str, line: int, character: int) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_diagnostics(file_path: str) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_symbols(file_path: str | None = None) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_call_hierarchy(file_path: str, line: int, character: int, direction: str = "incoming") -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_type_definition(file_path: str, line: int, character: int) -> str: ...

@tool(permission=ToolPermission.READ)
async def lsp_format(file_path: str) -> str: ...
```

#### Backends (`vidbyte/lib/providers/lsp/`)

```python
# vidbyte/lib/providers/lsp/base.py
class BaseLspBackend(ABC):
    """Manages an LSP server subprocess with JSON-RPC communication."""
    @abstractmethod
    async def initialize(self, root_uri: str) -> None: ...
    @abstractmethod
    async def definition(self, uri: str, line: int, character: int) -> list[Location]: ...
    @abstractmethod
    async def references(self, uri: str, line: int, character: int) -> list[Location]: ...
    # ... one method per LSP capability
    async def shutdown(self) -> None: ...

# vidbyte/lib/providers/lsp/pyright_backend.py - Python via pyright-langserver
# vidbyte/lib/providers/lsp/typescript_backend.py - via typescript-language-server
# vidbyte/lib/providers/lsp/auto_backend.py - detects language from file extension
```

#### Implementation approach

- Spawn LSP server as subprocess, communicate via stdio JSON-RPC
- Maintain a connection pool: one server process per language
- Reuse connections across tool calls (don't respawn per call)
- Auto-detect language from file extension, pick the right server
- Requires `pygls` or raw JSON-RPC client (stdlib `subprocess` + `json`)

---

### 6.14 Monitor — `vidbyte/tools/builtins/monitor.py`

**File(s):** `vidbyte/tools/builtins/monitor.py`
**Type:** New file

4 tools: `monitor_start`, `monitor_list`, `monitor_stop`, `monitor_read`. Modeled after Claude Code's Monitor tool. Background process management with output buffering.

---

### 6.15 Verification Loop — `vidbyte/middleware/verification.py`

**File(s):** `vidbyte/middleware/verification.py`
**Type:** New file

Middleware that hooks into `after_tool_call`. After any file-mutating tool call:
1. Runs configured lint command → if errors, feeds back to agent as a synthetic observation
2. Runs configured test command → if failures, feeds back to agent
3. Agent can fix and retry (max 3 iterations)
4. If all pass, continues normally

No new tools needed — works transparently with existing file tools.

---

### 6.16 Memory — `vidbyte/tools/builtins/memory.py`

**File(s):** `vidbyte/tools/builtins/memory.py`
**Type:** New file

5 SAFE-permission tools: `memory_save`, `memory_load`, `memory_delete`, `memory_list`, `memory_search`. Persistent key-value store. File backend (JSON) for zero-config, SQLite backend for semantic search.

---

### 6.17 Approval Workflows — `vidbyte/middleware/approval.py`

**File(s):** `vidbyte/middleware/approval.py`
**Type:** New file

Middleware that gates tool execution behind human approval. Configurable via rules:

```python
class ApprovalMiddleware(AgentMiddleware):
    rules: list[ApprovalRule]
    handler: ApprovalHandler  # CLI prompt by default

@dataclass
class ApprovalRule:
    tool_name_pattern: str  # "git_push", "shell", "*" for all
    permission_level: ToolPermission | None  # Approve all EXECUTE tools
    require_approval: bool

class ApprovalHandler(ABC):
    @abstractmethod
    async def request_approval(self, tool_name: str, arguments: dict, reason: str) -> bool: ...
```

---

### 6.18 Stuck Loop Detection — `vidbyte/middleware/loop_detection.py`

**File(s):** `vidbyte/middleware/loop_detection.py`
**Type:** New file

Tracks last 10 tool calls. If the same tool+arguments repeats 3+ times, injects a system reminder. If the loop persists 5+ iterations, force-terminates with an error.

---

### 6.19 Tool Orphan Repair — `vidbyte/middleware/orphan_repair.py`

**File(s):** `vidbyte/middleware/orphan_repair.py`
**Type:** New file

Scans conversation history for tool calls without corresponding results. Re-executes orphaned calls or inserts synthetic error results to keep the conversation history valid for the provider.

---

### 6.20 Secret Redaction — `vidbyte/middleware/secret_redaction.py`

**File(s):** `vidbyte/middleware/secret_redaction.py`
**Type:** New file

Scans all tool inputs and outputs for patterns matching API keys, tokens, passwords, private keys, and connection strings. Redacts before logging. Uses regex + entropy detection.

---

### 6.21 Context Providers — `vidbyte/context/providers.py`

**File(s):** `vidbyte/context/providers.py`
**Type:** New file

```python
class ContextProvider(ABC):
    """Injects dynamic context before each model call without consuming tool slots."""
    @abstractmethod
    async def provide(self, context: dict) -> str: ...

class DateTimeProvider(ContextProvider): ...
class GitStatusProvider(ContextProvider): ...
class EnvironmentProvider(ContextProvider): ...
class RepoStructureProvider(ContextProvider): ...
```

---

### 6.22 Sandbox — `vidbyte/lib/providers/sandbox/`

**File(s):** `vidbyte/lib/providers/sandbox/{__init__,base,local,docker,e2b}.py`
**Type:** New files

Abstract backend for isolated code execution. Used by Shell tool and Code Execution tool. Five backends: local (no isolation), Docker (container), E2B (cloud), macOS Seatbelt, Pyodide (WASM).

---

## 7. Data Model Changes

N/A — No schema, database, or persistence model changes. This PR adds tool implementations, backends, and middleware. The only persistence is `.vidbyte/todos.json` and `.vidbyte/memory.json` (local files, not databases).

---

## 8. API Changes

N/A — No API endpoints. This is a Python SDK, not a web service.

### Public API Additions (Python import surface)

```python
# New tools available via:
from vidbyte.tools.builtins.web_search import web_search
from vidbyte.tools.builtins.web_fetch import web_fetch
from vidbyte.tools.builtins.shell import ShellTool
from vidbyte.tools.builtins.git import git_status, git_diff, git_commit, ...
from vidbyte.tools.builtins.http_client import http_get, http_post, http_put, http_delete
from vidbyte.tools.builtins.sql import sql_query, sql_list_tables, sql_describe_table
# ... etc for all 35+ tools

# New middleware:
from vidbyte.middleware.approval import ApprovalMiddleware, ApprovalRule
from vidbyte.middleware.plan_mode import PlanModeMiddleware
from vidbyte.middleware.verification import VerificationLoopMiddleware
from vidbyte.middleware.loop_detection import StuckLoopMiddleware
from vidbyte.middleware.orphan_repair import ToolOrphanRepairMiddleware
from vidbyte.middleware.secret_redaction import SecretRedactionMiddleware

# New backends (for direct use, not normally imported by end users):
from vidbyte.lib.providers.web_search import TavilyBackend, BraveBackend, DuckDuckGoBackend
from vidbyte.lib.providers.sandbox import DockerSandboxBackend, E2BSandboxBackend
# ... etc
```

---

## 9. File Change Manifest

This is a large expansion. Files organized by batch.

### Batch 1 — Table Stakes (6 tool families, ~35 files)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/builtins/web_search.py` | Web search tool |
| CREATE | `vidbyte/tools/builtins/web_fetch.py` | Web fetch tool |
| CREATE | `vidbyte/tools/builtins/shell.py` | Shell execution tool |
| CREATE | `vidbyte/tools/builtins/http_client.py` | HTTP client tools (GET/POST/PUT/DELETE) |
| CREATE | `vidbyte/tools/builtins/sql.py` | SQL query tools |
| CREATE | `vidbyte/tools/builtins/pdf.py` | PDF parsing tools |
| CREATE | `vidbyte/tools/builtins/git/__init__.py` | Git tools package |
| CREATE | `vidbyte/tools/builtins/git/status.py` | git_status tool |
| CREATE | `vidbyte/tools/builtins/git/diff.py` | git_diff tool |
| CREATE | `vidbyte/tools/builtins/git/log.py` | git_log tool |
| CREATE | `vidbyte/tools/builtins/git/branch.py` | git_branch_create, git_checkout tools |
| CREATE | `vidbyte/tools/builtins/git/commit.py` | git_add, git_commit tools |
| CREATE | `vidbyte/tools/builtins/git/push.py` | git_push tool |
| CREATE | `vidbyte/tools/builtins/git/clone.py` | git_clone, git_remote_list tools |
| CREATE | `vidbyte/lib/providers/__init__.py` | Providers package |
| CREATE | `vidbyte/lib/providers/web_search/__init__.py` | Web search backends package |
| CREATE | `vidbyte/lib/providers/web_search/base.py` | BaseWebSearchBackend ABC |
| CREATE | `vidbyte/lib/providers/web_search/tavily.py` | Tavily backend |
| CREATE | `vidbyte/lib/providers/web_search/brave.py` | Brave backend |
| CREATE | `vidbyte/lib/providers/web_search/duckduckgo.py` | DuckDuckGo backend (zero-config) |
| CREATE | `vidbyte/lib/providers/web_search/serper.py` | Serper backend |
| CREATE | `vidbyte/lib/providers/web_search/exa.py` | Exa backend |
| CREATE | `vidbyte/lib/providers/web_search/auto.py` | Auto-detection backend |
| CREATE | `vidbyte/lib/providers/web_fetch/__init__.py` | Web fetch backends package |
| CREATE | `vidbyte/lib/providers/web_fetch/base.py` | BaseWebFetchBackend ABC |
| CREATE | `vidbyte/lib/providers/web_fetch/httpx_backend.py` | Httpx backend (uses existing transport) |
| CREATE | `vidbyte/lib/providers/web_fetch/browserbase_backend.py` | Browserbase backend |
| CREATE | `vidbyte/lib/providers/web_fetch/firecrawl_backend.py` | Firecrawl backend |
| CREATE | `vidbyte/lib/providers/shell/__init__.py` | Shell backends package |
| CREATE | `vidbyte/lib/providers/shell/base.py` | BaseShellBackend ABC |
| CREATE | `vidbyte/lib/providers/shell/subprocess_backend.py` | Subprocess backend |
| CREATE | `vidbyte/lib/providers/sandbox/__init__.py` | Sandbox backends package |
| CREATE | `vidbyte/lib/providers/sandbox/base.py` | BaseSandboxBackend ABC |
| CREATE | `vidbyte/lib/providers/sandbox/local_backend.py` | Local sandbox (no isolation) |
| CREATE | `vidbyte/lib/providers/sandbox/docker_backend.py` | Docker sandbox |
| CREATE | `vidbyte/lib/providers/git/__init__.py` | Git backends package |
| CREATE | `vidbyte/lib/providers/git/base.py` | BaseGitBackend ABC |
| CREATE | `vidbyte/lib/providers/git/subprocess_backend.py` | Subprocess git backend |
| CREATE | `vidbyte/lib/providers/http/__init__.py` | HTTP backends package |
| CREATE | `vidbyte/lib/providers/http/base.py` | BaseHttpBackend ABC |
| CREATE | `vidbyte/lib/providers/http/httpx_backend.py` | Httpx HTTP backend |
| CREATE | `vidbyte/lib/providers/sql/__init__.py` | SQL backends package |
| CREATE | `vidbyte/lib/providers/sql/base.py` | BaseSqlBackend ABC |
| CREATE | `vidbyte/lib/providers/sql/sqlite_backend.py` | SQLite backend (zero-config) |
| CREATE | `vidbyte/lib/providers/sql/postgres_backend.py` | Postgres backend |
| CREATE | `vidbyte/lib/providers/pdf/__init__.py` | PDF backends package |
| CREATE | `vidbyte/lib/providers/pdf/base.py` | BasePdfBackend ABC |
| CREATE | `vidbyte/lib/providers/pdf/pymupdf_backend.py` | PyMuPDF backend |
| CREATE | `vidbyte/lib/providers/pdf/pdfplumber_backend.py` | PDFPlumber backend |
| MODIFY | `pyproject.toml` | Add new dependencies (httpx, duckduckgo-search, pymupdf) |
| MODIFY | `vidbyte/lib/config/constants.py` | Add provider config constants |

### Batch 2 — High-Value Additions (~45 files)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/builtins/todo.py` | Todo tracking tools |
| CREATE | `vidbyte/tools/builtins/plan.py` | Plan mode tools |
| CREATE | `vidbyte/tools/builtins/image_gen.py` | Image generation tools |
| CREATE | `vidbyte/tools/builtins/browser/__init__.py` | Browser tools package |
| CREATE | `vidbyte/tools/builtins/browser/navigate.py` | Navigate, screenshot, content tools |
| CREATE | `vidbyte/tools/builtins/browser/interaction.py` | Click, type, press_key, scroll tools |
| CREATE | `vidbyte/tools/builtins/browser/extraction.py` | extract, act tools |
| CREATE | `vidbyte/tools/builtins/browser/session.py` | Tab management tools |
| CREATE | `vidbyte/tools/builtins/github/__init__.py` | GitHub tools package |
| CREATE | `vidbyte/tools/builtins/github/issues.py` | Issue tools |
| CREATE | `vidbyte/tools/builtins/github/prs.py` | PR tools |
| CREATE | `vidbyte/lib/providers/browser/__init__.py` | Browser backends package |
| CREATE | `vidbyte/lib/providers/browser/base.py` | BaseBrowserBackend ABC |
| CREATE | `vidbyte/lib/providers/browser/playwright_backend.py` | Playwright backend |
| CREATE | `vidbyte/lib/providers/browser/browserbase_backend.py` | Browserbase backend |
| CREATE | `vidbyte/lib/providers/browser/stagehand_backend.py` | Stagehand backend |
| CREATE | `vidbyte/lib/providers/image_gen/__init__.py` | Image gen backends package |
| CREATE | `vidbyte/lib/providers/image_gen/base.py` | BaseImageGenBackend ABC |
| CREATE | `vidbyte/lib/providers/image_gen/openai_dalle_backend.py` | OpenAI DALL-E backend |
| CREATE | `vidbyte/lib/providers/image_gen/replicate_backend.py` | Replicate backend |
| CREATE | `vidbyte/lib/providers/image_gen/stability_backend.py` | Stability AI backend |
| CREATE | `vidbyte/lib/providers/github/__init__.py` | GitHub backends package |
| CREATE | `vidbyte/lib/providers/github/base.py` | BaseGitHubBackend ABC |
| CREATE | `vidbyte/lib/providers/github/gh_cli_backend.py` | gh CLI backend |
| CREATE | `vidbyte/lib/providers/github/rest_backend.py` | REST API backend |
| CREATE | `vidbyte/lib/providers/todo/__init__.py` | Todo backends package |
| CREATE | `vidbyte/lib/providers/todo/base.py` | BaseTodoBackend ABC |
| CREATE | `vidbyte/lib/providers/todo/memory_backend.py` | In-memory backend |
| CREATE | `vidbyte/lib/providers/todo/file_backend.py` | File backend |
| CREATE | `vidbyte/middleware/plan_mode.py` | Plan mode middleware |
| MODIFY | `pyproject.toml` | Add optional deps (playwright, pygithub) |

### Batch 3 — Unique Differentiators (~25 files)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/builtins/lsp.py` | LSP code intelligence tools (8 tools) |
| CREATE | `vidbyte/tools/builtins/monitor.py` | Background monitor tools (4 tools) |
| CREATE | `vidbyte/tools/builtins/verification.py` | Verification tools (lint+test runners) |
| CREATE | `vidbyte/tools/builtins/memory.py` | Persistent memory tools (5 tools) |
| CREATE | `vidbyte/lib/providers/lsp/__init__.py` | LSP backends package |
| CREATE | `vidbyte/lib/providers/lsp/base.py` | BaseLspBackend ABC |
| CREATE | `vidbyte/lib/providers/lsp/pyright_backend.py` | Python LSP |
| CREATE | `vidbyte/lib/providers/lsp/typescript_backend.py` | TypeScript LSP |
| CREATE | `vidbyte/lib/providers/lsp/auto_backend.py` | Auto-detect language |
| CREATE | `vidbyte/lib/providers/monitor/__init__.py` | Monitor backends package |
| CREATE | `vidbyte/lib/providers/monitor/base.py` | BaseMonitorBackend ABC |
| CREATE | `vidbyte/lib/providers/monitor/subprocess_backend.py` | Subprocess monitor |
| CREATE | `vidbyte/lib/providers/memory/__init__.py` | Memory backends package |
| CREATE | `vidbyte/lib/providers/memory/base.py` | BaseMemoryBackend ABC |
| CREATE | `vidbyte/lib/providers/memory/file_backend.py` | JSON file backend |
| CREATE | `vidbyte/lib/providers/memory/sqlite_backend.py` | SQLite backend |
| CREATE | `vidbyte/middleware/verification.py` | Verification loop middleware |

### Batch 4 — Reliability & Infrastructure (~15 files)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/middleware/approval.py` | Approval workflow middleware |
| CREATE | `vidbyte/middleware/loop_detection.py` | Stuck loop detection middleware |
| CREATE | `vidbyte/middleware/orphan_repair.py` | Tool orphan repair middleware |
| CREATE | `vidbyte/middleware/secret_redaction.py` | Secret redaction middleware |
| CREATE | `vidbyte/context/providers.py` | Context providers (4 providers) |
| CREATE | `vidbyte/lib/providers/sandbox/e2b_backend.py` | E2B cloud sandbox |
| CREATE | `vidbyte/lib/providers/sandbox/seatbelt_backend.py` | macOS Seatbelt sandbox |
| CREATE | `vidbyte/lib/providers/sandbox/pyodide_backend.py` | Pyodide WASM sandbox |

### Tests (all new, ~25 files)

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `tests/tools/test_web_search.py` | Web search tests |
| CREATE | `tests/tools/test_web_fetch.py` | Web fetch tests |
| CREATE | `tests/tools/test_shell.py` | Shell tests |
| CREATE | `tests/tools/test_git.py` | Git tests |
| CREATE | `tests/tools/test_http_client.py` | HTTP client tests |
| CREATE | `tests/tools/test_sql.py` | SQL tests |
| CREATE | `tests/tools/test_browser.py` | Browser tests |
| CREATE | `tests/tools/test_pdf.py` | PDF tests |
| CREATE | `tests/tools/test_todo.py` | Todo tests |
| CREATE | `tests/tools/test_plan.py` | Plan mode tests |
| CREATE | `tests/tools/test_image_gen.py` | Image gen tests |
| CREATE | `tests/tools/test_lsp.py` | LSP tests |
| CREATE | `tests/tools/test_monitor.py` | Monitor tests |
| CREATE | `tests/tools/test_verification.py` | Verification tests |
| CREATE | `tests/tools/test_memory.py` | Memory tests |
| CREATE | `tests/tools/test_github.py` | GitHub tests |
| CREATE | `tests/middleware/test_plan_mode.py` | Plan mode middleware tests |
| CREATE | `tests/middleware/test_verification.py` | Verification middleware tests |
| CREATE | `tests/middleware/test_approval.py` | Approval middleware tests |
| CREATE | `tests/middleware/test_loop_detection.py` | Loop detection tests |
| CREATE | `tests/middleware/test_orphan_repair.py` | Orphan repair tests |
| CREATE | `tests/middleware/test_secret_redaction.py` | Secret redaction tests |

### Summary

| Action | Count |
|--------|-------|
| CREATE | ~120 files |
| MODIFY | 2 files (`pyproject.toml`, `vidbyte/lib/config/constants.py`) |
| DELETE | 0 files |

---

## 10. Testing Plan

### Unit Tests

**Tool tests** — each tool tests:
- `test_<tool>_valid_input` — happy path with valid arguments
- `test_<tool>_missing_required` — validation error when required args missing
- `test_<tool>_invalid_input` — graceful error for bad input
- `test_<tool>_spec` — ToolSpec has correct name, description, parameters
- `test_<tool>_execute_returns_toolresult` — output is valid ToolResult
- `test_<tool>_permission_level` — permission is correct (READ/WRITE/EXECUTE/SAFE)

**Backend tests** — each backend tests:
- `test_<backend>_implements_abc` — all abstract methods are implemented
- `test_<backend>_happy_path` — mock HTTP/subprocess for deterministic testing
- `test_<backend>_error_handling` — graceful error on network failure, timeout, auth failure

**Middleware tests** — each middleware tests:
- `test_<middleware>_blocks_when_active` — blocks correct tools
- `test_<middleware>_allows_when_inactive` — allows tools when condition not met
- `test_<middleware>_hook_registration` — registers correct hooks (before_tool_call, after_tool_call, etc.)

**Auto-detection tests**:
- `test_auto_backend_falls_back` — when primary fails, falls to next
- `test_auto_backend_uses_env_var` — respects provider env var overrides
- `test_auto_backend_default` — DuckDuckGo for search, SQLite for SQL, subprocess for shell/git

### Integration Tests

- **Web search → web fetch**: Search for a topic, then fetch the first result URL
- **Shell → monitor**: Start a background shell command via shell tool, then read output via monitor
- **Git status → diff → commit**: Complete git workflow: check status, view diff, stage, commit
- **Plan mode + write tools**: Enter plan mode, attempt write → blocked, exit plan mode, write succeeds
- **Verification loop**: Edit a file that introduces lint error → middleware detects → feeds back → agent fixes → passes
- **Approval workflow**: Configure approval for EXECUTE tools → attempt git push → middleware pauses → approve → continues
- **Loop detection**: Force 4 identical tool calls → middleware injects reminder → another → force-terminates

### Manual / QA Test Cases

1. Given no API keys configured, when agent calls web_search, then DuckDuckGo is used and returns results
2. Given TAVILY_API_KEY set, when agent calls web_search, then Tavily is used (verify via metadata)
3. Given a local git repo, when agent calls git_status, then returns working tree status
4. Given plan mode active, when agent attempts git_commit, then middleware blocks with clear message
5. Given a PDF file, when agent calls pdf_read, then text is extracted correctly
6. Given Python code open in workspace, when agent calls lsp_definition, then returns definition location

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `httpx` | >=0.27 | HTTP client for web fetch, HTTP tools, provider backends | Low — pure Python, well-maintained |
| `duckduckgo-search` | >=6.0 | Zero-config web search fallback | Low — pure Python, rate-limited |
| `pymupdf` | >=1.24 | PDF text extraction (primary) | Low — well-maintained, native libs |
| `pdfplumber` | >=0.11 | PDF table extraction (optional) | Low — pure Python |
| `playwright` | >=1.48 (optional extra) | Browser automation | Medium — 300MB install, optional extra only |
| `pygithub` | >=2.5 (optional extra) | GitHub REST API | Low — well-maintained |
| Tavily API | cloud | Web search (primary paid) | Low — agent-focused, fast |
| Brave Search API | cloud | Web search (free tier) | Low — generous free tier |
| Serper API | cloud | Web search (Google results) | Low — paid |
| Exa API | cloud | Web search (semantic) | Low — paid |
| Browserbase API | cloud | Browser automation (cloud) | Low — paid |
| Firecrawl API | cloud | Web scraping (AI-optimized) | Low — paid |
| E2B API | cloud | Cloud sandbox for code execution | Low — paid |
| OpenAI API | cloud | DALL-E image generation | Medium — paid, one of several backends |
| Replicate API | cloud | Image generation (Flux, SD) | Low — paid |
| Stability AI API | cloud | Image generation | Low — paid |

**Zero-config default**: DuckDuckGo (search), httpx (fetch), subprocess (shell/git), SQLite (SQL), PyMuPDF (PDF), file-based (todo/memory). No API keys needed for basic functionality.

---

## 12. Rollout & Deployment

- No breaking changes — all new files, 2 modified files (add deps, add config constants)
- Feature flags: Not needed. New tools are opt-in — agents only use tools registered in their catalog
- Deployment: Standard `pip install` with new dependencies. Optional extras via `[browser]`, `[lsp]`, `[github]`
- Rollback: Remove new files, revert `pyproject.toml` and `constants.py` to previous state
- Migration path: N/A — no existing code paths change

---

## 13. Open Questions

- [ ] Should browser automation be a separate `vidbyte-sdk[browser]` extra due to Playwright's 300MB size?
- [ ] Should LSP use subprocess (pyright CLI) or JSON-RPC (pyright-langserver)? Subprocess is simpler, JSON-RPC is more capable.
- [ ] Should Git tools be discrete (10 tools, as designed) or one `git` tool with a command argument? Discrete gives finer permission control.
- [ ] Should Memory be encrypted at rest? For credential storage, yes. For preferences, no.
- [ ] Should auto-detection backend factory be lazy (on first call) or eager (at import)? Lazy is preferred — no API validation at import time.
- [ ] Should every backend category be installable as an optional extra (`vidbyte-sdk[web_search]`, `vidbyte-sdk[browser]`, etc.)?
- [ ] Which batch order makes sense for the PR? One massive PR vs. one PR per batch?
- [ ] Should the design doc itself be committed first in a PR before Batch 1 implementation?
- [ ] Is DuckDuckGo search acceptable as the zero-config default, or should there be no default and a clear error message?

---

## 14. Alternatives Considered

### Alternative 1: MCP-only approach (delegate everything to MCP servers)

- **What**: Instead of building tools into the SDK, provide MCP server references for web search, browser, GitHub, etc.
- **Why rejected**: MCP is great for SaaS integrations but adds latency and dependency overhead for primitive operations. A web search should be one API call, not a round-trip through an MCP server. The SDK should have table-stakes tools as first-class primitives.

### Alternative 2: One monolithic `git` tool instead of discrete tools

- **What**: A single `git(command, workdir)` tool that accepts any git subcommand as a string argument.
- **Why rejected**: Coarse-grained permission gating. Can't distinguish between safe `git status` and dangerous `git push --force`. Discrete tools enable per-operation approval workflows.

### Alternative 3: Vendor-specific tools instead of backend abstraction

- **What**: `tavily_search`, `brave_search`, `ddg_search` as separate tools instead of one `web_search` with backend switching.
- **Why rejected**: Backend abstraction lets users swap providers in config without changing agent code or tool registrations. Follows the existing `BaseFileSystemBackend` → `LocalFileSystemBackend` pattern already in the codebase.

### Alternative 4: Skip the unique differentiators, ship only table stakes

- **What**: Only implement Batch 1 (web search, web fetch, shell, git, HTTP, SQL).
- **Why rejected**: The unique differentiators (LSP, monitor, verification loop, memory, approval workflows) are what make vidbyte-sdk stand out. They're the highest-leverage primitives for a harness SDK used by agent developers.
