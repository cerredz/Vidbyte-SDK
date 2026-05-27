# Context Protocol Header
# Description: Automated integration verification script for OpenRouter integration.
# Purpose: Simulates end-to-end model execution and payload generation using FakeTransport to satisfy Phase 5 requirements.
# Architecture: Direct execution script wrapping unittest suite and output formatting.
# Key Functions:
#   - run_integration_verification: Main orchestrator invoking unit tests and printing formatted summaries.
# Codebase Relation: Phase 5 executable verification script.
# Similar Files: tests/test_openrouter_provider.py

from __future__ import annotations

import sys
import unittest

from tests.test_openrouter_provider import TestOpenRouterProvider


def run_integration_verification() -> int:
    # Run the OpenRouter provider integration tests and format output for user review.
    print("=" * 60)
    print("RUNNING OPENROUTER INTEGRATION VERIFICATION")
    print("=" * 60)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestOpenRouterProvider)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed

    for failure in result.failures:
        print(f"[FAIL] {failure[0]} - Details: {failure[1]}")
    for error in result.errors:
        print(f"[ERROR] {error[0]} - Details: {error[1]}")

    print(f"\nResult: {passed}/{total} tests passed.")
    print("=" * 60)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_integration_verification())
