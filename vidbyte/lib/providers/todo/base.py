"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for todo backends.
Purpose:
    Provides a typed contract that todo provider backends must implement,
    along with the shared TodoItem dataclass.
Architecture:
    - TodoItem: Dataclass with id, title, description, status, priority, and dependency fields.
    - BaseTodoBackend: ABC requiring async create, update, list_all, add_dependency, get.
Relations:
    Related to vidbyte.lib.providers.todo and vidbyte.tools.builtins.todo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class TodoItem:
    id: str
    title: str
    description: str
    status: str  # pending, in_progress, completed, cancelled
    priority: str  # low, medium, high
    parent_id: str | None
    depends_on: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class BaseTodoBackend(ABC):
    @abstractmethod
    async def create(self, title: str, description: str, priority: str, parent_id: str | None) -> TodoItem:
        ...

    @abstractmethod
    async def update(self, task_id: str, **kwargs: object) -> TodoItem | None:
        ...

    @abstractmethod
    async def list_all(self, status: str | None) -> list[TodoItem]:
        ...

    @abstractmethod
    async def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        ...

    @abstractmethod
    async def get(self, task_id: str) -> TodoItem | None:
        ...


__all__ = [
    "BaseTodoBackend",
    "TodoItem",
]
