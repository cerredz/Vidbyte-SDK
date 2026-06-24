"""Executable verification script for the context-window reasoning algorithms.

Runs every test case from the design doc testing plan for both the
problem-space search and error-correction algorithms (Section 10 of
docs/design/context-window-reasoning-algorithms.md), printing PASS/FAIL per
case with a final summary. Exits with code 1 if any test fails.

Usage:
    python scripts/test-context-window-reasoning-algorithms.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests import test_error_correction_algorithm, test_problem_space_search_algorithm


class _ReportingResult(unittest.TestResult):
    """Collects per-test outcomes for PASS/FAIL reporting."""

    def __init__(self) -> None:
        super().__init__()
        self.outcomes: list[tuple[str, bool, str]] = []
        self._failed_ids: set[str] = set()

    def addError(self, test: unittest.TestCase, err: object) -> None:
        # Records an errored test so it reports as FAIL.
        super().addError(test, err)  # type: ignore[arg-type]
        self._failed_ids.add(test.id())

    def addFailure(self, test: unittest.TestCase, err: object) -> None:
        # Records a failed assertion so it reports as FAIL.
        super().addFailure(test, err)  # type: ignore[arg-type]
        self._failed_ids.add(test.id())

    def stopTest(self, test: unittest.TestCase) -> None:
        # Finalizes one test outcome after it completes.
        super().stopTest(test)
        detail = self._detail_for(test.id())
        self.outcomes.append((self._name(test), test.id() not in self._failed_ids, detail))

    def _detail_for(self, test_id: str) -> str:
        # Returns the first traceback line for a failed test, if any.
        for collection in (self.errors, self.failures):
            for failed_test, trace in collection:
                if failed_test.id() == test_id:
                    return trace.strip().splitlines()[-1]
        return ""

    @staticmethod
    def _name(test: unittest.TestCase) -> str:
        # Builds a compact, readable test name from the test id.
        parts = test.id().split(".")
        return f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else test.id()


def _run_module(module: object) -> _ReportingResult:
    # Loads and runs every test case in a module against a reporting result.
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = _ReportingResult()
    suite.run(result)
    return result


def main() -> int:
    # Runs both reasoning-algorithm suites and prints PASS/FAIL plus a summary.
    modules = (
        ("Problem-Space Search", test_problem_space_search_algorithm),
        ("Error Correction", test_error_correction_algorithm),
    )
    passed = 0
    total = 0
    for label, module in modules:
        print(f"\n=== {label} ===")
        result = _run_module(module)
        for name, ok, detail in sorted(result.outcomes):
            status = "PASS" if ok else "FAIL"
            suffix = f" — {detail}" if detail and not ok else ""
            print(f"  [{status}] {name}{suffix}")
            total += 1
            passed += 1 if ok else 0
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
