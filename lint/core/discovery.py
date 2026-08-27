"""FILE: lint/core/discovery.py

PURPOSE: Reads tracked SDK Python/README sources once with deterministic paths.
ROLE IN CODEBASE: Prevents rules from re-walking, re-reading, or importing the package.
ARCHITECTURE NOTE: git ls-files is the authority, matching Semgrep's tracked-file gate.
FUNCTION INVENTORY: SourceCatalog.python_files()/all_python_files()/readmes() return cached source records.
WHAT NOT TO DO: Do not import vidbyte modules or follow sibling worktrees.
KNOWN EDGE CASES: UTF-8 BOMs are accepted so Windows checkouts match compileall.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SourceDiscoveryError(RuntimeError):
    """Actionable failure while locating or reading tracked source."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One tracked source file with text and optional parsed Python AST."""

    path: Path
    rel: str
    text: str
    tree: ast.Module | None = None
    parse_error: str | None = None

    def line_at(self, line: int) -> str:
        # Returns one 1-indexed source line without raising for analyzer edge cases.
        lines = self.text.splitlines()
        return lines[line - 1] if 0 < line <= len(lines) else ""


class SourceCatalog:
    """Caches tracked Python and README source records for all rules."""

    def __init__(self, root: Path | None = None) -> None:
        # Binds discovery to the repository root and starts empty caches.
        self.root = (root or repo_root()).resolve()
        self._tracked: tuple[str, ...] | None = None
        self._python: tuple[SourceFile, ...] | None = None
        self._all_python: tuple[SourceFile, ...] | None = None
        self._readmes: tuple[SourceFile, ...] | None = None

    def python_files(self) -> tuple[SourceFile, ...]:
        # Returns tracked production package modules sorted by relative path.
        if self._python is None:
            paths = (rel for rel in self._tracked_paths() if rel.startswith("vidbyte/") and rel.endswith(".py"))
            self._python = tuple(self._build(rel, parse_python=True) for rel in paths)
        return self._python

    def readmes(self) -> tuple[SourceFile, ...]:
        # Returns every tracked README for opt-in file-index parity analysis.
        if self._readmes is None:
            self._readmes = tuple(self._build(rel, parse_python=False) for rel in self._tracked_paths() if rel == "README.md" or rel.endswith("/README.md"))
        return self._readmes

    def all_python_files(self) -> tuple[SourceFile, ...]:
        # Returns every tracked Python source file for repository-wide metadata rules.
        if self._all_python is None:
            self._all_python = tuple(self._build(rel, parse_python=True) for rel in self._tracked_paths() if rel.endswith(".py"))
        return self._all_python

    def tracked_paths(self) -> tuple[str, ...]:
        # Exposes the stable tracked catalogue for cross-file manifest rules.
        return self._tracked_paths()

    def _tracked_paths(self) -> tuple[str, ...]:
        # Runs git without a shell and fails with the exact repository/command context.
        if self._tracked is not None:
            return self._tracked
        try:
            result = subprocess.run(["git", "ls-files", "-z"], cwd=self.root, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SourceDiscoveryError(f"Could not enumerate tracked files with git ls-files from {self.root}: {exc}. Run lint inside a Git worktree.") from exc
        self._tracked = tuple(sorted(path.replace("\\", "/") for path in result.stdout.split("\0") if path))
        return self._tracked

    def _build(self, rel: str, parse_python: bool) -> SourceFile:
        # Reads one tracked path and records syntax errors instead of executing the file.
        path = self.root / Path(rel)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceDiscoveryError(f"Could not read tracked source {path} as UTF-8 while building the lint catalogue: {exc}. Restore or re-encode the file.") from exc
        if not parse_python:
            return SourceFile(path=path, rel=rel, text=text)
        try:
            return SourceFile(path=path, rel=rel, text=text, tree=ast.parse(text, filename=rel))
        except SyntaxError as exc:
            return SourceFile(path=path, rel=rel, text=text, parse_error=f"{exc.msg} at {exc.lineno}:{exc.offset}")


def repo_root() -> Path:
    # Anchors all discovery and subprocess work to the repository, never caller CWD.
    return Path(__file__).resolve().parents[2]
