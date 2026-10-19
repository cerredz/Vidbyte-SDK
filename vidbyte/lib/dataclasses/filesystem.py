from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums import Platform
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError

if TYPE_CHECKING:
    from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend

# The smallest line cap; 0 would refuse every existing file or read
# nothing at all.
_MIN_LINE_LIMIT = 1

# The smallest file count or token total a folder can hold.
_MIN_FOLDER_COUNT = 0


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
class FolderTotals:
    """How many files a folder holds and their estimated token total, as FolderUsage counts them from disk."""

    files: int
    tokens: int

    def __post_init__(self) -> None:
        # Both are counts, so neither can be negative or a bool.
        for name in ("files", "tokens"):
            RecordFieldValidator.require_int(getattr(self, name), f"FolderTotals.{name}", minimum=_MIN_FOLDER_COUNT)


@dataclass(frozen=True, slots=True)
class LineLimit:
    """Validated line cap for a filesystem tool: the lines an existing file may have for write_text to replace it whole, or the lines one read_lines call returns; None means no limit.

    parameter is the keyword the caller set, so the error names it.
    """

    lines: int | None
    parameter: str

    def __post_init__(self) -> None:
        # @intent line-caps-are-whole-numbers-of-at-least-one
        # A number is the most lines a tool will rewrite or read in one
        # call, so it must be a real whole number of at least one; True
        # or 2.5 would quietly set a different limit.
        lines = self.lines
        if lines is not None and (isinstance(lines, bool) or not isinstance(lines, int) or lines < _MIN_LINE_LIMIT):
            raise ConfigurationError(f"{self.parameter} must be None or an int of at least {_MIN_LINE_LIMIT}.", details={"parameter": self.parameter, "value": repr(lines)})


@dataclass(frozen=True, slots=True)
class FileSystemToolConfig:
    """Configuration shared by root-scoped filesystem tools."""

    root: Path | str
    allow_write: bool = False
    encoding: str = "utf-8"
    platform: Platform | str = Platform.LOCAL
    backend: BaseFileSystemBackend | None = None
    max_overwrite_lines: int | None = None
    max_read_lines: int | None = None

    def __post_init__(self) -> None:
        # None lets write_text replace any existing file and read_lines
        # read to the end; a bad limit fails here, before any tool is
        # built.
        LineLimit(self.max_overwrite_lines, "max_overwrite_lines")
        LineLimit(self.max_read_lines, "max_read_lines")

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
    "FolderTotals",
    "LineLimit",
]
