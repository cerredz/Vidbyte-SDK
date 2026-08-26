"""FILE: lint/core/ruff.py

PURPOSE:
    Runs the pinned `ruff` analyzer exactly once per lint invocation and
    parses its JSON output into a typed, sorted finding tuple.
ROLE IN CODEBASE:
    Called once by lint/core/runner.py with the union of every selected
    rule's ruff_selectors; each rule then filters the shared result set.
ARCHITECTURE NOTE:
    `--isolated` is mandatory so a contributor's ambient Ruff config, or any
    future unrelated `[tool.ruff]` section in pyproject.toml, cannot change
    what this gate checks. `--exit-zero` makes Ruff's own exit code report
    only whether Ruff *ran*, not whether it found anything, so a nonzero
    exit here always means Ruff itself failed to execute.
WHAT NOT TO DO IN THIS FILE:
    Do not add a second Ruff subprocess call for a second rule; every rule's
    selectors must be unioned into this one invocation (FR-4 in the design).
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lint.core.rule import LintAnalyzerError


@dataclass(frozen=True, slots=True)
class RuffFinding:
    """One Ruff diagnostic: a rule code at one file, line, and column."""

    code: str
    file: Path
    line: int
    column: int
    message: str


class RuffAdapter:
    """Runs Ruff once and returns its findings as typed, sorted data."""

    @staticmethod
    def run(package_root: Path, selectors: tuple[str, ...]) -> tuple[RuffFinding, ...]:
        # Runs `ruff check` with the given selector union and parses its JSON output.
        command = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(package_root),
            "--isolated",
            "--output-format",
            "json",
            "--exit-zero",
            "--select",
            ",".join(selectors),
        ]
        result = RuffAdapter._run_ruff(command)
        return RuffAdapter._parse_findings(result.stdout, command)

    @staticmethod
    def _run_ruff(command: list[str]) -> subprocess.CompletedProcess[str]:
        # Executes the Ruff subprocess, converting any failure to start into LintAnalyzerError.
        cwd = Path.cwd()
        try:
            return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            exit_code = getattr(exc, "returncode", "unavailable")
            stderr = getattr(exc, "stderr", "") or ""
            raise LintAnalyzerError(
                f"Ruff failed with exit code {exit_code}: {' '.join(command)} (cwd={cwd}).\n{stderr}"
            ) from exc

    @staticmethod
    def _parse_findings(stdout: str, command: list[str]) -> tuple[RuffFinding, ...]:
        # Parses Ruff's JSON array into RuffFinding tuples, sorted by file/line/column.
        text = stdout.strip()
        if not text:
            return ()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LintAnalyzerError(
                f"Ruff produced unparsable JSON output for: {' '.join(command)}\n{exc}"
            ) from exc
        findings = tuple(
            RuffFinding(
                code=str(entry["code"]),
                file=Path(entry["filename"]),
                line=int(entry["location"]["row"]),
                column=int(entry["location"]["column"]),
                message=str(entry["message"]),
            )
            for entry in payload
            if entry.get("code")
        )
        return tuple(sorted(findings, key=lambda finding: (finding.file, finding.line, finding.column)))


__all__ = ["RuffAdapter", "RuffFinding"]
