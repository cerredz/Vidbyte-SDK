"""Context Protocol Header

Description:
    Re-exports permission contracts from the SDK dataclass namespace.
Purpose:
    Preserves `vidbyte.tools.security.permissions` imports while keeping
    dataclass definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for PermissionDecision and PermissionPolicy.
    - PermissionCeiling: the run-scoped cap every PermissionPolicy honors.
Relations:
    Related to vidbyte.lib.dataclasses.security and vidbyte.lib.permission_ceiling.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy
from vidbyte.lib.permission_ceiling import PermissionCeiling

__all__ = [
    "PermissionCeiling",
    "PermissionDecision",
    "PermissionPolicy",
]
