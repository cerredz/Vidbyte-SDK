"""Context Protocol Header

Description:
    Re-exports sandbox backend abstractions and local implementations.
Purpose:
    Provides a single import surface for sandbox backends used by shell tools.
Architecture:
    - BaseSandboxBackend: Abstract contract.
    - SandboxResult: Normalized execution result dataclass.
    - LocalSandboxBackend: Concrete asyncio-subprocess implementation.
Relations:
    Imported by vidbyte.tools.builtins.shell and future sandbox tools.
"""

from __future__ import annotations

from vidbyte.lib.providers.sandbox.base import BaseSandboxBackend, SandboxResult
from vidbyte.lib.providers.sandbox.local_backend import LocalSandboxBackend

__all__ = [
    "BaseSandboxBackend",
    "LocalSandboxBackend",
    "SandboxResult",
]
