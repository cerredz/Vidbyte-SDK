"""Context Protocol Header

Description:
    Re-exports todo backend implementations.
Purpose:
    Provides a stable import surface for todo provider backends without
    exposing internal implementation details.
Architecture:
    - BaseTodoBackend: Abstract contract.
    - FileTodoBackend: JSON-file-based todo persistence.
    - TodoItem: Data transfer object for todo entries.
Relations:
    Related to vidbyte.tools.builtins.todo.
"""

from __future__ import annotations

from vidbyte.lib.providers.todo.base import BaseTodoBackend, TodoItem
from vidbyte.lib.providers.todo.file_backend import FileTodoBackend

__all__ = [
    "BaseTodoBackend",
    "FileTodoBackend",
    "TodoItem",
]
