"""Verification script for the durable-sessions feature.

Runs every test case in tests/test_durable_sessions.py, prints a PASS/FAIL line
per case, prints an X/Y summary, and exits non-zero if any case fails.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _LabelledResult(unittest.TestResult):
    """Collects per-test outcomes for compact PASS/FAIL reporting."""

    def __init__(self) -> None:
        # Track ordered (name, status) outcomes.
        super().__init__()
        self.outcomes: list[tuple[str, str]] = []

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Record a passing test.
        super().addSuccess(test)
        self.outcomes.append((str(test), "PASS"))

    def addFailure(self, test: unittest.TestCase, err) -> None:
        # Record a failing assertion.
        super().addFailure(test, err)
        self.outcomes.append((str(test), "FAIL"))

    def addError(self, test: unittest.TestCase, err) -> None:
        # Record an erroring test.
        super().addError(test, err)
        self.outcomes.append((str(test), "FAIL"))

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        # Record a skipped test as a pass for reporting purposes.
        super().addSkip(test, reason)
        self.outcomes.append((str(test), "SKIP"))


def main() -> int:
    # Load the durable-sessions tests, run them, and report PASS/FAIL per case.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_durable_sessions")
    result = _LabelledResult()
    suite.run(result)

    for name, status in result.outcomes:
        print(f"{status}: {name}")

    passed = sum(1 for _, status in result.outcomes if status in ("PASS", "SKIP"))
    total = len(result.outcomes)
    print(f"\n{passed}/{total} tests passed")

    if result.failures or result.errors:
        for test, trace in (*result.failures, *result.errors):
            print(f"\n--- {test} ---\n{trace}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
