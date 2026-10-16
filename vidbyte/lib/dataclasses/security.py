"""Context Protocol Header

Description:
    Defines permission policy contracts for tool execution.
Purpose:
    Keeps immutable authorization data in the shared SDK dataclass namespace.
Architecture:
    - PermissionDecision: Allow/deny enum for policy results.
    - PermissionPolicy: Immutable set-based policy used by ToolExecutor and
      AgentRuntime; its check also honors the run's PermissionCeiling.
Relations:
    Re-exported by vidbyte.tools.security.permissions. The run-scoped cap
    lives in vidbyte/lib/permission_ceiling.py (docs/design/jev-read-only-intent.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolSpec
from vidbyte.lib.permission_ceiling import PermissionCeiling


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

    def __post_init__(self) -> None:
        """Store the allow-list as ToolPermission members whatever spelling the caller used."""
        # @intent tool-permission-is-one-canonical-enum
        # State export reads permission.value, so a {"safe", "read"} policy must hold enum members.
        if isinstance(self.allowed, (str, bytes)):
            raise ValueError(f"PermissionPolicy.allowed must be a collection of permissions, not a single string: {self.allowed!r}")
        object.__setattr__(self, "allowed", frozenset(ToolPermission(value) for value in self.allowed))

    def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
        """Return whether the tool call is allowed by this policy and by the run's active permission ceiling."""
        del call
        # @intent the-run-ceiling-caps-every-policy
        # Every executor decides here, so a run's ceiling binds each
        # agent it starts, whatever policy that agent was given.
        if spec.permission in self.allowed and PermissionCeiling.allows(spec.permission):
            return PermissionDecision.ALLOW
        return PermissionDecision.DENY

    @classmethod
    def allow_all(cls) -> "PermissionPolicy":
        """Return a policy that allows every declared tool permission."""
        return cls(allowed=frozenset(ToolPermission))
