"""Context Protocol Header

Description:
    Implements a file-based todo backend that persists tasks to JSON.
Purpose:
    Provides a simple, zero-dependency todo store using the local filesystem
    with async-safe file I/O via asyncio.to_thread.
Architecture:
    - FileTodoBackend: Uses ~/.vidbyte/todos.json, protected by asyncio.Lock.
    - Loads state on init, saves after every mutation.
Relations:
    Related to vidbyte.lib.providers.todo.base and vidbyte.tools.builtins.todo.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from vidbyte.lib.providers.todo.base import BaseTodoBackend, TodoItem

DEFAULT_STORE_PATH = Path.home() / ".vidbyte" / "todos.json"


class FileTodoBackend(BaseTodoBackend):
    """File-based todo persistence using JSON storage."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path or DEFAULT_STORE_PATH
        self._lock = asyncio.Lock()
        self._items: dict[str, TodoItem] = {}
        self._load_sync()

    def _load_sync(self) -> None:
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for task_id, data in raw.items():
            if isinstance(data, dict):
                self._items[task_id] = TodoItem(**data)

    async def _save(self) -> None:
        async with self._lock:

            def _write() -> None:
                self._store_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    task_id: {
                        "id": item.id,
                        "title": item.title,
                        "description": item.description,
                        "status": item.status,
                        "priority": item.priority,
                        "parent_id": item.parent_id,
                        "depends_on": item.depends_on,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                    for task_id, item in self._items.items()
                }
                self._store_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

            await asyncio.to_thread(_write)

    async def create(self, title: str, description: str, priority: str, parent_id: str | None) -> TodoItem:
        now = datetime.now(timezone.utc).isoformat()
        item = TodoItem(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            status="pending",
            priority=priority or "medium",
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        self._items[item.id] = item
        await self._save()
        return item

    async def update(self, task_id: str, **kwargs: object) -> TodoItem | None:
        existing = self._items.get(task_id)
        if existing is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, object] = {"updated_at": now}
        for key in ("title", "description", "status", "priority", "parent_id"):
            if key in kwargs and kwargs[key] is not None:
                updates[key] = kwargs[key]
        for k, v in updates.items():
            object.__setattr__(existing, k, v)
        await self._save()
        return existing

    async def list_all(self, status: str | None) -> list[TodoItem]:
        if status is None:
            return list(self._items.values())
        return [item for item in self._items.values() if item.status == status]

    async def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        if task_id not in self._items or depends_on_id not in self._items:
            return False
        if task_id == depends_on_id:
            return False
        item = self._items[task_id]
        if depends_on_id not in item.depends_on:
            item.depends_on.append(depends_on_id)
            now = datetime.now(timezone.utc).isoformat()
            object.__setattr__(item, "updated_at", now)
            await self._save()
        return True

    async def get(self, task_id: str) -> TodoItem | None:
        return self._items.get(task_id)


__all__ = ["FileTodoBackend"]
