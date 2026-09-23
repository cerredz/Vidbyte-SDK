"""FILE: scripts/test-jev-agent-scaffold.py

PURPOSE: Runs every focused Jev agent scaffold test and reports each case plus an aggregate result.
ROLE IN CODEBASE: Provides the executable verification entry point required by docs/design/jev-agent-scaffold.md.
ARCHITECTURE NOTE: The script loads the unittest module directly and never supplies credentials or contacts a live provider.
COMMON MODIFICATION PATTERNS: Keep module loading exhaustive as new cases are added; customize reporting without filtering tests.
KNOWN EDGE CASES: Assertion failures and unexpected errors both produce a non-zero process exit; skipped tests do not count as passes.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: This script executes tests/test_jev_agent.py and tests/test_jev_documentation.py and is itself exercised by the source CI script stage.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_agent, test_jev_documentation


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
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite((loader.loadTestsFromModule(test_jev_agent), loader.loadTestsFromModule(test_jev_documentation)))
    runner = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev scaffold tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
