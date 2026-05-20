from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.base import ToolResult
from vidbyte.tools.filesystem.base import FileSystemToolConfig, resolve_scoped_path


class ReadTextTool:
    """Read a text file inside a configured root."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        self._config = config

    def run(self, path: str) -> ToolResult:
        target = resolve_scoped_path(self._config, path)
        if not target.exists():
            raise ToolExecutionError("File does not exist.", details={"path": str(target)})
        if not target.is_file():
            raise ToolExecutionError("Path is not a file.", details={"path": str(target)})
        return ToolResult(
            value=target.read_text(encoding=self._config.encoding),
            metadata={"path": str(target), "encoding": self._config.encoding},
        )
