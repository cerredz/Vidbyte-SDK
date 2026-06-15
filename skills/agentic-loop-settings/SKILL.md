<!-- Context Protocol Header

Description:
    Ground-truth reference for all agentic loop settings in the Vidbyte SDK.
Purpose:
    Documents every parameter available on AgentLoopSettings — what it does,
    why it exists, which ones are enforced at runtime, and which are reserved
    for future runtime implementations.
Architecture:
    SDK Skill Guide.
Relations:
    Located in skills/agentic-loop-settings/SKILL.md.
    Implementation lives in vidbyte/agents/settings/loop.py.
    BaseAgent wiring lives in vidbyte/agents/base.py.
Similar Files:
    - skills/agent-runtimes/SKILL.md: Covers swappable runtime topologies.
    - skills/vidbyte-sdk/SKILL.md: Root SDK structure reference.
-->

# Agentic Loop Settings Skill Guide

This guide is the canonical reference for `AgentLoopSettings` — the Vidbyte SDK class that groups every deterministic parameter governing how an agent's execution loop runs. Come here when you have a question about what a setting does, when to use it, or what it controls at runtime.

---

## 1. What Are Agentic Loop Settings?

An agent in the Vidbyte SDK executes inside a loop. Each tick of that loop:
1. Calls the model.
2. Inspects the response for tool calls.
3. Executes those tools.
4. Feeds the results back into the next model call.
5. Repeats until a stop condition is hit.

**Agentic loop settings** are the deterministic parameters that control this loop. They are not dynamic — they are fixed at agent construction time. Every setting answers one of two questions:

- **When should the loop stop?** (budgets: `max_iterations`, `max_tokens`, `max_tool_calls`, `timeout_seconds`)
- **How should the loop behave while running?** (behavior: `max_parallel_tool_calls`, `max_retries`, `context_window_budget`, `allowed_tools`, compaction params)

These settings live on a single `AgentLoopSettings` object that is attached to every `BaseAgent` as `self.agent_loop_settings`. This makes it introspectable at any point in the agent's lifecycle.

---

## 2. The `AgentLoopSettings` Class

`AgentLoopSettings` is a plain Python class in `vidbyte/agents/settings/loop.py`. It validates all parameters at construction time and raises `ConfigurationError` immediately when any constraint is violated.

```python
from vidbyte.agents import AgentLoopSettings, BaseAgent

# Option A: Pass AgentLoopSettings directly (preferred for complex configs)
settings = AgentLoopSettings(
    max_iterations=10,
    max_tokens=8000,
    max_tool_calls=20,
    timeout_seconds=60.0,
)

agent = BaseAgent(
    name="my_agent",
    system_prompt="You are a helpful assistant.",
    runner=my_runner,
    agent_loop_settings=settings,
)

# Option B: Pass flat params (backward compatible, auto-constructs AgentLoopSettings internally)
agent = BaseAgent(
    name="my_agent",
    system_prompt="You are a helpful assistant.",
    runner=my_runner,
    max_iterations=10,
    max_tokens=8000,
)

# Both paths make self.agent_loop_settings available:
print(agent.agent_loop_settings.max_iterations)  # 10
```

> **Important:** Passing both `agent_loop_settings=` and individual flat params in the same constructor call raises `ConfigurationError`. Use one path or the other.

---

## 3. Parameter Reference

### 3.1 Currently Implemented (Enforced at Runtime)

These parameters are stored on `AgentLoopSettings`, validated at construction time, and actively enforced by `AgentRuntime` during the execution loop.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_iterations` | `int \| None` | `None` | Maximum number of model call + tool call cycles. The loop stops with `stop_reason=max_iterations` when this count is reached. Originally exposed as `max_tool_rounds`. |
| `max_tokens` | `int \| None` | `None` | Maximum cumulative tokens consumed across all model calls in the run. The loop stops with `stop_reason=max_tokens` when usage reaches this ceiling. |
| `max_tool_calls` | `int \| None` | `None` | Maximum total tool invocations across the entire run. Independent of iterations — an agent can hit this limit without exhausting `max_iterations` if it fans out many tools per iteration. Stops with `stop_reason=max_tool_calls`. |
| `compaction_trigger_tokens` | `int \| None` | `None` | Token usage level at which context compaction triggers. Must be greater than `compaction_target_tokens`. |
| `compaction_target_tokens` | `int \| None` | `None` | Target token usage after compaction completes. Must be less than `compaction_trigger_tokens`. |

### 3.2 Validated but Reserved (Not Yet Enforced at Runtime)

These parameters are accepted and validated on `AgentLoopSettings` at construction time, but the execution loop does not yet read or enforce them. They are stored on the settings object for introspection and documented here so that future runtime implementations have a stable API to target.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_parallel_tool_calls` | `int \| None` | `None` | Maximum number of tool calls that can be dispatched concurrently within a single iteration. A value of `1` forces strictly sequential tool execution. |
| `max_retries` | `int \| None` | `None` | Per-step retry budget. How many times the runtime may retry a failed model call or tool call before treating it as a hard failure and stopping the loop. |
| `timeout_seconds` | `float \| None` | `None` | Wall-clock time limit for the entire run in seconds. Distinct from iteration or token limits — enforces an absolute time ceiling regardless of progress. |
| `context_window_budget` | `int \| None` | `None` | Tokens reserved for context messages (history, tool results, primitives) as opposed to generation. Helps the agent self-regulate verbosity when it is aware that its context is constrained. |
| `allowed_tools` | `tuple[str, ...] \| None` | `None` | Explicit whitelist of tool names this agent is permitted to call. When set, the runtime will refuse any tool call whose name is not in this set. |

---

## 4. Validation Rules

`AgentLoopSettings` raises `ConfigurationError` (not `ValueError`) immediately at construction for any of the following:

| Condition | Error |
|-----------|-------|
| Any integer field is `0` or negative | `{field} must be greater than zero when provided` |
| `timeout_seconds` is `0.0` or negative | `timeout_seconds must be greater than zero when provided` |
| `compaction_target_tokens >= compaction_trigger_tokens` (when both set) | `compaction_target_tokens must be less than compaction_trigger_tokens` |
| Both `agent_loop_settings=` and flat params passed to `BaseAgent` | `Pass either agent_loop_settings= or individual loop params (...), not both.` |

---

## 5. Stop Reasons

When the runtime stops due to an `AgentLoopSettings` budget, the `AgentResult.metadata["stop_reason"]` field will contain one of:

| Stop Reason | Triggered By |
|-------------|-------------|
| `"max_iterations"` | `max_iterations` reached |
| `"max_tokens"` | `max_tokens` reached |
| `"max_tool_calls"` | `max_tool_calls` reached |
| `"final_response"` | Agent completed normally (no budget hit) |
| `"is_done"` | Agent called the `isDone` tool explicitly |

---

## 6. Context-Window Injection

On every iteration, the runtime injects a live snapshot of the agent's loop budgets into the system context, placed directly beneath the system-prompt header. This gives the model awareness of the execution envelope it is operating inside so it can pace its work (for example, wrapping up before `max_iterations` is exhausted).

The block is rendered by `AgentRuntime._render_loop_settings_block()` and assembled into the system string by `AgentRuntime._build_system_string()`. It renders each budget as `current usage / configured limit`:

```
Below are your agent loop settings, shown as current usage / configured limit. Stay within these limits:
- max_iterations: 1/3
- max_tokens: 100/6000
- max_tool_calls: 0/5
```

### What is injected

Only budgets that are **both numerically calculable and tracked by the runtime loop** are injected:

| Setting | Current value source |
|---------|----------------------|
| `max_iterations` | live iteration count |
| `max_tokens` | cumulative tokens used so far |
| `max_tool_calls` | live tool-call count |

Budgets that have no meaningful live "current/limit" measurement are intentionally **excluded** from the context window: `max_retries`, `timeout_seconds`, `allowed_tools`, `max_parallel_tool_calls`, `context_window_budget`, and the compaction params. They remain available for introspection on `agent.agent_loop_settings`.

A budget that is not configured (`None`) is omitted from the block. When none of the calculable budgets are set, no block is injected at all and the system context is unchanged.

---

## 7. Reading Settings at Runtime

```python
# Inspect any agent's loop settings:
agent.agent_loop_settings.max_iterations   # int | None
agent.agent_loop_settings.max_tool_calls   # int | None
agent.agent_loop_settings.timeout_seconds  # float | None

# Check if a budget is set:
has_tool_limit = agent.agent_loop_settings.max_tool_calls is not None
```

---

## 8. Design Intent

### Static Config vs Runtime-Injected State

`AgentLoopSettings` holds **static configuration** — values set once at agent construction that do not change during the run. This is distinct from **runtime-injected state**, which describes the agent's current position in its loop (e.g., how many iterations have elapsed, how many tokens have been consumed). Runtime-injected state is tracked internally by `AgentRuntime` and surfaced in result metadata, but it is not part of `AgentLoopSettings`.

### Why a Class, Not a Dataclass

`AgentLoopSettings` is a plain class following the `ActorRuntime` precedent. This allows `__init__`-level validation that can raise `ConfigurationError` with rich messages before any field is set. Frozen dataclasses defer to `__post_init__` and cannot hold `TYPE_CHECKING`-only imports cleanly.

### Relationship to `AgentRuntimeConfig`

`AgentRuntimeConfig` is an internal frozen dataclass used by `AgentRuntime`. `AgentLoopSettings` is the developer-facing class that converts to `AgentRuntimeConfig` via `to_runtime_config()`. This preserves backward compatibility while giving the public API room to grow independently of the internal contract.

---

## 9. Future Roadmap

The following runtime enforcement work is deferred to follow-up PRs:

- `max_parallel_tool_calls`: requires tool dispatch concurrency control in `AgentRuntime._process_tool_call`.
- `max_retries`: requires per-step retry loop integration into `AgentRuntime._invoke_with_middleware`.
- `timeout_seconds`: requires async wall-clock tracking via `asyncio.wait_for` wrapping the run.
- `context_window_budget`: requires the compaction middleware to read this value as a signal.
- `allowed_tools`: requires a pre-execution check in `AgentRuntime.execute_tool_call`.

Each deferred param is already validated and stored; adding runtime enforcement only requires reading the existing attribute.
