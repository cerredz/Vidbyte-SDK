from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vidbyte.lib.enums import Platform
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError

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
    max_overwrite_lines: int | None = None

    def __post_init__(self) -> None:
        # @intent big-existing-files-are-edited-not-rewritten
        # None means write_text may replace any existing file. A number
        # is the most lines an existing file may have and still be
        # replaced whole, so it must be a real whole number of at least
        # one; True or 2.5 would quietly set a different limit.
        limit = self.max_overwrite_lines
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise ConfigurationError("FileSystemToolConfig max_overwrite_lines must be None or an int of at least 1.", details={"max_overwrite_lines": repr(limit)})

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
