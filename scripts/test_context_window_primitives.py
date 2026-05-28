"""Verification script for the context window primitives feature.

Runs all test cases from the three test modules and reports PASS/FAIL per case.
Exits with code 1 if any test fails.
"""

from __future__ import annotations

import sys
import unittest


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for module_name in (
        "tests.test_context_primitives_registry",
        "tests.test_context_primitives_binding",
        "tests.test_context_primitives_builtins",
    ):
        suite.addTests(loader.loadTestsFromName(module_name))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    passed = total - failures

    print(f"\n{'=' * 60}")
    print(f"{passed}/{total} tests passed")
    print("=" * 60)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
