from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class TreeTool(FileSystemTool):
    """Return a bounded recursive directory tree for a scoped root."""

    def run(self, path: str = ".", *, max_depth: int = 3, max_entries: int = 200) -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_directory(target)
        root = self._config.resolved_root()
        entries: list[str] = []
        for child in sorted(target.rglob("*"), key=lambda item: str(item).lower()):
            relative_to_target = child.relative_to(target)
            if len(relative_to_target.parts) > max_depth:
                continue
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{child.relative_to(root).as_posix()}{suffix}")
            if len(entries) >= max_entries:
                break
        return ToolResult(
            value=tuple(entries),
            metadata={"path": str(target), "max_depth": max_depth, "truncated": len(entries) >= max_entries},
        )


__all__ = [
    "TreeTool",
]
