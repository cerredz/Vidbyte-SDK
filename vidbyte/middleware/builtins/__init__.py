"""Context Protocol Header

Description:
    Exports built-in middleware implementations.
Purpose:
    Gives developers ready-made runtime controls for common agent safety,
    reliability, observability, and security workflows.
Architecture:
    - TokenRateLimitMiddleware, RuntimeLimitMiddleware, ToolPolicyMiddleware,
      AuditLogMiddleware, ModelRetryMiddleware, CanaryTripwireMiddleware,
      ConfusedDeputyGuardMiddleware, and HoneypotToolMiddleware.
Relations:
    Related to vidbyte.middleware and vidbyte.agents.runtime.
"""

from __future__ import annotations

from vidbyte.middleware.builtins.audit import AuditLogMiddleware
from vidbyte.middleware.builtins.canary_tripwire import CanaryTripwireMiddleware
from vidbyte.middleware.builtins.confused_deputy import ConfusedDeputyGuardMiddleware
from vidbyte.middleware.builtins.honeypot_tool import HoneypotToolMiddleware
from vidbyte.middleware.builtins.rate_limit import TokenRateLimitMiddleware
from vidbyte.middleware.builtins.retry import ModelRetryMiddleware
from vidbyte.middleware.builtins.runtime_limits import RuntimeLimitMiddleware
from vidbyte.middleware.builtins.tool_policy import ToolPolicyMiddleware

__all__ = [
    "AuditLogMiddleware",
    "CanaryTripwireMiddleware",
    "ConfusedDeputyGuardMiddleware",
    "HoneypotToolMiddleware",
    "ModelRetryMiddleware",
    "RuntimeLimitMiddleware",
    "TokenRateLimitMiddleware",
    "ToolPolicyMiddleware",
]
