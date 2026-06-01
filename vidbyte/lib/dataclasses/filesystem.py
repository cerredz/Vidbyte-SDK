from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vidbyte.lib.enums import Platform
from vidbyte.lib.errors import ToolExecutionError

if TYPE_CHECKING:
    from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend


@dataclass(frozen=True, slots=True)
class FileStat:
    """Portable file metadata returned by filesystem stat operations."""

    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int | None
    modified_time: float | None


@dataclass(frozen=True, slots=True)
class FileSystemToolConfig:
    """Configuration shared by root-scoped filesystem tools."""

    root: Path | str
    allow_write: bool = False
    encoding: str = "utf-8"
    platform: Platform | str = Platform.LOCAL
    backend: BaseFileSystemBackend | None = None

    def normalized_platform(self) -> Platform:
        try:
            return self.platform if isinstance(self.platform, Platform) else Platform(self.platform)
        except ValueError as exc:
            raise ToolExecutionError(f"Unsupported filesystem platform: {self.platform!r}") from exc

    def resolved_root(self) -> Path:
        return Path(self.root).expanduser().resolve()

    def resolved_backend(self) -> BaseFileSystemBackend:
        if self.backend is not None:
            return self.backend
        platform = self.normalized_platform()
        if platform == Platform.LOCAL:
            from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend

            return LocalFileSystemBackend()
        raise ToolExecutionError(
            "Filesystem platform requires an explicit backend.",
            details={"platform": platform.value},
        )


__all__ = [
    "FileStat",
    "FileSystemToolConfig",
]
