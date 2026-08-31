"""Context Protocol Header

Description:
    Standalone Phase-5 verification script for docs/design/agent-speed-tracking.md.
Purpose:
    Runs every test case in that design doc's Testing Plan (tests/test_agent_speed.py
    and the AgentSpeedTrackingRuntimeTests class in tests/test_agent_runtime.py),
    printing one PASS/FAIL line per test and a final summary line, exiting non-zero
    on any failure.
Architecture:
    - Loads the two test modules with unittest's TestLoader rather than
      duplicating their assertions, so this script and the pytest suite can
      never drift out of sync with each other.
Relations:
    Exercises vidbyte/agents/speed/tracker.py, vidbyte/lib/dataclasses/speed.py,
    vidbyte/lib/util/math.py, vidbyte/agents/base.py, and vidbyte/agents/runtime.py
    via tests/test_agent_speed.py and tests/test_agent_runtime.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.test_agent_runtime import AgentSpeedTrackingRuntimeTests  # noqa: E402
from tests.test_agent_speed import (  # noqa: E402
    AgentSpeedTrackerBaseAgentIntegrationTests,
    AgentSpeedTrackerRecordCallTests,
    AgentSpeedTrackerRecordToolCallTests,
    AgentSpeedTrackerRollupTests,
    CallSpeedRecordTests,
    MathHelperTests,
    RecordModelCallInputValidationTests,
    ToolCallSpeedRecordTests,
)

TEST_CLASSES = (
    MathHelperTests,
    RecordModelCallInputValidationTests,
    CallSpeedRecordTests,
    ToolCallSpeedRecordTests,
    AgentSpeedTrackerRecordCallTests,
    AgentSpeedTrackerRecordToolCallTests,
    AgentSpeedTrackerRollupTests,
    AgentSpeedTrackerBaseAgentIntegrationTests,
    AgentSpeedTrackingRuntimeTests,
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
    for test in _all_run_tests(result):
        label = "FAIL" if test.id() in failed_ids else "PASS"
        print(f"{label} - {test.id()}")
    for test, traceback in result.failures + result.errors:
        print(f"\n--- {test.id()} ---\n{traceback}")
    passed = total - len(failed_ids)
    print(f"\n{passed}/{total} tests passed.")
    return 0 if not failed_ids else 1


def _all_run_tests(result: unittest.TestResult) -> list:
    # TestResult does not expose successes directly; reconstruct the full run order
    # from failures/errors plus every test the loader queued, in declaration order.
    seen = []
    for cls in TEST_CLASSES:
        for test in unittest.TestLoader().loadTestsFromTestCase(cls):
            seen.append(test)
    return seen


if __name__ == "__main__":
    sys.exit(run_and_report())
