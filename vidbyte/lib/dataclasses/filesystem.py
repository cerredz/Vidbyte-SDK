from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vidbyte.lib.enums import Platform
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError

if TYPE_CHECKING:
    from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend

# The smallest overwrite line limit; 0 would refuse every existing file.
_MIN_OVERWRITE_LINES = 1


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
class OverwriteLineLimit:
    """Validated limit on the lines an existing file may have for write_text to replace it whole; None means no limit.

    parameter is the keyword the caller set, so the error names it.
    """

    lines: int | None
    parameter: str

    def __post_init__(self) -> None:
        # @intent big-existing-files-are-edited-not-rewritten
        # A number is the most lines an existing file may have and still
        # be replaced whole, so it must be a real whole number of at
        # least one; True or 2.5 would quietly set a different limit.
        lines = self.lines
        if lines is not None and (isinstance(lines, bool) or not isinstance(lines, int) or lines < _MIN_OVERWRITE_LINES):
            raise ConfigurationError(f"{self.parameter} must be None or an int of at least {_MIN_OVERWRITE_LINES}.", details={"parameter": self.parameter, "value": repr(lines)})


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
        # None lets write_text replace any existing file; a bad limit
        # fails here, before any tool is built.
        OverwriteLineLimit(self.max_overwrite_lines, "max_overwrite_lines")

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
    "OverwriteLineLimit",
]
