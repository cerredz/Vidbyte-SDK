# Built-In Middleware

## Folder Intent

This folder provides ready-made middleware policies for audits, budgets, retries, rate limits, loop detection, circuit breaking, compaction, and tool safety.

## Non-Goals

Do not add provider-specific transport or concrete tool logic here; built-ins should remain runtime-policy components with explicit hook behavior.

## File Index

- `__init__.py`: Exports built-in middleware implementations. Gives developers ready-made runtime controls for common agent safety, reliability, observability, and security workflows. Key symbols: AuditLogMiddleware, CanaryTripwireMiddleware, CircuitBreakerMiddleware, CircuitState, ConfusedDeputyGuardMiddleware, CostBudgetMiddleware.
- `audit.py`: Provides structured audit logging middleware for agent runtime hooks. Lets developers observe direct text runtime lifecycle events without coupling application logging to AgentRuntime internals. Key symbols: AuditLogMiddleware.
- `canary_tripwire.py`: Provides data exfiltration detection middleware using canary watermark tokens. Lets developers detect prompt-injection-driven exfiltration attacks where adversarial content in tool results drives the model to reproduce internal content. Key symbols: CanaryTripwireMiddleware.
- `circuit_breaker.py`: Provides a three-state circuit breaker middleware for agent model calls. Lets developers protect against sustained model failures by short-circuiting model calls when error rate exceeds a rolling-window threshold, then recovering gradually through a half-open probe phase. Key symbols: CircuitState, CircuitBreakerMiddleware.
- `confused_deputy.py`: Provides confused deputy attack detection middleware for agent tool calls. Lets developers detect indirect prompt injection where adversarial content in prior tool results drives subsequent tool call arguments instead of the original user instruction. Key symbols: ConfusedDeputyGuardMiddleware.
- `context_compaction.py`: Owns context compaction behavior inside the vidbyte/middleware layer. Key symbols: MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware, TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware.
- `cost_budget.py`: Provides per-run cost budget middleware for direct text agent runs. Lets developers cap the estimated USD spend of a single agent run using a configurable blended cost-per-million-token rate, aborting before each iteration once the ceiling is reached. Key symbols: CostBudgetMiddleware.
- `exponential_backoff_retry.py`: Provides exponential backoff retry middleware for direct text agent runs. Lets direct text agent runtimes retry transient model failures with exponential backoff and optional jitter, filtered to specific exception types. Key symbols: ExponentialBackoffRetryMiddleware.
- `honeypot_tool.py`: Provides honeypot tool detection middleware for agent tool calls. Lets developers detect prompt injection or hallucination by planting decoy forbidden tool names that trigger an immediate abort if called. Key symbols: HoneypotToolMiddleware.
- `loop_detection.py`: Provides agent tool-call loop detection middleware. Lets developers react when the same tool is called with identical arguments consecutively more times than a configured threshold, or when any single tool produces the same output more than a total-count threshold, preventing infinite action loops that exhaust iteration or token limits slowly. Repeated-output detection supports a soft threshold (warn the agent in-context) and a hard threshold (abort the run). Key symbols: LoopDetectionMiddleware, REPEATED_OUTPUT_LOOP_NOTICE.
- `rate_limit.py`: Provides token rate limiting middleware for direct text agent runs. Lets developers slow agent loops when provider-reported token usage crosses a configured window threshold. Key symbols: TokenRateLimitMiddleware.
- `retry.py`: Provides deterministic model-call retry middleware. Lets direct text agent runtimes retry transient runner failures at a middleware-controlled boundary. Key symbols: ModelRetryMiddleware.
- `runtime_limits.py`: Provides runtime boundary middleware for direct text agent loops. Lets developers abort runs at middleware hook boundaries using elapsed, model-call, or tool-call limits. Key symbols: RuntimeLimitMiddleware.
- `token_budget.py`: Provides per-run token budget middleware for direct text agent runs. Lets developers cap the total provider-reported tokens consumed by a single agent run, aborting or requesting one final answer once the ceiling is reached. Key symbols: TokenBudgetMiddleware, TOKEN_BUDGET_FINAL_RESPONSE_NOTICE.
- `tool_error_policy.py`: Provides retry and circuit-break policy for failed tool calls. Lets agent loops silently retry transient idempotent tool errors while surfacing terminal errors through the formatter's full-detail rendering. Key symbols: ToolErrorPolicyMiddleware.
- `tool_policy.py`: Provides allowlist and denylist middleware for agent tool calls. Lets developers enforce runtime-specific tool policy before permission checks, validation, or tool execution occur. Key symbols: ToolPolicyMiddleware.

## Subfolder Routing

- No source subfolders.

## Logs

- 2026-07-07: Middleware metadata should remain safe for logs and useful for diagnosing which policy changed the run.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
