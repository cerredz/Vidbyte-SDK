"""Verification script for the cloud-trajectory-sinks feature.

Runs every test case in tests/test_cloud_trajectory_sinks.py, prints a PASS/FAIL
line per case, prints an X/Y summary, and exits non-zero if any case fails.
Uses pytest's own runner (not unittest.TestLoader) since the test module relies
on pytest fixtures (monkeypatch) and pytest-asyncio for async test functions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _OutcomeCollector:
    """pytest plugin that records one (nodeid, outcome) pair per test phase."""

    def __init__(self) -> None:
        # Track ordered (nodeid, outcome) results for the "call" phase only.
        self.outcomes: list[tuple[str, str]] = []

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Records the call-phase outcome; setup/teardown failures are reported as failures too.
        if report.when == "call":
            status = "PASS" if report.outcome == "passed" else "FAIL"
            self.outcomes.append((report.nodeid, status))
        elif report.when in ("setup", "teardown") and report.outcome == "failed":
            self.outcomes.append((f"{report.nodeid} [{report.when}]", "FAIL"))


def main() -> int:
    # Runs the cloud-trajectory-sinks test module under pytest and reports PASS/FAIL per case.
    collector = _OutcomeCollector()
    exit_code = pytest.main(["tests/test_cloud_trajectory_sinks.py", "-q"], plugins=[collector])

    for nodeid, status in collector.outcomes:
        print(f"{status}: {nodeid}")

    passed = sum(1 for _, status in collector.outcomes if status == "PASS")
    total = len(collector.outcomes)
    print(f"\n{passed}/{total} tests passed")

    return 0 if int(exit_code) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
