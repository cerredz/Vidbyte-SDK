# Context Protocol Header

- **Description**: Technical guide and skill reference for using and implementing agent runtime middleware in the Vidbyte SDK.
- **Purpose**: Helps developers and agent entities understand the architecture of runtime interceptor policies, select appropriate built-in middleware, and create custom middleware safely.
- **Architecture**:
  - Outlines the 9 lifecycle hooks exposed by `AgentRuntime`.
  - Details the 5 discrete middleware actions (`CONTINUE`, `SLEEP`, `ABORT_RUN`, `DENY_TOOL`, `RETRY`).
  - Categorizes all 14 built-in middlewares (Security, Reliability, Safety, Budgets).
  - Guides custom middleware creation with design patterns and best practices.
- **Relations**: Relates to `skills/vidbyte-sdk/SKILL.md` (root SDK directory structure), `vidbyte/middleware/` (implementation package), and `vidbyte/middleware/builtins/` (standard built-ins).
- **Similar Files**: `skills/vidbyte-sdk/pipelines.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`.

---

# Agent Runtime Middleware

## 1. What Middleware Is

Middleware in the Vidbyte SDK consists of deterministic, out-of-band runtime interceptor policies injected into the agent's execution loop. While **pipelines** connect separate agents together and **runtimes/context-window algorithms** shape reasoning loops, **middleware** controls the agent runtime's safety, reliability, budgets, and security borders without modifying the prompt context or being visible to the underlying LLM.

All middleware classes subclass the abstract base `AgentMiddleware` and override specific asynchronous lifecycle hooks. They receive a read-only `MiddlewareContext` containing granular execution facts and return a `MiddlewareDecision` determining the runtime's next action.

---

## 2. The Hook Lifecycle

An agent runs within `AgentRuntime` and triggers middleware hooks at nine discrete execution stages. The following table details the hooks, when they execute, and what contextual facts are available:

| Hook Name | Triggers When | Available Context Fields |
| :--- | :--- | :--- |
| `before_run` | Right before the agent runtime starts executing. | `agent_name`, `message`, `run_id`, `provider` |
| `before_iteration` | Right before each iteration step of the execution loop begins. | All `before_run` fields, plus `iteration_count`, `model_call_count`, `tool_call_count`, `elapsed_seconds` |
| `before_model_call` | Immediately prior to calling the LLM provider. | All `before_iteration` fields, plus active `tokens_used` |
| `after_model_response` | Immediately after receiving a successful completion from the LLM. | All `before_model_call` fields, plus `model_response` |
| `on_model_error` | When the LLM provider call raises a connection or validation error. | All `before_model_call` fields, plus `error` |
| `before_tool_call` | Before validating, checking permissions for, or running an agent tool. | All `after_model_response` fields, plus `tool_call`, `tool_is_internal` |
| `after_tool_call` | After the tool has finished executing or has been denied. | All `before_tool_call` fields, plus `tool_result` |
| `after_iteration` | At the end of an iteration loop, after tool executions are processed. | All iteration-accumulated counts and timings |
| `after_run` | At the end of one `_arun_once` attempt: returned results **and** terminal exceptions after retries/fallback. Raise-path calls set `error`. Abort/retry/deny on that path are ignored. | All run-level accumulated statistics; `error` when the attempt is raising |

---

## 3. Decisions and Effects (`MiddlewareDecision`)

A middleware hook MUST return a `MiddlewareDecision` object. The runtime intercepts this decision and applies the requested side-effects:

*   **`MiddlewareDecision.continue_()`**
    *   *Effect*: Execution proceeds normally.
*   **`MiddlewareDecision.sleep(seconds, reason=...)`**
    *   *Effect*: Temporarily suspends execution before proceeding. Useful for throttling or rate-limiting delays.
*   **`MiddlewareDecision.deny_tool(reason)`**
    *   *Effect*: Blocks execution of the active tool. The runtime bypasses the tool body and returns a mock error result indicating denial to the LLM. Only valid in `before_tool_call`.
*   **`MiddlewareDecision.retry(reason, sleep_seconds=...)`**
    *   *Effect*: Retries the failed model call. Only valid in `on_model_error`.
*   **`MiddlewareDecision.abort(reason, metadata=...)`**
    *   *Effect*: Immediately terminates the entire agent execution. The runtime halts and raises an `AgentExecutionError` carrying the reason and metadata.

---

## 4. Built-in Middleware Catalog

The Vidbyte SDK includes 14 built-in middlewares designed to guard and govern agent execution out of the box. Five additional **compaction** middlewares (`ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`, `TraceReplacementCompactionMiddleware`, `TraceSummaryTailCompactionMiddleware`) are covered separately in §5.1, bringing the public total to 19. Compaction implementations live in `vidbyte/middleware/compaction/` and are re-exported through `vidbyte/middleware/builtins/context_compaction.py`.

### A. Security & Defense

#### 1. `CanaryTripwireMiddleware`
*   **Class**: `CanaryTripwireMiddleware`
*   **Module**: `vidbyte.middleware.builtins.canary_tripwire`
*   **Purpose**: Detects prompt-injection-driven exfiltration attacks where adversarial data in tool results instructs the LLM to leak internal secrets or system instructions.
*   **How it works**: Probabilistically injects unique canary tokens (`VIDBYTE-CANARY-<hex>`) into external tool results. It scans all subsequent model response text; if a canary matches, it triggers an immediate abort.
*   **Arguments**:
    *   `watermark_prefix: str = "VIDBYTE-CANARY-"`
    *   `inject_probability: float = 0.3` (Chance to append to external tool results)
    *   `abort_reason: str = "canary_leaked"`
    *   `random_seed: int | None = None`

#### 2. `ConfusedDeputyGuardMiddleware`
*   **Class**: `ConfusedDeputyGuardMiddleware`
*   **Module**: `vidbyte.middleware.builtins.confused_deputy`
*   **Purpose**: Prevents confused deputy attacks where malicious data returned from an untrusted tool (e.g., email body, web content) is copied directly into subsequent critical tool calls (e.g., database writes, file deletions).
*   **How it works**: Tracks verbatim string overlap between accumulated tool results and arguments passed to subsequent tool calls. If overlap exceeds a threshold ratio, the run aborts.
*   **Arguments**:
    *   `max_external_content_ratio: float = 0.6` (Max ratio of argument text derived from a prior tool output)
    *   `min_argument_length: int = 20` (Skip checks for trivial short arguments)
    *   `abort_reason: str = "confused_deputy_detected"`

#### 3. `HoneypotToolMiddleware`
*   **Class**: `HoneypotToolMiddleware`
*   **Module**: `vidbyte.middleware.builtins.honeypot_tool`
*   **Purpose**: Catches direct model hallucinations or prompt-injection attempts that scan for non-existent administration/sensitive tools.
*   **How it works**: Plants fake decoy tools in the runtime. If the model attempts to invoke any of these decoy names, it triggers an immediate abort.
*   **Arguments**:
    *   `trap_tool_names: Iterable[str]` (List of fake tool names, e.g. `["delete_system_logs", "bypass_auth"]`)
    *   `abort_reason: str = "honeypot_triggered"`

---

### B. Budgets & Cost Gates

#### 4. `TokenBudgetMiddleware`
*   **Class**: `TokenBudgetMiddleware`
*   **Module**: `vidbyte.middleware.builtins.token_budget`
*   **Purpose**: Places absolute upper bounds on cumulative token utilization for a single run.
*   **How it works**: Checks accumulated token counts on iteration/model hooks and aborts the run if the budget is exceeded. When `allow_final_response_over_budget=True`, it permits one final over-budget model call and injects a system notice telling the agent to answer immediately instead of continuing exploration.
*   **Arguments**:
    *   `max_tokens: int` (Absolute token limit)
    *   `abort_reason: str = "token_budget_exceeded"`
    *   `allow_final_response_over_budget: bool = False` (When true, request one final answer after the limit is reached instead of aborting immediately)

#### 5. `CostBudgetMiddleware`
*   **Class**: `CostBudgetMiddleware`
*   **Module**: `vidbyte.middleware.builtins.cost_budget`
*   **Purpose**: Places financial cost limits (USD) on LLM provider expenditures per run.
*   **How it works**: Computes accumulated costs based on input/output token pricing of the current model and aborts if exceeded.
*   **Arguments**:
    *   `max_cost_usd: float`
    *   `abort_reason: str = "cost_budget_exceeded"`

---

### C. Reliability & Provider Resilience

#### 6. `ModelRetryMiddleware`
*   **Class**: `ModelRetryMiddleware`
*   **Module**: `vidbyte.middleware.builtins.retry`
*   **Purpose**: Handles intermittent LLM provider failures (timeouts, rate limits, server errors).
*   **How it works**: Intercepts model errors and requests a direct retry after a configured sleep delay.
*   **Arguments**:
    *   `max_retries: int = 3`
    *   `retry_delays: Sequence[float] = (1.0, 2.0, 4.0)`

#### 7. `ExponentialBackoffRetryMiddleware`
*   **Class**: `ExponentialBackoffRetryMiddleware`
*   **Module**: `vidbyte.middleware.builtins.exponential_backoff_retry`
*   **Purpose**: Applies structured backing-off intervals for retry recovery.
*   **How it works**: Retries failures using double backoff intervals with random jitter.
*   **Arguments**:
    *   `max_retries: int = 5`
    *   `initial_delay: float = 1.0`
    *   `multiplier: float = 2.0`
    *   `jitter: bool = True`

#### 8. `CircuitBreakerMiddleware`
*   **Class**: `CircuitBreakerMiddleware`
*   **Module**: `vidbyte.middleware.builtins.circuit_breaker`
*   **Purpose**: Prevents cascading failures and wasteful provider calls when an endpoint goes down.
*   **How it works**: Employs a state machine (`CLOSED`, `OPEN`, `HALF_OPEN`). When failure thresholds are tripped, it opens the circuit and immediately blocks model calls for a recovery window, avoiding unnecessary API charges.
*   **Arguments**:
    *   `error_threshold: int = 3` (Failures needed to open circuit)
    *   `recovery_time_seconds: float = 30.0` (Time spent in OPEN state before HALF_OPEN probe)

#### 9. `ToolErrorPolicyMiddleware`
*   **Class**: `ToolErrorPolicyMiddleware`
*   **Module**: `vidbyte.middleware.builtins.tool_error_policy`
*   **Purpose**: Applies developer-configured retry, backoff, and abort policy to failed tool calls.
*   **How it works**: Reads `ToolResult` failures after tool execution, classifies retryable transient kinds (`timeout`, `rate_limited`, `upstream_error` by default), retries idempotent calls when allowed, records tool-call state metadata, and can abort when `max_total_tool_errors` is exceeded. `AgentLoopSettings(tool_error_policy=...)` auto-registers this middleware for compatible linear agents.
*   **Arguments**:
    *   `policy: ToolErrorPolicy`
    *   Policy fields: `max_retries_per_tool_call`, `retry_on`, `retry_backoff_base_seconds`, `retry_backoff_multiplier`, `retry_backoff_cap_seconds`, `retry_only_idempotent`, `on_unrecoverable`, `max_total_tool_errors`
*   **Rendering**: Terminal tool errors are returned to the model with full detail. Do not document or invent `ErrorVerbosity` / tool-error render-options APIs.

---

### D. Safety & Observability

#### 10. `LoopDetectionMiddleware`
*   **Class**: `LoopDetectionMiddleware`
*   **Module**: `vidbyte.middleware.builtins.loop_detection`
*   **Purpose**: Interrupts repeating, circular model reasoning sequences (e.g., repeated tool calls with identical parameters).
*   **How it works**: Hashes iteration text/tool calls and halts execution if duplicate signatures are detected.
*   **Arguments**:
    *   `max_repeats: int = 3`
    *   `abort_reason: str = "repetitive_loop_detected"`

#### 11. `RuntimeLimitMiddleware`
*   **Class**: `RuntimeLimitMiddleware`
*   **Module**: `vidbyte.middleware.builtins.runtime_limits`
*   **Purpose**: Places absolute safety rails on agent iteration count and execution duration.
*   **How it works**: Monitors counts and timing at every step, aborting immediately if limits are breached.
*   **Arguments**:
    *   `max_iterations: int | None = None`
    *   `max_elapsed_seconds: float | None = None`
    *   `abort_reason: str = "runtime_limit_exceeded"`

#### 12. `ToolPolicyMiddleware`
*   **Class**: `ToolPolicyMiddleware`
*   **Module**: `vidbyte.middleware.builtins.tool_policy`
*   **Purpose**: Implements strict, dynamic whitelisting/blacklisting policies on tool execution.
*   **How it works**: Scans tool call names and denies them if they violate the configured rules.
*   **Arguments**:
    *   `allowed_tools: Iterable[str] | None = None` (Whitelisted tools)
    *   `denied_tools: Iterable[str] | None = None` (Blacklisted tools)

#### 13. `TokenRateLimitMiddleware`
*   **Class**: `TokenRateLimitMiddleware`
*   **Module**: `vidbyte.middleware.builtins.rate_limit`
*   **Purpose**: Complies with provider rate-limiting policies (TPM).
*   **How it works**: Enforces rate limiting by calculating window usage and introducing deterministic sleep steps if limits are approached.
*   **Arguments**:
    *   `limit: int` (Tokens per period)
    *   `period_seconds: float = 60.0`

#### 14. `AuditLogMiddleware`
*   **Class**: `AuditLogMiddleware`
*   **Module**: `vidbyte.middleware.builtins.audit`
*   **Purpose**: Provides full compliance, observability, and structured logging of agent steps.
*   **How it works**: Emits structured log events at every lifecycle hook containing inputs, decisions, actions, and timings.
*   **Arguments**:
    *   `logger: logging.Logger | None = None`
    *   `log_level: int = logging.INFO`

---

## 5. Attaching Middleware to Agents

Multiple middlewares can be attached to an agent by passing them as a list to the `middleware` constructor parameter. The order of execution matches the list order:

```python
from vidbyte import Agent
from vidbyte.middleware import (
    RuntimeLimitMiddleware,
    TokenBudgetMiddleware,
    CanaryTripwireMiddleware,
    HoneypotToolMiddleware,
)

agent = Agent(
    name="secure-research-agent",
    system_prompt="Analyze code repositories and run local checks.",
    tools=[search_code, run_linter],
    middleware=[
        # 1. Budget and Time Rails
        RuntimeLimitMiddleware(max_iterations=15, max_elapsed_seconds=120.0),
        TokenBudgetMiddleware(max_tokens=50000),
        
        # 2. Injection & Hallucination Defenses
        HoneypotToolMiddleware(trap_tool_names=["delete_database", "bypass_sandbox"]),
        CanaryTripwireMiddleware(inject_probability=0.5),
    ],
)
```

For tool-error policy, prefer the structured loop setting so the agent registers `ToolErrorPolicyMiddleware` consistently:

```python
from vidbyte import Agent
from vidbyte.agents import AgentLoopSettings, ToolErrorPolicy

agent = Agent(
    name="resilient-tool-user",
    system_prompt="Use tools and recover from transient failures.",
    tools=[lookup],
    agent_loop_settings=AgentLoopSettings(
        tool_error_policy=ToolErrorPolicy(max_retries_per_tool_call=2),
    ),
)
```

---

## 5.1 Context Compaction Middleware

Context compaction belongs in middleware for new agent code. Do not expose compaction as a model-visible tool unless you need legacy/manual behavior through `ContextCompactionTool`.

Use `ToolResultCompactionMiddleware` when the model-visible version of a tool result should be truncated, stripped, or hidden while raw output remains in runtime metadata:

```python
from vidbyte.middleware.builtins import ToolResultCompactionMiddleware

agent = Agent(
    name="repo-analyst",
    system_prompt="Use tools when useful.",
    tools=[lookup],
    middleware=[
        ToolResultCompactionMiddleware.truncate(max_chars=600),
    ],
)
```

Use `MessageHistoryCompactionMiddleware` for deterministic provider-message history pruning, such as `keep_last`, `remove_all_tool_calls`, `remove_last_n_tool_calls`, `remove_tool_call_percentage`, `clear_except_system_and_log`, `deduplicate_tool_calls`, `trim_to_token_budget`, `trim_with_provider_boundaries`, `delete_messages`, `tool_output_sliding_window`, `clear_tool_results_except`, `head_tail_tool_preview`, `scrub_bloat`, `summary_with_backrefs`, `selective_prune`, `salience_score_eviction`, `query_relevance_filter`, and `context_snapshot_branch_trim`.

```python
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware

middleware = [
    MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=8000),
    MessageHistoryCompactionMiddleware.query_relevance_filter(query=None, keep_recent=4),
]
```

Use `SummaryCompactionMiddleware` only with an explicitly injected summarizer. Middleware must not perform hidden provider calls for summarization.

Use `TraceReplacementCompactionMiddleware` to fold a continual-trace artifact back into provider history on `before_model_call`. The artifact is read (in precedence order) from an injected `artifact`, an async `refresh_callback`, an `artifact_provider`, or `run_state[run_state_key][trace_key]` (default `("__result_metadata__", "trace")`) — the same key the continual-trace agent publishes. If the artifact is empty/initial (cold start), the middleware applies `fallback_mode` or no-ops; it never replaces real history with an empty trace. The single mode `CompactionMode.REPLACE_WITH_TRACE` is parameterized by `scope` (`all_non_system`, `oldest_n_groups`, `oldest_percentage`, `middle_keep_bookends`), group-aware retention (`keep_last_groups`, `keep_last_user`, `keep_pinned`, `keep_errors`, `keep_active_branch`), `placement` (`summary`, `system_suffix`, `synthetic_user`), and render bounds via `render={...}` (`fields`, `max_chars`, `array_head`, `array_tail`, `max_tokens`). Named constructors expose each method:

```python
from vidbyte.middleware.builtins import TraceReplacementCompactionMiddleware

agent = Agent(
    name="long-runner",
    system_prompt="Work carefully.",
    tools=[lookup],
    middleware=[
        # Replace old history with the trace, keep the newest 2 tool groups verbatim.
        TraceReplacementCompactionMiddleware.keep_recent_tail(keep_last_groups=2),
    ],
)
```

Family A (scope): `replace_all_with_trace` (keeps the live user turn by default), `keep_recent_tail`, `replace_oldest_n_iterations`, `replace_oldest_percentage`, `replace_middle_keep_bookends`, `replace_keep_last_user`. Family B (placement): `trace_as_summary`, `trace_as_system_suffix`, `trace_as_synthetic_user`. Family C (render): `trace_truncated_chars`, `trace_field_subset`. Family E (freshness): `stale_ok`, `with_refresh(refresh_callback)`. Family F (composition): `trace_fallback_to_mechanical`, `trace_plus_strip_tool_results`. Family G (protected retention): `replace_keep_pinned`, `replace_keep_errors`, `replace_keep_active_branch`. Use `TraceSummaryTailCompactionMiddleware.trace_then_summarize_tail(summarizer, ...)` to collapse old history to the trace and summarize the recent tail with an injected summarizer.

The renderer (`TraceArtifactRenderer`) and strategy (`ReplaceWithTraceCompaction`) are pure: the middleware is the only layer that reads `run_state`. This middleware is the sanctioned, opt-in exception to the continual-trace invariant that the trace is never written into the main context window — it only crosses that boundary when explicitly attached.

Compaction middleware returns `MiddlewareDecision.continue_(transform=...)`. The runtime applies those transforms only at supported hook boundaries; custom middleware should not mutate runtime internals directly.

---

## 6. Writing Custom Middleware

To implement custom runtime policies, inherit from `AgentMiddleware` and override the required lifecycle hooks.

### Custom Middleware Implementation Rules:

1.  **Fail Closed**: By default, middlewares declare `fail_closed = True`. If an exception occurs within a hook, the runtime immediately aborts the execution to preserve safety.
2.  **No Direct Mutation**: Do not directly mutate the agent context or internals. Always request transitions or state changes by returning `MiddlewareDecision` values.
3.  **Context Protocol Header**: When creating or editing any source files for your middleware, you MUST add a context protocol header.

### Step-by-Step Custom Example: PII Sanitizer Guard

This middleware intercepts tool calls before execution and blocks any tool call attempting to pass sensitive PII (like Social Security Numbers or Credit Cards) inside string arguments:

```python
"""Context Protocol Header

Description:
    Provides sensitive personal data (PII) filtering middleware for tool calls.
Purpose:
    Ensures agent-invoked tools do not accidentally exfiltrate or process sensitive
    personal identifiers like SSNs.
Architecture:
    - PIISanitizerMiddleware: Scans tool argument strings using regular expressions
      and blocks tool execution via deny_tool if PII is detected.
Relations:
    Subclasses AgentMiddleware; attached to Agent executors.
"""

from __future__ import annotations
import re
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware import AgentMiddleware

class PIISanitizerMiddleware(AgentMiddleware):
    """Intercepts and blocks tool calls attempting to transmit PII."""

    name = "PIISanitizer"

    def __init__(self, *, ssn_only: bool = False) -> None:
        self._ssn_regex = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        self._cc_regex = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
        self._ssn_only = ssn_only

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Check if we have an active tool call
        if ctx.tool_call is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()

        # Scan string arguments for sensitive regex matches
        for arg_name, arg_val in ctx.tool_call.arguments.items():
            if not isinstance(arg_val, str):
                continue
                
            if self._ssn_regex.search(arg_val):
                return MiddlewareDecision.deny_tool(
                    reason=f"PII detected: SSN found in argument '{arg_name}'"
                )
                
            if not self._ssn_only and self._cc_regex.search(arg_val):
                return MiddlewareDecision.deny_tool(
                    reason=f"PII detected: Credit Card number found in argument '{arg_name}'"
                )

        return MiddlewareDecision.continue_()
```

### Exposing Your Custom Middleware:

To make new middleware built-ins importable under `vidbyte.middleware` or `vidbyte.middleware.builtins`:
1.  Save the module under `vidbyte/middleware/builtins/<name>.py`.
2.  Import it and register it in `vidbyte/middleware/builtins/__init__.py`.
3.  Import it and register it in `vidbyte/middleware/__init__.py`.
4.  Update the **Context Protocol Header** in all affected files to document the additions.
