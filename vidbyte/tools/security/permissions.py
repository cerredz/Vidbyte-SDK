"""Context Protocol Header

Description:
    Re-exports permission contracts from the SDK dataclass namespace.
Purpose:
    Preserves `vidbyte.tools.security.permissions` imports while keeping
    dataclass definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for PermissionDecision and PermissionPolicy.
Relations:
    Related to vidbyte.lib.dataclasses.security.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy

__all__ = [
    "PermissionDecision",
    "PermissionPolicy",
]
