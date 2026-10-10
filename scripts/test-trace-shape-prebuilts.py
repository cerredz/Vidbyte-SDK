"""Context Protocol Header

Description:
    Standalone verification script for the OTel GenAI and OpenInference trace
    shape prebuilts.
Purpose:
    Runs every test case from docs/design/otel-genai-and-openinference-trace-shapes.md
    Section 10 and prints PASS/FAIL per case with a final summary, exiting
    non-zero on any failure.
Architecture:
    - Loads tests.test_otel_tracer_transport, tests.test_otel_genai_trace_shape,
      and tests.test_openinference_trace_shape via unittest's TestLoader, then
      runs them with a result class that prints one PASS/FAIL line per test.
Relations:
    Mirrors the three test modules under tests/ against the public vidbyte surface.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MODULES = (
    "tests.test_otel_tracer_transport",
    "tests.test_otel_genai_trace_shape",
    "tests.test_openinference_trace_shape",
)


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
