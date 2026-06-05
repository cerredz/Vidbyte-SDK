"""Context Protocol Header

Description:
    Standalone verification script for the create-handoff-tool feature.
Purpose:
    Runs every test case from tests/test_create_handoff_tool.py individually, prints a
    PASS/FAIL label per case, prints an X/Y summary, and exits non-zero on any failure.
Architecture:
    - CreateHandoffVerification: Loads the test module, runs each case, and reports results.
Relations:
    Exercises vidbyte.tools.builtins.handoff.CreateHandoffTool and the BaseAgent handoff
    recording integration. Mirrors the Testing Plan in docs/design/create-handoff-tool.md.
Similar Files:
    - scripts/test_handoff_agent.py: The runner pattern this script follows.
    - tests/test_create_handoff_tool.py: The unittest suite this script drives case by case.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CreateHandoffVerification:
    """Runs the create-handoff test suite case by case and reports a PASS/FAIL summary."""

    def __init__(self) -> None:
        # Load every test case from the create-handoff unittest module.
        loader = unittest.TestLoader()
        self.cases = list(self._flatten(loader.loadTestsFromName("tests.test_create_handoff_tool")))

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
        name = case.id().split("test_create_handoff_tool.")[-1]
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
    sys.exit(CreateHandoffVerification().run())
