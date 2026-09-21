"""FILE: scripts/test_jev_decide_tool.py

PURPOSE: Runs every jev-decide-tool test case from docs/design/jev-decide-tool.md section 10 and prints PASS or FAIL per case.
ROLE IN CODEBASE: The design-doc verification script for the TypeSafe Jev bolt-on tool; the same cases also run in the pytest source stage.
ARCHITECTURE NOTE: Loads tests/test_jev_decide_tool.py and executes each case individually against the checkout this script lives in, never an installed package.
COMMON MODIFICATION PATTERNS: Add new cases to the test module; this runner discovers them automatically.
KNOWN EDGE CASES: Exits non-zero when any case fails or errors, or when no case was discovered.
RELATED DOCS: docs/design/jev-decide-tool.md.
TESTS: python scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class JevDecideVerification:
    """Discovers the Jev test cases, runs each one, and reports a PASS/FAIL line per case."""

    def run(self) -> int:
        # Runs every discovered case and returns the process exit code.
        cases = self._discover_cases()
        passed = sum(self._run_case(case) for case in cases)
        print(f"{passed}/{len(cases)} tests passed")
        return 0 if cases and passed == len(cases) else 1

    def _discover_cases(self) -> list[unittest.TestCase]:
        # Loads tests/test_jev_decide_tool.py and flattens its suite into individual cases.
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_jev_decide_tool")
        return list(self._flatten(suite))

    def _flatten(self, suite: unittest.TestSuite):
        # Yields leaf test cases from a nested suite.
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from self._flatten(item)
            else:
                yield item

    def _run_case(self, case: unittest.TestCase) -> bool:
        # Runs one case and prints its PASS/FAIL label with the category docstring.
        result = unittest.TestResult()
        case.run(result)
        ok = result.wasSuccessful()
        label = case.shortDescription() or ""
        print(f"{'PASS' if ok else 'FAIL'} {case.id().split('.', 2)[-1]} {label}")
        for _, trace in result.failures + result.errors:
            print(trace)
        return ok


if __name__ == "__main__":
    raise SystemExit(JevDecideVerification().run())
