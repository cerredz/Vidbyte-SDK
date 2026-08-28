"""Context Protocol Header

Description:
    Exports tool security policy and sandbox protocol types.
Purpose:
    Provides one import surface for permission checks and future isolated
    execution transports.
Architecture:
    - PermissionPolicy and PermissionDecision from permissions.
    - SandboxRequest, SandboxResult, and SandboxTransport from sandbox.
Relations:
    Related to vidbyte.tools.executor and risky built-in tools.
"""

from __future__ import annotations

from vidbyte.tools.security.permissions import PermissionDecision, PermissionPolicy
from vidbyte.tools.security.sandbox import (
    SandboxRequest,
    SandboxResult,
    SandboxTransport,
)
from vidbyte.tools.types import ToolPermission

__all__ = [
    "PermissionDecision",
    "PermissionPolicy",
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
    "ToolPermission",
]
