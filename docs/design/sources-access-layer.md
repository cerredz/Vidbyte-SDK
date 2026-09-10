# Design Doc: Sources Access Layer

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-10
**Last Updated:** 2026-09-10

---

## 1. Overview

`Sources` is one developer-facing object that turns a list of external resource selections into the three things `BaseAgent.__init__` already accepts: `context_items`, `tools`, and `permission_policy`. A developer writes `Sources([...], max_tokens=...)`, awaits `resolve()`, and hands the result to an agent. Each selection declares a mode: `LOAD` fetches content before the first model call and admits it into the context window as `DocumentContextItem`s, `TOOLS` attaches resource-scoped tools the agent calls during the run, and `HYBRID` does both from one resolved connection. This PR ships the access layer, the scope enforcement, the budgets, and the reporting — it deliberately ships **no concrete providers**; a provider is registered by implementing the `ProviderAdapter` protocol.

---

## 2. Goals & Non-Goals

### Goals
- Add a `Sources` class whose first parameter is a positional array of selections and whose every other parameter is keyword-only.
- Support both access paths from one object: content admitted into the context window (`LOAD`) and resource-scoped tools the agent calls (`TOOLS`), plus `HYBRID`.
- Enforce resource scope at the tool boundary so an agent granted one resource cannot reach a sibling resource by changing a tool argument.
- Bound both paths: a token budget for loaded content, and call/byte budgets for tool exploration.
- Report coverage honestly — what loaded, what truncated, what failed, and why — instead of silently under-delivering.
- Define the `ProviderAdapter` protocol and an adapter registry so a provider can be added later without touching this layer.
- Define the `CredentialResolver` protocol plus an in-SDK implementation, so the SDK never needs to import a CLI to resolve a connection.
- Export `Sources` and its supporting types from the root `vidbyte` namespace.

### Non-Goals
- **No concrete providers.** No GitHub, Slack, Google Drive, or Notion adapter ships in this PR. The protocol and registry ship; implementations do not.
- No OAuth flows, no browser-based login, no device-code handshake.
- No CLI changes. `vidbyte-cli` is entirely out of scope for this PR.
- No changes to `vidbyte/context/`, `vidbyte/agents/`, or the existing `Source[T]` lifecycle in `vidbyte/sources/`.
- No remote MCP transport, HTTP OAuth, or MCP resource discovery.
- No indexing, embedding, or vector search over provider corpora.
- No hosted/backend connection service.
- No persisted manifest file format (`from_file`) or URL-parsing convenience (`from_urls`). Both are follow-ups.

---

## 3. Background & Context

The SDK can already compile a *public, unauthenticated* artifact into context: `Source.load()` in `vidbyte/sources/base.py` runs fetch → pin → parse → emit → cache and emits `DocumentContextItem`s carrying provenance and an untrusted-content fence. What it cannot do is represent an *authenticated, scoped* resource — a private repository, a workspace channel — or offer that resource to the agent as a tool rather than as pre-loaded text.

Two existing mechanisms come close and fall short in ways that motivate this design:

1. **MCP presets** (`vidbyte/tools/mcp/presets.py`) already name GitHub, Slack, Google Drive and many others. These are server *configurations*. `attach_mcp_server` (`vidbyte/tools/mcp/attach.py:66`) maps a server-wide `McpToolPermission.READONLY` onto every discovered tool as `ToolPermission.READ`. That labels the operation *kind*; it says nothing about *which* repository or channel a call may touch, and the label is asserted by the server rather than verified by the SDK.
2. **`PermissionPolicy.check(spec, call)`** (`vidbyte/lib/dataclasses/security.py:37`) already receives the full `ToolCall` and then discards it with `del call` on line 39. The seam for argument-aware authorization exists and is unused.

This PR fills the first gap by defining the access layer and closes the second by shipping `ResourceScopePolicy`, the first policy in the SDK that reads `call.arguments`.

**Constraint that shapes the whole design:** lint rule `A006` (`lint/rules/a006_directed_dependency_graph.py`) classifies `vidbyte.sources` as a *lower layer* and `vidbyte.context`, `vidbyte.tools`, and `vidbyte.agents` as *orchestration*. A concrete module under `vidbyte/sources/` may not import `vidbyte.tools`. Because `Sources` must produce tools **and** context items, it cannot live under `vidbyte/sources/`. It goes in a new `vidbyte/integrations/` package, which is unclassified by `A006` and may therefore depend on both layers. Nothing lower-layer imports it back.

---

## 4. Requirements

### Functional Requirements

1. `Sources(selections, *, ...)` accepts a positional sequence of `ResourceSelection` as its first argument; every other parameter is keyword-only.
2. An empty selection list is valid and resolves to empty context items, empty tools, and a permission policy that denies every scoped resource.
3. `Sources.resolve()` is asynchronous and returns a `ResolvedSources` exposing `context_items`, `tools`, `permission_policy`, and `report`.
4. A selection in `LOAD` mode causes its adapter's `load()` to be awaited during `resolve()`, and its emitted items to appear in `ResolvedSources.context_items`.
5. A selection in `TOOLS` mode causes no content fetch during `resolve()`; it contributes one `ScopedProviderTool` per operation the adapter declares in `capabilities()`.
6. A selection in `HYBRID` mode contributes both loaded items and scoped tools from one adapter resolution.
7. A generated tool's `ToolSpec` must not expose the resource identifier as a model-fillable parameter; the resource is bound at tool construction.
8. `ResourceScopePolicy` denies a tool call whose resolved resource is not in the run's granted set, before the adapter is invoked.
9. Loaded content is admitted against a token budget. When the budget is exhausted, remaining items are recorded as skipped rather than silently dropped.
10. An item that exceeds the remaining budget on its own is truncated at a character boundary and recorded as truncated with both the original and retained token estimate.
11. Every load failure is captured as a typed `AccessState` (`AUTH_REQUIRED`, `REAUTH_REQUIRED`, `INSUFFICIENT_SCOPE`, `RESOURCE_UNAVAILABLE`, `RATE_LIMITED`, `TRANSPORT_FAILED`) with the selection that produced it.
12. `on_failure="require_all"` raises `SourceAccessError` when any selection fails to load; `on_failure="report"` continues and records the failure.
13. A selection naming a provider with no registered adapter fails with a typed error at resolve time, not at run time.
14. A selection naming a connection with no registered credentials produces `AUTH_REQUIRED`, never an unauthenticated call.
15. `ToolBudget` denies a scoped tool call once the configured call count or cumulative byte ceiling is reached, returning a failed `ToolResult` rather than raising.
16. Every scoped tool result carries provenance metadata: provider, resource id, connection id, and a truncation marker.
17. `Sources` and its public supporting types are importable from the root `vidbyte` namespace.
18. Duplicate selections (same provider, resource, and mode) are rejected at construction with `ConfigurationError`.

### Non-Functional Requirements

- **Performance:** `LOAD` selections resolve concurrently via `asyncio.gather`; N selections cost roughly one round trip, not N sequential ones. `TOOLS` selections perform no network I/O during `resolve()`.
- **Scalability:** Budgets are the scaling control. Token, call-count, and byte ceilings all have defaults from `vidbyte/lib/constants/integrations.py` so an unbounded corpus cannot exhaust a context window.
- **Security:** Credentials never appear in a `ToolSpec`, a `ContextItem`, a report entry, or an exception message. Scope is enforced twice — by `ResourceScopePolicy` before execution and by the resource being closed over in the tool rather than passed in. All loaded provider content is wrapped by the existing untrusted-content fence so a model cannot read fetched text as instruction.
- **Observability:** `SourcesReport` is the observable surface: per-selection outcome, token accounting, and failure state, renderable as a single summary string.
- **Reliability:** One failing selection never aborts the others under `on_failure="report"`. An adapter that raises an unexpected exception is recorded as `TRANSPORT_FAILED` rather than propagating.

---

## 5. High-Level Design

The central idea is that `Sources.resolve()` is a *compiler*: selections in, agent constructor arguments out. It never wraps the agent, never subclasses it, and never adds a constructor parameter to it. This keeps the entire agent layer, `ContextManager`, and compaction untouched.

```
Sources([...selections], max_tokens=..., on_failure=...)
   |
   |  .resolve()
   v
SourcesResolver
   ├─ ConnectionRegistry.resolve(name) ──────> Connection
   ├─ CredentialResolver.resolve(connection) > Credentials     (AUTH_REQUIRED if absent)
   ├─ AdapterRegistry.get(provider) ─────────> ProviderAdapter (typed error if absent)
   |
   ├─ LOAD / HYBRID path                      TOOLS / HYBRID path
   |    adapter.load(request)                   adapter.capabilities()
   |      -> DocumentContextItem[]                -> ProviderToolset.build()
   |    ContextAdmissionBudget.admit()                        -> ScopedProviderTool per op
   |      -> kept / truncated / skipped          ResourceScopePolicy(granted ids)
   v                                                 v
ResolvedSources(context_items=..., tools=..., permission_policy=..., report=...)
   |
   v
Agent(context_items=..., tools=..., permission_policy=...)
```

At run time the tools path is enforced inside the existing loop. `AgentRuntime` already calls `self.permission_policy.check(spec, call)` at `vidbyte/agents/runtime.py:1221`; supplying a `ResourceScopePolicy` there is what makes an out-of-scope call return a denial instead of data.

Three design decisions are worth naming:

**`resolve()` is explicit and awaited rather than lazy inside `arun()`.** Loading performs authenticated network I/O that can take seconds and can fail on credentials. Hiding it inside agent construction would surface an auth failure in the middle of a run instead of at setup, and would force a synchronous constructor to drive async I/O. The cost is one extra line in the developer's code; the benefit is that failure happens where the developer can read the report.

**Scope is bound in a closure, not passed as a tool argument.** `ScopedProviderTool` holds `(adapter, resource, connection, credentials)` from construction. The model-facing `ToolSpec` describes only the operation's own arguments. This makes an out-of-scope call structurally impossible rather than merely denied, and `ResourceScopePolicy` is the second, auditable layer that turns a malformed attempt into a typed refusal the agent can read.

**No provider ships.** The registry starts empty. This keeps the PR reviewable as one architectural layer and means the first real provider is a pure addition — a module implementing `ProviderAdapter` plus a registration call — with no change to anything landed here.

---

## 6. Detailed Design

### 6.1 Integration enums

**File(s):** `vidbyte/lib/enums/integrations.py`
**Type:** New file

#### What it does
Owns every categorical vocabulary the access layer uses, as `str, Enum` classes in the central enum namespace (per the repo's "centralize categorical vocabularies" convention).

#### Interface / API
```python
class LoadMode(str, Enum):
    LOAD = "load"
    TOOLS = "tools"
    HYBRID = "hybrid"

class ProviderOperation(str, Enum):
    LIST = "list"
    SEARCH = "search"
    READ = "read"

class AccessState(str, Enum):
    GRANTED = "granted"
    AUTH_REQUIRED = "auth_required"
    REAUTH_REQUIRED = "reauth_required"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    RATE_LIMITED = "rate_limited"
    TRANSPORT_FAILED = "transport_failed"

class LoadOutcome(str, Enum):
    LOADED = "loaded"
    TRUNCATED = "truncated"
    SKIPPED = "skipped"
    FAILED = "failed"
    TOOLS_ONLY = "tools_only"

class FailurePolicy(str, Enum):
    REPORT = "report"
    REQUIRE_ALL = "require_all"
```
Each exposes a `values()` classmethod returning `tuple[str, ...]`.

#### Logic / Algorithm
Pure declaration. `values()` is derived from `__members__` so parser choices cannot drift from the enum.

#### Edge Cases & Error Handling
- Coercion from a raw string happens in `Sources.__init__`, never inside a dataclass field, per the "avoid union fields" convention.

---

### 6.2 Integration constants

**File(s):** `vidbyte/lib/constants/integrations.py`
**Type:** New file

#### What it does
Holds every numeric bound so limits are discoverable and widenable without editing validation bodies.

#### Interface / API
```python
INTEGRATIONS_DEFAULT_MAX_TOKENS = 20_000
INTEGRATIONS_MAX_TOKENS_CEILING = 1_000_000
INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS = 40
INTEGRATIONS_MAX_TOOL_CALLS_CEILING = 10_000
INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES = 2_000_000
INTEGRATIONS_MAX_SELECTIONS = 200
INTEGRATIONS_CHARS_PER_TOKEN = 4
INTEGRATIONS_MIN_TRUNCATION_CHARS = 200
```

#### Edge Cases & Error Handling
N/A — declarations only.

---

### 6.3 Integration dataclasses

**File(s):** `vidbyte/lib/dataclasses/integrations.py`
**Type:** New file

#### What it does
Owns every validated value type. Each is `@dataclass(frozen=True, slots=True)` and owns its rules in `__post_init__`, raising `ConfigurationError`, per the repo's strict-config-dataclass convention.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class Connection:
    connection_id: str
    provider: str
    account_label: str = ""

@dataclass(frozen=True, slots=True)
class Credentials:
    connection_id: str
    token: str
    scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool: ...
    def covers(self, required: tuple[str, ...]) -> bool: ...

@dataclass(frozen=True, slots=True)
class ResourceSelection:
    provider: str
    resource_id: str
    connection: str
    mode: LoadMode = LoadMode.LOAD
    filters: Mapping[str, Any] = field(default_factory=dict)
    limit: int | None = None
    required_scopes: tuple[str, ...] = ()

    @property
    def loads(self) -> bool: ...
    @property
    def exposes_tools(self) -> bool: ...
    def identity(self) -> tuple[str, str, str]: ...

@dataclass(frozen=True, slots=True)
class LoadRequest:
    selection: ResourceSelection
    connection: Connection
    credentials: Credentials

@dataclass(frozen=True, slots=True)
class ResourceScope:
    provider: str
    resource_id: str
    connection_id: str

    def qualified_id(self) -> str: ...      # "provider:resource_id"

@dataclass(frozen=True, slots=True)
class SelectionReportEntry:
    selection: ResourceSelection
    outcome: LoadOutcome
    state: AccessState
    item_count: int = 0
    tokens_loaded: int = 0
    tokens_original: int = 0
    detail: str = ""

@dataclass(frozen=True, slots=True)
class ContextBudgetPlan:
    max_tokens: int
    max_tool_calls: int
    max_tool_bytes: int
```

#### Logic / Algorithm
1. `Connection.__post_init__` requires non-empty `connection_id` and `provider`.
2. `Credentials.__post_init__` requires non-empty `connection_id` and `token`; `expires_at` must be timezone-aware when present (rule `S004` forbids naive datetimes).
3. `ResourceSelection.__post_init__` requires non-empty `provider`, `resource_id`, and `connection`; coerces `filters` to an immutable mapping; rejects `limit <= 0`.
4. `ContextBudgetPlan.__post_init__` rejects negatives and values above the ceilings in the constants module.
5. `ResourceScope.qualified_id()` produces the single string `ResourceScopePolicy` compares against.

#### Edge Cases & Error Handling
- A mutable default (`{}`) on a frozen dataclass is a lint violation (`S027`); `filters` uses `field(default_factory=dict)` and is frozen into a `MappingProxyType` in `__post_init__`.
- `Credentials.covers(())` returns `True` — a selection requiring no scopes is always covered.
- `is_expired` on a credential with no `expires_at` returns `False`; a non-expiring token is not an expired one.

---

### 6.4 Access error

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** Modified

#### What it does
Adds `SourceAccessError(SourceError)`, raised when `require_all` is violated, when a provider has no adapter, or when a selection references an unknown connection under a strict policy.

#### Interface / API
```python
class SourceAccessError(SourceError):
    """Signals that a requested source could not be accessed under the run's policy."""

    DIAGNOSTIC_FIELDS = ("error_kind", "expected", "actual", "safe_runtime_details",
                         "likely_causes", "repair_approaches", "related_docs", "relevant_tests")

    def __init__(self, provider: str, resource_id: str, state: str, detail: str = "") -> None: ...
```

#### Logic / Algorithm
Mirrors `ReasoningTraceArgumentError`'s exact shape: assigns all eight canonical fields as attributes and passes the same keys into `details`. Rule `A003` requires the full packet on any new class in this file.

#### Edge Cases & Error Handling
- `safe_runtime_details` carries provider, resource id, and state — never a token, and never raw provider response text.

---

### 6.5 Provider adapter protocol and registry

**File(s):** `vidbyte/integrations/adapters.py`
**Type:** New file

#### What it does
Defines what a provider must implement, and the registry that maps a provider name to its adapter. Ships **no** implementations.

#### Interface / API
```python
class ProviderAdapter(Protocol):
    @property
    def provider(self) -> str: ...
    def capabilities(self) -> frozenset[ProviderOperation]: ...
    async def load(self, request: LoadRequest) -> tuple[DocumentContextItem, ...]: ...
    async def invoke(self, operation: ProviderOperation, scope: ResourceScope,
                     credentials: Credentials, arguments: Mapping[str, Any]) -> str: ...
    def describe_operation(self, operation: ProviderOperation) -> ToolSpec: ...


class AdapterRegistry:
    def register(self, adapter: ProviderAdapter) -> "AdapterRegistry": ...
    def get(self, provider: str) -> ProviderAdapter: ...
    def has(self, provider: str) -> bool: ...
    def providers(self) -> tuple[str, ...]: ...
    def clear(self) -> None: ...
```

#### Logic / Algorithm
1. `register` rejects an adapter whose `provider` is blank or already registered (`ConfigurationError`).
2. `get` raises `SourceAccessError` with state `RESOURCE_UNAVAILABLE` naming the registered providers when the name is unknown.
3. A module-level `DEFAULT_ADAPTERS` instance is the registry `Sources` uses when none is injected.

#### Edge Cases & Error Handling
- `describe_operation` returning a spec whose parameters include the resource id is a contract violation the toolset detects (see 6.8) rather than trusting.

---

### 6.6 Connections and credential resolution

**File(s):** `vidbyte/integrations/connections.py`
**Type:** New file

#### What it does
Maps a developer-facing connection name to an immutable `Connection`, and resolves that connection to `Credentials`. The `CredentialResolver` protocol is the seam a CLI or a hosted backend implements later without the SDK importing either.

#### Interface / API
```python
class CredentialResolver(Protocol):
    async def resolve(self, connection: Connection) -> Credentials | None: ...


class ConnectionRegistry:
    def register(self, name: str, connection: Connection) -> "ConnectionRegistry": ...
    def resolve(self, name: str) -> Connection | None: ...
    def names(self) -> tuple[str, ...]: ...


class InMemoryCredentialResolver:
    def add(self, connection_id: str, credentials: Credentials) -> "InMemoryCredentialResolver": ...
    async def resolve(self, connection: Connection) -> Credentials | None: ...


class ConnectionBroker:
    def __init__(self, *, connections: ConnectionRegistry, resolver: CredentialResolver) -> None: ...
    async def authorize(self, selection: ResourceSelection) -> AuthorizationResult: ...
```

`AuthorizationResult` is a frozen dataclass carrying `state`, and — only when `state is GRANTED` — the `Connection` and `Credentials`.

#### Logic / Algorithm
`ConnectionBroker.authorize` runs one ordered chain:
1. Look up the connection name. Missing → `AUTH_REQUIRED`.
2. Confirm `connection.provider == selection.provider`. Mismatch → `INSUFFICIENT_SCOPE`.
3. Await the resolver. `None` → `AUTH_REQUIRED`.
4. `credentials.is_expired()` → `REAUTH_REQUIRED`.
5. `credentials.covers(selection.required_scopes)` false → `INSUFFICIENT_SCOPE`.
6. Otherwise `GRANTED`.

#### Edge Cases & Error Handling
- A resolver that raises is caught and mapped to `TRANSPORT_FAILED`; a broken keyring must not abort every other selection.
- `AuthorizationResult.credentials` is `None` on every non-granted state, so no caller can read a credential off a denied result.

---

### 6.7 Budgets

**File(s):** `vidbyte/integrations/budget.py`
**Type:** New file

#### What it does
`ContextAdmissionBudget` decides which loaded items are admitted, and how. `ToolBudget` bounds exploration at run time.

#### Interface / API
```python
class ContextAdmissionBudget:
    def __init__(self, *, max_tokens: int) -> None: ...
    def admit(self, items: tuple[DocumentContextItem, ...]) -> BudgetAdmission: ...
    @staticmethod
    def estimate_tokens(text: str) -> int: ...


class ToolBudget:
    def __init__(self, *, max_calls: int, max_bytes: int) -> None: ...
    def charge(self, byte_count: int) -> bool: ...
    def would_exceed(self) -> bool: ...
    def remaining_calls(self) -> int: ...
```

`BudgetAdmission` is a frozen dataclass of `items`, `tokens_admitted`, `tokens_original`, and `outcome`.

#### Logic / Algorithm
`ContextAdmissionBudget.admit` walks items in order:
1. Estimate the item's tokens as `ceil(len(content) / INTEGRATIONS_CHARS_PER_TOKEN)`.
2. If it fits in the remaining budget, admit it whole.
3. If it does not fit but the remaining budget is at least `INTEGRATIONS_MIN_TRUNCATION_CHARS`, truncate the content at that character count, append a truncation marker, stamp `metadata["truncated"] = True`, and record `TRUNCATED`.
4. If less than the minimum remains, stop and record every remaining item as `SKIPPED`.

`ToolBudget` splits its two ceilings across the tool call. `reserve()` claims one call before the provider is contacted and returns `False` once the call ceiling is reached. `admit_output()` runs after the provider responds and charges the returned payload — measured in UTF-8 bytes, because that is what actually consumes the agent's context — clipping and marking anything that overruns the remaining budget. Both ceilings are sticky: once either is crossed the budget stays closed for the rest of the run.

#### Edge Cases & Error Handling
- `max_tokens=0` admits nothing and reports every item skipped — it does not raise.
- Truncation slices the wrapped content string, so the untrusted-content opening fence is preserved and a closing marker is appended; a truncated item is never left with an unterminated fence.
- `estimate_tokens("")` is `0`, so an empty document is admitted free rather than counted as one token.

---

### 6.8 Scoped provider tools

**File(s):** `vidbyte/integrations/toolsets.py`
**Type:** New file

#### What it does
Turns an adapter's declared capabilities into `BaseTool` instances whose resource is bound at construction, and which charge a `ToolBudget` on every call.

#### Interface / API
```python
class ScopedProviderTool(BaseTool):
    def __init__(self, *, adapter: ProviderAdapter, operation: ProviderOperation,
                 scope: ResourceScope, credentials: Credentials, budget: ToolBudget,
                 spec: ToolSpec) -> None: ...
    def spec(self) -> ToolSpec: ...
    def validate_call(self, call: ToolCall) -> str | None: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...


class ProviderToolset:
    @staticmethod
    def build(*, adapter: ProviderAdapter, scope: ResourceScope, credentials: Credentials,
              budget: ToolBudget) -> tuple[ScopedProviderTool, ...]: ...
```

#### Logic / Algorithm
`ProviderToolset.build` iterates the adapter's capabilities in deterministic enum order and, per operation:
1. Asks the adapter for its `ToolSpec` via `describe_operation`.
2. Rejects a spec declaring a parameter named `resource_id`, `repo`, `channel`, or `connection` — a provider must not let the model address the resource (`ConfigurationError`).
3. Rewrites the spec's `name` to `f"{provider}_{operation}_{sanitized_resource}"` so two selections on the same provider produce distinct, non-colliding tool names.
4. Stamps `metadata["resource_id"] = scope.qualified_id()` — the field `ResourceScopePolicy` reads.
5. Forces `permission = ToolPermission.READ`.

`ScopedProviderTool.execute` runs four steps: charge the budget, invoke the adapter with the closed-over scope, wrap the result with provenance metadata, and map any adapter exception to a failed `ToolResult`.

#### Edge Cases & Error Handling
- Budget exhausted → `ToolResult.failure` with `metadata["error"] = "budget_exhausted"`; never an exception, so the agent can adapt.
- Adapter raises → `ToolResult.failure` with `error_type` set to the exception class name and no raw provider text (rule `S017` forbids raw exception disclosure).
- A resource id containing characters illegal in a tool name is sanitized to `[a-z0-9_]` and truncated, with a short hash suffix to keep two similar ids distinct.

---

### 6.9 Resource scope policy

**File(s):** `vidbyte/lib/dataclasses/security.py`
**Type:** Modified

#### What it does
The first argument-aware permission policy in the SDK. Denies a tool call whose spec names a resource outside the run's granted set.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ResourceScopePolicy(PermissionPolicy):
    granted_resources: frozenset[str] = frozenset()

    def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision: ...
```

#### Logic / Algorithm
1. Delegate to `PermissionPolicy.check` first; a permission-level denial short-circuits.
2. Read `spec.metadata.get("resource_id")`. Absent → the tool is not a scoped provider tool, so allow (this policy must not break ordinary tools).
3. Present and not in `granted_resources` → `DENY`.
4. Otherwise `ALLOW`.

#### Edge Cases & Error Handling
- An empty `granted_resources` denies every scoped tool while still allowing unscoped tools — the correct behavior for `Sources([])`.
- The policy reads the *spec*, not `call.arguments`, for the resource: the resource is never a call argument by construction, and reading the spec means a forged argument cannot influence the decision.

---

### 6.10 Sources and the resolver

**File(s):** `vidbyte/integrations/sources.py`
**Type:** New file

#### What it does
The developer-facing object. Its `__init__` is a thin adapter that coerces loose arguments into validated dataclasses; `resolve()` delegates to `SourcesResolver`.

#### Interface / API
```python
class Sources:
    def __init__(self, selections: Sequence[ResourceSelection], *,
                 max_tokens: int = INTEGRATIONS_DEFAULT_MAX_TOKENS,
                 max_tool_calls: int = INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS,
                 max_tool_bytes: int = INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES,
                 on_failure: FailurePolicy | str = FailurePolicy.REPORT,
                 connections: ConnectionRegistry | None = None,
                 credentials: CredentialResolver | None = None,
                 adapters: AdapterRegistry | None = None) -> None: ...

    @property
    def selections(self) -> tuple[ResourceSelection, ...]: ...
    @property
    def budget(self) -> ContextBudgetPlan: ...
    async def resolve(self) -> ResolvedSources: ...


@dataclass(frozen=True, slots=True)
class ResolvedSources:
    context_items: tuple[DocumentContextItem, ...]
    tools: tuple[BaseTool, ...]
    permission_policy: ResourceScopePolicy
    report: SourcesReport
```

#### Logic / Algorithm
`__init__`:
1. Coerce `selections` to a tuple; reject a bare `ResourceSelection` passed without a list, and reject a count above `INTEGRATIONS_MAX_SELECTIONS`.
2. Reject duplicate `selection.identity()` values with `ConfigurationError`.
3. Coerce `on_failure` from `str` to `FailurePolicy` here, so the stored value is one concrete type.
4. Build one `ContextBudgetPlan`, which owns every numeric bound check.
5. Default the three registries to fresh/among-module instances.

`SourcesResolver.resolve()` composes four named steps:
1. `_authorize_all()` — awaits `ConnectionBroker.authorize` for every selection concurrently, returning granted pairs and failure entries.
2. `_load_content()` — awaits `adapter.load` for every granted `LOAD`/`HYBRID` selection concurrently, then admits results through `ContextAdmissionBudget`.
3. `_build_tools()` — builds scoped tools for every granted `TOOLS`/`HYBRID` selection and collects granted resource ids.
4. `_assemble()` — constructs `ResourceScopePolicy`, the `SourcesReport`, and the `ResolvedSources`; raises `SourceAccessError` first when the policy is `REQUIRE_ALL` and any entry failed.

#### Edge Cases & Error Handling
- `asyncio.gather(..., return_exceptions=True)` is used for both concurrent phases so one adapter raising cannot cancel its siblings; each exception becomes a `TRANSPORT_FAILED` entry.
- A `HYBRID` selection that fails authorization contributes neither items nor tools, and appears exactly once in the report.
- An adapter returning an empty tuple is `LOADED` with `item_count=0`, not `FAILED` — an empty channel is a valid answer.

---

### 6.11 Sources report

**File(s):** `vidbyte/integrations/report.py`
**Type:** New file

#### What it does
The honest-coverage surface. Records one entry per selection and answers whether the run got what it asked for.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class SourcesReport:
    entries: tuple[SelectionReportEntry, ...] = ()

    @property
    def loaded(self) -> tuple[SelectionReportEntry, ...]: ...
    @property
    def truncated(self) -> tuple[SelectionReportEntry, ...]: ...
    @property
    def skipped(self) -> tuple[SelectionReportEntry, ...]: ...
    @property
    def failed(self) -> tuple[SelectionReportEntry, ...]: ...
    @property
    def complete(self) -> bool: ...
    def tokens_admitted(self) -> int: ...
    def summary(self) -> str: ...
```

#### Logic / Algorithm
`complete` is `True` only when no entry is `FAILED`, `TRUNCATED`, or `SKIPPED`. `summary()` renders one line per outcome group, omitting empty groups, and never prints a credential.

#### Edge Cases & Error Handling
- An empty report is `complete` and summarizes as `"no sources requested"` rather than an empty string.

---

### 6.12 Package exports

**File(s):** `vidbyte/integrations/__init__.py`, `vidbyte/__init__.py`
**Type:** New file / Modified

#### What it does
Exposes the public surface. Rule `S015` requires every root public import to appear in the root `__all__`.

#### Interface / API
```python
from vidbyte import Sources, ResourceSelection, Connection, Credentials, LoadMode
```

#### Edge Cases & Error Handling
- Names are appended to the existing root `__all__`; `S015` fails the build if any imported public name is omitted.

---

### 6.13 Package README

**File(s):** `vidbyte/integrations/README.md`
**Type:** New file

#### What it does
Documents the layer for the next agent. Rule `S020` compares a README's `## File Index` against the folder's tracked direct children, so the index must list every module in the package.

---

## 7. Data Model Changes

N/A — the SDK has no database. The dataclass contracts introduced in 6.3 are in-memory value types only; nothing is persisted to disk or a store by this feature.

---

## 8. API Changes

N/A — the SDK exposes no HTTP endpoints. The public Python API additions are specified in Section 6 and summarized in Section 9.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/sources-access-layer.md` | This design doc |
| CREATE | `vidbyte/lib/enums/integrations.py` | `LoadMode`, `ProviderOperation`, `AccessState`, `LoadOutcome`, `FailurePolicy` |
| CREATE | `vidbyte/lib/constants/integrations.py` | Budget defaults and ceilings |
| CREATE | `vidbyte/lib/dataclasses/integrations.py` | `Connection`, `Credentials`, `ResourceSelection`, `LoadRequest`, `ResourceScope`, report/budget value types |
| CREATE | `vidbyte/integrations/__init__.py` | Public surface of the access layer |
| CREATE | `vidbyte/integrations/README.md` | Folder documentation with File Index (rule `S020`) |
| CREATE | `vidbyte/integrations/adapters.py` | `ProviderAdapter` protocol and `AdapterRegistry` |
| CREATE | `vidbyte/integrations/connections.py` | `ConnectionRegistry`, `CredentialResolver`, `InMemoryCredentialResolver`, `ConnectionBroker` |
| CREATE | `vidbyte/integrations/budget.py` | `ContextAdmissionBudget`, `ToolBudget` |
| CREATE | `vidbyte/integrations/toolsets.py` | `ScopedProviderTool`, `ProviderToolset` |
| CREATE | `vidbyte/integrations/report.py` | `SourcesReport` |
| CREATE | `vidbyte/integrations/sources.py` | `Sources`, `SourcesResolver`, `ResolvedSources` |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Re-export the new enums |
| MODIFY | `vidbyte/lib/dataclasses/security.py` | Add `ResourceScopePolicy` |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `SourceAccessError` with the full diagnostic packet |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Re-export `SourceAccessError` |
| MODIFY | `vidbyte/__init__.py` | Export `Sources` and supporting public types |
| MODIFY | `README.md` | Add `vidbyte/integrations/` to the Layer Guide |
| CREATE | `tests/test_sources_access_layer.py` | Full unit and integration suite from Section 10 |
| CREATE | `scripts/test-sources-access-layer.py` | Phase-5 verification script |

**Totals:** 15 created, 6 modified, 0 deleted.

---

## 10. Testing Plan

A `FakeAdapter` test double implements `ProviderAdapter` in the test module. It is a test fixture, not a shipped provider, and it is configurable to return content, raise, or return empty.

### Unit Tests

**`Sources` construction**
- `it('accepts a positional list and keyword-only options')` — [Hidden Assumption] — asserts `Sources([], max_tokens=1)` works and `Sources([], 1)` raises `TypeError`, proving every non-first parameter is keyword-only.
- `it('resolves an empty selection list to empty everything')` — [Edge Case] — zero-length input is the boundary case; must not raise.
- `it('rejects a bare ResourceSelection passed without a list')` — [Hidden Assumption] — a `ResourceSelection` is iterable-adjacent enough to be silently mis-accepted.
- `it('rejects duplicate selections with the same provider, resource, and mode')` — [Silent Failure] — a duplicate would otherwise double-charge the token budget and register a colliding tool name.
- `it('rejects a selection count above INTEGRATIONS_MAX_SELECTIONS')` — [Edge Case]
- `it('coerces a string on_failure into FailurePolicy')` — [Hidden Assumption]
- `it('rejects max_tokens above the ceiling and below zero')` — [Edge Case]

**`ContextAdmissionBudget`**
- `it('admits one item that fits exactly at the budget boundary')` — [Edge Case] — off-by-one at `tokens == max_tokens` is the classic failure here.
- `it('truncates an item that exceeds the remaining budget')` — [Silent Failure] — the danger is admitting a truncated item while reporting it as fully loaded.
- `it('marks truncated content with metadata and a visible marker')` — [Silent Failure]
- `it('preserves the untrusted-content fence when truncating')` — [Hidden Failure] — a slice through the fence would leave the model reading provider text as unfenced instruction.
- `it('skips remaining items once the budget is exhausted rather than dropping them silently')` — [Silent Failure]
- `it('admits nothing and reports all skipped when max_tokens is zero')` — [Edge Case]
- `it('estimates zero tokens for an empty document')` — [Edge Case]

**`ToolBudget`**
- `it('denies the call after the call ceiling is reached')` — [Edge Case]
- `it('denies once the cumulative byte ceiling is crossed')` — [Edge Case]
- `it('stays denied after the first denial')` — [Hidden Failure] — a budget that resets would allow unbounded exploration after one refusal.

**`ConnectionBroker`**
- `it('returns AUTH_REQUIRED when the connection name is unregistered')` — [Hidden Assumption]
- `it('returns AUTH_REQUIRED when the resolver yields None')` — [Hidden Assumption] — the implementation must never proceed unauthenticated.
- `it('returns REAUTH_REQUIRED for an expired credential')` — [Edge Case]
- `it('returns INSUFFICIENT_SCOPE when required scopes are not covered')` — [Hidden Assumption]
- `it('returns INSUFFICIENT_SCOPE when the connection provider does not match the selection')` — [Silent Failure] — a Slack connection silently used for a GitHub selection would produce confusing auth errors far downstream.
- `it('returns TRANSPORT_FAILED when the resolver raises')` — [Hidden Failure]
- `it('never exposes credentials on a non-granted result')` — [Hidden Failure]
- `it('treats an empty required_scopes tuple as covered')` — [Edge Case]

**`ResourceScopePolicy`**
- `it('allows a tool whose spec carries no resource_id')` — [Hidden Assumption] — ordinary non-provider tools must keep working under this policy.
- `it('denies a scoped tool whose resource is not granted')` — [Hidden Failure] — the core security assertion.
- `it('denies every scoped tool when granted_resources is empty')` — [Edge Case]
- `it('short-circuits to DENY when the base permission level is disallowed')` — [Hidden Assumption]

**`ProviderToolset` / `ScopedProviderTool`**
- `it('does not expose the resource id as a model-fillable parameter')` — [Hidden Failure] — the whole scoping guarantee collapses if it does.
- `it('rejects an adapter spec that declares a resource-addressing parameter')` — [Hidden Assumption] — a third-party adapter is untrusted input to this layer.
- `it('generates distinct tool names for two selections on the same provider')` — [Silent Failure] — colliding names raise `ToolRegistrationError` in `Tools`, or worse, shadow one resource with another.
- `it('sanitizes a resource id containing characters illegal in a tool name')` — [Edge Case]
- `it('returns a failed ToolResult when the budget is exhausted')` — [Hidden Failure]
- `it('returns a failed ToolResult without raw provider text when the adapter raises')` — [Hidden Failure]
- `it('stamps provenance metadata on every successful result')` — [Silent Failure]
- `it('builds tools in deterministic order across runs')` — [Hidden Failure]

**`SourcesResolver`**
- `it('loads content for a LOAD selection')` — happy path
- `it('performs no fetch for a TOOLS selection')` — [Silent Failure] — a TOOLS selection that quietly loads would blow the token budget the developer never allocated.
- `it('produces both items and tools for a HYBRID selection')` — [Edge Case]
- `it('continues loading siblings when one adapter raises')` — [Hidden Failure]
- `it('records a failing selection exactly once for HYBRID')` — [Silent Failure] — double-counting would make the report lie about coverage.
- `it('raises SourceAccessError under require_all when any selection fails')` — [Hidden Assumption]
- `it('treats an adapter returning zero items as LOADED, not FAILED')` — [Silent Failure] — an empty channel is a valid answer, and reporting it as failure would send a developer chasing a non-bug.
- `it('raises a typed error for a provider with no registered adapter')` — [Hidden Assumption]
- `it('resolves LOAD selections concurrently rather than sequentially')` — [Hidden Failure]

**`SourcesReport`**
- `it('reports complete only when nothing failed, truncated, or was skipped')` — [Silent Failure]
- `it('summarizes an empty report without an empty string')` — [Edge Case]
- `it('never includes a credential token in the summary')` — [Hidden Failure]

### Integration Tests

- **Full resolve into a real `Agent`.** Construct `Sources` with one LOAD and one TOOLS selection against `FakeAdapter`, resolve, and pass all three outputs into a real `Agent`. Asserts the outputs are actually accepted by the existing constructor — the single assumption the whole design rests on.
- **Scope denial through the real runtime path.** Register two scoped tools, grant only one, and drive `permission_policy.check` with a `ToolCall` for the ungranted tool exactly as `AgentRuntime` does at `runtime.py:1221`. Asserts denial happens on the real code path, not a mocked one.
- **Mocked vs. real:** the adapter is the only fake — it stands in for network I/O. `ContextManager`, `Tools`, `PermissionPolicy`, `ToolExecutor`, and `Agent` are all real, because the integration risk lives at those seams.
- **Silent failure path between components:** a `DocumentContextItem` admitted by the budget but not reaching `ContextManager` would leave the agent running with less context than reported. The integration test asserts the item count that reaches a real `ContextManager` equals the count the report claims.
- **Hidden assumption only integration surfaces:** `Tools` raises `ToolRegistrationError` on duplicate names. Unit tests on `ProviderToolset` alone would not catch a name collision between two *different* selections; the integration test builds both and constructs a real `Tools` catalog.

### Manual / QA Test Cases

1. Given a `Sources` with three LOAD selections and a `max_tokens` too small for all three, when resolved, then the report names exactly which were truncated and skipped and the admitted token count is at or below the budget — [Silent Failure].
2. Given a selection whose credential is expired, when resolved with `on_failure="report"`, then the run continues, the entry reads `REAUTH_REQUIRED`, and no network call is attempted — [Hidden Assumption].
3. Given the same setup with `on_failure="require_all"`, when resolved, then `SourceAccessError` is raised and its message contains no token — [Hidden Failure].
4. Given a TOOLS selection for resource A and a crafted `ToolCall` naming resource B's tool, when checked against the policy, then the decision is `DENY` — [Hidden Failure].
5. Given `Sources([])`, when resolved and passed to an `Agent`, then the agent constructs and runs normally with no tools and no added context — [Edge Case].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `asyncio` | 3.11+ | Concurrent authorization and loading | None — already used throughout the SDK |
| Python stdlib `dataclasses` | 3.11+ | Frozen, slotted value types | None |
| `vidbyte.context.primitives` | in-repo | `DocumentContextItem` emitted by adapters | Existing contract; not modified |
| `vidbyte.tools` | in-repo | `BaseTool`, `ToolSpec`, `ToolResult` | Existing contract; not modified |

No new third-party dependency is introduced. No external service is contacted by this PR, because no provider ships.

---

## 12. Rollout & Deployment

- **Feature flags:** none. Every addition is new public API; no existing behavior changes path.
- **Breaking change:** no. `ResourceScopePolicy` is a new subclass — the default `PermissionPolicy` is untouched, and an agent constructed without `permission_policy` behaves exactly as before. The one modified shared file, `vidbyte/lib/dataclasses/security.py`, only gains a class.
- **Deployment order:** single package; no ordering concern.
- **Rollback:** revert the branch. Nothing persists state, so there is no data to migrate back.
- **Migration path:** none needed — no existing caller uses these names today.

---

## 13. Open Questions

- [ ] Should `Credentials` support a refresh token and an automatic refresh hook now, or wait for the first OAuth provider that actually needs it? This PR stores `expires_at` and reports `REAUTH_REQUIRED` without attempting refresh.
- [ ] Should loaded content participate in `PinPolicy` / `SnapshotCache` so a `LOAD` selection can pin a revision across runs? Deferred: pinning is meaningful per provider (a PR wants pinning, a live channel does not), and no provider exists yet to decide against.
- [ ] Is `estimate_tokens` at 4 characters per token accurate enough, or should the budget accept an injected tokenizer? Deferred: an injected counter is a pure addition later, and the current estimate is deliberately conservative.
- [ ] Should `Sources` expose a synchronous `resolve_sync()` wrapper for non-async callers? Deferred until a caller asks.

---

## 14. Alternatives Considered

### Alternative 1: Add a `sources=` parameter to `Agent.__init__`
- **What:** Let `Agent(sources=Sources([...]))` resolve lazily on the first `arun()`.
- **Why rejected:** Resolution performs authenticated network I/O. Hiding it inside a synchronous constructor means an auth failure surfaces mid-run instead of at setup, and the developer never sees the coverage report before the model reads the context. It also adds a parameter to the SDK's most central class for a feature that composes cleanly without one. Explicit `resolve()` costs one line and keeps `BaseAgent` untouched.

### Alternative 2: Put `Sources` under `vidbyte/sources/`
- **What:** The obvious home, given the name.
- **Why rejected:** Lint rule `A006` classifies `vidbyte.sources` as a lower layer that may not import `vidbyte.tools` or `vidbyte.context`. `Sources` must build tools, so this placement is a blocking lint regression, not a style preference. `vidbyte/integrations/` is unclassified by `A006` and may depend on both layers.

### Alternative 3: Build the tools path on MCP instead of a native protocol
- **What:** Reuse `attach_mcp_server` and the existing MCP presets for the tools path.
- **Why rejected:** `attach_mcp_server` maps a server-wide permission onto every discovered tool, which cannot express "this repository only." Resource-level scope is the security property this feature exists to provide. An MCP-backed adapter remains possible later — it just implements `ProviderAdapter` like any other.

### Alternative 4: Pass the resource id as a tool parameter and validate it
- **What:** Let the model call `github_read_file(repo, path)` and reject a bad `repo`.
- **Why rejected:** It makes an out-of-scope call *expressible*, so correctness then depends on the validator running on every path. Closing over the resource makes it inexpressible, and `ResourceScopePolicy` becomes a second audited layer rather than the only line of defense.

### Alternative 5: Ship one real provider alongside the layer
- **What:** Include a GitHub adapter to prove the design end to end.
- **Why rejected:** The user scoped this PR to the access layer explicitly. A `FakeAdapter` in the test suite exercises every path a real provider would, and keeps the diff reviewable as one architectural change.

---

---

## 15. Implementation Deviations

Recorded during the Phase 5.5 self-critique; each is a deliberate departure from the
text above, not drift.

### 15.1 `ContextBudget` renamed to `ContextAdmissionBudget`

`vidbyte/lib/dataclasses/context.py` already defines a `ContextBudget` that is
exported from the root `vidbyte` namespace. Shipping a second class under that
name would have shadowed an existing public symbol — a silent breaking change for
any caller doing `from vidbyte import ContextBudget`. The admission budget is
therefore `ContextAdmissionBudget`, which also states what it does more precisely.

### 15.2 `LoadOutcome.TOOLS_ONLY` added

Section 6.1 listed four outcomes. A `TOOLS` selection contributes capability rather
than content, so recording it as `LOADED` with zero items would have been
misleading, and recording it as `SKIPPED` would have wrongly marked the report
incomplete. A fifth member keeps `SourcesReport.complete` honest.

### 15.3 `ToolBudget.charge()` split into `reserve()` and `admit_output()`

The first implementation charged `len(str(call.arguments))` — the *request*, not the
*response*. That left `max_tool_bytes` inert: an agent could return unbounded bytes
across its allowed call count, which is the exact context-flooding case the ceiling
exists to prevent. The budget now claims the call before the provider is contacted
and charges the returned payload afterwards, clipping and marking an overrun. This
also supplies the truncation marker Requirement 16 asks for on every scoped result.

### 15.4 `ResourceScopePolicy.check` calls its base explicitly

`@dataclass(slots=True)` rebuilds the class object, so a zero-argument `super()`
resolves its implicit `__class__` cell to the discarded pre-slots class and raises
`TypeError` on every call. The base method is invoked as
`PermissionPolicy.check(self, spec, call)` instead.
