"""Standalone verification script for filesystem tool migration.

Run with: python scripts/test-filesystem-tool-migration.py

Loads the test suite from tests/test_filesystem_tools.py and runs it with
a verbose text runner. Prints PASS/FAIL per test case and exits non-zero
if any test fails.
"""

from __future__ import annotations

import os
import sys
import unittest

# Ensure the repo root is on sys.path so 'tests' is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Load test suite
# ---------------------------------------------------------------------------

loader = unittest.TestLoader()
suite = loader.loadTestsFromName("tests.test_filesystem_tools")

# ---------------------------------------------------------------------------
# Run with verbose output
# ---------------------------------------------------------------------------

runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
result = runner.run(suite)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

total = result.testsRun
passed = total - len(result.failures) - len(result.errors)
print(f"\n{'='*60}")
print(f"{total} tests run — {passed} passed, {len(result.failures)} failed, {len(result.errors)} errors")
print(f"{'='*60}\n")

sys.exit(0 if result.wasSuccessful() else 1)
