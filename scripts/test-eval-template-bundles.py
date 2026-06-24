"""Executable verification script for eval template bundle behavior."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_evals import EvalTests


class TemplateBundleTestResult(unittest.TextTestResult):
    """Test result that prints explicit PASS, FAIL, and ERROR labels."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Prints a PASS label for each successful test.
        super().addSuccess(test)
        print(f"PASS: {test._testMethodName}")

    def addFailure(self, test: unittest.TestCase, err: object) -> None:
        # Prints a FAIL label for each assertion failure.
        super().addFailure(test, err)
        print(f"FAIL: {test._testMethodName}")

    def addError(self, test: unittest.TestCase, err: object) -> None:
        # Prints an ERROR label for each unexpected exception.
        super().addError(test, err)
        print(f"ERROR: {test._testMethodName}")


class TemplateBundleTestRunner(unittest.TextTestRunner):
    """Test runner that installs the template bundle result class."""

    def _makeResult(self) -> TemplateBundleTestResult:
        # Creates the custom result object used for labeled output.
        return TemplateBundleTestResult(self.stream, self.descriptions, self.verbosity)


def main() -> None:
    # Runs the eval test suite and exits non-zero on any failure.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(EvalTests)
    runner = TemplateBundleTestRunner(stream=sys.stdout, verbosity=0)
    result = runner.run(suite)

    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"{passed}/{total} tests passed")
    if failed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

