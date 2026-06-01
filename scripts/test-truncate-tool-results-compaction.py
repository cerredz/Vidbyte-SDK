"""Context Protocol Header

Description:
    Verification script for the truncate_tool_results context compaction strategy.
Purpose:
    Instantiates and programmatically runs the updated ContextCompactionToolTests suite
    to verify all smart truncation behaviors (edge cases, failures, boundaries, and placeholders).
Architecture:
    - Runs the unittest runner on the ContextCompactionToolTests suite.
    - Captures result details, prints clear summaries, and returns non-zero codes on failure.
Functions:
    - run_verification_suite: Programmatically executes all test cases and reports PASS/FAIL status.
Relations:
    Directly runs test cases defined in tests.test_context_compaction_tools.
"""

from __future__ import annotations

import sys
import unittest

from tests.test_context_compaction_tools import ContextCompactionToolTests


def run_verification_suite() -> None:
    # Programmatically execute all compaction test cases and report PASS/FAIL.
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(ContextCompactionToolTests))

    print("====================================================")
    print("Running Smart Truncation Compaction Verification Suite")
    print("====================================================\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n====================================================")
    print("Summary:")
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    print(f"{passed}/{total} tests passed")
    print("====================================================")

    if not result.wasSuccessful():
        print("\nVerification FAILED.")
        sys.exit(1)
    else:
        print("\nVerification PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    run_verification_suite()
