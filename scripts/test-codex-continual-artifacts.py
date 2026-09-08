"""Run every Codex live-observation design case with named PASS/FAIL output.
COMMON MODIFICATION PATTERNS: Extend the native event contract with a matching acceptance case.
RELATED DOCS: docs/design/codex-continual-artifacts.md
PURPOSE: Execute every observation acceptance case with named outcomes.
ROLE IN CODEBASE: Local feature verification entry point.
ARCHITECTURE NOTE: Loads actual tests without duplicating assertions.
KNOWN EDGE CASES: Missing optional Codex dependency prevents verification.
TESTS: tests/codex_continual/test_continual.py
"""

import importlib.util
import unittest
from pathlib import Path


class VerificationResult(unittest.TextTestResult):
    """Render an explicit outcome for every independently executable case."""

    def addSuccess(self, test):
        # Print the case identity after its assertions completed.
        super().addSuccess(test)
        print(f"PASS {test.id()}")

    def addFailure(self, test, err):
        # Preserve the traceback and render the failing case name.
        super().addFailure(test, err)
        print(f"FAIL {test.id()}")

    def addError(self, test, err):
        # Treat unexpected exceptions as failed verification cases.
        super().addError(test, err)
        print(f"FAIL {test.id()}")


class Verification:
    """Load the actual acceptance pack instead of duplicating test assertions."""

    @staticmethod
    def run():
        # Execute the complete feature pack and fail on any skipped or failed case.
        path = Path(__file__).resolve().parents[1] / "tests/codex_continual/test_continual.py"
        spec = importlib.util.spec_from_file_location("codex_continual_tests", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(resultclass=VerificationResult).run(suite)
        passed = result.testsRun - len(result.errors) - len(result.failures) - len(result.skipped)
        print(f"{passed}/{result.testsRun} tests passed")
        return 0 if passed == result.testsRun and passed else 1


if __name__ == "__main__":
    raise SystemExit(Verification.run())
