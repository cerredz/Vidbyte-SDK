"""Context Protocol Header

Description:
    Standalone verification script for the trace-backed compaction methods.
Purpose:
    Runs every test case from the design doc's testing plan against the real
    implementation and prints a PASS/FAIL line per case with a final summary.
Architecture:
    - main: loads tests.test_trace_replacement_compaction and runs it with a
      reporting TestResult, then exits non-zero on any failure.
Relations:
    Exercises vidbyte.middleware.compaction trace strategy, renderer, and middleware.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _ReportingResult(unittest.TextTestResult):
    """TestResult that prints one PASS/FAIL line per test case."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Records and prints a passing test case.
        super().addSuccess(test)
        print(f"PASS  {test.id().split('.')[-1]}")

    def addFailure(self, test: unittest.TestCase, err) -> None:
        # Records and prints a failing assertion.
        super().addFailure(test, err)
        print(f"FAIL  {test.id().split('.')[-1]}")

    def addError(self, test: unittest.TestCase, err) -> None:
        # Records and prints an errored test case.
        super().addError(test, err)
        print(f"FAIL  {test.id().split('.')[-1]} (error)")


def main() -> int:
    # Loads and runs the trace-compaction test module and returns a process exit code.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_trace_replacement_compaction")
    runner = unittest.TextTestRunner(resultclass=_ReportingResult, verbosity=0)
    result = runner.run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"\n{total - failed}/{total} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
