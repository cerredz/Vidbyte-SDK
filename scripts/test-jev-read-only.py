"""FILE: scripts/test-jev-read-only.py

PURPOSE: Runs the focused offline Jev read-only intent feature test pack and prints PASS or FAIL for each case.
ROLE IN CODEBASE: Provides the executable verification entrypoint documented by tests/features/jev_read_only/README.md.
ARCHITECTURE NOTE: The script loads the full feature test module, prints one PASS or FAIL line per test and an X/Y summary, and returns a nonzero status when any test fails.
COMMON MODIFICATION PATTERNS: Add tests to the single loaded module so this entrypoint remains exhaustive.
KNOWN EDGE CASES: The repository root is inserted for direct script execution from any current directory. The token-length test is skipped, and reported as SKIP, when tiktoken is not installed.
RELATED DOCS: `docs/design/jev-read-only-intent.md` and `tests/features/jev_read_only/FEATURE.md`.
TESTS: `python scripts/test-jev-read-only.py`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.features.jev_read_only import test_jev_read_only


class LabeledResult(unittest.TextTestResult):
    """Prints one PASS, FAIL, or SKIP line per test so the run reads as a checklist."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Records a pass and prints its label.
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.TestCase, err: object) -> None:
        # Records a failed assertion and prints its label.
        super().addFailure(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.TestCase, err: object) -> None:
        # Records an unexpected exception as a failure and prints its label.
        super().addError(test, err)
        self.stream.writeln(f"FAIL {test.id()}")

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        # Records a skipped test and prints why it did not run.
        super().addSkip(test, reason)
        self.stream.writeln(f"SKIP {test.id()} ({reason})")


def main() -> int:
    # Runs every feature test, prints the X/Y summary, and turns the result into the script exit status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_read_only)
    result = unittest.TextTestRunner(resultclass=LabeledResult, verbosity=0).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed - len(result.skipped)}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
