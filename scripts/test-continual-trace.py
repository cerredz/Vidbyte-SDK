"""Run the continual trace feature verification suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


class PassFailResult(unittest.TextTestResult):
    """Unittest result that prints one PASS or FAIL line per test case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records and prints a passing test case.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: object) -> None:
        # Records and prints a failing assertion.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: object) -> None:
        # Records and prints an unexpected test error.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


class PassFailRunner(unittest.TextTestRunner):
    """Unittest runner using the PASS/FAIL result format."""

    resultclass = PassFailResult


def main() -> int:
    # Discovers and runs every continual trace test from the approved design plan.
    sys.dont_write_bytecode = True
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_continual_trace")
    result = PassFailRunner(stream=sys.stdout, verbosity=0).run(suite)
    failed = len(result.failures) + len(result.errors)
    passed = result.testsRun - failed
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
