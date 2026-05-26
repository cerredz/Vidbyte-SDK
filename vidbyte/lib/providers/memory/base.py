"""Context Protocol Header

Description:
    Defines the abstract base class for persistent memory backends.
Purpose:
    Provides a typed contract that all memory provider backends must implement,
    enabling agents to save, load, delete, list, and search key-value pairs.
Architecture:
    - BaseMemoryBackend: ABC requiring save, load, delete, list_keys, and search.
Relations:
    Related to vidbyte.lib.providers.memory and vidbyte.tools.builtins.memory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMemoryBackend(ABC):
    """Abstract contract for agent memory backends."""

    @abstractmethod
    async def save(self, key: str, value: str) -> None:
        """Persist a key-value pair."""
        ...

    @abstractmethod
    async def load(self, key: str) -> str | None:
        """Retrieve a value by key, or None if not found."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Remove a key-value pair. Returns True if the key existed."""
        ...

    @abstractmethod
    async def list_keys(self, prefix: str | None) -> list[str]:
        """Return all keys, optionally filtered by prefix."""
        ...

    @abstractmethod
    async def search(self, query: str) -> list[dict]:
        """Return [{key, value}] entries where value contains the query substring."""
        ...


__all__ = ["BaseMemoryBackend"]
