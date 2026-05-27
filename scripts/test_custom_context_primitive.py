"""Verification script for the custom-context-primitive feature.

Runs all 36 test cases from test_context_primitives_define and reports
PASS/FAIL per case. Exits with code 1 if any test fails.
"""

from __future__ import annotations

import sys
import unittest


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_context_primitives_define")
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
