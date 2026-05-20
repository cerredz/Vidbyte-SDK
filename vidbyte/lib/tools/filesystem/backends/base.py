from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from vidbyte.lib.dataclasses import FileStat


class BaseFileSystemBackend(ABC):
    """Backend interface used by platform-neutral filesystem tools."""

    @abstractmethod
    def read_text(self, path: Path, *, encoding: str) -> str:
        """Read text from a scoped path."""

    @abstractmethod
    def read_binary(self, path: Path) -> bytes:
        """Read bytes from a scoped path."""

    @abstractmethod
    def write_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        """Write text to a scoped path."""

    @abstractmethod
    def append_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        """Append text to a scoped path."""

    @abstractmethod
    def list_dir(self, path: Path) -> tuple[str, ...]:
        """List one scoped directory."""

    @abstractmethod
    def make_dir(self, path: Path, *, parents: bool, exist_ok: bool) -> None:
        """Create a scoped directory."""

    @abstractmethod
    def delete(self, path: Path, *, recursive: bool) -> None:
        """Delete a scoped file or directory."""

    @abstractmethod
    def move(self, source: Path, destination: Path) -> None:
        """Move or rename a scoped file or directory."""

    @abstractmethod
    def copy(self, source: Path, destination: Path) -> None:
        """Copy a scoped file or directory."""

    @abstractmethod
    def stat(self, path: Path) -> FileStat:
        """Return portable metadata for a scoped path."""

    @abstractmethod
    def find(self, root: Path, pattern: str) -> tuple[str, ...]:
        """Find matching paths under a scoped root."""

    @abstractmethod
    def diff_text(self, left: Path, right_content: str, *, encoding: str, label: str) -> str:
        """Return a unified diff between scoped text and provided content."""

    @abstractmethod
    def zip_path(self, source: Path, destination: Path) -> None:
        """Create a zip archive from a scoped source."""

    @abstractmethod
    def unzip_path(self, source: Path, destination: Path) -> tuple[str, ...]:
        """Extract a zip archive into a scoped destination."""


__all__ = [
    "BaseFileSystemBackend",
]
