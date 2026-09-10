"""FILE: scripts/test-sources-access-layer.py

PURPOSE:
    Standalone Phase-5 verification script for
    docs/design/sources-access-layer.md. Runs every test case in that design
    doc's Testing Plan, printing one PASS/FAIL line per test and a final
    summary line, exiting non-zero on any failure, per the design-doc skill's
    Phase 5 requirement for an executable script separate from the pytest
    suite.

ROLE IN CODEBASE:
    Loads and runs tests/test_sources_access_layer.py's test classes, which
    exercise vidbyte/integrations/, vidbyte/lib/dataclasses/integrations.py,
    and ResourceScopePolicy in vidbyte/lib/dataclasses/security.py. Not
    imported by any production code.

ARCHITECTURE NOTE:
    Loads the test module with unittest's TestLoader rather than duplicating
    its assertions, so this script and the pytest suite can never drift out of
    sync. Every test runs offline against a FakeAdapter test double, because
    no concrete provider ships with the access layer.

FUNCTION INVENTORY:
    run_and_report() -> int: runs the full suite, prints per-test results,
    returns the process exit code.
    _report_results(result, total) -> int: prints PASS/FAIL per test id plus
    the final "X/Y tests passed" summary line.
    _all_run_tests() -> list: reconstructs the full ordered test list for
    reporting, since TestResult does not expose successes directly.

COMMON MODIFICATION PATTERNS:
    When a new test class is added to tests/test_sources_access_layer.py, add
    it to TEST_CLASSES here in the same change so this script keeps covering
    every test case in the design doc's Testing Plan.

WHAT NOT TO DO IN THIS FILE:
    1. Do not write new assertions here; every assertion belongs in
       tests/test_sources_access_layer.py, and this script only runs and
       reports on them.
    2. Do not import this script from production code; it is a Phase-5
       verification tool only.

KNOWN EDGE CASES:
    The concurrency test asserts a wall-clock bound, so a heavily loaded
    machine can make it the one flaky case; rerun before investigating it.

RELATED DOCS:
    docs/design/sources-access-layer.md

TESTS:
    This script is itself a test runner; run it directly with
    `python scripts/test-sources-access-layer.py`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.test_sources_access_layer import (  # noqa: E402
    ConnectionBrokerTests,
    ContextAdmissionBudgetTests,
    ProviderToolsetTests,
    ResourceScopePolicyTests,
    SourcesConstructionTests,
    SourcesIntegrationTests,
    SourcesReportTests,
    SourcesResolverTests,
    ToolBudgetTests,
)

TEST_CLASSES = (
    SourcesConstructionTests,
    ContextAdmissionBudgetTests,
    ToolBudgetTests,
    ConnectionBrokerTests,
    ResourceScopePolicyTests,
    ProviderToolsetTests,
    SourcesResolverTests,
    SourcesReportTests,
    SourcesIntegrationTests,
)


def run_and_report() -> int:
    """Run every test case, print PASS/FAIL per test and a final summary, return the exit code."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(cls) for cls in TEST_CLASSES)
    total = suite.countTestCases()
    result = unittest.TestResult()
    suite.run(result)
    return _report_results(result, total)


def _report_results(result: unittest.TestResult, total: int) -> int:
    # Prints one PASS/FAIL line per test case, in the order the runner executed them.
    failed_ids = {test.id() for test, _ in (result.failures + result.errors)}
    for test in _all_run_tests():
        label = "FAIL" if test.id() in failed_ids else "PASS"
        print(f"{label} - {test.id()}")
    for test, traceback in result.failures + result.errors:
        print(f"\n--- {test.id()} ---\n{traceback}")
    passed = total - len(failed_ids)
    print(f"\n{passed}/{total} tests passed.")
    return 0 if not failed_ids else 1


def _all_run_tests() -> list:
    # TestResult does not expose successes directly; reconstruct the full run order
    # from every test the loader queued, in declaration order.
    seen = []
    for cls in TEST_CLASSES:
        for test in unittest.TestLoader().loadTestsFromTestCase(cls):
            seen.append(test)
    return seen


if __name__ == "__main__":
    sys.exit(run_and_report())
