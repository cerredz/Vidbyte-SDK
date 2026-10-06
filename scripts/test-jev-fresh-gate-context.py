"""FILE: scripts/test-jev-fresh-gate-context.py

PURPOSE: Runs focused offline verification for the fresh-continuation gate assessment.
ROLE IN CODEBASE: Exercises the registered gate guidance, failed-question records, and fresh prompt rendering.
ARCHITECTURE NOTE: Reuses deterministic unit-test cases so verification never calls an external model.
COMMON MODIFICATION PATTERNS: Add every gate-assessment behavior case to the source test classes and this runner.
KNOWN EDGE CASES: Runs from the repository root; the SDK source checkout must be importable on PYTHONPATH.
RELATED DOCS: docs/design/jev-fresh-gate-context.md and skills/jev-continuation/SKILL.md.
TESTS: python scripts/test-jev-fresh-gate-context.py.
"""

from __future__ import annotations

import sys
import unittest

from tests.test_jev_done import JevDoneQuestionTests
from tests.test_jev_fresh_continuation import JevFreshContinuationTests


class LabeledTestResult(unittest.TextTestResult):
    """Print an explicit label beside each design-plan verification case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Makes successful cases individually visible in script output.
        super().addSuccess(test)
        self.stream.writeln(f"PASS: {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Marks a failed assertion before unittest prints its traceback.
        self.stream.writeln(f"FAIL: {test.id()}")
        super().addFailure(test, err)

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Marks an unexpected exception before unittest prints its traceback.
        self.stream.writeln(f"FAIL: {test.id()}")
        super().addError(test, err)


def main() -> int:
    # Runs the registry and fresh-continuation cases without calling an external model.
    """Run the design-plan cases and report a clear result for each test."""
    suite = unittest.TestSuite()
    for test_case in (JevDoneQuestionTests, JevFreshContinuationTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_case))
    runner = unittest.TextTestRunner(verbosity=0, resultclass=LabeledTestResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
