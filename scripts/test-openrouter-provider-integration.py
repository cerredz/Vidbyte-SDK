"""Context Protocol Header

Description:
    Phase 5 verification script for OpenRouter provider comments resolution.
Purpose:
    Instantiates and runs all unit and integration test cases defined in the design doc for resolving PR #60 comments,
    printing clear PASS/FAIL labels and exiting non-zero on any failure.
Architecture:
    - Runs unittest runner programmatically against OpenRouterProviderTests and ModelRegistryTests.
Relations:
    Validates the entire centralized registry, modality fallback, and OpenRouter adapter suite.
Similar Files:
    - scripts/test-resolve-pr-68-comments.py
"""

from __future__ import annotations

import sys
import unittest

from tests.test_model_registry import ModelRegistryTests
from tests.test_openrouter_provider import OpenRouterProviderTests


def run_verification_suite() -> None:
    # Programmatically execute all registry and OpenRouter provider tests and report PASS/FAIL.
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(ModelRegistryTests))
    suite.addTest(loader.loadTestsFromTestCase(OpenRouterProviderTests))

    print("====================================================")
    print("Running OpenRouter & Model Registry Verification Suite")
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
