"""Context Protocol Header

Description:
    Re-exports memory backend implementations.
Purpose:
    Provides a stable import surface for memory provider backends without
    exposing internal implementation details.
Architecture:
    - BaseMemoryBackend: Abstract contract.
    - FileMemoryBackend: Concrete file-based JSON persistence backend.
Relations:
    Related to vidbyte.tools.builtins.memory.
"""

from __future__ import annotations

from vidbyte.lib.providers.memory.base import BaseMemoryBackend
from vidbyte.lib.providers.memory.file_backend import FileMemoryBackend

__all__ = [
    "BaseMemoryBackend",
    "FileMemoryBackend",
]
