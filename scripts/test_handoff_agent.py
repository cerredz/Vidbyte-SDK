"""Context Protocol Header

Description:
    Standalone verification script for the handoff agent feature.
Purpose:
    Runs every handoff test case from tests/test_handoff_agent.py individually, prints a
    PASS/FAIL label per case, prints an X/Y summary, and exits non-zero on any failure.
Architecture:
    - HandoffVerification: Loads the handoff test module, runs each test, and reports results.
Relations:
    Exercises vidbyte.context.handoffs, vidbyte.agents.handoff, and the BaseAgent handoff
    integration. Mirrors the Testing Plan in docs/design/handoff-agent.md.
Similar Files:
    - tests/test_handoff_agent.py: The unittest suite this script drives case by case.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HandoffVerification:
    """Runs the handoff test suite case by case and reports a PASS/FAIL summary."""

    def __init__(self) -> None:
        # Load every test case from the handoff unittest module.
        loader = unittest.TestLoader()
        self.cases = list(self._flatten(loader.loadTestsFromName("tests.test_handoff_agent")))

    def run(self) -> int:
        # Execute each case, print its result, and return a process exit code.
        passed = 0
        for case in self.cases:
            if self._run_one(case):
                passed += 1
        total = len(self.cases)
        print(f"\n{passed}/{total} tests passed")
        return 0 if passed == total else 1

    def _run_one(self, case: unittest.TestCase) -> bool:
        # Run a single test case and print a PASS/FAIL line with its name and any error.
        result = unittest.TestResult()
        case.run(result)
        name = case.id().split("test_handoff_agent.")[-1]
        if result.wasSuccessful():
            print(f"PASS  {name}")
            return True
        problem = (result.failures + result.errors)[0][1].strip().splitlines()[-1]
        print(f"FAIL  {name}  -> {problem}")
        return False

    def _flatten(self, suite: unittest.TestSuite):
        # Yield individual TestCase instances from an arbitrarily nested suite.
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from self._flatten(item)
            else:
                yield item


if __name__ == "__main__":
    sys.exit(HandoffVerification().run())
