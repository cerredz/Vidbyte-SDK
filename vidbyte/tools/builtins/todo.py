"""Context Protocol Header

Description:
    Built-in todo management tools for task tracking within agent sessions.
Purpose:
    Provides agents with persistent task creation, listing, dependency
    management, and tree visualization.
Architecture:
    - Lazy-initialized backend via _get_backend().
    - Wraps FileTodoBackend with @tool-decorated functions.
Relations:
    Related to vidbyte.lib.providers.todo and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        from vidbyte.lib.providers.todo.file_backend import FileTodoBackend

        _backend = FileTodoBackend()
    return _backend


@tool(permission=ToolPermission.SAFE)
async def todo_create(title: str, description: str = "", priority: str = "medium", parent_id: str | None = None) -> str:
    """Create a new todo task. Returns the task ID."""
    item = await _get_backend().create(title, description, priority, parent_id)
    return f"Created task {item.id}: {item.title} [{item.priority}]"


@tool(permission=ToolPermission.SAFE)
async def todo_update(task_id: str, status: str | None = None, title: str | None = None, description: str | None = None) -> str:
    """Update a todo task. Status can be: pending, in_progress, completed, cancelled."""
    kwargs: dict[str, object] = {}
    if status is not None:
        kwargs["status"] = status
    if title is not None:
        kwargs["title"] = title
    if description is not None:
        kwargs["description"] = description
    item = await _get_backend().update(task_id, **kwargs)
    if item:
        return f"Updated task {item.id}: status={item.status}"
    return f"Task {task_id} not found."


@tool(permission=ToolPermission.SAFE)
async def todo_list(status: str | None = None) -> str:
    """List all todo tasks, optionally filtered by status."""
    items = await _get_backend().list_all(status)
    if not items:
        return "No tasks found."
    lines = []
    icon_map = {"pending": " ", "in_progress": ">", "completed": "x", "cancelled": "-"}
    for item in items:
        status_icon = icon_map.get(item.status, " ")
        lines.append(f"[{status_icon}] {item.id[:8]} {item.title} [{item.priority}]")
    return "\n".join(lines)


@tool(permission=ToolPermission.SAFE)
async def todo_add_dependency(task_id: str, depends_on_id: str) -> str:
    """Add a dependency between two tasks."""
    ok = await _get_backend().add_dependency(task_id, depends_on_id)
    return f"{'Added' if ok else 'Failed to add'} dependency: {task_id} depends on {depends_on_id}"


@tool(permission=ToolPermission.SAFE)
async def todo_visualize() -> str:
    """Display the task tree with dependencies as ASCII art."""
    items = await _get_backend().list_all(None)
    if not items:
        return "No tasks."
    item_map = {i.id: i for i in items}
    roots = [i for i in items if i.parent_id is None or i.parent_id not in item_map]
    icon_map = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "cancelled": "[-]"}

    def _short(ids: list[str]) -> str:
        return ", ".join(d[:8] for d in ids)

    def _render_tree(item, indent):
        status_icon = icon_map.get(item.status, "[?]")
        deps = f" (depends: {_short(item.depends_on)})" if item.depends_on else ""
        line = f"{indent}{status_icon} {item.title} [{item.priority}]{deps}"
        children = [i for i in items if i.parent_id == item.id]
        child_lines = []
        for idx, child in enumerate(children):
            is_last = idx == len(children) - 1
            prefix = f"{indent}  " if is_last else f"{indent} |"
            child_lines.extend(_render_tree(child, prefix).split("\n"))
        result = [line]
        result.extend(child_lines)
        return "\n".join(result)

    return "\n".join(_render_tree(root, "") for root in roots)


__all__ = [
    "todo_add_dependency",
    "todo_create",
    "todo_list",
    "todo_update",
    "todo_visualize",
]
