"""Run every Jev agent scaffold test with explicit per-case output."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_agent


class ReportingResult(unittest.TextTestResult):
    """Prints a stable PASS or FAIL line for every executed test."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records success through unittest before emitting the concise case line.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records assertion failures and emits a concise failure line.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records unexpected errors and emits a concise failure line.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


def main() -> int:
    # Loads the focused module, runs every case, and returns a shell-friendly status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_agent)
    runner = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev scaffold tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
