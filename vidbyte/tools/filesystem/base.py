from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vidbyte.lib.errors import ToolExecutionError


@dataclass(frozen=True, slots=True)
class FileSystemToolConfig:
    """Configuration shared by root-scoped filesystem tools."""

    root: Path | str
    allow_write: bool = False
    encoding: str = "utf-8"

    def resolved_root(self) -> Path:
        return Path(self.root).expanduser().resolve()


def resolve_scoped_path(config: FileSystemToolConfig, path: str) -> Path:
    root = config.resolved_root()
    requested = (root / path).expanduser().resolve()
    if requested != root and root not in requested.parents:
        raise ToolExecutionError(
            "Filesystem tool path escaped the configured root.",
            details={"root": str(root), "path": path},
        )
    return requested


def require_write_enabled(config: FileSystemToolConfig) -> None:
    if not config.allow_write:
        raise ToolExecutionError("Filesystem writes require allow_write=True.")
