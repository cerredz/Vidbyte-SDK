"""FILE: lint/core/discovery.py

PURPOSE:
    Lists the tracked Python files the lint suite is allowed to scan, so
    untracked scratch files and build output never silently affect a run.
ROLE IN CODEBASE:
    Called once by lint/core/runner.py before the single Ruff invocation.
FUNCTION INVENTORY:
    SourceCatalog.python_files: Tracked *.py paths under one package root.
WHAT NOT TO DO IN THIS FILE:
    Do not read file contents here; this module only resolves which paths
    exist and are tracked, matching the field guide's Semgrep gotcha where
    an untracked new file silently passes a git-tracked-only scan.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    field-guide/vidbyte-sdk/local-ci-verification.md
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lint.core.rule import LintConfigurationError


class SourceCatalog:
    """Resolves the tracked Python files one lint run scans."""

    @staticmethod
    def python_files(repository_root: Path, package_root: Path) -> tuple[Path, ...]:
        # Returns sorted absolute paths of tracked *.py files under package_root.
        tracked = SourceCatalog._tracked_paths(repository_root)
        matches = (
            repository_root / entry
            for entry in tracked
            if entry.endswith(".py") and "__pycache__" not in Path(entry).parts
        )
        package_root_resolved = package_root.resolve()
        return tuple(
            sorted(
                path.resolve()
                for path in matches
                if package_root_resolved in path.resolve().parents
            )
        )

    @staticmethod
    def _tracked_paths(repository_root: Path) -> tuple[str, ...]:
        # Runs `git ls-files -z` and splits its NUL-delimited stdout.
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=repository_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise LintConfigurationError(
                f"Could not list tracked files with `git ls-files -z` in {repository_root}: {exc}"
            ) from exc
        return tuple(entry for entry in result.stdout.split("\0") if entry)


__all__ = ["SourceCatalog"]
