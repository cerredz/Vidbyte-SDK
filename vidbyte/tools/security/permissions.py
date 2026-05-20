"""Context Protocol Header

Description:
    Implements permission decisions for tool execution.
Purpose:
    Keeps authorization policy separate from individual tools so native and MCP
    bridged tools are checked consistently.
Architecture:
    - PermissionDecision: Allow/deny enum for policy results.
    - PermissionPolicy: Immutable set-based policy used by ToolExecutor.
Relations:
    Related to vidbyte.tools.executor and vidbyte.tools.types.ToolPermission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vidbyte.tools.types import ToolCall, ToolPermission, ToolSpec


class PermissionDecision(str, Enum):
    """Authorization decision returned by a policy."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    """Simple allow-list policy for tool permission levels."""

    allowed: frozenset[ToolPermission] = frozenset(
        {ToolPermission.SAFE, ToolPermission.READ}
    )

    def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
        """Return whether the tool call is allowed by the current policy."""
        del call
        if spec.permission in self.allowed:
            return PermissionDecision.ALLOW
        return PermissionDecision.DENY

    @classmethod
    def allow_all(cls) -> "PermissionPolicy":
        """Return a policy that allows every declared tool permission."""
        return cls(allowed=frozenset(ToolPermission))
