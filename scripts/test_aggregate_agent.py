"""Standalone verification script for aggregate agents and BaseAgent aggregation boundaries.

Runs every test case from tests/test_aggregate_agent.py, printing PASS/FAIL per case
with a final summary, and exits non-zero if any case fails.

Usage:
    python scripts/test_aggregate_agent.py
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _LabelingResult(unittest.TestResult):
    """Collects per-test outcomes so the script can print a PASS/FAIL line for each."""

    def __init__(self) -> None:
        super().__init__()
        self.outcomes: list[tuple[str, bool, str]] = []

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self.outcomes.append((str(test), True, ""))

    def addFailure(self, test: unittest.TestCase, err) -> None:  # type: ignore[no-untyped-def]
        super().addFailure(test, err)
        self.outcomes.append((str(test), False, self._exc_to_text(err)))

    def addError(self, test: unittest.TestCase, err) -> None:  # type: ignore[no-untyped-def]
        super().addError(test, err)
        self.outcomes.append((str(test), False, self._exc_to_text(err)))

    @staticmethod
    def _exc_to_text(err) -> str:  # type: ignore[no-untyped-def]
        # Renders the exception type and message for a compact one-line reason.
        exc_type, exc_value, _ = err
        return f"{exc_type.__name__}: {exc_value}"


def main() -> int:
    # Loads the aggregate-agent test suite, runs it, and prints labeled results.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_aggregate_agent")
    result = _LabelingResult()
    suite.run(result)

    passed = 0
    for name, ok, reason in result.outcomes:
        label = "PASS" if ok else "FAIL"
        print(f"[{label}] {name}" + (f"  -> {reason}" if not ok else ""))
        passed += int(ok)

    total = len(result.outcomes)
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total and total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
