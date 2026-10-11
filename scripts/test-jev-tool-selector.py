"""FILE: scripts/test-jev-tool-selector.py

PURPOSE: Runs all focused Jev tool-selector tests and reports each case plus an aggregate result.
ROLE IN CODEBASE: Provides the offline verification entry point for docs/design/jev-tool-selector.md.
ARCHITECTURE NOTE: The script loads the unittest module directly and never contacts TypeSafe or a generative provider.
COMMON MODIFICATION PATTERNS: Keep module loading exhaustive as selector cases are added.
KNOWN EDGE CASES: Assertion failures and unexpected errors both produce a non-zero process exit.
RELATED DOCS: docs/design/jev-tool-selector.md and skills/jev-agent/SKILL.md.
TESTS: This script executes tests/test_jev_tool_selector.py and is itself exercised by source CI.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_tool_selector


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
    # Loads every selector case and returns a shell-friendly status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_tool_selector)
    result = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev tool-selector tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
