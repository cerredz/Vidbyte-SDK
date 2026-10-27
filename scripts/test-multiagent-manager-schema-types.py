"""Verification script for the MultiAgent manager schema fix.

Covers every test case in docs/design/multiagent-manager-schema-types.md Section 10,
plus the existing multi-agent pack, with a PASS or FAIL line per test.
Run with: python scripts/test-multiagent-manager-schema-types.py
"""

from __future__ import annotations

import sys

import pytest

TARGETS = ["tests/multi_agent"]


class ResultPrinter:
    """Pytest plugin that prints one PASS or FAIL line per test and counts them."""

    def __init__(self) -> None:
        # Starts with no results recorded.
        self.passed = 0
        self.failed = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Records the call phase, and any setup or teardown failure, of each test.
        if report.when == "call" or report.failed:
            ok = report.passed
            self.passed += int(ok)
            self.failed += int(not ok)
            print(f"  {'PASS' if ok else 'FAIL'}  {report.nodeid}")


def main() -> int:
    # Runs the targets once, prints the summary line, and exits non-zero on any failure.
    printer = ResultPrinter()
    code = pytest.main(["-q", "-p", "no:cacheprovider", *TARGETS], plugins=[printer])
    print(f"{printer.passed}/{printer.passed + printer.failed} tests passed")
    return 1 if code != 0 or printer.failed else 0


if __name__ == "__main__":
    sys.exit(main())
