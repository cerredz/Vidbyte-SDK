"""Context Protocol Header

Description:
    Executable test verification script for the Competitor Growth Analyzer Harness.
Purpose:
    Runs all tests from the Testing Plan, prints clear PASS/FAIL labels, and exits with a non-zero code on failures.
Architecture:
    - CustomTextTestResult: Subclass formatting test results exactly as required by the design workflow.
    - CustomTextTestRunner: Runner using CustomTextTestResult.
Relation to codebase as a whole:
    Belongs under scripts/ and acts as the final gatekeeper verification for this feature before merge.
Similar files:
    - tests/test_competitor_growth_harness.py: The actual test case definitions.
"""

from __future__ import annotations

import sys
import unittest

# Import the tests we want to execute
from tests.test_competitor_growth_harness import CompetitorGrowthHarnessTests


class CustomTextTestResult(unittest.TextTestResult):
    """Formats test results with clear PASS/FAIL labels and counts successful runs."""

    def __init__(self, *args, **kwargs) -> None:
        # Initialize parent result and counts.
        super().__init__(*args, **kwargs)
        self.passed_count = 0
        self.failed_count = 0

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Prints PASS when a test case passes.
        super().addSuccess(test)
        self.passed_count += 1
        print(f"PASS: {test.id().split('.')[-1]}")

    def addFailure(self, test: unittest.TestCase, err: tuple) -> None:
        # Prints FAIL when a test case fails.
        super().addFailure(test, err)
        self.failed_count += 1
        print(f"FAIL: {test.id().split('.')[-1]} - {err[1]}")

    def addError(self, test: unittest.TestCase, err: tuple) -> None:
        # Prints FAIL when a test case raises an error.
        super().addError(test, err)
        self.failed_count += 1
        print(f"FAIL (ERROR): {test.id().split('.')[-1]} - {err[1]}")


class CustomTextTestRunner(unittest.TextTestRunner):
    """Executes the test suite using CustomTextTestResult formatting."""

    def _makeResult(self) -> CustomTextTestResult:
        # Returns an instance of CustomTextTestResult.
        return CustomTextTestResult(self.stream, self.descriptions, self.verbosity)


def main() -> None:
    # Runs the competitor growth harness tests and exits with non-zero code if any fail.
    print("Running Competitor Growth Analyzer Harness Test Suite...\n")
    suite = unittest.TestLoader().loadTestsFromTestCase(CompetitorGrowthHarnessTests)
    runner = CustomTextTestRunner(verbosity=0)
    result = runner.run(suite)

    total_tests = result.passed_count + result.failed_count
    print(f"\nSummary: {result.passed_count}/{total_tests} tests passed.")

    if result.failed_count > 0:
        print("\nVerification FAILED.")
        sys.exit(1)
    else:
        print("\nVerification PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
