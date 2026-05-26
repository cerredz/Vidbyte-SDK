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
from vidbyte.middleware.approval import ApprovalMiddleware
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    ModelRetryMiddleware,
    RuntimeLimitMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
)
from vidbyte.middleware.loop_detection import StuckLoopMiddleware
from vidbyte.middleware.orphan_repair import ToolOrphanRepairMiddleware
from vidbyte.middleware.plan_mode import PlanModeMiddleware
from vidbyte.middleware.pipeline import MiddlewarePipeline
from vidbyte.middleware.secret_redaction import SecretRedactionMiddleware

__all__ = [
    "AgentMiddleware",
    "ApprovalMiddleware",
    "AuditLogMiddleware",
    "ModelRetryMiddleware",
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "MiddlewarePipeline",
    "PlanModeMiddleware",
    "RuntimeLimitMiddleware",
    "SecretRedactionMiddleware",
    "StuckLoopMiddleware",
    "TokenRateLimitMiddleware",
    "ToolOrphanRepairMiddleware",
    "ToolPolicyMiddleware",
]
