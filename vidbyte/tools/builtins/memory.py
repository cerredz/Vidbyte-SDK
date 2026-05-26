"""Context Protocol Header

Description:
    Built-in memory tools for persistent key-value storage across agent sessions.
Purpose:
    Enables agents to save, load, delete, list, and search persistent key-value
    pairs stored in ~/.vidbyte/memory.json.
Architecture:
    - Uses the @tool decorator with ToolPermission.SAFE.
    - Delegates to FileMemoryBackend for all persistence operations.
    - search returns JSON array of matching [{key, value}] entries.
Relations:
    Related to vidbyte.lib.providers.memory and vidbyte.tools.decorators.
"""

from __future__ import annotations

import json

from vidbyte.lib.providers.memory.file_backend import FileMemoryBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

_backend = FileMemoryBackend()


@tool(permission=ToolPermission.SAFE)
async def memory_save(key: str, value: str) -> str:
    """Save a value under a given key for later retrieval.

    Args:
        key: The key to store the value under.
        value: The string value to persist.
    """
    try:
        await _backend.save(key, value)
        return f"Saved key '{key}'."
    except Exception as exc:
        return f"Error saving key '{key}': {exc}"


@tool(permission=ToolPermission.SAFE)
async def memory_load(key: str) -> str:
    """Load a previously saved value by its key.

    Args:
        key: The key to retrieve.
    """
    try:
        value = await _backend.load(key)
        if value is None:
            return f"No value found for key '{key}'."
        return value
    except Exception as exc:
        return f"Error loading key '{key}': {exc}"


@tool(permission=ToolPermission.SAFE)
async def memory_delete(key: str) -> str:
    """Delete a key and its associated value.

    Args:
        key: The key to remove.
    """
    try:
        deleted = await _backend.delete(key)
        if deleted:
            return f"Deleted key '{key}'."
        return f"Key '{key}' not found."
    except Exception as exc:
        return f"Error deleting key '{key}': {exc}"


@tool(permission=ToolPermission.SAFE)
async def memory_list(prefix: str | None = None) -> str:
    """List all stored keys, optionally filtered by a prefix.

    Args:
        prefix: Optional prefix to filter keys by.
    """
    try:
        keys = await _backend.list_keys(prefix)
        if not keys:
            return "No keys found."
        return json.dumps(keys, indent=2)
    except Exception as exc:
        return f"Error listing keys: {exc}"


@tool(permission=ToolPermission.SAFE)
async def memory_search(query: str) -> str:
    """Search stored values for a given query substring (case-insensitive).

    Args:
        query: The substring to search for in stored values.
    """
    try:
        results = await _backend.search(query)
        if not results:
            return f"No values matched query '{query}'."
        return json.dumps(results, indent=2)
    except Exception as exc:
        return f"Error searching memory: {exc}"
