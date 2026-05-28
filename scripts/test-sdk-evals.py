"""Context Protocol Header

Description:
    Executable test verification script for the sdk-evals evaluations harness.
Purpose:
    Enforces Phase 5 script verification by executing all unit, integration, and edge-case
    scenarios, printing pass/fail indicators, and returning non-zero codes on failure.
Architecture:
    - CustomTextTestResult: Intercepts test completions and formats labeled output.
    - CustomTextTestRunner: Runs the loaded test suite and handles final summary scoring.
Relations:
    Related to tests/test_evals.py (loads test cases directly from there).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from tests.test_evals import EvalTests


class CustomTextTestResult(unittest.TextTestResult):
    """Custom test result interceptor to print clear PASS/FAIL labels with test case descriptions."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Prints a clear PASS label along with the test method name.
        super().addSuccess(test)
        print(f"PASS: {test._testMethodName} - {test._testMethodDoc or 'No description.'}")

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        # Prints a clear FAIL label along with the failure details.
        super().addFailure(test, err)
        print(f"FAIL: {test._testMethodName} - {test._testMethodDoc or 'No description.'}")

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        # Prints a clear ERROR label along with the execution error details.
        super().addError(test, err)
        print(f"ERROR: {test._testMethodName} - {test._testMethodDoc or 'No description.'}")


class CustomTextTestRunner(unittest.TextTestRunner):
    """Custom test runner wrapping CustomTextTestResult execution."""

    def _makeResult(self) -> CustomTextTestResult:
        # Returns an instance of our CustomTextTestResult interceptor.
        return CustomTextTestResult(self.stream, self.descriptions, self.verbosity)


def main() -> None:
    # Loads and executes all test cases, printing final pass ratios and exiting cleanly.
    print("=" * 70)
    print("Starting SDK Evals Harness Feature Verification Script")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(EvalTests)
    
    runner = CustomTextTestRunner(stream=sys.stdout, verbosity=0)
    result = runner.run(suite)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors

    print("=" * 70)
    print(f"Verification Summary: {passed}/{total} tests passed.")
    print("=" * 70)

    if failures > 0 or errors > 0:
        print("FAIL: Verification script detected test failures or errors.")
        sys.exit(1)
    else:
        print("PASS: All verification tests completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
