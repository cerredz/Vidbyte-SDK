from __future__ import annotations

import sys
import unittest
from pathlib import Path


def add_repo_root_to_path() -> None:
    # Ensures the local vidbyte package and tests package are importable when run from scripts/.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))


class PassFailResult(unittest.TextTestResult):
    """Unittest result that prints one PASS or FAIL line per executed case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records a passing test and prints the design-doc script label.
        super().addSuccess(test)
        print(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: object) -> None:
        # Records an assertion failure and prints the design-doc script label.
        super().addFailure(test, err)
        print(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: object) -> None:
        # Records an unexpected error and prints the design-doc script label.
        super().addError(test, err)
        print(f"FAIL {test.id()}")

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        # Records a skipped test and prints it as FAIL because this script requires full coverage.
        super().addSkip(test, reason)
        print(f"FAIL {test.id()} skipped: {reason}")


class PassFailRunner(unittest.TextTestRunner):
    """Unittest runner that uses PassFailResult and emits a compact summary."""

    resultclass = PassFailResult


def main() -> int:
    # Runs deterministic compaction middleware tests and returns a process exit code.
    add_repo_root_to_path()
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_deterministic_compaction_middleware")
    result = PassFailRunner(verbosity=0).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors) + len(result.skipped)
    print(f"{total - failed}/{total} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
