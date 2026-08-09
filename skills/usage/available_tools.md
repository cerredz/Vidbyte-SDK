# Available Tools

Tools included out of the box in the Vidbyte SDK. Every tool is a callable capability that models can invoke during execution. Tools extend what an agent can do beyond text generation — they let agents search code, read files, run calculations, edit files, and more.

Import tools from their category packages under `vidbyte.tools.builtins.*` or `vidbyte.tools.filesystem`.

## Decorator (Create Your Own)

The foundation for all tool creation. The `@tool` decorator wraps any Python function into a `FunctionTool` that agents can call. It automatically inspects the function signature, type hints, and docstring to generate the tool specification. This is the recommended way to create tools for most use cases.

| Tool | Import | Description |
|------|--------|-------------|
| `@tool` | `from vidbyte import tool` | Wrap any Python function into a tool — signature, type hints, and docstring are auto-inspected |
| `@vidbyte_tool` | `from vidbyte import vidbyte_tool` | Alias for `@tool`, same behavior |
| `FunctionTool` | `from vidbyte import FunctionTool` | Imperative construction from a callable — use when you need to build tools programmatically |
| `Tools` | `from vidbyte import Tools` | Immutable tool catalog (Sequence) — the standard way to group tools for an agent |
| `ToolRegistry` | `from vidbyte import ToolRegistry` | Mutable, thread-safe tool registry — used internally and for dynamic tool management |

## Code Search

Code search tools let agents find and understand code in a repository. They support pattern matching (glob), regex search (grep), and semantic search (embeddings). Attach these to software engineering agents so they can navigate unfamiliar codebases.

```python
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
```

| Tool | Description |
|------|-------------|
| `GlobTool(root_dir=".")` | Find files by glob pattern (e.g., `**/*.py`, `src/**/*.ts`). Returns matching file paths. |
| `GrepTool(root_dir=".")` | Search file contents by regex pattern. Returns matching lines with file paths and line numbers. |
| `SemanticSearchTool()` | Semantic (embedding-based) code search. Finds code that is semantically related to a query, not just text matches. |

These are the most commonly used built-in tools for agents that need to understand and modify codebases.

## Editing

Editing tools let agents modify source files with precision. The patch tool uses exact string replacement — find a string in a file and replace it — which is safer and more predictable than line-based editing.

```python
from vidbyte.tools.builtins.editing import PatchTool
```

| Tool | Description |
|------|-------------|
| `PatchTool()` | Exact string-replacement patch editing. Finds an exact string in a file and replaces it with new content. Fails if the old string is not found or appears multiple times. |

## Context (legacy compaction tool)

> Context compaction is now **middleware**, not a tool. For new agents, prefer the compaction middlewares (`ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`) documented in [`skills/vidbyte-sdk/middleware.md`](../vidbyte-sdk/middleware.md). The tool below remains only for manual/legacy flows.

```python
from vidbyte.tools.builtins.context import ContextCompactionTool
```

| Tool | Description |
|------|-------------|
| `ContextCompactionTool()` | **Legacy/manual.** Model-callable context compaction. New code should use compaction middleware instead. |

## Context Primitives

Context-primitive tools let the model read and write structured items in the agent's context window through the shared `ContextManager`. They are `SAFE` (no filesystem, network, or external state).

```python
from vidbyte import ContextManager
from vidbyte.tools.builtins.context_primitives import ContextWindowFactory

ctx = ContextManager()
tools = ContextWindowFactory(ctx).build()
```

| Tool | Description |
|------|-------------|
| `ContextWindowFactory(context_manager).build(include=None, management=True)` | Mount per-primitive create tools plus list/remove/stats/edit/move management tools. |
| `context_window_tools(...)` | Convenience wrapper around `ContextWindowFactory(...).build(...)`. |
| `context_create_<key>` | Typed create/upsert tools for `text`, `document`, `memory`, `plan`, `task`, `progress`, `artifact`, `environment`, and `git_diff`. |
| `ContextListTool(context_manager)` | List the current context items. |
| `ContextRemoveTool(context_manager)` | Remove a non-frozen context item by id. |
| `ContextStatsTool(context_manager)` | Inspect id, kind, title, placement, frozen flag, and char count. |
| `ContextEditTool(context_manager)` | Replace one exact, unique string across editable string/tuple fields. |
| `ContextReciteTool(context_manager)` | Re-emit a primitive at end-of-conversation attention via a recitation copy. |
| `ContextMoveTool(context_manager)` | Move a non-frozen primitive to a different context placement. |
| `ContextUpsertTool(context_manager)` | Legacy flattened insert/update tool retained for compatibility. |

See [`skills/vidbyte-sdk/context-primitives.md`](../vidbyte-sdk/context-primitives.md).

## Context Algorithm Tools

Model-callable forms of context-window algorithms. The model decides when to record state, writing the same `ContextItem` primitives that the runtime-triggered algorithms produce. See [`skills/vidbyte-sdk/context-algorithm-to-tool.md`](../vidbyte-sdk/context-algorithm-to-tool.md).

```python
from vidbyte.tools.builtins.reflexion import ReflexionTool
from vidbyte.tools.builtins.trajectory_checkpoint import TrajectoryCheckpointTool
```

| Tool | Description |
|------|-------------|
| `ReflexionTool(context_manager)` | Record a self-critique and correction plan when the model detects a reasoning error. |
| `TrajectoryCheckpointTool(context_manager)` | Record a compressed checkpoint of reasoning, trajectory, output, score, and feedback. |

## Agent Forking

`ForkConversationTool` lets a model ask its current agent to run an isolated child conversation immediately. It calls `BaseAgent.fork(...)`, runs the child branch on a focused prompt, and returns the child answer as a normal tool result.

```python
from vidbyte.tools.builtins import ForkConversationTool
```

| Tool | Description |
|------|-------------|
| `ForkConversationTool(allowed_models=..., extra_toolsets=...)` | Agent-bound fork tool for immediate isolated child execution. Model swaps are allowlisted, extra tools must come from developer-provided toolsets, permission policy is inherited, and child state does not mutate the parent. |

Use this for live scratch work inside an agent run. Use durable session fork tools when you only need to create checkpoint-DAG branches for later execution.

## Session Tools

Durable session tools bind to a live `Session` and operate through a `SessionStore`. Cross-session reads are gated by `SessionScope`.

```python
from vidbyte.tools.builtins.sessions import (
    BatchForkTool,
    CheckpointTool,
    ForkTool,
    ResumeAppendTool,
    ResumeOutputTool,
    ResumeReplaceTool,
    RewindTool,
    SessionTool,
)
```

| Tool | Description |
|------|-------------|
| `CheckpointTool(store)` | Snapshot the current thread or copy an in-scope session head as a labeled checkpoint. |
| `ForkTool(store)` | Create one durable child session from the current head or an in-scope checkpoint. |
| `BatchForkTool(store)` | Create 1-64 durable child sessions from the same checkpoint and return compact created/failed results. It does not run the children. |
| `RewindTool(store)` | Move the current session head back to an earlier checkpoint. |
| `ResumeReplaceTool(store)` | Replace the current context with another in-scope checkpoint. |
| `ResumeAppendTool(store)` | Append another in-scope checkpoint history as a framed resumed thread. |
| `ResumeOutputTool(store)` | Append only the final assistant output from a completed in-scope session. |
| `SessionTool(store)` | Combined session utility for checkpoint, fork, list, and read operations. |

## Memory

Memory tools connect agents to external memory providers so they can store and retrieve long-term memories across runs. Each provider has its own tool family. See [`skills/vidbyte-sdk/memory-tools.md`](../vidbyte-sdk/memory-tools.md).

```python
from vidbyte.tools.builtins.memory import (
    Mem0AddMemoryTool, Mem0SearchMemoryTool, Mem0GetMemoriesTool, Mem0DeleteMemoryTool,
    ZepAddMemoryTool, ZepSearchMemoryTool, ZepGetMemoryTool, ZepDeleteSessionTool,
    SupermemoryAddMemoryTool, SupermemorySearchMemoryTool, SupermemoryDeleteMemoryTool,
    LettaAddArchivalMemoryTool, LettaSearchArchivalMemoryTool, LettaGetMemoryBlockTool, LettaDeleteArchivalMemoryTool,
    CogneeAddTool, CogneeCognifyTool, CogneeSearchTool, CogneeDeleteTool,
)
```

| Provider | Tools |
|----------|-------|
| Mem0 | `Mem0AddMemoryTool`, `Mem0SearchMemoryTool`, `Mem0GetMemoriesTool`, `Mem0DeleteMemoryTool` |
| Zep | `ZepAddMemoryTool`, `ZepSearchMemoryTool`, `ZepGetMemoryTool`, `ZepDeleteSessionTool` |
| Supermemory | `SupermemoryAddMemoryTool`, `SupermemorySearchMemoryTool`, `SupermemoryDeleteMemoryTool` |
| Letta | `LettaAddArchivalMemoryTool`, `LettaSearchArchivalMemoryTool`, `LettaGetMemoryBlockTool`, `LettaDeleteArchivalMemoryTool` |
| Cognee | `CogneeAddTool`, `CogneeCognifyTool`, `CogneeSearchTool`, `CogneeDeleteTool` |

## Computation

Computation tools give agents the ability to evaluate math, execute code in sandboxes, and retrieve documents from indexes. These are useful for agents that need to verify calculations, run code snippets, or search through documentation.

```python
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
```

| Tool | Description |
|------|-------------|
| `CalculatorTool()` | Evaluate mathematical expressions safely. Supports standard arithmetic, functions, and constants. |
| `CodeExecutionTool()` | Execute Python code in a sandboxed environment. Useful for agents that need to test or run code snippets. Requires `EXECUTE` permission. |
| `DocumentRetrievalTool()` | Retrieve documents from a pre-built index. Useful for agents that need to search through documentation or knowledge bases. |

## Search & Fetch (Priced Operations)

Priced operation tools give agents first-class web search and page-fetch capabilities. Each tool declares a `(operation, provider)` identity so the runtime can track and bill tool spend through the `UsageTracker`. Use these when your agent needs to search the web, fetch page content, or extract structured data — and you want transparent per-operation pricing reflected in `agent.get_cost_usd()`.

```python
from vidbyte.tools.builtins.operations import (
    BraveSearchTool, ExaSearchTool, TavilySearchTool,
    LinkupSearchTool, ParallelSearchTool, OpenAlexSearchTool,
    SemanticScholarSearchTool,
    FirecrawlFetchTool, ParallelExtractTool, TavilyExtractTool,
    LinkupFetchTool, DirectHttpFetchTool,
    PricedOperationTool,  # base class for creating your own
)
```

### Search Tools (7)

| Tool | Provider | Billing | Description |
|------|----------|---------|-------------|
| `BraveSearchTool()` | Brave | Flat per-request ($0.005) | Privacy-focused web search returning ranked result snippets. |
| `ExaSearchTool()` | Exa | Per-result ($0.007 base + $0.001/result beyond 10) | Neural search returning hyper-relevant results with contents. Supports `type` param: `auto`, `fast`, `deep-lite`, `deep`, `deep-reasoning`. |
| `TavilySearchTool()` | Tavily | Depth-tiered (basic $0.008 / advanced $0.016) | LLM-optimized web search returning ready-to-consume snippets. Supports `search_depth`: `basic`, `advanced`. |
| `LinkupSearchTool()` | Linkup | Depth-tiered (standard $0.005 / deep $0.05) | Web search returning sourced results or answers. Supports `depth`: `standard`, `deep`. |
| `ParallelSearchTool()` | Parallel | Per-result (turbo $0.001/req, pro $0.005/req, + $0.001/result beyond 10) | Web search with processor tier selection. Supports `processor`: `turbo`, `pro`. |
| `OpenAlexSearchTool()` | OpenAlex | Flat per-request ($0.001) | Scholarly works search returning matching academic records. |
| `SemanticScholarSearchTool()` | Semantic Scholar | Free | Paper search returning matching academic records from Semantic Scholar. |

All search tools accept a `query` (or `objective` for Parallel) parameter. Exa, Parallel, and OpenAlex also accept a result count parameter controlling how many results are returned — and therefore how many units are billed.

### Fetch Tools (5)

| Tool | Provider | Billing | Description |
|------|----------|---------|-------------|
| `FirecrawlFetchTool()` | Firecrawl | Per-page ($0.00083/page) | Scrapes web pages into clean markdown. Accepts `url` or `urls` (array). |
| `ParallelExtractTool()` | Parallel | Per-URL ($0.001/URL) | Extracts LLM-ready content from web pages via Parallel Extract API. Accepts `urls` array. |
| `TavilyExtractTool()` | Tavily | Per-URL, depth-tiered, 5-URL batch (basic $0.008 / advanced $0.016 per batch) | Extracts cleaned content from web pages. Accepts `urls` array and `extract_depth`: `basic`, `advanced`. |
| `LinkupFetchTool()` | Linkup | Per-page, tiered (no-JS $0.001 / JS $0.005) | Fetches a single web page's content. Accepts `url` and `render_js` (bool). |
| `DirectHttpFetchTool()` | Direct HTTP | Free | Fetches a single URL over plain HTTP using the SDK's built-in `HttpFetcher`. No third-party cost. Accepts `url`. |

All fetch tools (except Linkup and DirectHttp) price by the number of URLs/pages requested. Tavily batches in groups of 5 URLs.

### Creating a Priced Operation Tool

Subclass `PricedOperationTool` and set the `operation` and `provider` ClassVars:

```python
from vidbyte.tools.builtins.operations import PricedOperationTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolParameter

class MySearchTool(PricedOperationTool):
    operation = "search"
    provider = "my_provider"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="my_search",
            description="Custom search tool.",
            parameters=(ToolParameter(name="query", type="string", description="Search query.", required=True),),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return self._contract_result(f"search: {call.arguments.get('query', '')}", units=1)
```

## Filesystem (21 tools)

Filesystem tools give agents full read/write access to the filesystem. They mirror common shell commands (`ls`, `mkdir`, `cp`, `mv`, `rm`, `cat`, `find`, `diff`, `zip`) and operate through a backend abstraction layer. Tools that modify the filesystem (`WRITE` operations) require the appropriate permission policy.

Use these tools for agents that need to create, read, update, or delete files — software engineering agents, data processing agents, or any agent that manages persistent state.

```python
from vidbyte.tools.filesystem import (
    ReadTextTool,     # read file as text
    ReadLinesTool,    # read file as list of lines
    ReadBinaryTool,   # read file as bytes
    WriteTextTool,    # write text to file (WRITE permission)
    AppendTool,       # append text to file (WRITE permission)
    ReplaceTextTool,  # find-and-replace in file (WRITE permission)
    ListDirTool,      # list directory contents
    MakeDirTool,      # create directory (WRITE permission)
    DeleteTool,       # delete file/directory (WRITE permission)
    CopyTool,         # copy file (WRITE permission)
    MoveTool,         # move/rename file (WRITE permission)
    RenameTool,       # rename file (WRITE permission)
    ExistsTool,       # check if path exists
    StatTool,         # file metadata (size, mtime, etc.)
    FindTool,         # recursive file find by name
    TreeTool,         # directory tree display
    DiffTool,         # compute file diffs
    ChecksumTool,     # compute file checksum
    TouchTool,        # create empty file / update mtime (WRITE permission)
    UnzipTool,        # extract zip archive (WRITE permission)
    ZipTool,          # create zip archive (WRITE permission)
)
```

Filesystem tools are organized around a backend system (`vidbyte/lib/tools/filesystem/backends/`) so the same tool works across local filesystems, remote storage, or virtual filesystems.

## MCP Bridge

The MCP (Model Context Protocol) bridge connects external MCP servers to the SDK as native tools. This lets agents use tools from any MCP-compatible server — filesystem servers, database servers, API servers — without the SDK needing to know about them at build time.

```python
from vidbyte.tools.mcp import (
    McpClient,           # JSON-RPC MCP client for communicating with MCP servers
    McpBridgedTool,      # Expose a remote MCP tool as a native SDK tool
    McpStdioTransport,   # Subprocess stdio transport for MCP servers
    McpServerConfig,     # Server command/config wrapper for defining MCP server connections
)
```

Attach MCP servers to agents via `agent.attach_mcp_server(...)` or `agent.with_mcp_server(...)`. Each MCP server's tools become available to the agent as if they were built-in.

## Security

Security tools enforce permission policies and sandbox constraints on tool execution. They ensure agents cannot perform unauthorized operations.

```python
from vidbyte.tools.security import (
    PermissionPolicy,     # Allow/deny rules for tool permissions (SAFE, READ, WRITE, EXECUTE)
    PermissionDecision,   # Result of a permission check — ALLOW, DENY, NEEDS_APPROVAL
)
```

Every tool declares a permission level. The agent evaluates each tool call against its policy. The default policy allows `SAFE` and `READ` tools, and denies `WRITE` and `EXECUTE` tools. Override with `permission_policy=PermissionPolicy.allow_all()` or a custom policy.

## Using the Tools Catalog

Tools are grouped into a `Tools` catalog for clean management. The catalog handles deduplication, incremental updates, and spec generation for model providers.

```python
from vidbyte import Tools

catalog = Tools([GlobTool(root_dir="."), GrepTool(root_dir=".")])
catalog.specs()   # model-facing tool declarations — the schema sent to the model
catalog.names()   # ("glob", "grep", ...)
catalog.all()     # tuple of BaseTool instances
```

The catalog is immutable by design. Operations like `add()` and `without()` return new `Tools` instances — the original is never mutated. This prevents accidental tool leakage between agents.

## Tool Execution Internals

These are internal subsystems that power tool execution. They are not typically used directly but are useful to understand:

- **`ToolExecutor`** — Validates permissions and executes tool calls. Checks each tool call against the agent's permission policy before execution.
- **`ToolsFormatter`** — Translates SDK tool specs to provider-specific schemas (OpenAI function calling, Anthropic tool use, Gemini function declarations, xAI tool format).
- **`IsDoneTool`** — An internal tool auto-injected into every agent so the model can signal when it is finished with tool calling and ready to return a final text response.
