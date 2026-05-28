"""Context Protocol Header

Description:
    Exports public agent runtime middleware contracts and built-ins.
Purpose:
    Gives SDK users a concise import path for creating and attaching runtime
    middleware to direct text agents.
Architecture:
    - AgentMiddleware: Optional hook base class for custom middleware.
    - MiddlewarePipeline: Ordered hook dispatcher used by AgentRuntime.
    - Dataclass re-exports: hooks, actions, contexts, decisions, events.
    - Built-ins: AuditLogMiddleware, ModelRetryMiddleware, RuntimeLimitMiddleware,
      TokenRateLimitMiddleware, ToolPolicyMiddleware, TokenBudgetMiddleware,
      CostBudgetMiddleware, ExponentialBackoffRetryMiddleware,
      LoopDetectionMiddleware, CircuitBreakerMiddleware, and CircuitState.
Relations:
    Related to vidbyte.agents.runtime and vidbyte.middleware.builtins.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
)
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    CircuitBreakerMiddleware,
    CircuitState,
    CostBudgetMiddleware,
    ExponentialBackoffRetryMiddleware,
    LoopDetectionMiddleware,
    ModelRetryMiddleware,
    RuntimeLimitMiddleware,
    TokenBudgetMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
)
from vidbyte.middleware.pipeline import MiddlewarePipeline

__all__ = [
    "AgentMiddleware",
    "AuditLogMiddleware",
    "CircuitBreakerMiddleware",
    "CircuitState",
    "CostBudgetMiddleware",
    "ExponentialBackoffRetryMiddleware",
    "LoopDetectionMiddleware",
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "MiddlewarePipeline",
    "ModelRetryMiddleware",
    "RuntimeLimitMiddleware",
    "TokenBudgetMiddleware",
    "TokenRateLimitMiddleware",
    "ToolPolicyMiddleware",
]
