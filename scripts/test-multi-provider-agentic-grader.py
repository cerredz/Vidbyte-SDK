"""Context Protocol Header

Description:
    Verification script for Multi-Provider Agentic Grader algorithm.
Purpose:
    Instantiates and runs all unit and integration test cases defined in the design doc,
    printing clear PASS/FAIL labels and exiting non-zero on any failure.
Architecture:
    - Runs unittest runner against MultiProviderAgenticGraderTests.
Relations:
    Validates the entire Multi-Provider Agentic Grader codebase feature.
"""

from __future__ import annotations

import sys
import unittest

from tests.test_multi_provider_agentic_grader import MultiProviderAgenticGraderTests


def run_verification_suite() -> None:
    # Programmatically execute all Grader test cases and report PASS/FAIL.
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(MultiProviderAgenticGraderTests))

    print("====================================================")
    print("Running Multi-Provider Agentic Grader Verifications")
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
