"""FILE: lint/core/mypy.py

PURPOSE: Runs pinned mypy once and parses its staged contract findings.
ROLE IN CODEBASE: Gives S009 a fail-closed, count-ratcheted type-analysis source.
ARCHITECTURE NOTE: Finding exit code 1 is valid; analyzer/config failures are not.
FUNCTION INVENTORY: MypyStore.records() returns cached normalized diagnostics.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S009.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

from lint.core.discovery import repo_root

MYPY_LINE = re.compile(r"^(.*?):(\d+):(\d+): (error|note): (.*?)(?:  \[([^\]]+)\])?$")


class MypyAnalyzerError(RuntimeError):
    """Mypy failed to provide a complete parseable finding set."""


@dataclass(frozen=True, slots=True)
class MypyRecord:
    """One normalized mypy error diagnostic."""

    rel_path: str
    line: int
    column: int
    message: str
    code: str


class MypyStore:
    """Caches one complete package mypy invocation."""

    _cache: tuple[MypyRecord, ...] | None = None

    @classmethod
    def records(cls) -> tuple[MypyRecord, ...]:
        # Returns cached records or executes the exact staged command once.
        if cls._cache is None:
            cls._cache = cls._run()
        return cls._cache

    @classmethod
    def _run(cls) -> tuple[MypyRecord, ...]:
        # Accepts clean/finding statuses and rejects analyzer/config/internal failures.
        command = [sys.executable, "-m", "mypy", "--config-file", "lint/mypy.ini", "vidbyte"]
        try:
            result = subprocess.run(command, cwd=repo_root(), check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            raise MypyAnalyzerError(f"Could not start mypy from {repo_root()} with {command!r}: {exc}. Install the project dev extra.") from exc
        if result.returncode not in {0, 1}:
            raise MypyAnalyzerError(f"mypy failed with exit code {result.returncode}; command={command!r}; stderr={result.stderr.strip() or '<empty>'}.")
        records: list[MypyRecord] = []
        unparsed: list[str] = []
        for line in result.stdout.splitlines():
            match = MYPY_LINE.match(line)
            if not match:
                if line.strip() and not line.startswith(("Success:", "Found ")):
                    unparsed.append(line)
                continue
            path, row, column, severity, message, code = match.groups()
            if severity == "error":
                records.append(MypyRecord(rel_path=path.replace("\\", "/"), line=int(row), column=int(column), message=message, code=code or "mypy"))
        if unparsed:
            raise MypyAnalyzerError(f"mypy produced unrecognized output; first lines={unparsed[:5]!r}. Update the pinned parser before accepting analyzer drift.")
        return tuple(records)
