"""FILE: scripts/test-jev-run-state-relation.py

PURPOSE: Runs the focused offline Jev run-state relation test suite and reports each case.
ROLE IN CODEBASE: Provides the executable verification entrypoint required by docs/design/jev-run-state-relation.md.
ARCHITECTURE NOTE: The script loads every test in tests/test_jev_run_state_relation.py and exits non-zero on any failure.
COMMON MODIFICATION PATTERNS: Keep the module loader exhaustive as focused relation cases are added.
KNOWN EDGE CASES: The repository root is inserted for direct execution from any current working directory.
RELATED DOCS: docs/design/jev-run-state-relation.md and skills/jev-agent/SKILL.md.
TESTS: This script executes tests/test_jev_run_state_relation.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_run_state_relation


class ReportingResult(unittest.TextTestResult):
    """Prints a stable PASS or FAIL line for every executed test."""

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Records the passing test before printing its per-case status.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records assertion failures before printing their per-case status.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        # Records unexpected errors before printing their per-case status.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")


def main() -> int:
    # Loads every focused test and returns a shell-friendly status.
    """Run every relation test and report its aggregate result."""
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_run_state_relation)
    result = unittest.TextTestRunner(verbosity=0, resultclass=ReportingResult).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} Jev run-state relation tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
