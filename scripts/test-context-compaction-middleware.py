"""Run context compaction middleware verification cases with PASS/FAIL labels."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def iter_tests(suite: unittest.TestSuite):
    # Yields individual test cases from nested unittest suites.
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def run_test(test: unittest.TestCase) -> bool:
    # Runs one unittest case and prints a stable PASS or FAIL line.
    result = unittest.TestResult()
    test(result)
    name = test.id()
    if result.wasSuccessful():
        print(f"PASS {name}")
        return True
    print(f"FAIL {name}")
    for _, traceback in result.failures + result.errors:
        print(traceback)
    return False


def main() -> int:
    # Loads and runs every compaction verification test case.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for module_name in ("tests.test_context_compaction_middleware", "tests.test_context_compaction_tools"):
        suite.addTests(loader.loadTestsFromName(module_name))
    tests = list(iter_tests(suite))
    passed = sum(1 for test in tests if run_test(test))
    total = len(tests)
    print(f"{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
