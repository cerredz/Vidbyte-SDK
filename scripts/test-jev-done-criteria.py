"""FILE: scripts/test-jev-done-criteria.py

PURPOSE: Runs every focused Jev minimum-duration test and prints a machine-readable per-case result.
ROLE IN CODEBASE: Called from the SDK root during local verification; delegates all assertions to tests/test_jev_done_criteria.py.
ARCHITECTURE NOTE: The script uses unittest discovery and exits non-zero for failed or errored cases.
FUNCTION INVENTORY: main -> int; FeatureTestResult prints named PASS/FAIL outcomes.
COMMON MODIFICATION PATTERNS: Keep the loaded test module aligned with Section 10 of docs/design/jev-done-criteria.md.
WHAT NOT TO DO: Do not reproduce production checks in this script or contact live model providers.
KNOWN EDGE CASES: Unittest errors and assertion failures both count as failed cases.
RELATED DOCS: docs/design/jev-done-criteria.md and tests/features/jev_minimum_duration/FEATURE.md.
TESTS: Execute directly with python scripts/test-jev-done-criteria.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


class FeatureTestResult(unittest.TestResult):
    """Prints one explicit status line for every executed feature test."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Prints the successful test's stable unittest identifier.
        super().addSuccess(test)
        print(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Prints the failed test name and assertion details.
        super().addFailure(test, err)
        print(f"FAIL {test.id()}: {err[1]}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Prints the errored test name and exception details.
        super().addError(test, err)
        print(f"FAIL {test.id()}: {err[1]}")


def main() -> int:
    # Loads the feature test module, reports each case, and returns a process status.
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_jev_done_criteria.py")
    result = unittest.TextTestRunner(stream=sys.stdout, resultclass=FeatureTestResult).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
