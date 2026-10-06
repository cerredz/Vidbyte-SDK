"""FILE: scripts/test-session-failure-vocabulary.py

PURPOSE: Runs the focused Session failure vocabulary verification matrix.
ROLE IN CODEBASE: Provides a deterministic, labelled command for local and CI checks.
ARCHITECTURE NOTE: Loads unittest cases without adding a second test framework.
COMMON MODIFICATION PATTERNS: Add a labelled test expectation when the failure contract changes.
KNOWN EDGE CASES: Reports every failed or errored case while preserving unittest diagnostics.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/README.md.
TESTS: python scripts/test-session-failure-vocabulary.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


class LabeledResult(unittest.TestResult):
    """Print one PASS/FAIL line for every discovered verification test."""

    def __init__(self) -> None:
        # Track completed tests so the final summary includes errors and failures.
        super().__init__()
        self.failed_tests: set[str] = set()

    def startTest(self, test: unittest.case.TestCase) -> None:
        # Let unittest track the test while retaining its readable id.
        super().startTest(test)

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Print a positive result as soon as one test completes.
        super().addSuccess(test)
        print(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err) -> None:
        # Print assertion failures with the test name and defer the traceback to unittest.
        super().addFailure(test, err)
        self.failed_tests.add(test.id())
        print(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err) -> None:
        # Print unexpected errors using the same machine-scannable label.
        super().addError(test, err)
        self.failed_tests.add(test.id())
        print(f"FAIL {test.id()}")


def load_suite() -> unittest.TestSuite:
    """Load every test in the Session failure verification module."""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import tests.test_session_failures as module

    return unittest.defaultTestLoader.loadTestsFromModule(module)


def main() -> int:
    """Run the complete failure verification suite and return a shell exit code."""
    suite = load_suite()
    result = LabeledResult()
    suite.run(result)
    passed = result.testsRun - len(result.failed_tests)
    print(f"{passed}/{result.testsRun} tests passed")
    if result.failures or result.errors:
        unittest.TextTestRunner(verbosity=2).run(suite)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
