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
    - skills/tool-settings/SKILL.md: Process guide for ToolSettings creation and extension.
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
    max_parallel_tool_calls=4,
    max_retries=2,
    timeout_seconds=60.0,
    context_window_budget=16000,
    allowed_tools=("search", "read_file"),
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
| `max_parallel_tool_calls` | `int \| None` | `None` | Maximum tool bodies dispatched concurrently within one direct-runtime iteration. `None` preserves legacy sequential execution and `1` forces sequential execution. Results are committed in provider order. |
| `max_retries` | `int \| None` | `None` | Maximum model-call retries after the initial failed attempt. The setting enables immediate model retries on its own and caps middleware-requested retries. Tool bodies are not retried by this setting. Exhaustion stops with `stop_reason=max_retries`. |
| `timeout_seconds` | `float \| None` | `None` | One wall-clock deadline around the complete direct run, including context algorithms, middleware, model calls, and tool calls. Expiry stops with `stop_reason=timeout`. |
| `context_window_budget` | `int \| None` | `None` | Approximate maximum model-input tokens. The runtime uses a deterministic four-characters-per-token estimate, trims oldest removable provider messages with boundary repair, and stops with `stop_reason=context_window_budget` when fixed input cannot fit. |
| `allowed_tools` | `tuple[str, ...] \| None` | `None` | User-tool allowlist enforced in provider schemas and again before lookup, permission checks, validation, or execution. `()` denies all user tools. Internal runtime tools such as `isDone` remain available. |
| `compaction_trigger_tokens` | `int \| None` | `None` | Token usage level at which context compaction triggers. Must be greater than `compaction_target_tokens`. |
| `compaction_target_tokens` | `int \| None` | `None` | Target token usage after compaction completes. Must be less than `compaction_trigger_tokens`. |

### 3.1.1 Nested settings objects

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_settings` | `ToolSettings \| None` | `None` | Nested universal tool-use constraints (deny/truncate plus hard budgets: per-iteration, identical-call, consecutive/total failures, per-call timeout, sliding window). Enforced **inline by the direct runtime** (not middleware). `ToolSettings.max_calls` maps to the same budget as `max_tool_calls` and must match if both are set. Non-linear runtimes reject `tool_settings` at construction. See `skills/tool-settings/SKILL.md`. |

To **configure** tool settings, nest them on `AgentLoopSettings`. To **add or extend** tool settings fields, follow the process skill:

- **Process guide:** `skills/tool-settings/SKILL.md`
- **Architecture design:** `docs/design/tool-settings-runtime-enforcement.md`

```python
from vidbyte.agents import AgentLoopSettings, ToolSettings

settings = AgentLoopSettings(
    max_iterations=10,
    tool_settings=ToolSettings(
        denied_tools={"delete_file"},
        max_calls=20,
        result_max_chars=8000,
        on_deny="continue",
    ),
)
```

> `tool_error_policy` is a separate nested object for tool-error retry/render behavior (middleware-oriented). Do not confuse it with `tool_settings`.

### 3.1.2 Output contracts (effort floors)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_contracts` | `Sequence[OutputContract]` | `()` | Deterministic **floors** that gate when a linear agent may stop. Owned as `settings.output_contract` (`AgentLoopSettingsOutputContract`). Empty = no-op. |
| `max_contract_rejections` | `int` | `3` | How many unmet finalization attempts are allowed before the run stops with `stop_reason=contract_unsatisfied`. Must be `> 0`. |

**Ceilings say when the agent MUST stop. Output contracts say when it MAY stop.**

When the model calls `isDone` (or tries to finalize with no tool calls) before every floor is met, the runtime injects corrective feedback and continues the loop. See the full process guide:

- **Output contracts skill:** `skills/output-contracts/SKILL.md`
- **Framework design:** `docs/design/output-contracts-loop-settings.md`
- **Extended floors design:** `docs/design/output-contract-skill-and-extended-floors.md`

```python
from vidbyte.agents import AgentLoopSettings, MinToolCalls, MinSuccessfulToolCalls, MinTimeTaken

settings = AgentLoopSettings(
    max_tool_calls=20,
    max_contract_rejections=5,
    output_contracts=[MinToolCalls(5), MinSuccessfulToolCalls(3), MinTimeTaken(15)],
)
```

### 3.2 Direct-Runtime Scope and Ordering

These safeguards apply to the default direct text runtime. They do not implicitly change MCTS, actor-model, or non-text runtimes. Parallel dispatch performs allowlist and middleware preflight in provider order, executes approved bodies under the configured ceiling, and finalizes contexts and model-visible results in provider order. The first `isDone` call is a barrier: later calls in the same model response are not dispatched. A hallucinated hidden tool is recorded as denied with reason `tool_not_allowed_by_loop_settings` and still consumes normal tool-call accounting.

---

## 4. Validation Rules

`AgentLoopSettings` raises `ConfigurationError` (not `ValueError`) immediately at construction for any of the following:

| Condition | Error |
|-----------|-------|
| Any integer field is `0` or negative | `{field} must be greater than zero when provided` |
| `timeout_seconds` is `0.0` or negative | `timeout_seconds must be greater than zero when provided` |
| `compaction_target_tokens >= compaction_trigger_tokens` (when both set) | `compaction_target_tokens must be less than compaction_trigger_tokens` |
| `tool_settings` is not a `ToolSettings` instance | `tool_settings must be a ToolSettings instance when provided` |
| `max_tool_calls` and `ToolSettings.max_calls` both set and differ | must match when both are provided |
| Effort floor `minimum >=` paired ceiling (when ceiling set) | floor is unreachable (require minimum < ceiling) |
| `MinToolCallsById` minimum `>=` `ToolSettings.max_calls_per_tool[name]` when set | floor is unreachable for that tool |
| Both `agent_loop_settings=` and flat params passed to `BaseAgent` | `Pass either agent_loop_settings= or individual loop params (...), not both.` |

---

## 5. Stop Reasons

When the runtime stops due to an `AgentLoopSettings` budget, the `AgentResult.metadata["stop_reason"]` field will contain one of:

| Stop Reason | Triggered By |
|-------------|-------------|
| `"max_iterations"` | `max_iterations` reached |
| `"max_tokens"` | `max_tokens` reached |
| `"max_tool_calls"` | `max_tool_calls` / `ToolSettings.max_calls` reached |
| `"timeout"` | Whole-run `timeout_seconds` deadline expired |
| `"max_retries"` | Configured model-call retries were exhausted |
| `"context_window_budget"` | Fixed model input could not fit the approximate context budget |
| `"max_calls_per_iteration"` | `ToolSettings.max_calls_per_iteration` hard-stop |
| `"max_identical_calls"` | `ToolSettings.max_identical_calls` hard-stop |
| `"max_consecutive_failures"` | `ToolSettings.max_consecutive_failures` hard-stop |
| `"max_error_calls"` | `ToolSettings.max_error_calls` hard-stop |
| `"sliding_window_max_calls"` | `ToolSettings` sliding-window hard-stop |
| `"tool_settings_denied"` | `ToolSettings` denial with `on_deny="abort"` |
| `"final_response"` | Agent completed normally (no budget hit) |
| `"is_done"` | Agent called the `isDone` tool explicitly |
| `"contract_unsatisfied"` | Output-contract floors still unmet after `max_contract_rejections` attempts |

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

Settings that have no meaningful live "current/limit" measurement are intentionally **excluded** from this block: `max_retries`, `timeout_seconds`, `allowed_tools`, `max_parallel_tool_calls`, `context_window_budget`, and the compaction params. The direct runtime still enforces them at model, tool, and whole-run boundaries, and they remain available for introspection on `agent.agent_loop_settings`.

A budget that is not configured (`None`) is omitted from the block. When none of the calculable budgets are set, no block is injected at all and the system context is unchanged.

---

## 7. Reading Settings at Runtime

```python
# Inspect any agent's loop settings:
agent.agent_loop_settings.max_iterations   # int | None
agent.agent_loop_settings.max_tool_calls   # int | None
agent.agent_loop_settings.timeout_seconds  # float | None
agent.agent_loop_settings.tool_settings    # ToolSettings | None

# Check if a budget is set:
has_tool_limit = agent.agent_loop_settings.max_tool_calls is not None
has_tool_policy = agent.agent_loop_settings.tool_settings is not None
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

## 9. Remaining Limitations

- `max_retries` covers model invocations only. Automatic tool-body retries require an explicit idempotency-aware policy such as the existing tool-error middleware.
- `context_window_budget` is deterministic but approximate; it does not use provider-specific tokenizers.
- Async cancellation is best-effort. Synchronous work already offloaded to a thread may continue after the runtime returns a timeout result.
- These enforcement paths belong to the direct text runtime; other runtime families must define their own equivalent contracts before adopting the settings.
