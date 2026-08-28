"""Context Protocol Header

Description:
    Re-exports sandbox contracts from the SDK dataclass namespace.
Purpose:
    Preserves `vidbyte.tools.security.sandbox` imports while keeping dataclass
    definitions under `vidbyte.lib.dataclasses`.
Architecture:
    - Compatibility shim for SandboxRequest, SandboxResult, and SandboxTransport.
Relations:
    Related to vidbyte.lib.dataclasses.sandbox.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sandbox import (
    SandboxRequest,
    SandboxResult,
    SandboxTransport,
)

__all__ = [
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
]
