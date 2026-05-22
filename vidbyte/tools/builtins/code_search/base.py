"""Context Protocol Header

Description:
    Provides shared root-scoped helpers for code search tools.
Purpose:
    Owns safe path resolution, ignored-directory filtering, text-file detection,
    and bounded file reading for glob, grep, and semantic search tools.
Architecture:
    - BaseCodeSearchTool: Base class with root safety and iteration helpers.
Relations:
    Related to vidbyte.tools.builtins.code_search.grep, glob, and semantic.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

from vidbyte.tools.base import BaseTool


class BaseCodeSearchTool(BaseTool):
    """Common base for root-scoped code search tools."""

    def __init__(
        self,
        root_dir: str | Path,
        *,
        ignore_patterns: Sequence[str] | None = None,
        max_file_bytes: int = 1_000_000,
    ) -> None:
        """Store the resolved root and search safety settings."""
        self.root_dir = Path(root_dir).resolve()
        self.ignore_patterns = tuple(
            ignore_patterns
            or (".git", "node_modules", "__pycache__", ".venv", "venv")
        )
        self.max_file_bytes = max_file_bytes

    def resolve_under_root(self, path: str | Path = ".") -> Path:
        """Resolve a path under root and reject traversal outside it."""
        candidate = (self.root_dir / path).resolve()
        try:
            candidate.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError(f"Path escapes root: {path}") from exc
        return candidate

    def relative_path(self, path: Path) -> str:
        """Return a stable POSIX-style path relative to the configured root."""
        return path.resolve().relative_to(self.root_dir).as_posix()

    def should_ignore(self, path: Path) -> bool:
        """Return whether a path is inside an ignored directory or file part."""
        return any(part in self.ignore_patterns for part in path.parts)

    def iter_files(
        self,
        subdir: str | Path = ".",
        *,
        extensions: Sequence[str] = (),
    ) -> Iterator[Path]:
        """Yield text-like files beneath a safe subdirectory."""
        start = self.resolve_under_root(subdir)
        if not start.exists():
            return
        extension_set = tuple(ext if ext.startswith(".") else f".{ext}" for ext in extensions)
        candidates = (start,) if start.is_file() else start.rglob("*")
        for path in candidates:
            if not path.is_file() or self.should_ignore(path):
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(self.root_dir)
            except ValueError:
                continue
            if extension_set and resolved.suffix not in extension_set:
                continue
            if not self.is_text_file(resolved):
                continue
            yield resolved

    def is_text_file(self, path: Path) -> bool:
        """Return whether a file appears safe to read as bounded text."""
        try:
            if path.stat().st_size > self.max_file_bytes:
                return False
            sample = path.read_bytes()[:2048]
        except OSError:
            return False
        return b"\x00" not in sample

    def read_text_lines(self, path: Path) -> list[str]:
        """Read a text file into split lines using UTF-8 replacement."""
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
