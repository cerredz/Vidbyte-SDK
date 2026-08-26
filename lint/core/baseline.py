"""FILE: lint/core/baseline.py

PURPOSE:
    Loads/saves lint/baseline.json and decides, per rule, whether the
    current finding count is clean, holding steady, improved, or regressed.
ROLE IN CODEBASE:
    Called by lint/core/runner.py once per selected rule, and by lint/run.py
    directly for the --update-baseline command.
ARCHITECTURE NOTE:
    Never raise a number in this file by hand to make a run pass; the only
    sanctioned way to change a baseline count is `python lint/run.py
    --update-baseline` after the new count has been manually reviewed.
WHAT NOT TO DO IN THIS FILE:
    Do not decide whether a missing/stale baseline key fails the run here;
    that is a registry-wide set-membership question owned by LintRunner,
    since this class only ever sees one rule's count at a time.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from lint.core.rule import LintConfigurationError


class LintVerdict(str, Enum):
    """One rule's outcome for a single lint run."""

    CLEAN = "clean"
    RATCHETED = "ratcheted"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    ERRORED = "errored"


class BaselineStore:
    """Reads, writes, and evaluates the frozen per-rule debt counts."""

    @staticmethod
    def load(path: Path) -> dict[str, int]:
        # Returns the sorted rule_id -> count mapping, or {} if the file does not exist yet.
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise LintConfigurationError(f"{path} is not valid JSON: {exc}") from exc
        return {str(rule_id): int(count) for rule_id, count in payload.items()}

    @staticmethod
    def save(path: Path, counts: dict[str, int]) -> None:
        # Writes a sorted-key JSON mapping with a trailing newline.
        ordered = dict(sorted(counts.items()))
        path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def evaluate(baseline_count: int, actual_count: int) -> LintVerdict:
        # Compares the current count against the frozen baseline count.
        if actual_count > baseline_count:
            return LintVerdict.REGRESSED
        if actual_count < baseline_count:
            return LintVerdict.IMPROVED
        if actual_count == 0:
            return LintVerdict.CLEAN
        return LintVerdict.RATCHETED


__all__ = ["BaselineStore", "LintVerdict"]
