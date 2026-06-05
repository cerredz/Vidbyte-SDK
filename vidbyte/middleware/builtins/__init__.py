"""Context Protocol Header

Description:
    Exports built-in middleware implementations.
Purpose:
    Gives developers ready-made runtime controls for common agent safety,
    reliability, observability, and security workflows.
Architecture:
    - TokenRateLimitMiddleware: Limits request tokens.
    - RuntimeLimitMiddleware: Places constraints on execution loops and elapsed time.
    - ToolPolicyMiddleware: Filters allowed tools.
    - AuditLogMiddleware: Logs agent and tool interactions.
    - ModelRetryMiddleware: Retries failed model calls.
    - TokenBudgetMiddleware: Controls token usage.
    - CostBudgetMiddleware: Places monetary spending limits.
    - ToolResultCompactionMiddleware: Compacts model-visible tool outputs.
    - MessageHistoryCompactionMiddleware: Compacts provider message history.
    - SummaryCompactionMiddleware: Summarizes provider message history.
    - TraceReplacementCompactionMiddleware: Replaces history with a rendered continual-trace artifact.
    - TraceSummaryTailCompactionMiddleware: Replaces old history with the trace and summarizes the recent tail.
    - ExponentialBackoffRetryMiddleware: Retries steps using backing-off intervals.
    - LoopDetectionMiddleware: Halts execution if a repetitive prompt loop occurs.
    - CircuitBreakerMiddleware & CircuitState: Cuts off calls when error thresholds are exceeded.
    - CanaryTripwireMiddleware: Security boundary detection using system secrets.
    - ConfusedDeputyGuardMiddleware: Authorization check to prevent confused deputy exploits.
    - HoneypotToolMiddleware: Traps unauthorized tool usages with fake honey tools.
Relations:
    Related to vidbyte.middleware and vidbyte.agents.runtime.
"""

from __future__ import annotations

from vidbyte.middleware.builtins.audit import AuditLogMiddleware
from vidbyte.middleware.builtins.canary_tripwire import CanaryTripwireMiddleware
from vidbyte.middleware.builtins.circuit_breaker import CircuitBreakerMiddleware, CircuitState
from vidbyte.middleware.builtins.confused_deputy import ConfusedDeputyGuardMiddleware
from vidbyte.middleware.builtins.context_compaction import MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware, TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware
from vidbyte.middleware.builtins.cost_budget import CostBudgetMiddleware
from vidbyte.middleware.builtins.exponential_backoff_retry import ExponentialBackoffRetryMiddleware
from vidbyte.middleware.builtins.honeypot_tool import HoneypotToolMiddleware
from vidbyte.middleware.builtins.loop_detection import LoopDetectionMiddleware
from vidbyte.middleware.builtins.rate_limit import TokenRateLimitMiddleware
from vidbyte.middleware.builtins.retry import ModelRetryMiddleware
from vidbyte.middleware.builtins.runtime_limits import RuntimeLimitMiddleware
from vidbyte.middleware.builtins.token_budget import TokenBudgetMiddleware
from vidbyte.middleware.builtins.tool_policy import ToolPolicyMiddleware

__all__ = [
    "AuditLogMiddleware",
    "CanaryTripwireMiddleware",
    "CircuitBreakerMiddleware",
    "CircuitState",
    "ConfusedDeputyGuardMiddleware",
    "CostBudgetMiddleware",
    "ExponentialBackoffRetryMiddleware",
    "HoneypotToolMiddleware",
    "LoopDetectionMiddleware",
    "ModelRetryMiddleware",
    "RuntimeLimitMiddleware",
    "MessageHistoryCompactionMiddleware",
    "SummaryCompactionMiddleware",
    "TokenBudgetMiddleware",
    "TokenRateLimitMiddleware",
    "ToolResultCompactionMiddleware",
    "ToolPolicyMiddleware",
    "TraceReplacementCompactionMiddleware",
    "TraceSummaryTailCompactionMiddleware",
]
