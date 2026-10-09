from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

# Smallest accepted recursion depth; negative depths have no meaning for a tree listing.
_MIN_MAX_DEPTH = 0
# Smallest accepted entry cap; a tree listing must be allowed to return at least one entry.
_MIN_MAX_ENTRIES = 1


class TreeTool(FileSystemTool):
    """Return a bounded recursive directory tree for a scoped path, newline-joined."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for recursively listing a directory tree.
        return ToolSpec(
            name="tree",
            description="Return a recursive directory tree listing for a path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path of the root to traverse.", required=False),
                ToolParameter(name="max_depth", type="integer", description="Maximum directory depth to recurse into.", required=False),
                ToolParameter(name="max_entries", type="integer", description="Maximum number of entries to return.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Traverse the directory tree up to max_depth/max_entries and return entries newline-joined.
        path = call.arguments.get("path", ".")
        max_depth = int(call.arguments.get("max_depth", 3))
        max_entries = int(call.arguments.get("max_entries", 200))
        try:
            if max_depth < _MIN_MAX_DEPTH:
                raise ToolExecutionError(f"TreeTool max_depth must be at least {_MIN_MAX_DEPTH}.")
            if max_entries < _MIN_MAX_ENTRIES:
                raise ToolExecutionError(f"TreeTool max_entries must be at least {_MIN_MAX_ENTRIES}.")
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
            truncated = len(entries) >= max_entries
            return ToolResult.success(self.name, "\n".join(entries), metadata={"path": str(target), "max_depth": max_depth, "truncated": truncated})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "TreeTool",
]
