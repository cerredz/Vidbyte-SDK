from __future__ import annotations

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

# Documented defaults used when the model omits a bound or sends null for it.
_DEFAULT_MAX_DEPTH = 3
_DEFAULT_MAX_ENTRIES = 200


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
        try:
            # Read the optional arguments inside the error handling so a bad value becomes an error result.
            path = self._optional_argument(call, "path", default=".")
            max_depth = int(self._optional_argument(call, "max_depth", default=_DEFAULT_MAX_DEPTH))
            max_entries = int(self._optional_argument(call, "max_entries", default=_DEFAULT_MAX_ENTRIES))
            target = self._path(path)
            FileSystemPermissions.require_existing_directory(target)
            root = self._config.resolved_root()
            entries: list[str] = []
            truncated = False
            for child in sorted(target.rglob("*"), key=lambda item: str(item).lower()):
                relative_to_target = child.relative_to(target)
                if len(relative_to_target.parts) > max_depth:
                    continue
                # @intent tree-truncated-means-entries-were-cut
                # Report truncation only when an eligible entry is actually left out, not when the
                # folder merely holds exactly max_entries entries.
                if len(entries) >= max_entries:
                    truncated = True
                    break
                suffix = "/" if child.is_dir() else ""
                entries.append(f"{child.relative_to(root).as_posix()}{suffix}")
            return ToolResult.success(self.name, "\n".join(entries), metadata={"path": str(target), "max_depth": max_depth, "truncated": truncated})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "TreeTool",
]
