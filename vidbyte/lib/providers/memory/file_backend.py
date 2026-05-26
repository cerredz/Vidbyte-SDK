"""Context Protocol Header

Description:
    File-based memory backend persisting key-value pairs to disk as JSON.
Purpose:
    Provides a concrete implementation of BaseMemoryBackend that stores data
    in ~/.vidbyte/memory.json with asyncio.Lock for thread safety.
Architecture:
    - Loads an in-memory dict from the JSON file on init (empty if missing).
    - save/delete trigger persistence via asyncio.to_thread.
    - search performs case-insensitive substring matching on values.
    - Corrupt JSON files are handled gracefully by starting fresh.
Relations:
    Implements vidbyte.lib.providers.memory.base.BaseMemoryBackend.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


class FileMemoryBackend:
    """Concrete memory backend backed by ~/.vidbyte/memory.json."""

    def __init__(self) -> None:
        self._file = Path.home() / ".vidbyte" / "memory.json"
        self._lock = asyncio.Lock()
        self._data: dict[str, str] = {}
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Load data from disk on first access."""
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            try:
                if self._file.exists():
                    text = await asyncio.to_thread(lambda: self._file.read_text(encoding="utf-8"))
                    loaded = json.loads(text)
                    if isinstance(loaded, dict):
                        self._data = loaded
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self._data = {}
            self._loaded = True

    async def _persist(self) -> None:
        """Write current data dict to disk via a thread."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self._data, indent=2, ensure_ascii=False)
        await asyncio.to_thread(
            lambda: self._file.write_text(text, encoding="utf-8")
        )

    async def save(self, key: str, value: str) -> None:
        """Set a key-value pair and persist to disk."""
        await self._ensure_loaded()
        async with self._lock:
            self._data[key] = value
            await self._persist()

    async def load(self, key: str) -> str | None:
        """Return the value for a key, or None."""
        await self._ensure_loaded()
        async with self._lock:
            return self._data.get(key)

    async def delete(self, key: str) -> bool:
        """Remove a key. Returns True if the key was present."""
        await self._ensure_loaded()
        async with self._lock:
            if key in self._data:
                del self._data[key]
                await self._persist()
                return True
            return False

    async def list_keys(self, prefix: str | None) -> list[str]:
        """Return keys, optionally filtered by prefix."""
        await self._ensure_loaded()
        async with self._lock:
            if prefix is None:
                return list(self._data.keys())
            return [k for k in self._data if k.startswith(prefix)]

    async def search(self, query: str) -> list[dict]:
        """Return [{key, value}] entries where value contains the query (case-insensitive)."""
        await self._ensure_loaded()
        async with self._lock:
            q = query.lower()
            return [
                {"key": k, "value": v}
                for k, v in self._data.items()
                if q in v.lower()
            ]


__all__ = ["FileMemoryBackend"]
