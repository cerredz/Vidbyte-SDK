from __future__ import annotations

from pathlib import Path

from vidbyte.tools.base import ToolResult
from vidbyte.tools.filesystem.base import (
    FileSystemToolConfig,
    require_write_enabled,
    resolve_scoped_path,
)


class WriteTextTool:
    """Write a text file inside a configured root."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        self._config = config

    def run(self, path: str, content: str, *, create_parents: bool = False) -> ToolResult:
        require_write_enabled(self._config)
        target = resolve_scoped_path(self._config, path)
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=self._config.encoding)
        return ToolResult(
            value=Path(target),
            metadata={"path": str(target), "encoding": self._config.encoding},
        )
