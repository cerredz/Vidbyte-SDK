"""FILE: scripts/test-working-principles-preset.py

PURPOSE: Runs the offline system-prompt preset feature pack and prints PASS or FAIL for every test plus an "X/Y tests passed" summary.
ROLE IN CODEBASE: The executable verification entrypoint documented by tests/features/system_prompt_presets/README.md and the working-principles-preset design doc.
ARCHITECTURE NOTE: The pack's tests are unittest classes, so this script loads both modules directly; their OfflineAgentTest base replaces every model with a recording fake and refuses real network sends, so the script never spends money.
COMMON MODIFICATION PATTERNS: A new test module in the pack is added to MODULES so this entrypoint stays exhaustive.
KNOWN EDGE CASES: The repository root is inserted first on sys.path so the worktree's vidbyte package wins over an editable install that points at another checkout.
RELATED DOCS: docs/design/working-principles-preset.md and tests/features/system_prompt_presets/FEATURE.md.
TESTS: python scripts/test-working-principles-preset.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.features.system_prompt_presets import test_system_prompt_presets_propagation, test_system_prompt_presets_units

MODULES = (test_system_prompt_presets_units, test_system_prompt_presets_propagation)


class LabeledResult(unittest.TextTestResult):
    """Test result that prints one PASS or FAIL line per test."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        """Record a passing test and print its PASS line."""
        super().addSuccess(test)
        self.stream.writeln(f"PASS {test.id()}")

    def addFailure(self, test: unittest.TestCase, err: object) -> None:
        """Record a failing assertion and print its FAIL line."""
        super().addFailure(test, err)  # type: ignore[arg-type]
        self.stream.writeln(f"FAIL {test.id()}")

    def addError(self, test: unittest.TestCase, err: object) -> None:
        """Record a test that raised and print its FAIL line."""
        super().addError(test, err)  # type: ignore[arg-type]
        self.stream.writeln(f"FAIL {test.id()} (error)")


def main() -> int:
    """Run every feature test, print the summary line, and return a nonzero status on any failure."""
    # Load both modules of the pack, run them with per-test labels, and count the passes.
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in MODULES)
    result = unittest.TextTestRunner(verbosity=0, resultclass=LabeledResult).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
