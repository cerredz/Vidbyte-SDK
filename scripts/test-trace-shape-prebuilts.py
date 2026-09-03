"""FILE: scripts/test-trace-shape-prebuilts.py

PURPOSE: Runs the standalone verification suite for the direct OTel GenAI and OpenInference trace shapes.
ROLE IN CODEBASE: Gives contributors an executable check that mirrors the design document's required shape cases.
ARCHITECTURE NOTE: Loads the two provider unit/integration test modules through unittest and never starts an exporter.
COMMON MODIFICATION PATTERNS: Keep the loaded module list aligned with the provider shape tests and update the design document when coverage changes.
KNOWN EDGE CASES: The script adjusts sys.path for direct execution and exits non-zero when any test fails.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: Loads tests/test_otel_genai_trace_shape.py and tests/test_openinference_trace_shape.py.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MODULES = ("tests.test_otel_genai_trace_shape", "tests.test_openinference_trace_shape")


class _PrintingResult(unittest.TextTestResult):
    """TestResult subclass that prints one PASS/FAIL line per test as it runs."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        # Prints PASS immediately after a successful test.
        super().addSuccess(test)
        print(f"PASS: {test.id()}")

    def addFailure(self, test: unittest.TestCase, err: object) -> None:
        # Prints FAIL immediately after a failed assertion.
        super().addFailure(test, err)
        print(f"FAIL: {test.id()}")

    def addError(self, test: unittest.TestCase, err: object) -> None:
        # Prints FAIL immediately after an unexpected error.
        super().addError(test, err)
        print(f"FAIL: {test.id()} (error)")


def main() -> int:
    # Loads and runs every test case in the three trace-shape test modules, printing a final summary.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for module_name in _MODULES:
        suite.addTests(loader.loadTestsFromName(module_name))
    runner = unittest.TextTestRunner(resultclass=_PrintingResult, verbosity=0, stream=sys.stdout)
    result = runner.run(suite)
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{passed}/{total} tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
