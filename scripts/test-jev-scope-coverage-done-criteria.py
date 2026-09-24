"""FILE: scripts/test-jev-scope-coverage-done-criteria.py

PURPOSE: Runs the Jev done-criteria tests (multipart and scope coverage) with per-case reporting.
ROLE IN CODEBASE: Provides the design-doc feature gate without requiring live generative or TypeSafe credentials.
ARCHITECTURE NOTE: The script delegates behavior assertions to production-path tests using scripted model boundaries.
COMMON MODIFICATION PATTERNS: Add every new design-plan case to tests/test_jev_agent.py; this loader runs the module fully.
KNOWN EDGE CASES: Skipped tests are excluded from the pass count and any failure exits with status 1.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md and skills/jev-agent/SKILL.md.
TESTS: This script runs tests/test_jev_agent.py, including JevScopeCoverageDoneCriteriaTests and JevScopeCoverageContractTests.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_agent


class ReportingResult(unittest.TextTestResult):
    """Prints a stable PASS or FAIL line for every executed case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records the successful case and prints its stable test identity.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records an assertion failure and prints its stable test identity.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records an unexpected error and prints its stable test identity.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


def main() -> int:
    # Loads every Jev test case and returns a shell-friendly status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_agent)
    runner = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
