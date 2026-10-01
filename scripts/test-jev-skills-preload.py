"""FILE: scripts/test-jev-skills-preload.py

PURPOSE: Runs the focused Jev skills preload test module and reports each case plus an aggregate result.
ROLE IN CODEBASE: Provides the offline verification entry point for docs/design/jev-skills-preload.md.
ARCHITECTURE NOTE: The script runs scripted decision and generative boundaries and never contacts TypeSafe or a generative provider.
COMMON MODIFICATION PATTERNS: Keep module loading exhaustive as feature cases are added.
KNOWN EDGE CASES: Assertion failures and unexpected errors both produce a non-zero process exit.
RELATED DOCS: docs/design/jev-skills-preload.md and tests/features/jev_skills_preload/FEATURE.md.
TESTS: This script executes tests/test_jev_skill_preload.py and is itself exercised by source CI.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_skill_preload


class ReportingResult(unittest.TextTestResult):
    """Prints one stable PASS or FAIL line for every executed case."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records success before emitting the concise case line.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records an assertion failure before emitting the concise case line.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records an unexpected error before emitting the concise case line.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


def main() -> int:
    # Loads every feature case and returns a shell-friendly process status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_skill_preload)
    result = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev skills-preload tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
