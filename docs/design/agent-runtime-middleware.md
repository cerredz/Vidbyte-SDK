# Design Doc: Agent Runtime Middleware

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Add a public `vidbyte.middleware` package that lets SDK users attach deterministic runtime middleware to agents. Middleware runs at explicit lifecycle breakpoints in the PR #31 `AgentRuntime` loop, giving developers fine-grained control over authentication, authorization, rate limiting, retry, audit logging, and runtime budgets without exposing those policies as model-visible tools. Developers create middleware by subclassing an `AgentMiddleware` abstract base class and overriding only the hook methods they need.

---

## 2. Goals & Non-Goals

### Goals

- Add a new public `vidbyte/middleware/` package.
- Define an abstract `AgentMiddleware` base class with optional hook methods for runtime breakpoints.
- Define immutable middleware dataclasses centrally under `vidbyte/lib/dataclasses/middleware.py`.
- Let `BaseAgent` accept `middleware=[...]` and pass middleware into `AgentRuntime`.
- Run middleware inside the direct text `AgentRuntime` loop added by PR #31.
- Support hooks before and after runs, iterations, model calls, model responses, tool calls, and tool results.
- Support structured middleware decisions: continue, sleep, abort run, deny tool, and retry model call.
- Preserve PR #31 runtime semantics: text direct agents stop through internal `isDone` or budget stops; normal text responses remain intermediate progress.
- Keep internal runtime tools such as `isDone` visible to middleware through context metadata without exposing them as public tools.
- Ship useful built-in middleware out of the gate:
  - `TokenRateLimitMiddleware`
  - `RuntimeLimitMiddleware`
  - `ToolPolicyMiddleware`
  - `AuditLogMiddleware`
  - `ModelRetryMiddleware`
- Make middleware testable with fake clocks, fake sleepers, fake runners, and fake tools.
- Document custom middleware authoring in README and SDK structure guidance.

### Non-Goals

- No model-visible middleware tools. Middleware is runtime policy code, not a capability the model chooses.
- No middleware support for strategy-backed agents in the first implementation; strategies already own their own loops.
- No middleware execution for non-text direct modality runs in the first implementation; image/video direct runs still execute once.
- No arbitrary mutation of runtime context, provider messages, prompts, or tool results in v1.
- No persistent middleware registry, plugin marketplace, database, or remote policy service.
- No new third-party dependencies.
- No replacement of existing `PermissionPolicy`; middleware complements it.
- No character-count token estimation fallback. Token-aware middleware uses provider-reported token usage, matching PR #31.
- No hard cancellation of already-running sync runner calls. Runtime limits are checked at hook boundaries; async model retry wraps model-call exceptions only.

---

## 3. Background & Context

- PR #31 added `vidbyte/agents/runtime.py`, moving direct text agent execution into `AgentRuntime`.
- PR #31 changed direct text agents to loop until the model calls the private internal `isDone` tool or a configured budget stops the run.
- PR #31 added provider-reported token usage extraction in `vidbyte/lib/token_usage.py`; the SDK no longer invents local character-count token estimates.
- `BaseAgent` currently accepts tools, permission policy, runtime budget fields, modality routing, and metadata, then constructs `AgentRuntime` on demand.
- Tool execution already has deterministic permission checks through `PermissionPolicy`, but there is no general runtime policy hook for user-specific database checks, tenant quotas, audit logging, rate limiting, or retry behavior.
- Users want middleware as a deterministic runtime control plane with multiple breakpoints and a clear custom authoring interface.
- The repository convention keeps dataclasses under `vidbyte/lib/dataclasses/`, package exports in local `__init__.py` files, tests under `tests/`, and user-facing examples in `README.md`.
- The local checkout is dirty and behind `origin/main`; implementation must occur later in a clean isolated worktree from updated `main`, per the design-doc workflow.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte.middleware` must expose `AgentMiddleware`, `MiddlewarePipeline`, middleware dataclasses, and built-in middleware classes.
2. `AgentMiddleware` must be an abstract base class whose hook methods all default to `MiddlewareDecision.continue_()`.
3. Developers must be able to subclass `AgentMiddleware` and override only the lifecycle hooks they need.
4. Middleware hooks must include:
   - `before_run`
   - `before_iteration`
   - `before_model_call`
   - `after_model_response`
   - `on_model_error`
   - `before_tool_call`
   - `after_tool_call`
   - `after_iteration`
   - `after_run`
5. Hook methods must accept a `MiddlewareContext` and return a `MiddlewareDecision`.
6. `on_model_error` must also receive the exception, either through a dedicated parameter or through `MiddlewareContext.error`.
7. `MiddlewareDecision` must support `continue_()`, `sleep(seconds, reason=...)`, `abort(reason=...)`, `deny_tool(reason=...)`, and `retry(reason=..., sleep_seconds=...)` constructors.
8. `MiddlewareAction` must be an enum or enum-like string type with values for continue, sleep, abort run, deny tool, and retry.
9. `MiddlewareContext` must expose agent name, run id, provider, message, hook name, iteration count, model call count, tool call count, elapsed seconds, provider-reported tokens used, current `BaseAgentContext`, optional tool call, optional tool result, optional model response, optional error, internal-tool flag, and metadata.
10. `MiddlewarePipeline` must execute middleware in the order supplied to `BaseAgent`.
11. `MiddlewarePipeline` must apply `sleep` decisions using an injectable async sleeper, defaulting to `asyncio.sleep`.
12. `MiddlewarePipeline` must stop hook execution immediately for abort, deny-tool, and retry decisions.
13. Middleware exceptions must be handled according to each middleware instance's `fail_closed` flag.
14. `fail_closed=True` must convert middleware exceptions into abort decisions.
15. `fail_closed=False` must convert middleware exceptions into continue decisions while attaching safe error metadata.
16. `BaseAgent.__init__` must accept `middleware: Sequence[AgentMiddleware] = ()`.
17. `BaseAgent.fork()` must preserve middleware unless explicitly overridden.
18. `BaseAgent._runtime()` must construct `AgentRuntime(..., middleware=self.middleware)`.
19. `AgentRuntime.__init__` must accept middleware and construct a `MiddlewarePipeline`.
20. `AgentRuntime.arun()` must call `before_run` once before the loop.
21. `AgentRuntime.arun()` must call `before_iteration` before each loop iteration and `after_iteration` after each completed iteration.
22. `AgentRuntime.arun()` must call `before_model_call` immediately before invoking the runner.
23. `AgentRuntime.arun()` must call `after_model_response` after a successful runner response and token usage extraction.
24. `AgentRuntime.arun()` must call `on_model_error` when runner invocation raises.
25. `ModelRetryMiddleware` must be able to request retry of model-call errors up to a configured maximum.
26. `AgentRuntime` must call `before_tool_call` before permission validation and local tool execution.
27. A `deny_tool` decision from `before_tool_call` must produce a `ToolResult.error(...)` and `ToolCallContext(state=DENIED)` without executing the tool.
28. `AgentRuntime` must call `after_tool_call` after every executed or middleware-denied tool call.
29. `AgentRuntime` must call `after_run` before returning final, budget-stopped, or middleware-aborted results.
30. Middleware-aborted runs must return a `StrategyResult` with machine-readable stop metadata.
31. `AgentStopReason` must gain `MIDDLEWARE_ABORT = "middleware_abort"`.
32. Middleware metadata must be included in final `StrategyResult.metadata` under a stable key such as `middleware`.
33. Middleware must see internal tools through `MiddlewareContext.tool_is_internal`; built-in `ToolPolicyMiddleware` must allow internal tools by default.
34. `TokenRateLimitMiddleware` must use provider-reported `tokens_used`; if token usage is unavailable, it must continue without sleeping or aborting.
35. `RuntimeLimitMiddleware` must support max elapsed seconds, max model calls, and max tool calls at hook boundaries.
36. `ToolPolicyMiddleware` must support allowlist and denylist checks by tool name.
37. `AuditLogMiddleware` must emit structured events to an injected sink callable or list-like sink for every configured hook.
38. `ModelRetryMiddleware` must retry model-call exceptions with deterministic max attempts and optional sleep.
39. The README must show how to subclass `AgentMiddleware` for custom database permission checks.
40. Automated tests must cover custom middleware, built-in middleware, BaseAgent integration, runtime hook ordering, abort, sleep, deny tool, retry, and metadata.

### Non-Functional Requirements

- **Security:** Middleware-denied tools must not execute. Built-in tool policy must allow internal `isDone` by default to avoid accidentally trapping the runtime loop.
- **Reliability:** Middleware exceptions must not create unstructured crashes unless the middleware explicitly opts into fail-open behavior.
- **Observability:** Final agent metadata must expose middleware decisions and event metadata in a bounded structured form.
- **Compatibility:** Existing agent, tool, runtime, and provider tests must continue to pass without requiring users to pass middleware.
- **Performance:** Middleware dispatch should be O(number of middleware) per hook and avoid schema regeneration or tool catalog rebuilding.
- **Testability:** Clocks, sleepers, event sinks, and fake runners must be injectable or easy to fake.
- **Dependency control:** Use only Python standard library plus existing package dependencies.
- **API clarity:** Custom middleware should require no knowledge of provider-specific payload shapes for common policy use cases.

---

## 5. High-Level Design

The feature introduces a runtime policy layer between `BaseAgent` and `AgentRuntime`. `BaseAgent` remains the public construction surface and accepts a sequence of middleware instances. `AgentRuntime` receives that sequence and runs a `MiddlewarePipeline` at explicit breakpoints inside the PR #31 direct text loop.

Middleware is not modeled as a tool. It is not listed in `Agent.card()`, `tool_specs()`, `Tools.describe()`, or provider tool schemas. The model cannot choose middleware. The SDK deterministically invokes middleware around the runtime loop and interprets structured decisions.

The developer-facing custom middleware API is class-based:

```python
from vidbyte.middleware import AgentMiddleware, MiddlewareDecision

class DatabaseAuthMiddleware(AgentMiddleware):
    def __init__(self, db):
        self.db = db

    async def before_run(self, ctx):
        allowed = await self.db.can_start_agent(ctx.metadata["user_id"], ctx.agent_name)
        if not allowed:
            return MiddlewareDecision.abort("agent_run_not_allowed")
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx):
        allowed = await self.db.can_call_tool(ctx.metadata["user_id"], ctx.tool_call.tool_name)
        if not allowed:
            return MiddlewareDecision.deny_tool("tool_not_allowed")
        return MiddlewareDecision.continue_()
```

Data flow:

```text
User code
  -> Agent(..., middleware=[DatabaseAuthMiddleware(...), TokenRateLimitMiddleware(...)])
  -> BaseAgent.generate_reply()
  -> AgentRuntime(..., middleware=...)
     -> before_run
     -> loop:
        -> before_iteration
        -> before_model_call
        -> runner invocation
        -> after_model_response
        -> parse tool calls
        -> before_tool_call
        -> permission validation + tool execution, or middleware denial
        -> after_tool_call
        -> after_iteration
     -> after_run
  -> AgentMessage(metadata={"middleware": ...})
```

Key design decisions:

- Use optional abstract class methods instead of a single generic `handle(ctx)` switch, because the user specifically wants breakpoint-named methods.
- Keep middleware decisions explicit and small in v1. This makes runtime behavior testable and avoids accidental context mutation.
- Let custom middleware perform I/O, such as database permission checks. Built-in middleware remains deterministic/replay-friendly where possible.
- Treat token-aware middleware as provider-usage-only, consistent with PR #31.

---

## 6. Detailed Design

### 6.1 Middleware Dataclasses

**File(s):** `vidbyte/lib/dataclasses/middleware.py`, `vidbyte/lib/dataclasses/__init__.py`
**Type:** New file, Modified

#### What it does

Defines immutable shared middleware contracts in the central dataclass namespace.

#### Interface / API

```python
class MiddlewareHook(str, Enum):
    BEFORE_RUN = "before_run"
    BEFORE_ITERATION = "before_iteration"
    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_RESPONSE = "after_model_response"
    ON_MODEL_ERROR = "on_model_error"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    AFTER_ITERATION = "after_iteration"
    AFTER_RUN = "after_run"


class MiddlewareAction(str, Enum):
    CONTINUE = "continue"
    SLEEP = "sleep"
    ABORT_RUN = "abort_run"
    DENY_TOOL = "deny_tool"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class MiddlewareDecision:
    action: MiddlewareAction = MiddlewareAction.CONTINUE
    reason: str | None = None
    sleep_seconds: float = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def continue_(cls, *, metadata: Mapping[str, Any] | None = None) -> "MiddlewareDecision": ...
    @classmethod
    def sleep(cls, seconds: float, *, reason: str | None = None, metadata: Mapping[str, Any] | None = None) -> "MiddlewareDecision": ...
    @classmethod
    def abort(cls, reason: str, *, metadata: Mapping[str, Any] | None = None) -> "MiddlewareDecision": ...
    @classmethod
    def deny_tool(cls, reason: str, *, metadata: Mapping[str, Any] | None = None) -> "MiddlewareDecision": ...
    @classmethod
    def retry(cls, reason: str, *, sleep_seconds: float = 0, metadata: Mapping[str, Any] | None = None) -> "MiddlewareDecision": ...


@dataclass(frozen=True, slots=True)
class MiddlewareContext:
    hook: MiddlewareHook
    agent_name: str
    run_id: str | None = None
    provider: str | None = None
    message: str = ""
    iteration_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    elapsed_seconds: float = 0
    tokens_used: int | None = None
    agent_context: BaseAgentContext | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    model_response: object | None = None
    error: BaseException | None = None
    tool_is_internal: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MiddlewareEvent:
    middleware_name: str
    hook: MiddlewareHook
    action: MiddlewareAction
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Add enums and dataclasses.
2. Validate `MiddlewareDecision.sleep_seconds >= 0`.
3. Export new types from `vidbyte/lib/dataclasses/__init__.py`.
4. Keep dataclasses immutable for safe sharing across middleware instances.

#### Edge Cases & Error Handling

- Negative sleep values raise `ValueError`.
- Empty abort or deny reasons are accepted but should be discouraged in docs.
- `model_response` remains `object` because provider responses are intentionally provider-specific.

---

### 6.2 Middleware Base Class

**File(s):** `vidbyte/middleware/base.py`, `vidbyte/middleware/__init__.py`
**Type:** New file

#### What it does

Defines the public subclassing interface for custom middleware. Every hook is optional and defaults to continue.

#### Interface / API

```python
class AgentMiddleware(ABC):
    name: str | None = None
    fail_closed: bool = True

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...

    @property
    def middleware_name(self) -> str: ...
```

#### Logic / Algorithm

1. Provide async no-op hook methods returning `MiddlewareDecision.continue_()`.
2. `middleware_name` returns explicit `name` or class name.
3. Export `AgentMiddleware` from `vidbyte.middleware`.

#### Edge Cases & Error Handling

- Subclasses can use sync helper methods internally, but hook methods are async for a consistent runtime call path.
- No hook is abstract, so developers can override only one method.

---

### 6.3 Middleware Pipeline

**File(s):** `vidbyte/middleware/pipeline.py`, `vidbyte/middleware/__init__.py`
**Type:** New file, Modified

#### What it does

Executes middleware in order, applies sleep decisions, handles fail-open/fail-closed behavior, and records bounded middleware events for final metadata.

#### Interface / API

```python
class MiddlewarePipeline:
    def __init__(
        self,
        middleware: Sequence[AgentMiddleware] = (),
        *,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None: ...

    @property
    def events(self) -> tuple[MiddlewareEvent, ...]: ...

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...

    def metadata(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Store middleware as a tuple.
2. For each hook call, iterate in supplied order.
3. Call the matching hook method on each middleware.
4. Record events for non-continue decisions and middleware exceptions.
5. If decision is `SLEEP`, await the configured sleeper and continue to the next middleware.
6. If decision is `ABORT_RUN`, `DENY_TOOL`, or `RETRY`, return it immediately.
7. If a middleware hook raises:
   - If `fail_closed=True`, return `MiddlewareDecision.abort("middleware_error", ...)`.
   - If `fail_closed=False`, record event and continue.
8. `metadata()` returns event count and event tuple or bounded event dicts.

#### Edge Cases & Error Handling

- Empty middleware sequence returns continue for all hooks.
- Sleep of zero is a no-op.
- A retry decision outside `on_model_error` is treated as abort with metadata, or ignored. The implementation should reject unsupported retry contexts defensively.

---

### 6.4 Built-In Middleware

**File(s):** `vidbyte/middleware/builtins/__init__.py`, `vidbyte/middleware/builtins/rate_limit.py`, `vidbyte/middleware/builtins/runtime_limits.py`, `vidbyte/middleware/builtins/tool_policy.py`, `vidbyte/middleware/builtins/audit.py`, `vidbyte/middleware/builtins/retry.py`
**Type:** New files

#### What it does

Ships practical middleware classes developers can use directly or copy when writing custom middleware.

#### Interface / API

```python
class TokenRateLimitMiddleware(AgentMiddleware):
    def __init__(self, *, max_tokens: int, per_seconds: float, clock: Callable[[], float] | None = None) -> None: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...


class RuntimeLimitMiddleware(AgentMiddleware):
    def __init__(self, *, max_elapsed_seconds: float | None = None, max_model_calls: int | None = None, max_tool_calls: int | None = None) -> None: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...


class ToolPolicyMiddleware(AgentMiddleware):
    def __init__(self, *, allow_tools: Iterable[str] | None = None, deny_tools: Iterable[str] = (), allow_internal_tools: bool = True) -> None: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...


class AuditLogMiddleware(AgentMiddleware):
    def __init__(self, sink: Callable[[MiddlewareEvent], object] | list[MiddlewareEvent], *, hooks: Iterable[MiddlewareHook] | None = None) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    # all other hook methods delegate to the same event emission helper


class ModelRetryMiddleware(AgentMiddleware):
    def __init__(self, *, max_attempts: int = 2, sleep_seconds: float = 0) -> None: ...
    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm

1. `TokenRateLimitMiddleware` tracks a rolling window using provider-reported `ctx.tokens_used`.
2. If tokens are unavailable, token rate limiting continues without action.
3. If the window is exceeded, return `sleep(...)` for remaining window time.
4. `RuntimeLimitMiddleware` aborts when elapsed/model/tool call limits are exceeded.
5. `ToolPolicyMiddleware` denies denylisted tools, denies non-allowlisted tools when an allowlist exists, and allows internal tools by default.
6. `AuditLogMiddleware` emits lightweight events to a callable sink or appends to a list.
7. `ModelRetryMiddleware` returns `retry(...)` from `on_model_error` until max attempts are exhausted, then returns abort.

#### Edge Cases & Error Handling

- Built-ins validate positive numeric thresholds at construction.
- `ToolPolicyMiddleware` treats missing `ctx.tool_call` as continue.
- `AuditLogMiddleware` sink exceptions follow `fail_closed`.
- `ModelRetryMiddleware` counts attempts per middleware instance and run; implementation may reset counters in `before_run`.

---

### 6.5 AgentRuntime Integration

**File(s):** `vidbyte/agents/runtime.py`, `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Runs middleware at lifecycle breakpoints and interprets middleware decisions in the direct text loop.

#### Interface / API

```python
class AgentRuntime:
    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
        middleware: Sequence[AgentMiddleware] = (),
    ) -> None: ...
```

#### Logic / Algorithm

1. Add `middleware` parameter and create `self.middleware = MiddlewarePipeline(middleware)`.
2. Track run start time with the pipeline clock.
3. Build `MiddlewareContext` through an internal helper to avoid duplicated context construction.
4. Before the loop, call `before_run`.
5. At the top of each loop, check existing runtime budgets, then call `before_iteration`.
6. Before invoking the runner, call `before_model_call`.
7. Wrap runner invocation in a retry loop:
   - On success, continue.
   - On exception, call `on_model_error`.
   - If decision is retry, optionally sleep and retry.
   - If decision is abort, return middleware-aborted result.
   - Otherwise re-raise the runner exception.
8. After successful runner response and token extraction, call `after_model_response`.
9. If no tool calls are parsed, append assistant message and call `after_iteration`.
10. For every tool call:
    - Build context including `tool_call` and `tool_is_internal`.
    - Call `before_tool_call`.
    - If decision is deny, create denied `ToolCallContext` and error `ToolResult`.
    - Otherwise call `execute_tool_call`.
    - Call `after_tool_call` with the result.
    - Append provider tool result messages for non-internal tools.
    - If call is `isDone`, call `after_run` and return final result.
11. On runtime budget stop or middleware abort, call `after_run`.
12. Include `self.middleware.metadata()` in every final/stopped result metadata.
13. Add `AgentStopReason.MIDDLEWARE_ABORT`.

#### Edge Cases & Error Handling

- Middleware abort before the first model call returns a controlled `StrategyResult`.
- Middleware deny of user tools sends a tool error result back to the model, preserving the PR #31 loop contract.
- Middleware deny of `isDone` is allowed but dangerous; built-in policy middleware avoids it by default.
- Retry decisions after max attempts produce middleware abort.
- `after_run` exceptions follow pipeline fail-closed/fail-open behavior but must not hide an already completed successful output unless fail-closed returns abort before finalization.

---

### 6.6 BaseAgent Integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds public `middleware=` construction and carries middleware into runtime and forks.

#### Interface / API

```python
class BaseAgent(McpAttachableMixin):
    def __init__(
        self,
        *,
        ...
        middleware: Sequence[AgentMiddleware] = (),
        ...
    ) -> None: ...
```

#### Logic / Algorithm

1. Add `middleware` keyword argument after runtime policy fields.
2. Store `self.middleware = tuple(middleware)`.
3. `fork(..., middleware: Sequence[AgentMiddleware] | None = None)` preserves middleware by default and replaces it when provided.
4. `_runtime()` passes middleware to `AgentRuntime`.
5. Keep card/tool specs unchanged so middleware is not model-visible.

#### Edge Cases & Error Handling

- Non-iterable middleware raises naturally or through explicit tuple conversion.
- Strategy-backed agents store middleware but do not use it in v1.
- Non-text direct runs do not invoke middleware in v1, matching non-goals.

---

### 6.7 Public Exports

**File(s):** `vidbyte/middleware/__init__.py`, `vidbyte/middleware/builtins/__init__.py`, `vidbyte/__init__.py`
**Type:** New files, Modified

#### What it does

Makes the middleware API discoverable from `vidbyte.middleware` and common root imports.

#### Interface / API

```python
from vidbyte.middleware import AgentMiddleware, MiddlewareDecision
from vidbyte.middleware.builtins import ToolPolicyMiddleware, TokenRateLimitMiddleware

from vidbyte import AgentMiddleware, MiddlewareDecision
```

#### Logic / Algorithm

1. Export base class, pipeline, dataclasses, and built-ins from `vidbyte.middleware`.
2. Export selected stable public middleware symbols from root `vidbyte.__init__`.
3. Do not add a `VidbyteSDK().middleware` namespace client in v1.

#### Edge Cases & Error Handling

- Avoid import cycles by keeping middleware dataclasses independent from `BaseAgent`.
- Root exports should not expose internal implementation helpers.

---

### 6.8 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Documents middleware as the public runtime control plane for direct text agents.

#### Interface / API

```python
class DatabaseAuthMiddleware(AgentMiddleware):
    async def before_run(self, ctx):
        ...

agent = Agent(
    name="worker",
    system_prompt="...",
    runner=my_runner,
    tools=[lookup],
    middleware=[DatabaseAuthMiddleware(db)],
)
```

#### Logic / Algorithm

1. Add a README section after tools or runtime-loop docs.
2. Show subclassing `AgentMiddleware`.
3. Show built-in middleware use.
4. Clarify that middleware is runtime code and not model-visible.
5. Update SDK structure rules to include `vidbyte/middleware/` and dataclasses under `vidbyte/lib/dataclasses/`.

#### Edge Cases & Error Handling

- Documentation must avoid real database credentials or network secrets.
- Documentation must state direct text runtime scope for v1.

---

### 6.9 Tests

**File(s):** `tests/test_agent_middleware.py`, `tests/test_middleware_builtins.py`, `tests/test_agent_runtime.py`, `tests/test_agent_base.py`
**Type:** New files, Modified

#### What it does

Adds focused coverage for middleware dataclasses, custom middleware authoring, built-ins, and runtime integration.

#### Interface / API

```python
class AgentMiddlewareTests(unittest.IsolatedAsyncioTestCase): ...
class MiddlewareBuiltinsTests(unittest.IsolatedAsyncioTestCase): ...
```

#### Logic / Algorithm

1. Use fake runners and fake responses following existing `tests/test_agent_runtime.py` style.
2. Use fake sleeper and fake clock for sleep/rate-limit tests.
3. Use fake middleware subclasses to record hook order.
4. Use fake tools to verify deny decisions do not execute tool bodies.
5. Use fake model-call failures to verify retry behavior.

#### Edge Cases & Error Handling

- No live provider calls.
- No wall-clock sleeping in tests.
- Tests assert middleware metadata is included in final replies.

---

## 7. Data Model Changes

### 7.1 `MiddlewareHook`, `MiddlewareAction`, `MiddlewareDecision`, `MiddlewareContext`, `MiddlewareEvent`

**Change type:** New

```python
class MiddlewareHook(str, Enum): ...
class MiddlewareAction(str, Enum): ...

@dataclass(frozen=True, slots=True)
class MiddlewareDecision: ...

@dataclass(frozen=True, slots=True)
class MiddlewareContext: ...

@dataclass(frozen=True, slots=True)
class MiddlewareEvent: ...
```

**Migration strategy:** N/A - in-memory SDK dataclasses only.

- Forward migration: add new dataclasses and export from `vidbyte.lib.dataclasses` and `vidbyte.middleware`.
- Rollback plan: remove dataclasses and middleware package; restore `BaseAgent` and `AgentRuntime` constructor signatures.

### 7.2 `AgentStopReason`

**Change type:** Modified

```python
class AgentStopReason(str, Enum):
    MIDDLEWARE_ABORT = "middleware_abort"
```

**Migration strategy:** N/A - in-memory enum only.

- Forward migration: add enum member and use it for middleware-aborted runtime results.
- Rollback plan: remove enum member and middleware-abort result path.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

### 8.1 Python SDK: Custom Middleware

**Change type:** New

**Request:**

```python
class TenantMiddleware(AgentMiddleware):
    async def before_run(self, ctx):
        if "tenant_id" not in ctx.metadata:
            return MiddlewareDecision.abort("missing_tenant_id")
        return MiddlewareDecision.continue_()

agent = Agent(..., middleware=[TenantMiddleware()])
```

**Response:**

```python
AgentMessage(
    content="...",
    metadata={
        "strategy": "direct_runner",
        "stop_reason": "is_done" | "middleware_abort" | "...",
        "middleware": {...},
    },
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Middleware exception with `fail_closed=True` aborts the run with `stop_reason=middleware_abort`. |
| N/A | Middleware exception with `fail_closed=False` records metadata and continues. |
| N/A | `deny_tool` decisions prevent tool execution and return a tool error result to the model. |

### 8.2 Python SDK: Built-In Middleware

**Change type:** New

**Request:**

```python
agent = Agent(
    ...,
    middleware=[
        ToolPolicyMiddleware(allow_tools={"lookup"}),
        RuntimeLimitMiddleware(max_elapsed_seconds=30),
        ModelRetryMiddleware(max_attempts=2),
    ],
)
```

**Response:**

```python
reply.metadata["middleware"]
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Runtime limit aborts before the next iteration. |
| N/A | Tool policy denies a blocked tool before execution. |
| N/A | Retry middleware aborts after max attempts are exhausted. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-runtime-middleware.md` | Design doc for middleware feature |
| CREATE | `vidbyte/lib/dataclasses/middleware.py` | Shared immutable middleware contracts |
| CREATE | `vidbyte/middleware/__init__.py` | Public middleware package exports |
| CREATE | `vidbyte/middleware/base.py` | `AgentMiddleware` abstract base class |
| CREATE | `vidbyte/middleware/pipeline.py` | Ordered middleware execution and decision handling |
| CREATE | `vidbyte/middleware/builtins/__init__.py` | Built-in middleware exports |
| CREATE | `vidbyte/middleware/builtins/rate_limit.py` | Token rate limiting middleware |
| CREATE | `vidbyte/middleware/builtins/runtime_limits.py` | Elapsed/model/tool call budget middleware |
| CREATE | `vidbyte/middleware/builtins/tool_policy.py` | Tool allowlist/denylist middleware |
| CREATE | `vidbyte/middleware/builtins/audit.py` | Structured audit event middleware |
| CREATE | `vidbyte/middleware/builtins/retry.py` | Model-call retry middleware |
| CREATE | `tests/test_agent_middleware.py` | Runtime/custom middleware integration tests |
| CREATE | `tests/test_middleware_builtins.py` | Built-in middleware unit tests |
| MODIFY | `vidbyte/agents/base.py` | Accept and pass middleware into runtime; preserve in fork |
| MODIFY | `vidbyte/agents/runtime.py` | Invoke middleware hooks inside the direct text loop |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export middleware dataclasses |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentStopReason.MIDDLEWARE_ABORT` |
| MODIFY | `vidbyte/__init__.py` | Root public middleware exports |
| MODIFY | `README.md` | Document custom and built-in middleware usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add middleware package structure and rules |
| MODIFY | `tests/test_agent_runtime.py` | Extend runtime tests for middleware interaction if shared fixtures are useful |
| MODIFY | `tests/test_agent_base.py` | Verify `BaseAgent` stores and forks middleware |

Summary: 13 files created, 9 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_agent_middleware.py` -> `test_custom_middleware_can_abort_before_run`: custom `before_run` abort returns `stop_reason=middleware_abort` and no runner call occurs.
- `tests/test_agent_middleware.py` -> `test_hook_order_for_successful_tool_loop`: records `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `before_tool_call`, `after_tool_call`, `after_iteration`, `after_run`.
- `tests/test_agent_middleware.py` -> `test_custom_middleware_denies_tool_before_execution`: `before_tool_call` returns deny, tool body is not called, tool context state is denied.
- `tests/test_agent_middleware.py` -> `test_middleware_can_observe_internal_is_done_tool`: custom middleware sees `tool_is_internal=True` for `isDone`.
- `tests/test_agent_middleware.py` -> `test_model_retry_middleware_retries_runner_exception`: fake runner fails once, retry middleware retries, second response calls `isDone`.
- `tests/test_agent_middleware.py` -> `test_fail_closed_middleware_exception_aborts`: hook exception aborts by default.
- `tests/test_agent_middleware.py` -> `test_fail_open_middleware_exception_continues`: hook exception with `fail_closed=False` records middleware metadata and continues.
- `tests/test_middleware_builtins.py` -> `test_token_rate_limit_sleeps_when_provider_tokens_exceed_window`: fake clock/sleeper records sleep.
- `tests/test_middleware_builtins.py` -> `test_token_rate_limit_continues_without_token_usage`: no sleep when `tokens_used` is `None`.
- `tests/test_middleware_builtins.py` -> `test_runtime_limit_aborts_on_elapsed_seconds`: limit decision aborts.
- `tests/test_middleware_builtins.py` -> `test_tool_policy_denies_denylisted_tool`: denylist blocks user tool.
- `tests/test_middleware_builtins.py` -> `test_tool_policy_allows_internal_tool_by_default`: internal `isDone` is not denied.
- `tests/test_middleware_builtins.py` -> `test_audit_log_appends_events`: list sink receives events.
- `tests/test_agent_base.py` -> `test_agent_fork_preserves_middleware`: forked agent receives same middleware tuple unless overridden.

### Integration Tests

- Run existing full unittest suite: `python -m unittest discover -s tests`.
- Run compile verification: `python -m compileall vidbyte`.
- No live providers, databases, network services, or MCP subprocesses are needed.

### Manual / QA Test Cases

1. Create an `Agent` with a fake runner that calls `isDone`; no middleware; verify existing behavior is unchanged.
2. Create an `Agent` with custom database-like middleware that aborts before run; verify no model call happens.
3. Create an `Agent` with `ToolPolicyMiddleware(allow_tools={"lookup"})`; verify `lookup` executes and another user tool is denied.
4. Create an `Agent` with `AuditLogMiddleware([])`; verify events appear in the list and in reply metadata.
5. Run import smoke test:

```python
from vidbyte import AgentMiddleware, MiddlewareDecision
from vidbyte.middleware.builtins import ToolPolicyMiddleware
print(AgentMiddleware, MiddlewareDecision, ToolPolicyMiddleware)
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | ABCs, dataclasses, enums, asyncio sleep, monotonic clock, unittest | Existing runtime only |
| pydantic | Existing `>=2,<3` | N/A for middleware directly | Existing dependency only |

No new external services or package dependencies are introduced.

---

## 12. Rollout & Deployment

- This is a package-only SDK change.
- No feature flag is required.
- The change is additive and should be backward-compatible for agents that do not pass middleware.
- Middleware only runs for direct text `AgentRuntime` execution in v1.
- Rollout sequence:
  1. After approval, create an isolated worktree from updated `main`.
  2. Commit this design doc first.
  3. Add middleware dataclasses and exports.
  4. Add `AgentMiddleware` and `MiddlewarePipeline`.
  5. Add built-in middleware.
  6. Wire `BaseAgent` and `AgentRuntime`.
  7. Add tests.
  8. Update README and SDK skill guidance.
  9. Run compile and unittest verification.
  10. Push branch and open draft PR.
- Rollback procedure:
  1. Revert the feature branch merge commit.
  2. Remove `vidbyte/middleware/` and middleware dataclasses.
  3. Restore `BaseAgent` and `AgentRuntime` constructor signatures.
  4. Remove README/skill middleware guidance.

---

## 13. Open Questions

- [ ] Should middleware also run for strategy-backed agents in a follow-up PR, likely through a separate strategy middleware adapter?
- [ ] Should non-text direct runs get `before_run` and `after_run` hooks even though they do not use the text loop?
- [ ] Should root `VidbyteSDK` expose `sdk.middleware`, or are direct imports from `vidbyte.middleware` sufficient for v1?
- [ ] Should middleware metadata include full event tuples, or should final metadata cap events to avoid large replies?
- [ ] Should `after_run` be allowed to abort a successful final result, or should it only record metadata once output has been produced?

---

## 14. Alternatives Considered

### Alternative 1: Single `handle(ctx)` Middleware Method

- What: Define middleware with one generic `handle(ctx)` method and a hook enum.
- Why rejected: The desired developer API is an abstract class with optional breakpoint-named methods. Named methods are clearer, easier to document, and easier to type-check.

### Alternative 2: Middleware As Tools

- What: Implement middleware as special tools that the model can call.
- Why rejected: Middleware is deterministic runtime policy. The model should not choose whether authentication, rate limiting, or audit logging happens.

### Alternative 3: Free Context Mutation

- What: Let middleware directly mutate provider messages, prompts, tool results, and context state.
- Why rejected: Free mutation would make the runtime hard to reason about and could create security ambiguity. V1 uses explicit structured decisions only.

### Alternative 4: Only Built-In Middleware, No Custom API

- What: Ship rate limiting and tool policy middleware but no subclassing interface.
- Why rejected: The core user need is custom runtime control, such as database-backed permission checks.

### Alternative 5: Strategy-Wide Middleware Now

- What: Run middleware for all agents, including strategy-backed agents and multi-agent strategies.
- Why rejected: Strategy loops are heterogeneous and not owned by `AgentRuntime`. Direct text runtime middleware is the clear first boundary after PR #31.
